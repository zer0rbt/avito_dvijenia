from __future__ import annotations

from avito.sizes import map_color, map_sizes, pick_primary_size
from tests.conftest import categories_doc

CATEGORIES = categories_doc()


def test_map_sizes_converts_letters_to_avito_dictionary_strings():
    """Авито хочет «48 (M)», а не «M» — буквенная сетка поставщика в
    справочнике Size отсутствует как таковая."""
    mapped, unmapped = map_sizes(["S", "M", "L"], categories=CATEGORIES)
    assert mapped == ["46 (S)", "48 (M)", "50 (L)"]
    assert unmapped == []
    assert all(size in CATEGORIES.allowed("Size") for size in mapped)


def test_map_sizes_normalizes_case_and_whitespace():
    mapped, unmapped = map_sizes([" s ", "xl"], categories=CATEGORIES)
    assert mapped == ["46 (S)", "54 (XL)"]
    assert unmapped == []


def test_map_sizes_flags_unknown_tokens_instead_of_dropping_silently():
    mapped, unmapped = map_sizes(["M", "42", ""], categories=CATEGORIES)
    assert mapped == ["48 (M)"]
    assert unmapped == ["42"]


def test_map_sizes_deduplicates_repeated_values():
    mapped, _ = map_sizes(["M", "M", "L"], categories=CATEGORIES)
    assert mapped == ["48 (M)", "50 (L)"]


def test_map_sizes_empty_input_gives_empty_output():
    assert map_sizes([], categories=CATEGORIES) == ([], [])


def test_pick_primary_size_returns_middle_of_the_grid():
    mapped, _ = map_sizes(["S", "M", "L"], categories=CATEGORIES)
    assert pick_primary_size(mapped) == "48 (M)"


def test_pick_primary_size_sorts_numerically_not_lexicographically():
    """«60 (3XL)» лексикографически меньше «8...», поэтому важен разбор числа."""
    mapped, _ = map_sizes(["S", "XXXL"], categories=CATEGORIES)
    assert pick_primary_size(mapped) == "46 (S)"


def test_pick_primary_size_is_stable_regardless_of_input_order():
    forward, _ = map_sizes(["S", "M", "L", "XL"], categories=CATEGORIES)
    backward, _ = map_sizes(["XL", "L", "M", "S"], categories=CATEGORIES)
    assert pick_primary_size(forward) == pick_primary_size(backward)


def test_pick_primary_size_none_for_empty():
    assert pick_primary_size([]) is None


def test_map_color_maps_supplier_freetext_to_dictionary():
    assert map_color("Черные", categories=CATEGORIES) == "Чёрный"
    assert map_color("ЧЕРНЫЙ", categories=CATEGORIES) == "Чёрный"
    assert map_color("белый", categories=CATEGORIES) == "Белый"


def test_map_color_returns_dictionary_value_verbatim_when_already_exact():
    assert map_color("Чёрный", categories=CATEGORIES) == "Чёрный"


def test_map_color_returns_none_for_unknown_or_empty():
    assert map_color(None, categories=CATEGORIES) is None
    assert map_color("", categories=CATEGORIES) is None
    assert map_color("перламутровый", categories=CATEGORIES) is None
