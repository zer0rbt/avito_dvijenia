from __future__ import annotations

from avito.sizes import map_sizes


def test_map_sizes_passes_through_known_letter_grid():
    mapped, unmapped = map_sizes(["S", "M", "L"])
    assert mapped == ["S", "M", "L"]
    assert unmapped == []


def test_map_sizes_normalizes_case_and_whitespace():
    mapped, unmapped = map_sizes([" s ", "xl"])
    assert mapped == ["S", "XL"]
    assert unmapped == []


def test_map_sizes_flags_unknown_tokens_instead_of_dropping_silently():
    mapped, unmapped = map_sizes(["M", "42", ""])
    assert mapped == ["M"]
    assert unmapped == ["42"]


def test_map_sizes_deduplicates_repeated_values():
    mapped, _ = map_sizes(["M", "M", "L"])
    assert mapped == ["M", "L"]


def test_map_sizes_empty_input_gives_empty_output():
    assert map_sizes([]) == ([], [])
