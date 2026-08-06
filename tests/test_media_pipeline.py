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


def test_export_photos_are_used_when_post_is_out_of_preview_window(session, tmp_path, monkeypatch):
    """Главный сценарий выгрузки: пост давно вышел из окна веб-превью, но
    лежит в локальной выгрузке — фото должны взяться оттуда, без сети."""

    def must_not_be_called(*_a, **_k):
        raise AssertionError("при наличии выгрузки в сеть ходить не должны")

    monkeypatch.setattr(pipeline_module, "fetch_post_photo_urls", must_not_be_called)
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", must_not_be_called)

    export_root = _make_export(tmp_path / "export", message_id=1545, photos=2)
    item = _make_item(session, post_url="https://t.me/best_dropship/1545")
    store = LocalFSStore(tmp_path / "store")

    summary = sync_media_for_supplier_items(session, store, dry_run=False, export_root=export_root)

    assert summary.fetched == [item.id]
    assert summary.from_export == [item.id]
    assets = list(session.exec(select(MediaAsset)))
    assert len(assets) == 2
    # Путь к файлу на чужой машине адресом не является — ссылаемся на пост.
    assert {a.source_url for a in assets} == {"https://t.me/best_dropship/1545"}


def test_export_without_matching_post_falls_back_to_network(session, tmp_path, monkeypatch):
    """Выгрузка не того периода не должна ломать обычный путь."""
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)
    monkeypatch.setattr(
        pipeline_module, "fetch_post_photo_urls", lambda post_url, **k: ["https://cdn.tg/p.jpg"]
    )
    export_root = _make_export(tmp_path / "export", message_id=999, photos=1)
    item = _make_item(session, post_url="https://t.me/best_dropship/1545")
    store = LocalFSStore(tmp_path / "store")

    summary = sync_media_for_supplier_items(session, store, dry_run=False, export_root=export_root)

    assert summary.fetched == [item.id]
    assert summary.from_export == []
    assert [a.source_url for a in session.exec(select(MediaAsset))] == ["https://cdn.tg/p.jpg"]


def _make_export(root, *, message_id: int, photos: int):
    """Минимальная выгрузка Telegram Desktop с одним постом-альбомом."""
    (root / "photos").mkdir(parents=True)
    blocks = []
    for n in range(photos):
        name = f"photo_{n}.jpg"
        (root / "photos" / name).write_bytes(FAKE_PHOTO_BYTES)
        blocks.append(
            f'<div class="message default clearfix" id="message{message_id + n}">'
            '<div class="body">'
            '<div class="pull_right date details" title="01.07.2026 00:19:59 UTC+03:00">00:19</div>'
            f'<div class="media_wrap clearfix"><a class="photo_wrap" href="photos/{name}"></a></div>'
            + ('<div class="text">Товар</div>' if n == 0 else "")
            + "</div></div>"
        )
    (root / "messages.html").write_text(
        f'<html><body><div class="history">{"".join(blocks)}</div></body></html>',
        encoding="utf-8",
    )
    return root


def test_network_failure_while_resolving_does_not_kill_the_whole_sync(
    session, tmp_path, monkeypatch
):
    """Позиция, для которой не отвечает сеть, не должна мешать остальным.

    Реальный случай: с выгрузкой на диске синк падал целиком, потому что у
    одной непривязанной позиции веб-превью ушло в ConnectError (B-013).
    """

    def unreachable(*_a, **_k):
        raise OSError("[Errno 101] Network is unreachable")

    monkeypatch.setattr(pipeline_module, "fetch_post_photo_urls", unreachable)
    monkeypatch.setattr(pipeline_module, "fetch_photo_bytes", lambda url, **k: FAKE_PHOTO_BYTES)

    broken = _make_item(session, post_url="https://t.me/ch/1")
    fine = _make_item(session, source_key="gsheets:test:2", photo_urls="https://example.com/a.jpg")
    store = LocalFSStore(tmp_path)

    summary = sync_media_for_supplier_items(session, store, dry_run=False)

    assert broken.id in summary.failed
    assert summary.fetched == [fine.id]


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
