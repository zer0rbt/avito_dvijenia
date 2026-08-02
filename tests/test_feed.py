from __future__ import annotations

from avito.categories import CategoriesDoc
from avito.feed import build_feed_xml, validate_feed_xml
from core.models import GeoCity, Listing, ListingState, Product

VERIFIED_CATEGORIES = CategoriesDoc(
    verified=True,
    verified_at="2026-08-02",
    source_note="test fixture",
    category_path="Личные вещи → Одежда, обувь, аксессуары",
    common_fields={"Category": {"required": True, "value": "Личные вещи"}},
    goods_types=[
        {
            "key": "mens_outerwear",
            "label_ru": "Мужская одежда",
            "avito_goods_type": "Мужская одежда",
            "extra_fields": {},
        }
    ],
    open_questions=[],
)


def _product(**overrides) -> Product:
    defaults = dict(
        id=1,
        supplier_item_id=1,
        title="Balenciaga Arena",
        avito_category="mens_outerwear",
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
        title_rendered="Balenciaga Arena",
        description_rendered="Описание",
        price_rendered=4500.0,
        photo_urls_rendered="https://cdn.example.com/photo1.jpg",
    )
    defaults.update(overrides)
    return Listing(**defaults)


def test_build_feed_xml_includes_ready_listing():
    product = _product()
    listing = _listing()

    result = build_feed_xml([listing], {1: product}, categories=VERIFIED_CATEGORIES)

    assert result.included_listing_ids == [1]
    assert result.excluded == []
    assert "<Id>1-MSK-g1</Id>" in result.xml
    assert "Balenciaga Arena" in result.xml
    assert "4500" in result.xml
    assert "photo1.jpg" in result.xml


def test_build_feed_xml_excludes_draft_listing():
    product = _product()
    listing = _listing(state=ListingState.DRAFT)

    result = build_feed_xml([listing], {1: product}, categories=VERIFIED_CATEGORIES)

    assert result.included_listing_ids == []
    assert result.excluded[0][0] == 1
    assert "DRAFT" in result.excluded[0][1] or "state" in result.excluded[0][1]


def test_build_feed_xml_excludes_listing_without_category():
    product = _product(avito_category=None)
    listing = _listing()

    result = build_feed_xml([listing], {1: product}, categories=VERIFIED_CATEGORIES)

    assert result.included_listing_ids == []
    assert "avito_category" in result.excluded[0][1]


def test_build_feed_xml_excludes_listing_without_photos():
    product = _product()
    listing = _listing(photo_urls_rendered="")

    result = build_feed_xml([listing], {1: product}, categories=VERIFIED_CATEGORIES)

    assert result.included_listing_ids == []
    assert "фото" in result.excluded[0][1]


def test_build_feed_xml_excludes_listing_with_unknown_category_key():
    product = _product(avito_category="does_not_exist")
    listing = _listing()

    result = build_feed_xml([listing], {1: product}, categories=VERIFIED_CATEGORIES)

    assert result.included_listing_ids == []
    assert "неизвестный" in result.excluded[0][1]


def test_validate_feed_xml_passes_for_well_formed_feed():
    product = _product()
    listing = _listing()
    result = build_feed_xml([listing], {1: product}, categories=VERIFIED_CATEGORIES)

    assert validate_feed_xml(result.xml) == []


def test_validate_feed_xml_reports_malformed_xml():
    assert validate_feed_xml("<Ads><Ad><Id>1</Id></Ad>") != []


def test_validate_feed_xml_flags_missing_required_tag():
    xml = '<?xml version="1.0"?><Ads><Ad><Id>1</Id><Title>X</Title></Ad></Ads>'
    errors = validate_feed_xml(xml)
    assert any("Description" in e for e in errors)


def test_build_feed_xml_escapes_special_characters():
    product = _product()
    listing = _listing(title_rendered='Товар <бренд> & "цена"')

    result = build_feed_xml([listing], {1: product}, categories=VERIFIED_CATEGORIES)

    assert "<бренд>" not in result.xml
    assert "&lt;бренд&gt;" in result.xml
