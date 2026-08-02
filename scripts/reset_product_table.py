"""Разовый скрипт: пересоздать таблицу product после смены схемы (brand/
color/goods_type стали Optional). Безопасно, только пока таблица пуста —
проверяет это перед DROP.
"""

from sqlmodel import Session, select

from core.db import engine, init_db
from core.models import Product

with Session(engine) as session:
    existing = session.exec(select(Product)).all()
    if existing:
        raise SystemExit(f"В product уже {len(existing)} строк — не трогаю, разбирайся руками.")

Product.__table__.drop(engine, checkfirst=True)
init_db()
print("product пересоздана с обновлённой схемой")
