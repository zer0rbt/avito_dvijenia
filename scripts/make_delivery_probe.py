"""Собрать пробный фид, чтобы выяснить допустимые значения Delivery (B-024).

Зачем: `Delivery` — обязательное поле, а списка его значений нет ни в
xlsx-шаблоне (проверено разбором как zip: dataValidation на столбец Y
отсутствует), ни в открытой документации. Значит правду знает только сам
Авито — и у него есть публичный валидатор:

    https://autoload.avito.ru/format/xmlcheck/

Скрипт делает файл, который туда загружают. Первые два объявления —
диагностические: одно вообще без `Delivery`, второе с заведомо неверным
значением. Валидатор на них ругнётся, и часто прямо в тексте ошибки
перечисляет допустимые значения — это и есть ответ. Остальные объявления
проверяют написания-кандидаты: которое пройдёт, то и верное.

Ничего не публикует и не пишет в БД: читает данные и печатает файл.
Использование:

    python scripts/make_delivery_probe.py [путь к файлу]
"""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlmodel import Session, select

from avito.categories import load_categories
from avito.feed import _append_ad, _build_ad_fields
from core.db import engine, init_db
from core.models import Listing, ListingState, Product, ProductStatus

# Диагностические строки идут первыми: их задача — вызвать ошибку с текстом,
# в котором Авито сам перечислит допустимые значения.
PROBE_MISSING = None  # тег вообще не выводим
PROBE_INVALID = "ЗАВЕДОМО-НЕВЕРНОЕ-ЗНАЧЕНИЕ"

# Написания-кандидаты. Заказчик сказал «доставка — авито»; как именно это
# записано в справочнике Авито, не знает никто из нас, поэтому перебираем.
CANDIDATES = [
    "Авито доставка",
    "Авито Доставка",
    "Доставка Авито",
    "Авито-доставка",
    "Доставка",
    "Самовывоз",
]


def main() -> None:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("delivery_probe.xml")
    init_db()
    categories = load_categories()

    with Session(engine) as session:
        listing = session.exec(
            select(Listing)
            .where(Listing.product_id == Product.id)
            .where(Product.status == ProductStatus.APPROVED)
            .where(Listing.photo_urls_rendered != "")
            .limit(1)
        ).first()
        if listing is None:
            print("Нет ни одной собранной карточки с фото — сначала content build.")
            raise SystemExit(1)
        product = session.get(Product, listing.product_id)

        # Фид отдаёт только QUEUED/PUBLISHED, а карточки у нас в DRAFT.
        # Подменяем состояние в памяти и откатываем — в БД ничего не уходит.
        listing.state = ListingState.QUEUED
        fields, reason = _build_ad_fields(listing, product, categories)
        if reason is not None:
            print(f"Карточку #{listing.id} собрать не удалось: {reason}")
            raise SystemExit(1)

        feed_cfg = categories.feed
        root = ET.Element(feed_cfg.get("root_tag", "Ads"), feed_cfg.get("root_attrs", {}))

        variants: list[tuple[str, str | None]] = [
            ("probe-00-без-Delivery", PROBE_MISSING),
            ("probe-01-неверное", PROBE_INVALID),
        ]
        variants += [
            (f"probe-{i:02d}-кандидат", value) for i, value in enumerate(CANDIDATES, start=2)
        ]

        for probe_id, delivery in variants:
            ad_fields = dict(fields)
            ad_fields["Id"] = probe_id
            if delivery is not None:
                ad_fields["Delivery"] = delivery
            _append_ad(root, ad_fields, listing, categories)

        session.rollback()  # состояние listing в БД не меняем

    ET.indent(root, space="\t")
    xml = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(root, encoding="unicode")
    out_path.write_text(xml, encoding="utf-8")

    print(f"Файл: {out_path.resolve()}")
    print(f"Объявлений: {len(variants)} (по одному на вариант Delivery)")
    print()
    print("Что делать:")
    print("  1. открыть https://autoload.avito.ru/format/xmlcheck/")
    print("  2. загрузить этот файл")
    print("  3. посмотреть ошибки по Id:")
    print("       probe-00 — есть ли ошибка «Delivery обязателен»")
    print("       probe-01 — текст ошибки часто содержит список допустимых значений")
    print("       probe-02+ — какой из кандидатов прошёл, тот и верный")
    print()
    print("  4. закрыть B-024:")
    print('       python cli.py categories-resolve-field Delivery "<то, что прошло>"')
    print()
    print("Фото в файле ведут на локальный MediaStore — валидатор их не увидит,")
    print("и ругань на недоступные картинки тут ожидаема, на Delivery не влияет.")


if __name__ == "__main__":
    main()
