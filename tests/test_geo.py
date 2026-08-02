from __future__ import annotations

from content.geo import CITY_SEED_OFFSET, photo_variate_seed, select_raw_assets_for_city
from core.models import GeoCity, MediaAsset, MediaAssetKind


def _raw_asset(idx: int) -> MediaAsset:
    return MediaAsset(
        id=idx,
        supplier_item_id=1,
        kind=MediaAssetKind.RAW,
        storage_key=f"raw/item_1/{idx}.jpg",
    )


def test_photo_variate_seed_is_stable_and_unique_per_city():
    seeds = {city: photo_variate_seed(product_id=42, city=city) for city in GeoCity}
    assert len(set(seeds.values())) == len(GeoCity)
    assert photo_variate_seed(product_id=42, city=GeoCity.MSK) == photo_variate_seed(
        product_id=42, city=GeoCity.MSK
    )


def test_select_raw_assets_returns_empty_when_no_photos():
    assert select_raw_assets_for_city([], city=GeoCity.MSK) == []


def test_select_raw_assets_round_robins_without_overlap_when_enough_photos():
    assets = [_raw_asset(i) for i in range(10)]
    selections = {city: select_raw_assets_for_city(assets, city=city) for city in GeoCity}

    all_selected_ids = [a.id for sel in selections.values() for a in sel]
    assert len(all_selected_ids) == len(set(all_selected_ids))  # без пересечений


def test_select_raw_assets_reuses_single_photo_for_every_city():
    assets = [_raw_asset(1)]
    for city in GeoCity:
        selected = select_raw_assets_for_city(assets, city=city)
        assert selected == [assets[0]]


def test_city_seed_offset_covers_all_cities():
    assert set(CITY_SEED_OFFSET) == set(GeoCity)
