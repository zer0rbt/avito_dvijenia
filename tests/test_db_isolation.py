"""Регрессия на B-020: pytest не должен доставать до боевой БД — никак.

Проверяем не «фикстура работает», а именно тот путь, которым в реальную
БД ушли два Listing: тест, который фикстуру `session` не просит, и
исполнитель, который открывает сессию сам.
"""

from __future__ import annotations

from pathlib import Path

import core.db as db_module
from core.config import get_settings
from tests.conftest import IN_MEMORY_URL


def test_engine_is_in_memory_even_without_session_fixture():
    assert str(db_module.engine.url) == IN_MEMORY_URL


def test_get_session_does_not_open_the_file_database():
    with db_module.get_session() as s:
        assert s.get_bind().url.database in (None, "", ":memory:")


def test_settings_database_url_is_overridden_for_tests():
    # .env указывает на файл; в процессе pytest он не должен быть виден
    # даже через настройки — иначе кто-нибудь построит engine руками.
    assert get_settings().database_url == IN_MEMORY_URL


def test_publish_executor_cannot_touch_the_file_database(monkeypatch):
    # Ровно сценарий B-020: фикстуры session нет, исполнителя строим через
    # реестр, а mark_queued() внутри открывает сессию сам.
    import lifecycle.publish
    from bot.registry import build_executor
    from core.models import OperationKind

    # Проверку бюджета глушим намеренно: она ходит в сеть и сама по себе
    # остановила бы исполнителя раньше БД — а проверить надо именно то,
    # что до боевого файла не дотягивается сам переход в QUEUED.
    monkeypatch.setattr(lifecycle.publish, "_require_budget", lambda: None)

    db_file = Path(db_module.__file__).resolve().parent.parent / "data" / "avito_dvijenia.db"
    before = db_file.stat().st_mtime_ns if db_file.exists() else None

    build_executor(OperationKind.PUBLISH, [1, 2])()

    after = db_file.stat().st_mtime_ns if db_file.exists() else None
    assert before == after, "исполнитель PUBLISH дотянулся до файловой БД"
