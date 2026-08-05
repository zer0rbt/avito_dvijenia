"""Тесты telethon-пути (B-018).

Сеть и аккаунт Telegram здесь не задействованы: проверяем ровно то, что
можно проверить без них — что без кредов модуль внятно отказывается, что
файл сессии кладётся в secrets/, и что media/pipeline.py подхватывает
telethon только как запасной путь и не падает, когда он не настроен.
"""

from __future__ import annotations

import re

import pytest

import media.pipeline as pipeline_module
from core.config import Settings
from media.telegram_source import TelethonNotConfiguredError, _require_config
from tests.test_media_pipeline import FAKE_PHOTO_BYTES, _make_item


def test_require_config_raises_without_credentials(monkeypatch):
    monkeypatch.setattr(
        "media.telegram_source.get_settings", lambda: Settings(tg_api_id="", tg_api_hash="")
    )
    with pytest.raises(TelethonNotConfiguredError, match=re.escape("my.telegram.org")):
        _require_config()


def test_session_file_lives_in_secrets(tmp_path, monkeypatch):
    settings = Settings(tg_api_id="123", tg_api_hash="abc", tg_session_name="supplier")
    monkeypatch.setattr("media.telegram_source.get_settings", lambda: settings)

    api_id, api_hash, session_path = _require_config()

    assert api_id == 123
    assert api_hash == "abc"
    # Файл сессии = доступ к аккаунту, ему место только в secrets/ (gitignore)
    assert session_path.parent.name == "secrets"
    assert session_path.name == "supplier.session"


def test_pipeline_falls_back_to_telethon_when_preview_has_no_photos(session, tmp_path, monkeypatch):
    from media.store import LocalFSStore

    monkeypatch.setattr(pipeline_module, "fetch_post_photo_urls", lambda url, **k: [])
    monkeypatch.setattr(
        pipeline_module, "_resolve_telethon_photos", lambda item: [FAKE_PHOTO_BYTES]
    )

    item = _make_item(session, post_url="https://t.me/best_dropship/1545")
    summary = pipeline_module.sync_media_for_supplier_items(
        session, LocalFSStore(tmp_path), dry_run=False
    )

    assert summary.fetched == [item.id]

    from sqlmodel import select

    from core.models import MediaAsset

    asset = session.exec(select(MediaAsset)).one()
    # у медиа Telegram ссылки временные, поэтому запоминаем пост
    assert asset.source_url == "https://t.me/best_dropship/1545"
    assert asset.phash


def test_pipeline_survives_telethon_not_configured(session, tmp_path, monkeypatch):
    """Без TG_API_ID синк не должен падать — большинству команд проекта
    аккаунт Telegram не нужен."""
    from media.store import LocalFSStore

    monkeypatch.setattr(pipeline_module, "fetch_post_photo_urls", lambda url, **k: [])
    monkeypatch.setattr(
        "media.telegram_source.get_settings", lambda: Settings(tg_api_id="", tg_api_hash="")
    )

    item = _make_item(session, post_url="https://t.me/best_dropship/1545")
    summary = pipeline_module.sync_media_for_supplier_items(
        session, LocalFSStore(tmp_path), dry_run=False
    )

    assert summary.failed == {}
    assert summary.skipped_no_source == [item.id]
