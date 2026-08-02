"""Собрать 5 гео-копий (Listing) для одобренного Product — контент готов,
публикация ещё нет (план, Э4: "готовая карточка в БД, отрендеренная, не
опубликованная"). Приоритизация, подтверждение оператора и сама
публикация — Э5 (lifecycle/planner.py, avito/feed.py).

Идемпотентно по (product_id, city): если Listing уже существует (любой
generation), город пропускается. Перезалив с новым generation — забота
lifecycle/wiper.py (Э7), не этой функции.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from avito.sizes import map_sizes
from content.descriptions import render_description
from content.geo import photo_variate_seed, select_raw_assets_for_city
from content.titles import render_title
from core.models import GeoCity, Listing, MediaAsset, MediaAssetKind, Product, utcnow
from media.store import MediaStore, content_key
from media.variate import variate


@dataclass
class BuildSummary:
    created: list[int] = field(default_factory=list)  # listing_id
    skipped_existing: list[tuple[int, str]] = field(default_factory=list)  # (product_id, city)
    skipped_unmapped_sizes: list[int] = field(default_factory=list)  # product_id


def build_listings_for_product(
    session: Session, product: Product, store: MediaStore
) -> BuildSummary:
    summary = BuildSummary()
    assert product.id is not None

    mapped_sizes, _unmapped = map_sizes(product.sizes_supplier.split(","))
    if not mapped_sizes:
        summary.skipped_unmapped_sizes.append(product.id)
        return summary

    if product.sizes_avito != ",".join(mapped_sizes):
        product.sizes_avito = ",".join(mapped_sizes)
        product.updated_at = utcnow()
        session.add(product)

    title = render_title(brand=product.brand, raw_title=product.title)

    raw_assets = list(
        session.exec(
            select(MediaAsset)
            .where(MediaAsset.supplier_item_id == product.supplier_item_id)
            .where(MediaAsset.kind == MediaAssetKind.RAW)
        )
    )

    for city in GeoCity:
        existing = session.exec(
            select(Listing.id)
            .where(Listing.product_id == product.id)
            .where(Listing.city == city)
            .limit(1)
        ).first()
        if existing is not None:
            summary.skipped_existing.append((product.id, city.value))
            continue

        description = render_description(
            city, title=title, brand=product.brand, color=product.color, sizes=mapped_sizes
        )
        photo_urls = _render_photos_for_city(
            session, store, product_id=product.id, city=city, raw_assets=raw_assets
        )

        listing = Listing(
            product_id=product.id,
            city=city,
            internal_id=f"{product.id}-{city.value}-g1",
            title_rendered=title,
            description_rendered=description,
            price_rendered=product.price_final,
            photo_urls_rendered=",".join(photo_urls),
        )
        session.add(listing)
        session.flush()  # получить listing.id для отчёта
        summary.created.append(listing.id)

    session.commit()
    return summary


def _render_photos_for_city(
    session: Session,
    store: MediaStore,
    *,
    product_id: int,
    city: GeoCity,
    raw_assets: list[MediaAsset],
) -> list[str]:
    selected = select_raw_assets_for_city(raw_assets, city=city)
    urls: list[str] = []

    for raw in selected:
        data = store.load(raw.storage_key)
        varied = variate(data, seed=photo_variate_seed(product_id=product_id, city=city))
        key = content_key(varied, prefix=f"variate/product_{product_id}_{city.value}")
        public_url = store.public_url(key) if store.exists(key) else store.save(key, varied)

        asset = MediaAsset(
            supplier_item_id=raw.supplier_item_id,
            kind=MediaAssetKind.VARIATE,
            derived_from_id=raw.id,
            storage_key=key,
            public_url=public_url,
        )
        session.add(asset)
        urls.append(public_url)

    return urls
