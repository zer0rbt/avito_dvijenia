"""Ручная проверка сквозного цикла admin sync на **боевой** таблице-пульте:
пишем "Решение" через gspread (эмулируем оператора), убеждаемся, что
apply_operator_decisions() поменял статус в БД, и возвращаем всё назад.

Запускать только руками и осознанно:

    .venv/bin/python scripts/probe_admin_roundtrip.py

Три вещи здесь сделаны специально, все три — по следам B-020:

1. Имя файла не начинается с `test_`, а работа спрятана в main() под
   `if __name__ == "__main__"`. Раньше файл назывался
   `scripts/test_admin_roundtrip.py` и делал всё в теле модуля — pytest
   забирал его по маске, а сбор тестов = импорт = выполнение. Каждый
   `make check` писал в живую таблицу и отклонял очередной товар в
   боевой БД; за сессию так набралось 10 «решений оператора», которых
   оператор не принимал.
2. Применяем ровно одно решение — своё, по target_id. Раньше в
   apply_operator_decisions() уходил весь словарь из таблицы, то есть и
   все ячейки, оставленные прошлыми прогонами.
3. Прибираем за собой в finally: ячейка чистится, статус товара
   возвращается. Проба не должна менять состояние, которое потом
   считают настоящим.
"""

from __future__ import annotations

from sqlmodel import Session, select

import admin.sheet as sheet_module
from admin.queue import apply_operator_decisions
from core.db import engine
from core.models import Product, ProductStatus


def main() -> int:
    with Session(engine) as session:
        target = session.exec(
            select(Product).where(Product.status == ProductStatus.NEEDS_REVIEW)
        ).first()
        if target is None:
            print("Нет товаров в NEEDS_REVIEW — пробовать не на чем.")
            return 1
        target_id = target.id
        status_before = target.status
        reason_before = target.review_reason
        print("до:", target_id, status_before, reason_before)

    sheet = sheet_module.AdminSheet()
    ws = sheet._worksheet(sheet_module.TAB_PRODUCTS, sheet_module.PRODUCTS_HEADER)

    row_idx = None
    for i, row in enumerate(ws.get_all_values()[1:], start=2):  # 1-based, +1 за заголовок
        if row and row[sheet_module.ID_COLUMN_INDEX] == str(target_id):
            row_idx = i
            break
    if row_idx is None:
        print(f"Строка с ID={target_id} не найдена в таблице")
        return 1

    col_letter = chr(ord("A") + sheet_module.DECISION_COLUMN_INDEX)
    cell = f"{col_letter}{row_idx}"

    try:
        ws.update([["пропустить"]], cell)
        print(f"записал 'пропустить' в {cell}")

        decisions = sheet.pull_decisions()
        mine = decisions.get(target_id)
        print("прочитано решений всего:", len(decisions), "| наше:", mine)
        if mine is None:
            print("ОШИБКА: решение не вычиталось обратно из таблицы")
            return 1

        with Session(engine) as session:
            # Только своё решение: чужие ячейки — не забота этой пробы.
            applied = apply_operator_decisions(session, {target_id: mine})
            print("применено:", applied.get(target_id))

            refreshed = session.get(Product, target_id)
            print("после:", refreshed.id, refreshed.status, refreshed.review_reason)
            if refreshed.status != ProductStatus.REJECTED:
                print("ОШИБКА: решение оператора не применилось")
                return 1
        print("OK: решение оператора применилось корректно")
        return 0
    finally:
        ws.update([[""]], cell)
        with Session(engine) as session:
            restored = session.get(Product, target_id)
            if restored is not None:
                restored.status = status_before
                restored.review_reason = reason_before
                session.add(restored)
                session.commit()
        print(f"прибрано: ячейка {cell} очищена, товар #{target_id} возвращён в {status_before}")


if __name__ == "__main__":
    raise SystemExit(main())
