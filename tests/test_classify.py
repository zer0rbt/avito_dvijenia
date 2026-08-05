from __future__ import annotations

import pytest

from avito.classify import classify_goods_subtype, classify_product
from tests.conftest import categories_doc

CATEGORIES = categories_doc()


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("ХУДИ \nALEXANDER MCQUEEN", "Худи"),
        ("Зип худи Stone_Island", "Худи"),
        ("ХУДИ CHAMPION", "Худи"),
        ("Утки Поло", "Поло"),
        ("Свитер ERD", "Свитер"),
        ("Футболка Nike", "Футболка"),
        ("Толстовка Adidas", "Толстовка"),
        ("Свитшот Carhartt", "Свитшот"),
        ("Кардиган COS", "Кардиган"),
        ("Майка Puma", "Майка"),
    ],
)
def test_classifies_real_catalog_titles(title, expected):
    subtype, _matched = classify_goods_subtype(title)
    assert subtype == expected


def test_every_result_is_a_valid_avito_dictionary_value():
    titles = ["ХУДИ MCQUEEN", "Утки Поло", "Свитер ERD", "Футболка Nike", "Кофта серая"]
    for title in titles:
        subtype, _ = classify_goods_subtype(title)
        assert subtype in CATEGORIES.allowed("GoodsSubType")


def test_zip_hoodie_is_hoodie_not_generic_kofta():
    """«Зип худи» содержит подстроку, под которую могла бы подойти «Кофта» —
    порядок ключей в словаре обязан отдать более специфичный ответ."""
    assert classify_goods_subtype("ЗИП ХУДИ MARTINE ROSE")[0] == "Худи"


def test_falls_back_to_description_when_title_is_uninformative():
    subtype, _ = classify_goods_subtype("Balenciaga Arena", "Тёплая толстовка из хлопка")
    assert subtype == "Толстовка"


def test_returns_none_instead_of_guessing():
    subtype, matched = classify_goods_subtype("Balenciaga Arena")
    assert subtype is None
    assert matched is None


def test_reports_which_keyword_matched():
    _subtype, matched = classify_goods_subtype("ХУДИ CHAMPION")
    assert matched == "худи"


def test_is_case_and_yo_insensitive():
    assert classify_goods_subtype("КОФТА")[0] == "Кофта"
    assert classify_goods_subtype("кофта")[0] == "Кофта"


def test_classify_product_returns_structured_result():
    result = classify_product("ХУДИ MCQUEEN")
    assert result["GoodsSubType"] == "Худи"
    assert result["matched_keyword"] == "худи"
