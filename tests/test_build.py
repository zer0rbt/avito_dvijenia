from __future__ import annotations

import io

from PIL import Image
from sqlmodel import select

from content.build import build_listings_for_product, refresh_photos_for_product
from core.models import (
    GeoCity,
    Listing,
    ListingState,
    MediaAsset,
    MediaAssetKind,
    Product,
    ProductStatus,
)
from media.store import LocalFSStore, content_key


def _fake_photo_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=(80, 140, 200)).save(buf, format="JPEG")
    return buf.getvalue()


def _make_product(session, **overrides) -> Product:
    defaults = dict(
        supplier_item_id=1,
        title="Худи Alexander McQueen",
        brand="Alexander McQueen",
        color="Черный",
        sizes_supplier="S,M,L",
        price_purchase=2500.0,
        price_rrc=3000.0,
        price_final=4500.0,
        status=ProductStatus.APPROVED,
    )
    defaults.update(overrides)
    product = Product(**defaults)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def test_build_creates_one_listing_per_city_without_photos(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)

    summary = build_listings_for_product(session, product, store)

    assert len(summary.created) == len(GeoCity)
    listings = list(session.exec(select(Listing).where(Listing.product_id == product.id)))
    assert {listing.city for listing in listings} == set(GeoCity)
    assert all(listing.photo_urls_rendered == "" for listing in listings)
    assert all(listing.price_rendered == 4500.0 for listing in listings)
    assert all(listing.title_rendered == "Alexander McQueen Худи" for listing in listings)


def test_build_internal_id_is_unique_per_product_and_city(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)
    build_listings_for_product(session, product, store)

    listings = list(session.exec(select(Listing).where(Listing.product_id == product.id)))
    internal_ids = {listing.internal_id for listing in listings}
    assert len(internal_ids) == len(GeoCity)


def test_build_skips_product_with_no_recognized_sizes(session, tmp_path):
    product = _make_product(session, sizes_supplier="")
    store = LocalFSStore(tmp_path)

    summary = build_listings_for_product(session, product, store)

    assert summary.created == []
    assert summary.skipped_unmapped_sizes == [product.id]
    assert list(session.exec(select(Listing))) == []


def test_build_is_idempotent_on_second_run(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)

    build_listings_for_product(session, product, store)
    summary = build_listings_for_product(session, product, store)

    assert summary.created == []
    assert len(summary.skipped_existing) == len(GeoCity)
    listings = list(session.exec(select(Listing).where(Listing.product_id == product.id)))
    assert len(listings) == len(GeoCity)  # не задвоилось


def test_build_records_sizes_avito_on_product(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)

    build_listings_for_product(session, product, store)

    session.refresh(product)
    # строки справочника Авито, а не буквы поставщика (B-002)
    assert product.sizes_avito == "46 (S),48 (M),50 (L)"


def _add_raw_asset(session, store, *, supplier_item_id: int = 1) -> MediaAsset:
    raw_bytes = _fake_photo_bytes()
    key = content_key(raw_bytes, prefix=f"raw/supplier_item_{supplier_item_id}")
    store.save(key, raw_bytes)
    asset = MediaAsset(
        supplier_item_id=supplier_item_id,
        kind=MediaAssetKind.RAW,
        storage_key=key,
        public_url=store.public_url(key),
    )
    session.add(asset)
    session.commit()
    session.refresh(asset)
    return asset


def test_refresh_photos_fills_drafts_built_before_photos_arrived(session, tmp_path):
    """Фото поставщика приезжают позже текста (B-018), а build существующую
    карточку пропускает целиком — без дозаполнения она осталась бы без
    Images навсегда, и Автозагрузка её не приняла бы."""
    product = _make_product(session)
    store = LocalFSStore(tmp_path)
    build_listings_for_product(session, product, store)
    assert all(
        listing.photo_urls_rendered == ""
        for listing in session.exec(select(Listing).where(Listing.product_id == product.id))
    )

    _add_raw_asset(session, store)
    summary = refresh_photos_for_product(session, product, store, dry_run=False)

    assert len(summary.filled) == len(GeoCity)
    listings = list(session.exec(select(Listing).where(Listing.product_id == product.id)))
    assert all(listing.photo_urls_rendered for listing in listings)
    assert len(listings) == len(GeoCity)  # карточки те же, не пересозданы


def test_refresh_photos_dry_run_changes_nothing(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)
    build_listings_for_product(session, product, store)
    _add_raw_asset(session, store)

    summary = refresh_photos_for_product(session, product, store, dry_run=True)

    assert len(summary.filled) == len(GeoCity)
    assert (
        list(session.exec(select(MediaAsset).where(MediaAsset.kind == MediaAssetKind.VARIATE)))
        == []
    )


def test_refresh_photos_leaves_published_listings_alone(session, tmp_path):
    """У карточки, уехавшей в Авито, фото меняет перезалив (Э7), не мы."""
    product = _make_product(session)
    store = LocalFSStore(tmp_path)
    build_listings_for_product(session, product, store)
    for listing in session.exec(select(Listing).where(Listing.product_id == product.id)):
        listing.state = ListingState.PUBLISHED
        session.add(listing)
    session.commit()
    _add_raw_asset(session, store)

    summary = refresh_photos_for_product(session, product, store, dry_run=False)

    assert summary.filled == []
    assert all(
        listing.photo_urls_rendered == ""
        for listing in session.exec(select(Listing).where(Listing.product_id == product.id))
    )


def test_refresh_photos_reports_product_without_raw(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)
    build_listings_for_product(session, product, store)

    summary = refresh_photos_for_product(session, product, store, dry_run=False)

    assert summary.filled == []
    assert summary.no_raw == [product.id]


def test_build_generates_photo_variations_from_raw_asset(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)

    raw_asset = _add_raw_asset(session, store)

    build_listings_for_product(session, product, store)

    listings = list(session.exec(select(Listing).where(Listing.product_id == product.id)))
    assert all(listing.photo_urls_rendered for listing in listings)

    variate_assets = list(
        session.exec(select(MediaAsset).where(MediaAsset.kind == MediaAssetKind.VARIATE))
    )
    assert len(variate_assets) == len(GeoCity)
    assert all(a.derived_from_id == raw_asset.id for a in variate_assets)

    # у каждого города свой файл варианта, а не общий на все пять
    storage_keys = {a.storage_key for a in variate_assets}
    assert len(storage_keys) == len(GeoCity)
