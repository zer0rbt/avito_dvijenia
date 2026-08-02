"""Генерация XML-фида Автозагрузки из Listing (план, Э5: "публикация
/feed.xml через web/app.py + Cloudflare Tunnel").

Тег-схема берётся из avito/categories.py (черновик, verified: false).
build_feed_xml() САМА ПО СЕБЕ не требует verified: true — так можно
проверять структуру XML в dry-run до того, как категории сверены с ЛК
(план, Верификация: "cli.py feed build --dry-run ... Ни одного запроса к
боевому API"). verified: true обязателен только там, где фид реально
уходит наружу — см. web/app.py, /feed.xml.

Листинг, для которого чего-то не хватает (нет avito_category — сейчас
100% товаров, см. docs/BACKLOG.md B-010; нет фото — B-018; не запускался
content build), в фид молча не попадает — попадает в FeedBuildResult.excluded
с причиной, чтобы недостачу было видно, а не терять её в общем счётчике.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from xml.sax.saxutils import escape

from avito.categories import CategoriesDoc, load_categories
from core.models import GEO_ADDRESSES, Listing, ListingState, Product

# Тег фото не подтверждён (categories_draft.yaml, open_questions: "Images/
# Image/ImageUrls — какой актуален"). Images/Image — самый частый вариант в
# открытых источниках, но это ДОГАДКА, не факт — сверить вместе с остальными
# категориями перед verified: true.
IMAGE_LIST_TAG_GUESS = "Images"
IMAGE_ITEM_TAG_GUESS = "Image"

REQUIRED_COMMON_TAGS = ["Id", "Title", "Description", "Price", "Category", "GoodsType", "Address"]


@dataclass
class FeedBuildResult:
    xml: str
    included_listing_ids: list[int] = field(default_factory=list)
    excluded: list[tuple[int, str]] = field(default_factory=list)  # (listing_id, reason)


def build_feed_xml(
    listings: list[Listing],
    products_by_id: dict[int, Product],
    *,
    categories: CategoriesDoc | None = None,
) -> FeedBuildResult:
    categories = categories or load_categories()
    result = FeedBuildResult(xml="")
    ad_elements: list[str] = []

    for listing in listings:
        reason = _exclusion_reason(listing, products_by_id, categories)
        if reason is not None:
            result.excluded.append((listing.id, reason))
            continue

        product = products_by_id[listing.product_id]
        goods_type = categories.goods_type_by_key(product.avito_category)
        address = GEO_ADDRESSES[listing.city]
        photo_urls = [u for u in listing.photo_urls_rendered.split(",") if u]

        images_xml = "".join(f'<{IMAGE_ITEM_TAG_GUESS} url="{escape(u)}"/>' for u in photo_urls)

        ad_elements.append(
            "<Ad>"
            f"<Id>{escape(listing.internal_id)}</Id>"
            f"<Title>{escape(listing.title_rendered)}</Title>"
            f"<Description><![CDATA[{listing.description_rendered}]]></Description>"
            f"<Price>{int(listing.price_rendered)}</Price>"
            f"<Category>{escape(categories.common_fields.get('Category', {}).get('value', ''))}</Category>"
            f"<GoodsType>{escape(goods_type['avito_goods_type'])}</GoodsType>"
            f"<Address>{escape(address['address'] or address['city'])}</Address>"
            f"<{IMAGE_LIST_TAG_GUESS}>{images_xml}</{IMAGE_LIST_TAG_GUESS}>"
            "</Ad>"
        )
        result.included_listing_ids.append(listing.id)

    result.xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<Ads formatVersion="3" target="Avito.ru">' + "".join(ad_elements) + "</Ads>"
    )
    return result


def _exclusion_reason(
    listing: Listing, products_by_id: dict[int, Product], categories: CategoriesDoc
) -> str | None:
    if listing.state not in (ListingState.QUEUED, ListingState.PUBLISHED):
        return f"state={listing.state.value}, ожидается QUEUED/PUBLISHED"

    product = products_by_id.get(listing.product_id)
    if product is None:
        return "product не найден"

    if not product.avito_category:
        return "avito_category не проставлена (см. B-010)"

    try:
        categories.goods_type_by_key(product.avito_category)
    except KeyError:
        return f"неизвестный avito_category={product.avito_category!r}"

    if not listing.title_rendered or not listing.description_rendered:
        return "title/description не отрендерены — запустить content build"

    if listing.price_rendered is None:
        return "price не рассчитана"

    if not listing.photo_urls_rendered:
        return "нет фото (см. B-018)"

    return None


def validate_feed_xml(xml: str) -> list[str]:
    """Локальные проверки без обращения к Авито: XML валиден, обязательные
    общие теги на месте в каждом <Ad> (план, Верификация: "прогон через...
    свой набор правил категории"). Не замена официального валидатора Авито.
    """
    errors: list[str] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return [f"невалидный XML: {e}"]

    for i, ad in enumerate(root.findall("Ad")):
        for tag in REQUIRED_COMMON_TAGS:
            if ad.find(tag) is None:
                errors.append(f"Ad #{i}: отсутствует обязательный тег <{tag}>")
        images = ad.find(IMAGE_LIST_TAG_GUESS)
        if images is None or len(images) == 0:
            errors.append(f"Ad #{i}: нет фото (<{IMAGE_LIST_TAG_GUESS}>)")

    return errors
