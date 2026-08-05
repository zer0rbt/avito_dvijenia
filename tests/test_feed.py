from __future__ import annotations

import xml.etree.ElementTree as ET

from avito.feed import build_feed_xml, validate_feed_xml
from core.models import GeoCity, Listing, ListingState, Product
from tests.conftest import categories_doc

CATEGORIES = categories_doc()


def _product(**overrides) -> Product:
    defaults = dict(
        id=1,
        supplier_item_id=1,
        title="Alexander McQueen Худи",
        brand="Alexander McQueen",
        color="Черный",
        sizes_supplier="S,M,L",
        avito_category="Худи",
        price_final=4500.0,
    )
    defaults.update(overrides)
    return Product(**defaults)


def _listing(**overrides) -> Listing:
    defaults = dict(
        id=1,
        product_id=1,
        city=GeoCity.MSK,
        internal_id="1-MSK-g1",
        state=ListingState.QUEUED,
        title_rendered="Alexander McQueen Худи",
        description_rendered="Описание",
        price_rendered=4500.0,
        photo_urls_rendered="https://cdn.example.com/photo1.jpg",
    )
    defaults.update(overrides)
    return Listing(**defaults)


def _build(listing=None, product=None):
    listing = listing or _listing()
    product = product or _product()
    return build_feed_xml([listing], {1: product}, categories=CATEGORIES)


def test_feed_contains_every_required_tag():
    result = _build()
    assert result.included_listing_ids == [1]

    ad = ET.fromstring(result.xml).find("Ad")
    for tag in CATEGORIES.required_tags:
        if tag in CATEGORIES.unresolved_required_fields:
            continue  # Delivery: значений не знаем, см. avito/feed.py
        assert ad.find(tag) is not None, f"нет обязательного тега <{tag}>"


def test_feed_uses_values_from_avito_dictionaries():
    ad = ET.fromstring(_build().xml).find("Ad")
    assert ad.findtext("Category") == "Одежда, обувь, аксессуары"
    assert ad.findtext("GoodsType") == "Мужская одежда"
    assert ad.findtext("Apparel") == "Кофты и футболки"
    assert ad.findtext("GoodsSubType") == "Худи"
    assert ad.findtext("Condition") == "Новое с биркой"
    # NBSP, а не пробел — Авито сверяет строкой
    assert ad.findtext("AdType") == "Товар приобретен на\xa0продажу"


def test_size_is_single_avito_value_not_supplier_letter():
    """Size у Авито — одно значение из справочника. S,M,L -> «48 (M)»."""
    ad = ET.fromstring(_build().xml).find("Ad")
    size = ad.findtext("Size")
    assert size == "48 (M)"
    assert size in CATEGORIES.allowed("Size")


def test_supplier_color_is_mapped_to_dictionary_value():
    ad = ET.fromstring(_build().xml).find("Ad")
    assert ad.findtext("Color") == "Чёрный"  # из «Черный», через ё


def test_images_use_confirmed_tag_shape():
    ad = ET.fromstring(_build().xml).find("Ad")
    images = ad.find("Images")
    assert images is not None
    assert [img.get("url") for img in images] == ["https://cdn.example.com/photo1.jpg"]


def test_feed_excludes_draft_listing():
    result = _build(listing=_listing(state=ListingState.DRAFT))
    assert result.included_listing_ids == []
    assert "DRAFT" in result.excluded[0][1]


def test_feed_excludes_listing_without_photos():
    result = _build(listing=_listing(photo_urls_rendered=""))
    assert result.included_listing_ids == []
    assert "фото" in result.excluded[0][1]


def test_feed_excludes_product_without_brand():
    result = _build(product=_product(brand=None))
    assert result.included_listing_ids == []
    assert "бренд" in result.excluded[0][1]


def test_feed_excludes_product_without_goods_subtype():
    result = _build(product=_product(avito_category=None))
    assert result.included_listing_ids == []
    assert "GoodsSubType" in result.excluded[0][1]


def test_feed_excludes_goods_subtype_outside_dictionary():
    result = _build(product=_product(avito_category="Ботинки"))
    assert result.included_listing_ids == []
    assert "справочник" in result.excluded[0][1]


def test_feed_excludes_unmappable_size():
    result = _build(product=_product(sizes_supplier="S,42,L"))
    assert result.included_listing_ids == []
    assert "размер" in result.excluded[0][1]


def test_validate_passes_for_well_formed_feed():
    assert validate_feed_xml(_build().xml, categories=CATEGORIES) == []


def test_validate_reports_malformed_xml():
    assert validate_feed_xml("<Ads><Ad><Id>1</Id></Ad>", categories=CATEGORIES) != []


def test_validate_flags_value_outside_dictionary():
    xml = _build().xml.replace(
        "<Condition>Новое с биркой</Condition>", "<Condition>Б/у</Condition>"
    )
    errors = validate_feed_xml(xml, categories=CATEGORIES)
    assert any("Condition" in e for e in errors)


def test_validate_flags_missing_required_tag():
    xml = '<?xml version="1.0"?><Ads><Ad><Id>x</Id><Title>T</Title></Ad></Ads>'
    errors = validate_feed_xml(xml, categories=CATEGORIES)
    assert any("Description" in e for e in errors)
    assert any("фото" in e for e in errors)


def test_validate_does_not_demand_unresolved_delivery_value():
    """Delivery обязателен у Авито, но его допустимых значений мы не знаем,
    поэтому локальный валидатор про него молчит — рубильник стоит в
    require_verified(), а не здесь."""
    errors = validate_feed_xml(_build().xml, categories=CATEGORIES)
    assert not any("Delivery" in e for e in errors)


def test_special_characters_are_escaped():
    result = _build(listing=_listing(title_rendered='Худи <b> & "цена"'))
    assert "&lt;b&gt;" in result.xml
    ad = ET.fromstring(result.xml).find("Ad")
    assert ad.findtext("Title") == 'Худи <b> & "цена"'
