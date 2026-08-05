"""Изоляция тестов от боевой БД.

Изоляция здесь **autouse** и намеренно не оставлена на усмотрение теста
(B-020). Раньше её давала только фикстура `session`; тест, который её не
просил, молча работал с файловой БД из .env. Так два реальных Listing и
ушли в QUEUED: `tests/test_bot_registry.py` собирал исполнителя PUBLISH и
вызывал его, а `lifecycle/publish.py` открывает сессию сам, через
`core.db.get_session()` — то есть фикстура тесту "не нужна", а до БД он
дотягивается. Теперь боевой БД в процессе pytest просто нет.

Два рубежа, потому что они закрывают разные дыры:
  1. DATABASE_URL до импорта core.db — на случай `from core.db import engine`
     (engine связывается по значению в момент импорта, monkeypatch его уже
     не догонит);
  2. monkeypatch самого core.db.engine — на случай, если engine кто-то
     пересоздаст в рантайме.
"""

from __future__ import annotations

import os

# Строго до импорта core.db: он создаёт engine на уровне модуля.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

import core.db as db_module
from avito.categories import CategoriesDoc, load_categories

IN_MEMORY_URL = "sqlite://"


def categories_doc(**overrides) -> CategoriesDoc:
    """Реальная схема из avito/data/categories.yaml с точечными правками.

    Именно реальная, а не самодельная заглушка: тогда тесты фида ловят
    расхождение между кодом и справочником, который реально уедет в Авито.
    load_categories() каждый раз читает файл заново, так что правки одного
    теста не текут в другой.
    """
    doc = load_categories()
    for key, value in overrides.items():
        if not hasattr(doc, key):
            raise AttributeError(f"CategoriesDoc не имеет поля {key!r}")
        setattr(doc, key, value)
    return doc


@pytest.fixture(autouse=True)
def isolated_engine(monkeypatch):
    """Своя пустая in-memory БД на каждый тест — включая те, что про БД
    вообще не думают.

    StaticPool обязателен: без него у каждого нового подключения к
    "sqlite://" — своя пустая база (SQLite in-memory изолирован по
    соединению). tests/test_web.py гоняет запросы через FastAPI TestClient,
    который исполняет хендлер в отдельном потоке (anyio.to_thread) — без
    общего пула тот поток видел бы БД без единой таблицы.
    """
    engine = create_engine(
        IN_MEMORY_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    monkeypatch.setattr(db_module, "engine", engine)
    return engine


@pytest.fixture()
def session(isolated_engine):
    with Session(isolated_engine) as s:
        yield s
