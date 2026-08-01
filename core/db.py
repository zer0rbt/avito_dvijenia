"""Подключение к БД. SQLite для local/vps на старте, DATABASE_URL меняется
на Postgres без переделки кода — SQLModel одинаково работает с обоими.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from core.config import get_settings

# noqa: импортируем модели, чтобы SQLModel.metadata их увидел при create_all
from core import models  # noqa: F401


def _engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite"):
        # создаём папку под файл БД, если её нет (напр. ./data/)
        path_part = url.split("///")[-1]
        Path(path_part).parent.mkdir(parents=True, exist_ok=True)
        return create_engine(url, connect_args={"check_same_thread": False})
    return create_engine(url)


engine = _engine()


def init_db() -> None:
    SQLModel.metadata.create_all(engine)


@contextmanager
def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
