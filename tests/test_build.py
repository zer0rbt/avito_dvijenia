from __future__ import annotations

import io

from PIL import Image
from sqlmodel import select

from content.build import build_listings_for_product
from core.models import GeoCity, Listing, MediaAsset, MediaAssetKind, Product, ProductStatus
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
    assert product.sizes_avito == "S,M,L"


def test_build_generates_photo_variations_from_raw_asset(session, tmp_path):
    product = _make_product(session)
    store = LocalFSStore(tmp_path)

    raw_bytes = _fake_photo_bytes()
    key = content_key(raw_bytes, prefix="raw/supplier_item_1")
    store.save(key, raw_bytes)
    raw_asset = MediaAsset(
        supplier_item_id=1,
        kind=MediaAssetKind.RAW,
        storage_key=key,
        public_url=store.public_url(key),
    )
    session.add(raw_asset)
    session.commit()

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
