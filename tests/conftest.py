from __future__ import annotations

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import core.db as db_module


@pytest.fixture()
def session(monkeypatch):
    """Изолированная in-memory БД на тест, вместо файла из .env.

    StaticPool обязателен: без него у каждого нового подключения к
    "sqlite://" — своя пустая база (SQLite in-memory изолирован по
    соединению). tests/test_web.py гоняет запросы через FastAPI TestClient,
    который исполняет хендлер в отдельном потоке (anyio.to_thread) — без
    общего пула тот поток видел бы БД без единой таблицы.
    """
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    with Session(engine) as s:
        yield s
