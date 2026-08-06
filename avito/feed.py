"""Генерация XML-фида Автозагрузки из Listing.

Схема — из avito/categories.py (сверена с официальными шаблонами, B-002).
Прошлая версия этого модуля отдавала 9 тегов из 15 обязательных и брала
`Category` = «Личные вещи» — такой фид Авито отклонил бы целиком. Теперь
набор тегов и все значения сверяются со справочниками до того, как строка
попадёт в XML.

`build_feed_xml()` сама по себе НЕ требует require_verified(): нужно уметь
собирать и проверять XML локально, пока справочник ещё не дозаполнен
(план, Верификация п.7 — «ни одного запроса к боевому API»). Рубильник
стоит там, где фид реально уходит наружу, — web/app.py, /feed.xml.

Листинг, которому чего-то не хватает, в фид молча не попадает: он уходит в
FeedBuildResult.excluded с причиной. Тихо публиковать половину карточки
хуже, чем не публиковать: за просмотры платим мы.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from avito.categories import CategoriesDoc, load_categories
from avito.sizes import map_color, map_sizes, pick_primary_size
from core.models import GEO_ADDRESSES, Listing, ListingState, Product


@dataclass
class FeedBuildResult:
    xml: str
    included_listing_ids: list[int] = field(default_factory=list)
    excluded: list[tuple[int, str]] = field(default_factory=list)  # (listing_id, причина)


def build_feed_xml(
    listings: list[Listing],
    products_by_id: dict[int, Product],
    *,
    categories: CategoriesDoc | None = None,
) -> FeedBuildResult:
    categories = categories or load_categories()
    feed_cfg = categories.feed
    root = ET.Element(feed_cfg.get("root_tag", "Ads"), feed_cfg.get("root_attrs", {}))
    result = FeedBuildResult(xml="")

    for listing in listings:
        product = products_by_id.get(listing.product_id)
        fields, reason = _build_ad_fields(listing, product, categories)
        if reason is not None:
            result.excluded.append((listing.id, reason))
            continue

        _append_ad(root, fields, listing, categories)
        result.included_listing_ids.append(listing.id)

    ET.indent(root, space="\t")
    result.xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    return result


def _build_ad_fields(
    listing: Listing, product: Product | None, categories: CategoriesDoc
) -> tuple[dict[str, str], None] | tuple[None, str]:
    """Собрать значения тегов или объяснить, почему карточка не готова."""
    if listing.state not in (ListingState.QUEUED, ListingState.PUBLISHED):
        return None, f"state={listing.state.value}, ожидается QUEUED/PUBLISHED"
    if product is None:
        return None, "product не найден"
    if not listing.title_rendered or not listing.description_rendered:
        return None, "title/description не отрендерены — запустить content build"
    if listing.price_rendered is None:
        return None, "price не рассчитана"
    if not listing.photo_urls_rendered:
        return None, "нет фото (см. B-018), а Images — обязательный тег"
    if not product.brand:
        return None, "нет бренда, а Brand — обязательный тег (см. B-011)"

    mapped_sizes, unmapped = map_sizes(product.sizes_supplier.split(","), categories=categories)
    if unmapped:
        return None, f"размеры не смаппились: {unmapped}"
    primary_size = pick_primary_size(mapped_sizes)
    if primary_size is None:
        return None, "нет ни одного размера"

    goods_subtype = product.avito_category
    if not goods_subtype:
        return None, "не определён GoodsSubType (см. B-010)"
    if not categories.is_allowed("GoodsSubType", goods_subtype):
        return None, f"GoodsSubType={goods_subtype!r} нет в справочнике"

    address = GEO_ADDRESSES[listing.city]
    fields: dict[str, str] = {
        "Id": listing.internal_id,
        "Title": listing.title_rendered,
        "Description": listing.description_rendered,
        "Category": categories.defaults["Category"],
        "Address": address["address"] or address["city"],
        "Price": str(int(listing.price_rendered)),
        "GoodsType": categories.defaults["GoodsType"],
        "Condition": categories.defaults["Condition"],
        "AdType": categories.defaults["AdType"],
        "Brand": product.brand,
        "Apparel": categories.defaults["Apparel"],
        "Size": primary_size,
        "GoodsSubType": goods_subtype,
    }

    color = map_color(product.color, categories=categories)
    if color:
        fields["Color"] = color

    return fields, None


def _append_ad(
    root: ET.Element, fields: dict[str, str], listing: Listing, categories: CategoriesDoc
) -> None:
    feed_cfg = categories.feed
    ad = ET.SubElement(root, feed_cfg.get("ad_tag", "Ad"))

    for tag, value in fields.items():
        ET.SubElement(ad, tag).text = value

    images = ET.SubElement(ad, feed_cfg.get("images_tag", "Images"))
    for url in listing.photo_urls_rendered.split(","):
        if url:
            ET.SubElement(
                images,
                feed_cfg.get("image_item_tag", "Image"),
                {feed_cfg.get("image_url_attr", "url"): url},
            )


def validate_feed_xml(xml: str, *, categories: CategoriesDoc | None = None) -> list[str]:
    """Локальные проверки без обращения к Авито: XML разбирается, все
    обязательные теги на месте, значения — из справочников. Не замена
    официальному валидатору Авито, но ловит то, что мы можем поймать сами.

    Delivery не проверяем и не отдаём вовсе: официальный валидатор Авито
    принял объявление без этого тега, хотя xlsx-шаблон зовёт его
    обязательным (см. комментарий в categories.yaml и B-024).
    """
    categories = categories or load_categories()
    errors: list[str] = []
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        return [f"невалидный XML: {e}"]

    images_tag = categories.feed.get("images_tag", "Images")

    for i, ad in enumerate(root.findall(categories.feed.get("ad_tag", "Ad"))):
        ad_id = ad.findtext("Id") or f"#{i}"

        for tag in categories.required_tags:
            if tag == images_tag:
                node = ad.find(images_tag)
                if node is None or len(node) == 0:
                    errors.append(f"{ad_id}: нет фото (<{images_tag}>)")
                continue
            if tag in categories.unresolved_required_fields:
                continue  # значений не знаем — см. докстринг
            if ad.find(tag) is None or not (ad.findtext(tag) or "").strip():
                errors.append(f"{ad_id}: отсутствует обязательный тег <{tag}>")

        for tag in (
            "Category",
            "GoodsType",
            "Apparel",
            "GoodsSubType",
            "Condition",
            "AdType",
            "Size",
            "Color",
        ):
            value = ad.findtext(tag)
            if value and not categories.is_allowed(tag, value):
                errors.append(f"{ad_id}: <{tag}> = {value!r} — нет в справочнике Авито")

    return errors
