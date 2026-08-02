"""Гео-копии: 5 городов = 5 независимых карточек одного Product (план,
"Ключевые решения" — "гео-копии — это самодубль, и с ним надо работать").
Каждый город получает свой шаблон описания (content/descriptions.py) и
свой набор фото.

Фото под город — не отдельная фотосессия (у поставщика её и нет, см.
docs/BACKLOG.md B-018 — фото есть в лучшем случае у части товаров), а
вариация исходных RAW-фото через media/variate.py со своим seed на город:
даже одно и то же исходное фото даёт 5 визуально разных файлов, поэтому
5 карточек не матчатся антидубликатором Авито по фото так же, как не
матчатся по тексту.
"""

from __future__ import annotations

from core.models import GeoCity, MediaAsset

# Детерминированный сдвиг seed'а на город — одна и та же пара (товар, город)
# всегда даёт один и тот же вариант фото и один и тот же выбор исходника,
# это важно для идемпотентности пересборки черновика (content/build.py).
CITY_SEED_OFFSET: dict[GeoCity, int] = {
    GeoCity.MSK: 0,
    GeoCity.SPB: 1,
    GeoCity.EKB: 2,
    GeoCity.KRD: 3,
    GeoCity.KRSK: 4,
}


def photo_variate_seed(*, product_id: int, city: GeoCity) -> int:
    return product_id * 10 + CITY_SEED_OFFSET[city]


def select_raw_assets_for_city(raw_assets: list[MediaAsset], *, city: GeoCity) -> list[MediaAsset]:
    """Раздаёт исходные фото по городам round-robin, без пересечений, если
    фото хватает на все 5 городов. Если фото меньше пяти (частый случай,
    см. B-018) — города переиспользуют одно и то же исходное фото, но
    каждый со своим seed'ом дальше по пайплайну (media/variate.py) это уже
    разводит по факту в разные файлы."""
    if not raw_assets:
        return []

    offset = CITY_SEED_OFFSET[city]
    n_cities = len(CITY_SEED_OFFSET)
    selected = raw_assets[offset::n_cities]
    return selected or [raw_assets[offset % len(raw_assets)]]
