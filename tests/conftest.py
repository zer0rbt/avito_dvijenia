from __future__ import annotations

import pytest
from sqlmodel import SQLModel, Session, create_engine

import core.db as db_module


@pytest.fixture()
def session(monkeypatch):
    """Изолированная in-memory БД на тест, вместо файла из .env."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    with Session(engine) as s:
        yield s
