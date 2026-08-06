"""Синк исходных фото под SupplierItem в MediaStore + реестр MediaAsset (Э3).

Источники фото, в порядке попыток:

1. прямая ссылка из таблицы (`SupplierItem.photo_urls`);
2. локальная выгрузка канала, если её передали (`media/telegram_export.py`) —
   идёт раньше сети, потому что она уже на диске и не зависит от того, не
   вышел ли пост из окна веб-превью;
3. веб-превью канала `t.me/s/<канал>` (`media/fetch.py`) — отдаёт только
   последние ~20 постов (B-018);
4. история канала через Telethon, если настроен.

Идемпотентно по SupplierItem: если для позиции уже есть RAW-ассеты,
повторный прогон её пропускает — иначе каждый суточный синк источников
заново скачивал бы одно и то же фото.

MediaAsset — реестр, а не подмена SupplierItem.photo_urls: исходное поле
остаётся тем, что реально прислал источник, а где физически лежит скачанная
копия — смотрим через MediaAsset.storage_key/public_url.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from core.models import MediaAsset, MediaAssetKind, SupplierItem
from media.fetch import fetch_photo_bytes, fetch_post_photo_urls
from media.phash import compute_phash
from media.store import MediaStore, content_key
from media.telegram_export import ItemRef, match_items_to_posts, parse_export

logger = logging.getLogger(__name__)


@dataclass
class MediaSyncSummary:
    fetched: list[int] = field(default_factory=list)  # supplier_item_id, скачано >=1 фото
    skipped_no_source: list[int] = field(default_factory=list)  # ни photo_urls, ни post_url
    skipped_already_fetched: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)
    from_export: list[int] = field(default_factory=list)  # взято из локальной выгрузки


def sync_media_for_supplier_items(
    session: Session,
    store: MediaStore,
    *,
    dry_run: bool = True,
    force: bool = False,
    export_root: Path | None = None,
) -> MediaSyncSummary:
    summary = MediaSyncSummary()

    items = list(session.exec(select(SupplierItem).where(SupplierItem.is_available)))
    export_photos = _resolve_export_photos(items, export_root)

    for item in items:
        if item.id is None:
            continue

        if not force and _has_raw_assets(session, item.id):
            summary.skipped_already_fetched.append(item.id)
            continue

        # Порядок важен: локальная выгрузка идёт раньше веб-превью, иначе
        # ради поста, который и так лежит на диске, мы бы ходили в сеть за
        # тем, что она чаще всего уже не отдаёт (B-018).
        export_paths = export_photos.get(item.id, [])
        source_urls = _resolve_direct_urls(item)
        if not source_urls and not export_paths:
            source_urls = _resolve_preview_urls(item)

        # Ни прямых ссылок, ни выгрузки, ни превью — последняя попытка через
        # историю канала. Telethon отдаёт байты, а не ссылки: медиа-URL
        # Telegram подписанные и временные.
        telethon_photos: list[bytes] = []
        if not source_urls and not export_paths:
            telethon_photos = _resolve_telethon_photos(item)

        if not source_urls and not export_paths and not telethon_photos:
            summary.skipped_no_source.append(item.id)
            continue

        if dry_run:
            summary.fetched.append(item.id)
            if export_paths and not source_urls:
                summary.from_export.append(item.id)
            continue

        try:
            if source_urls:
                saved = _fetch_and_store(session, store, item, source_urls)
            elif export_paths:
                saved = _store_export_photos(session, store, item, export_paths)
                summary.from_export.append(item.id)
            else:
                saved = _store_photo_bytes(session, store, item, telethon_photos)
        except Exception as e:  # сеть/битый файл — не должно ронять весь синк
            summary.failed[item.id] = str(e)
            continue

        if saved:
            summary.fetched.append(item.id)
        else:
            summary.skipped_no_source.append(item.id)

    if not dry_run:
        session.commit()

    return summary


def _has_raw_assets(session: Session, supplier_item_id: int) -> bool:
    existing = session.exec(
        select(MediaAsset.id)
        .where(MediaAsset.supplier_item_id == supplier_item_id)
        .where(MediaAsset.kind == MediaAssetKind.RAW)
        .limit(1)
    ).first()
    return existing is not None


def _resolve_direct_urls(item: SupplierItem) -> list[str]:
    """Ссылки, которые дала сама таблица поставщика. Сеть не трогаем."""
    return [u for u in item.photo_urls.split(",") if u] if item.photo_urls else []


def _resolve_preview_urls(item: SupplierItem) -> list[str]:
    """Ссылки из публичного веб-превью канала — только последние ~20 постов."""
    return fetch_post_photo_urls(item.post_url) if item.post_url else []


def _resolve_export_photos(
    items: list[SupplierItem], export_root: Path | None
) -> dict[int, list[Path]]:
    """Разобрать выгрузку один раз на весь синк и раздать фото по позициям.

    Привязка — в media/telegram_export.py: точная по id поста, если у позиции
    есть `post_url`, иначе по названию с отказом от неоднозначных совпадений.
    """
    if export_root is None:
        return {}

    posts = parse_export(export_root)
    refs = [
        ItemRef(item_id=item.id, title=item.raw_title, post_url=item.post_url)
        for item in items
        if item.id is not None
    ]
    result = match_items_to_posts(refs, posts)
    return {item_id: match.post.photos for item_id, match in result.matched.items()}


def _resolve_telethon_photos(item: SupplierItem) -> list[bytes]:
    """Запасной путь, когда пост уже вышел из окна веб-превью (B-018).

    Telethon подключается только если он настроен: без TG_API_ID/TG_API_HASH
    молча возвращаем пусто, а не роняем весь синк — большая часть команд
    проекта в аккаунте Telegram не нуждается.
    """
    if not item.post_url:
        return []
    try:
        from media.telegram_source import TelethonNotConfiguredError, fetch_post_photo_bytes
    except ImportError:
        return []
    try:
        return fetch_post_photo_bytes(item.post_url)
    except TelethonNotConfiguredError as e:
        logger.debug("Telethon недоступен для %s: %s", item.post_url, e)
        return []


def _fetch_and_store(
    session: Session, store: MediaStore, item: SupplierItem, source_urls: list[str]
) -> list[MediaAsset]:
    saved: list[MediaAsset] = []
    for source_url in source_urls:
        data = fetch_photo_bytes(source_url)
        saved.append(_store_one(session, store, item, data, source_url=source_url))
    return saved


def _store_export_photos(
    session: Session, store: MediaStore, item: SupplierItem, paths: list[Path]
) -> list[MediaAsset]:
    """Фото из локальной выгрузки. `source_url` ставим на пост канала —
    путь к файлу выгрузки живёт на чужой машине и адресом не является."""
    return [
        _store_one(session, store, item, path.read_bytes(), source_url=item.post_url)
        for path in paths
    ]


def _store_photo_bytes(
    session: Session, store: MediaStore, item: SupplierItem, photos: list[bytes]
) -> list[MediaAsset]:
    """То же, что _fetch_and_store, но данные уже скачаны (Telethon).
    source_url ставим на пост канала: ссылки на само медиа временные, а
    пост — стабильный адрес, по которому фото можно найти снова."""
    return [_store_one(session, store, item, data, source_url=item.post_url) for data in photos]


def _store_one(
    session: Session,
    store: MediaStore,
    item: SupplierItem,
    data: bytes,
    *,
    source_url: str | None,
) -> MediaAsset:
    key = content_key(data, prefix=f"raw/supplier_item_{item.id}")
    public_url = store.public_url(key) if store.exists(key) else store.save(key, data)

    asset = MediaAsset(
        supplier_item_id=item.id,
        kind=MediaAssetKind.RAW,
        source_url=source_url,
        storage_key=key,
        public_url=public_url,
        phash=compute_phash(data),
    )
    session.add(asset)
    return asset
