from __future__ import annotations

import io

from PIL import Image
from sqlmodel import select

import media.pipeline as pipeline_module
from core.models import MediaAsset, MediaAssetKind, SupplierItem
from media.pipeline import sync_media_for_supplier_items
from media.store import LocalFSStore


def _fake_photo_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (16, 16), color=(120, 60, 200)).save(buf, format="JPEG")
    return buf.getvalue()


FAKE_PHOTO_BYTES = _fake_photo_bytes()


def _make_item(session, **overrides) -> SupplierItem:
    defaults = dict(
        source_key="gsheets:test:1",
        source_type="gsheets",
        raw_title="Товар",
        is_available=True,
    )
    defaults.update(overrides)
    item = SupplierItem(**defaults)
    session.add(item)
    session.commit()
    session.refresh(item)
    return item


def test_dry_run_does_not_touch_store_or_db(session, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    item = _make_item(session, photo_urls="https://example.com/a.jpg")
    store = LocalFSStore(tmp_path)

    summary = sync_media_for_supplier_items(session, store, dry_run=True)

    assert summary.fetched == [item.id]
    assert list(session.exec(select(MediaAsset))) == []
    assert not any(tmp_path.rglob("*.jpg"))


def test_write_downloads_direct_photo_urls_and_registers_asset(session, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    item = _make_item(session, photo_urls="https://example.com/a.jpg,https://example.com/b.jpg")
    store = LocalFSStore(tmp_path)

    summary = sync_media_for_supplier_items(session, store, dry_run=False)

    assert summary.fetched == [item.id]
    assets = list(session.exec(select(MediaAsset).where(MediaAsset.supplier_item_id == item.id)))
    assert len(assets) == 2
    assert all(a.kind == MediaAssetKind.RAW for a in assets)
    assert all(a.phash for a in assets)
    assert {a.source_url for a in assets} == {
        "https://example.com/a.jpg",
        "https://example.com/b.jpg",
    }


def test_write_resolves_photos_via_telegram_post_when_no_direct_url(session, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    monkeypatch.setattr(
        pipeline_module,
        "fetch_post_photo_urls",
        lambda post_url, **k: ["https://cdn.tg/photo1.jpg"],
    )
    item = _make_item(session, post_url="https://t.me/best_dropship/1545")
    store = LocalFSStore(tmp_path)

    summary = sync_media_for_supplier_items(session, store, dry_run=False)

    assert summary.fetched == [item.id]
    assets = list(session.exec(select(MediaAsset)))
    assert len(assets) == 1
    assert assets[0].source_url == "https://cdn.tg/photo1.jpg"


def test_skips_items_without_any_photo_source(session, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    item = _make_item(session)
    store = LocalFSStore(tmp_path)

    summary = sync_media_for_supplier_items(session, store, dry_run=False)

    assert summary.skipped_no_source == [item.id]
    assert list(session.exec(select(MediaAsset))) == []


def test_second_run_skips_already_fetched_item(session, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    item = _make_item(session, photo_urls="https://example.com/a.jpg")
    store = LocalFSStore(tmp_path)

    sync_media_for_supplier_items(session, store, dry_run=False)
    summary = sync_media_for_supplier_items(session, store, dry_run=False)

    assert summary.skipped_already_fetched == [item.id]
    assert summary.fetched == []
    assets = list(session.exec(select(MediaAsset).where(MediaAsset.supplier_item_id == item.id)))
    assert len(assets) == 1  # не задвоилось


def test_force_refetches_even_if_already_has_assets(session, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    item = _make_item(session, photo_urls="https://example.com/a.jpg")
    store = LocalFSStore(tmp_path)

    sync_media_for_supplier_items(session, store, dry_run=False)
    summary = sync_media_for_supplier_items(session, store, dry_run=False, force=True)

    assert summary.fetched == [item.id]


def test_download_failure_is_recorded_and_does_not_stop_the_sync(session, tmp_path, monkeypatch):
    def failing_fetch(url, **_k):
        raise ValueError("сеть недоступна")

    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", failing_fetch)
    item = _make_item(session, photo_urls="https://example.com/a.jpg")
    store = LocalFSStore(tmp_path)

    summary = sync_media_for_supplier_items(session, store, dry_run=False)

    assert summary.fetched == []
    assert item.id in summary.failed
    assert list(session.exec(select(MediaAsset))) == []


def test_unavailable_items_are_not_synced(session, tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    _make_item(session, photo_urls="https://example.com/a.jpg", is_available=False)
    store = LocalFSStore(tmp_path)

    summary = sync_media_for_supplier_items(session, store, dry_run=False)

    assert summary.fetched == []
    assert summary.skipped_no_source == []
    assert summary.skipped_already_fetched == []
