from __future__ import annotations

from content.titles import render_title


def test_render_title_prefixes_brand_and_strips_it_from_raw_title():
    title = render_title(brand="Alexander McQueen", raw_title="ХУДИ \nALEXANDER MCQUEEN")
    assert title == "Alexander McQueen ХУДИ"


def test_render_title_without_brand_uses_raw_title_as_is():
    assert render_title(brand=None, raw_title="  Костюм Corteiz Велюр  ") == "Костюм Corteiz Велюр"


def test_render_title_brand_only_when_nothing_left_after_stripping():
    assert render_title(brand="Stone Island", raw_title="Stone Island") == "Stone Island"


def test_render_title_is_truncated_to_max_length():
    long_title = "A" * 100
    title = render_title(brand=None, raw_title=long_title)
    assert len(title) <= 50
