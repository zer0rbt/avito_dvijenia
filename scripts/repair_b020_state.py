"""Разовая починка состояния, испорченного B-020.

Что чинит (разбор — в docs/BACKLOG.md, B-020):

1. `Listing` в QUEUED, которые туда попали мимо `core/approval.py`.
   Их перевёл `mark_queued()`, вызванный из теста реестра исполнителей на
   боевой БД. Признак «в Авито ничего не ушло»: `avito_id` пуст и
   `published_at` пуст — только такие и трогаем, возвращая в DRAFT.

2. `Product` в REJECTED с `review_reason='operator_decision'`.
   Оператор этих решений не принимал: «пропустить» писал в таблицу
   `scripts/test_admin_roundtrip.py`, который pytest подхватывал по маске
   имени и выполнял при сборе тестов. Возвращаем статус, который даёт
   `evaluate_auto_status()` по текущему SupplierItem — та же функция,
   что проставила его в первый раз.

3. Колонка «Решение» в таблице-пульте: девять ячеек «пропустить» от того
   же скрипта. Без этого следующий `admin sync` вычитает их обратно и
   снова отклонит те же товары.

По умолчанию — dry-run. Реальная запись: `--write`.

    .venv/bin/python scripts/repair_b020_state.py           # показать
    .venv/bin/python scripts/repair_b020_state.py --write   # применить
"""

from __future__ import annotations

import sys

from sqlmodel import Session, select

from admin.queue import evaluate_auto_status
from core.approval import log_audit
from core.db import engine
from core.models import (
    Listing,
    ListingState,
    PendingOperation,
    Product,
    ProductStatus,
    SupplierItem,
    utcnow,
)

ACTOR = "maintenance:B-020"


def repair_db(session: Session, *, write: bool) -> None:
    # -- 1. Listing: QUEUED мимо подтверждения -------------------------------
    pending = session.exec(select(PendingOperation)).all()
    if pending:
        print(f"ВНИМАНИЕ: в PendingOperation {len(pending)} записей — разберись руками, выхожу")
        raise SystemExit(1)

    queued = session.exec(select(Listing).where(Listing.state == ListingState.QUEUED)).all()
    print(f"\nListing в QUEUED: {len(queued)}")
    for listing in queued:
        if listing.avito_id or listing.published_at:
            print(f"  #{listing.id} {listing.internal_id}: есть avito_id/published_at — НЕ трогаю")
            continue
        print(f"  #{listing.id} {listing.internal_id}: QUEUED -> DRAFT")
        if write:
            listing.state = ListingState.DRAFT
            listing.updated_at = utcnow()
            session.add(listing)

    # -- 2. Product: фантомные решения оператора -----------------------------
    phantom = session.exec(
        select(Product)
        .where(Product.status == ProductStatus.REJECTED)
        .where(Product.review_reason == "operator_decision")
    ).all()
    print(f"\nProduct в REJECTED с review_reason='operator_decision': {len(phantom)}")
    for product in phantom:
        item = (
            session.get(SupplierItem, product.supplier_item_id)
            if product.supplier_item_id
            else None
        )
        if item is None:
            print(f"  #{product.id} {product.title!r}: нет SupplierItem — НЕ трогаю")
            continue
        if not item.is_available:
            status, reason = ProductStatus.REJECTED, "disappeared_from_source"
        else:
            status, reason = evaluate_auto_status(item)
        print(
            f"  #{product.id} {product.title!r}: REJECTED/operator_decision -> {status.value}/{reason}"
        )
        if write:
            product.status = status
            product.review_reason = reason
            product.updated_at = utcnow()
            session.add(product)

    if write:
        session.commit()
        log_audit(
            session,
            actor=ACTOR,
            action="REPAIR B-020",
            details=(
                f"откат состояния, выставленного не оператором: "
                f"listings QUEUED->DRAFT={[listing.id for listing in queued]} "
                f"products REJECTED->авто-статус={[p.id for p in phantom]}"
            ),
        )


def repair_sheet(*, write: bool) -> None:
    import admin.sheet as sheet_module

    sheet = sheet_module.AdminSheet()
    ws = sheet._worksheet(sheet_module.TAB_PRODUCTS, sheet_module.PRODUCTS_HEADER)
    col_letter = chr(ord("A") + sheet_module.DECISION_COLUMN_INDEX)

    cells = []
    for i, row in enumerate(ws.get_all_values()[1:], start=2):
        if (
            len(row) > sheet_module.DECISION_COLUMN_INDEX
            and row[sheet_module.DECISION_COLUMN_INDEX].strip()
        ):
            cells.append((f"{col_letter}{i}", row[sheet_module.ID_COLUMN_INDEX]))

    print(f"\nНепустых ячеек «Решение» в таблице: {len(cells)}")
    for cell, product_id in cells:
        print(f"  {cell} (product_id={product_id}) -> очистить")

    if write and cells:
        ws.batch_update([{"range": cell, "values": [[""]]} for cell, _ in cells])
        print("Ячейки очищены.")


def main(argv: list[str]) -> int:
    write = "--write" in argv
    print("РЕЖИМ:", "ЗАПИСЬ" if write else "dry-run (для записи добавь --write)")

    # Таблица первой: если её не почистить, любой следующий admin sync
    # вычитает те же «пропустить» и отменит починку БД. Обратный порядок
    # безопасен — оставшиеся ячейки без починки БД ничего не ломают.
    try:
        repair_sheet(write=write)
    except Exception as e:
        # Ловим широко намеренно: сеть до Google нестабильна (B-013), а
        # молча чинить БД под грязной таблицей нельзя.
        print(f"\nТаблица-пульт недоступна ({type(e).__name__}: {e}).")
        print("БД НЕ трогаю: без очистки «Решение» следующий admin sync всё вернёт обратно.")
        return 1

    with Session(engine) as session:
        repair_db(session, write=write)

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
