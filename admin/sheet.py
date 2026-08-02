"""Двусторонний синк с таблицей-пультом (ADMIN_SHEET_ID).

Формат вкладок — план, "Админ-панель: очередь модерации". На Э2 реально
наполняется только "Товары" (двусторонне) и "Лог" (только на запись,
из AuditLogEntry). "Объявления" и "Настройки" заведены пустыми
заголовками — им есть что показывать только с Э5 (Listing) и когда
пороги decay.py (Э7) станут по-настоящему редактируемыми из таблицы.

Порядок синка (см. admin/queue.py и cli.py admin sync) обязателен:
сначала pull_decisions(), потом apply_operator_decisions() в БД, только
потом sync_products_from_supplier_items() и push_products() — иначе
свежий push перезапишет то, что оператор только что вписал.
"""

from __future__ import annotations

import gspread
from google.oauth2.service_account import Credentials

from core.config import get_settings
from core.models import Product

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
]

TAB_PRODUCTS = "Товары"
TAB_LISTINGS = "Объявления"
TAB_SETTINGS = "Настройки"
TAB_LOG = "Лог"

PRODUCTS_HEADER = [
    "ID",
    "Статус",
    "Название",
    "Бренд",
    "Цвет",
    "Размеры",
    "Закупка",
    "РРЦ",
    "Итоговая цена",
    "Источник",
    "Причина",
    "Решение",
]

# Столбец с "Решение" — единственный, который реально читаем обратно.
DECISION_COLUMN_INDEX = PRODUCTS_HEADER.index("Решение")  # 0-based
ID_COLUMN_INDEX = PRODUCTS_HEADER.index("ID")

LISTINGS_HEADER = [
    "ID",
    "Товар",
    "Город",
    "AvitoId",
    "Состояние",
    "Опубликовано",
    "Просмотры (3д)",
    "Контакты",
    "Расход",
    "Действие",
]

LOG_HEADER = ["Время", "Кто", "Действие", "Детали"]


class AdminSheetNotConfiguredError(RuntimeError):
    pass


class AdminSheet:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.google_service_account_json or not settings.admin_sheet_id:
            raise AdminSheetNotConfiguredError(
                "GOOGLE_SERVICE_ACCOUNT_JSON / ADMIN_SHEET_ID не заданы в .env"
            )
        creds = Credentials.from_service_account_file(
            settings.google_service_account_json, scopes=SCOPES
        )
        client = gspread.authorize(creds)
        self._spreadsheet = client.open_by_key(settings.admin_sheet_id)

    def _worksheet(self, title: str, header: list[str]) -> gspread.Worksheet:
        try:
            ws = self._spreadsheet.worksheet(title)
        except gspread.WorksheetNotFound:
            ws = self._spreadsheet.add_worksheet(title=title, rows=1000, cols=len(header) + 2)
            ws.update([header], "A1")
            return ws

        first_row = ws.row_values(1)
        if first_row != header:
            ws.update([header], "A1")
        return ws

    # -- Товары ----------------------------------------------------------

    def pull_decisions(self) -> dict[int, str]:
        """Читает колонку "Решение" вкладки Товары. {product_id: текст}.
        Пустая таблица (первый запуск) -> пустой словарь, не ошибка.
        """
        ws = self._worksheet(TAB_PRODUCTS, PRODUCTS_HEADER)
        rows = ws.get_all_values()[1:]  # без заголовка

        decisions: dict[int, str] = {}
        for row in rows:
            if len(row) <= DECISION_COLUMN_INDEX:
                continue
            decision_text = row[DECISION_COLUMN_INDEX].strip()
            if not decision_text:
                continue
            try:
                product_id = int(row[ID_COLUMN_INDEX])
            except (ValueError, IndexError):
                continue
            decisions[product_id] = decision_text
        return decisions

    def push_products(self, products: list[Product]) -> None:
        """Перезаписывает вкладку Товары целиком актуальным состоянием БД.
        Колонка "Решение" пушится пустой — статус теперь отражён в колонке
        "Статус", повторное решение оператор ставит заново осознанно.
        """
        ws = self._worksheet(TAB_PRODUCTS, PRODUCTS_HEADER)

        rows = [PRODUCTS_HEADER]
        for p in products:
            rows.append(
                [
                    str(p.id),
                    p.status.value,
                    p.title,
                    p.brand or "",
                    p.color or "",
                    p.sizes_supplier,
                    _fmt(p.price_purchase),
                    _fmt(p.price_rrc),
                    _fmt(p.price_final),
                    _source_label(p),
                    p.review_reason or "",
                    "",  # Решение — очищаем при каждом push
                ]
            )

        ws.clear()
        ws.update(rows, "A1")

    # -- Объявления / Настройки: пока только шапка -----------------------

    def ensure_placeholder_tabs(self) -> None:
        self._worksheet(TAB_LISTINGS, LISTINGS_HEADER)
        self._worksheet(TAB_SETTINGS, ["Параметр", "Значение"])

    # -- Лог ---------------------------------------------------------------

    def push_log(self, entries: list) -> None:
        """Дописывает новые записи AuditLogEntry в конец вкладки Лог."""
        ws = self._worksheet(TAB_LOG, LOG_HEADER)
        if not entries:
            return
        rows = [[e.at.isoformat(timespec="seconds"), e.actor, e.action, e.details] for e in entries]
        ws.append_rows(rows, value_input_option="RAW")


def _fmt(value: float | None) -> str:
    return "" if value is None else str(value)


def _source_label(product: Product) -> str:
    # На Э2 у Product нет прямой ссылки на source_type — только на
    # supplier_item_id. Полноценная метка источника (имя таблицы) появится,
    # когда источников станет больше одного вида на Product (после B-009).
    return f"supplier_item:{product.supplier_item_id}" if product.supplier_item_id else ""
