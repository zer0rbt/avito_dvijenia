"""Юнит-тесты чистой логики admin/sheet.py без реального обращения к
Google Sheets — AdminSheet.__init__ дёргает сеть, поэтому создаём объект
в обход него (object.__new__) и подсовываем поддельный worksheet.
Сквозной живой прогон — scripts/test_admin_roundtrip.py, гоняется руками.
"""

from __future__ import annotations

from admin.sheet import (
    DECISION_COLUMN_INDEX,
    ID_COLUMN_INDEX,
    PRODUCTS_HEADER,
    AdminSheet,
)
from core.models import Product, ProductStatus


class FakeWorksheet:
    def __init__(self, rows: list[list[str]] | None = None):
        self.rows = rows or [PRODUCTS_HEADER]
        self.cleared = False
        self.updated_with: list[list[str]] | None = None

    def get_all_values(self) -> list[list[str]]:
        return self.rows

    def row_values(self, n: int) -> list[str]:
        return self.rows[n - 1] if len(self.rows) >= n else []

    def clear(self) -> None:
        self.cleared = True

    def update(self, values, range_name=None) -> None:
        self.updated_with = values
        self.rows = values


def _bare_admin_sheet(ws: FakeWorksheet) -> AdminSheet:
    sheet = object.__new__(AdminSheet)
    sheet._worksheet = lambda title, header: ws
    return sheet


def test_pull_decisions_parses_id_and_decision_columns():
    rows = [PRODUCTS_HEADER]
    row = [""] * len(PRODUCTS_HEADER)
    row[ID_COLUMN_INDEX] = "42"
    row[DECISION_COLUMN_INDEX] = "публиковать"
    rows.append(row)

    sheet = _bare_admin_sheet(FakeWorksheet(rows))
    decisions = sheet.pull_decisions()

    assert decisions == {42: "публиковать"}


def test_pull_decisions_skips_empty_decision_cells():
    rows = [PRODUCTS_HEADER]
    row = [""] * len(PRODUCTS_HEADER)
    row[ID_COLUMN_INDEX] = "1"
    rows.append(row)

    sheet = _bare_admin_sheet(FakeWorksheet(rows))
    assert sheet.pull_decisions() == {}


def test_pull_decisions_skips_rows_with_non_numeric_id():
    rows = [PRODUCTS_HEADER]
    row = [""] * len(PRODUCTS_HEADER)
    row[ID_COLUMN_INDEX] = "не число"
    row[DECISION_COLUMN_INDEX] = "публиковать"
    rows.append(row)

    sheet = _bare_admin_sheet(FakeWorksheet(rows))
    assert sheet.pull_decisions() == {}


def test_pull_decisions_handles_empty_sheet():
    sheet = _bare_admin_sheet(FakeWorksheet([PRODUCTS_HEADER]))
    assert sheet.pull_decisions() == {}


def test_push_products_writes_header_and_clears_decision_column():
    product = Product(
        id=1,
        supplier_item_id=5,
        title="Balenciaga Arena",
        brand="Balenciaga",
        color="Чёрный",
        sizes_supplier="S,M,L",
        price_purchase=3000.0,
        price_rrc=None,
        price_final=4500.0,
        status=ProductStatus.APPROVED,
        review_reason=None,
    )

    ws = FakeWorksheet()
    sheet = _bare_admin_sheet(ws)
    sheet.push_products([product])

    assert ws.cleared is True
    assert ws.updated_with[0] == PRODUCTS_HEADER
    row = ws.updated_with[1]
    assert row[ID_COLUMN_INDEX] == "1"
    assert row[DECISION_COLUMN_INDEX] == ""  # решение всегда пушится пустым
    assert "Balenciaga Arena" in row


def test_push_products_handles_missing_brand_and_color_without_crashing():
    product = Product(
        id=2,
        title="Что-то без бренда",
        brand=None,
        color=None,
        sizes_supplier="",
        status=ProductStatus.NEEDS_REVIEW,
        review_reason="brand_unknown",
    )

    ws = FakeWorksheet()
    sheet = _bare_admin_sheet(ws)
    sheet.push_products([product])  # не должно бросить исключение

    row = ws.updated_with[1]
    assert row[PRODUCTS_HEADER.index("Бренд")] == ""
    assert row[PRODUCTS_HEADER.index("Цвет")] == ""
