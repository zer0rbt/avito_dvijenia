from __future__ import annotations

import pytest

from sources.normalizer import clean_title, guess_brand, parse_price_rub

NBSP = "\xa0"


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("3650₽  3500₽", 3500.0),  # старая/новая цена через ₽
        ("5000 3850₽", 3850.0),  # та же пара, но БЕЗ ₽ между числами — regression
        ("4400 4150₽", 4150.0),
        ("2990", 2990.0),
        (f"2{NBSP}890₽", 2890.0),  # разделитель тысяч — неразрывный пробел
        (f"5{NBSP}550₽", 5550.0),
        ("1650Р", 1650.0),  # кириллическая "Р" вместо ₽
        ("4500Р", 4500.0),
        ("", None),
        (None, None),
        ("   ", None),
    ],
)
def test_parse_price_rub(raw, expected):
    assert parse_price_rub(raw) == expected


def test_parse_price_rub_does_not_merge_two_four_digit_numbers_without_separator():
    """Regression: наивный \\d[\\d\\s]* схлопывал "5000 3850" в "50003850"."""
    assert parse_price_rub("5000 3850₽") == 3850.0
    assert parse_price_rub("5000 3850₽") != 50003850.0


def test_clean_title_collapses_newlines_and_strips_quotes():
    assert (
        clean_title('"ЗИП ХУДИ\nMARTINE ROSE \nx \nSUPREME"') == "ЗИП ХУДИ MARTINE ROSE x SUPREME"
    )
    assert clean_title("  Stone_Island  ") == "Stone_Island"
    assert clean_title(None) == ""
    assert clean_title("") == ""


def test_guess_brand_case_insensitive_substring():
    assert guess_brand("Зип худи Stone_Island") == "Stone Island"
    assert guess_brand("ХУДИ CAV EMPT") == "CAV EMPT"
    assert guess_brand("Костюм Corteiz Велюр") == "Corteiz"
    assert guess_brand("Никому не известный бренд XYZ") is None
