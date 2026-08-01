from __future__ import annotations

import pytest

from avito.categories import CategoriesNotVerifiedError, load_categories, render_markdown


def test_draft_is_not_verified_and_blocks_publication():
    doc = load_categories()
    assert doc.verified is False
    with pytest.raises(CategoriesNotVerifiedError):
        doc.require_verified()


def test_render_markdown_contains_status_and_goods_types():
    doc = load_categories()
    md = render_markdown(doc)
    assert "ЧЕРНОВИК" in md
    assert "Мужская обувь" in md
    assert "Женская одежда" in md


def test_goods_type_by_key_lookup():
    doc = load_categories()
    gt = doc.goods_type_by_key("mens_shoes")
    assert gt["label_ru"] == "Мужская обувь"
    with pytest.raises(KeyError):
        doc.goods_type_by_key("nonexistent")
