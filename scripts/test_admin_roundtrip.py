"""Разовая проверка сквозного цикла admin sync: пишем "Решение" в реальную
таблицу-пульт напрямую через gspread (эмулируем оператора), затем
проверяем, что после applied-логики статус в БД поменялся так, как ожидалось.
Не гоняет cli целиком — просто прощупывает API таблицы перед тем, как
полагаться на него в cli.py.
"""

from sqlmodel import Session, select

import admin.sheet as sheet_module
from admin.queue import apply_operator_decisions
from core.db import engine
from core.models import Product, ProductStatus

with Session(engine) as session:
    target = session.exec(
        select(Product).where(Product.status == ProductStatus.NEEDS_REVIEW)
    ).first()
    print("до:", target.id, target.status, target.review_reason)
    target_id = target.id

sheet = sheet_module.AdminSheet()
ws = sheet._worksheet(sheet_module.TAB_PRODUCTS, sheet_module.PRODUCTS_HEADER)

rows = ws.get_all_values()
row_idx = None
for i, row in enumerate(rows[1:], start=2):  # 1-based, +1 для заголовка
    if row and row[sheet_module.ID_COLUMN_INDEX] == str(target_id):
        row_idx = i
        break

if row_idx is None:
    raise SystemExit(f"Строка с ID={target_id} не найдена в таблице")

col_letter = chr(ord("A") + sheet_module.DECISION_COLUMN_INDEX)
ws.update([["пропустить"]], f"{col_letter}{row_idx}")
print(f"записал 'пропустить' в {col_letter}{row_idx}")

decisions = sheet.pull_decisions()
print("прочитано решений:", len(decisions), "для нашего id:", decisions.get(target_id))

with Session(engine) as session:
    applied = apply_operator_decisions(session, decisions)
    print("применено:", applied.get(target_id))

    refreshed = session.get(Product, target_id)
    print("после:", refreshed.id, refreshed.status, refreshed.review_reason)
    assert refreshed.status == ProductStatus.REJECTED, "решение не применилось!"
    print("OK: решение оператора применилось корректно")
