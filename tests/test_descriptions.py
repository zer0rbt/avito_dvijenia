from __future__ import annotations

import pytest

from content.descriptions import TEMPLATE_BY_CITY, render_description
from core.models import GeoCity


@pytest.mark.parametrize("city", list(GeoCity))
def test_render_description_includes_facts_for_every_city(city):
    text = render_description(
        city,
        title="Balenciaga Arena",
        brand="Balenciaga",
        color="Черный",
        sizes=["S", "M", "L"],
    )
    assert "Balenciaga Arena" in text
    assert "Черный" in text
    assert "Balenciaga" in text
    assert "S" in text and "M" in text and "L" in text


def test_all_five_cities_have_structurally_different_templates():
    texts = {
        city: render_description(city, title="Nike Air", brand="Nike", color="Белый", sizes=["M"])
        for city in GeoCity
    }
    # структурно разные шаблоны -> разные тексты после подстановки одних и
    # тех же фактов (иначе гео-копии читаются как самодубль, см. план)
    assert len(set(texts.values())) == len(GeoCity)


def test_render_description_never_mentions_original_or_replica():
    text = render_description(
        GeoCity.MSK, title="Vetements Hoodie", brand="Vetements", color="Серый", sizes=["L"]
    )
    lowered = text.lower()
    assert "оригинал" not in lowered
    assert "реплик" not in lowered


def test_render_description_does_not_mention_shipping_city():
    # план: "город отгрузки в описании не упоминаем" — сами шаблоны не
    # должны содержать топоним города доставки
    for city in GeoCity:
        text = render_description(city, title="X", brand="Brand", color="Цвет", sizes=["M"])
        assert "Москва" not in text
        assert "Красноярск" not in text


def test_template_by_city_covers_all_cities():
    assert set(TEMPLATE_BY_CITY) == set(GeoCity)
