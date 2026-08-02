"""Синк исходных фото под SupplierItem в MediaStore + реестр MediaAsset (Э3).

Источник фото: прямая ссылка, если таблица её даёт (SupplierItem.photo_urls),
иначе резолвим через пост TG-канала (SupplierItem.post_url, см.
media/fetch.py). Идемпотентно по SupplierItem: если для позиции уже есть
RAW-ассеты, повторный прогон её пропускает — иначе каждый суточный синк
источников заново скачивал бы одно и то же фото.

MediaAsset — реестр, а не подмена SupplierItem.photo_urls: исходное поле
остаётся тем, что реально прислал источник, а где физически лежит скачанная
копия — смотрим через MediaAsset.storage_key/public_url.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from core.models import MediaAsset, MediaAssetKind, SupplierItem
from media.fetch import fetch_photo_bytes, fetch_post_photo_urls
from media.phash import compute_phash
from media.store import MediaStore, content_key


@dataclass
class MediaSyncSummary:
    fetched: list[int] = field(default_factory=list)  # supplier_item_id, скачано >=1 фото
    skipped_no_source: list[int] = field(default_factory=list)  # ни photo_urls, ни post_url
    skipped_already_fetched: list[int] = field(default_factory=list)
    failed: dict[int, str] = field(default_factory=dict)


def sync_media_for_supplier_items(
    session: Session,
    store: MediaStore,
    *,
    dry_run: bool = True,
    force: bool = False,
) -> MediaSyncSummary:
    summary = MediaSyncSummary()

    items = list(session.exec(select(SupplierItem).where(SupplierItem.is_available)))
    for item in items:
        if item.id is None:
            continue

        if not force and _has_raw_assets(session, item.id):
            summary.skipped_already_fetched.append(item.id)
            continue

        source_urls = _resolve_source_urls(item)
        if not source_urls:
            summary.skipped_no_source.append(item.id)
            continue

        if dry_run:
            summary.fetched.append(item.id)
            continue

        try:
            saved = _fetch_and_store(session, store, item, source_urls)
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


def _resolve_source_urls(item: SupplierItem) -> list[str]:
    if item.photo_urls:
        return [u for u in item.photo_urls.split(",") if u]
    if item.post_url:
        return fetch_post_photo_urls(item.post_url)
    return []


def _fetch_and_store(
    session: Session, store: MediaStore, item: SupplierItem, source_urls: list[str]
) -> list[MediaAsset]:
    saved: list[MediaAsset] = []
    for source_url in source_urls:
        data = fetch_photo_bytes(source_url)
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
        saved.append(asset)
    return saved
