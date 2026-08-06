from __future__ import annotations

import shutil

import pytest

from avito.categories import (
    DATA_PATH,
    CategoriesNotVerifiedError,
    load_categories,
    render_markdown,
    resolve_field,
)
from tests.conftest import categories_doc


def test_shipped_schema_is_verified_against_avito_templates():
    doc = load_categories()
    assert doc.verified is True
    assert doc.template_id == 100343


def test_publication_still_blocked_while_required_field_values_unknown():
    """Схема сверена, но Delivery без справочника — публиковать нельзя.
    Это второй рубеж require_verified(), кроме флага verified."""
    doc = load_categories()
    assert "Delivery" in doc.unresolved_required_fields
    with pytest.raises(CategoriesNotVerifiedError, match="Delivery"):
        doc.require_verified()


def test_require_verified_passes_once_nothing_is_unresolved():
    categories_doc(unresolved_required_fields=[]).require_verified()


def test_require_verified_blocks_when_flag_is_false():
    with pytest.raises(CategoriesNotVerifiedError):
        categories_doc(verified=False, unresolved_required_fields=[]).require_verified()


def test_adtype_values_use_nbsp_exactly_as_in_template():
    """В шаблоне Авито тут неразрывный пробел. Обычный пробел визуально
    неотличим, но сверку строкой сломает — поэтому регресс."""
    doc = load_categories()
    assert doc.defaults["AdType"] == "Товар приобретен на\xa0продажу"
    assert "Товар от\xa0производителя" in doc.allowed("AdType")


def test_defaults_are_all_inside_their_dictionaries():
    doc = load_categories()
    for tag, value in doc.defaults.items():
        assert doc.is_allowed(tag, value), f"{tag}={value!r} нет в справочнике"


def test_size_map_targets_exist_in_size_dictionary():
    doc = load_categories()
    for supplier, avito in doc.size_map.items():
        assert avito in doc.allowed("Size"), f"{supplier} -> {avito!r} нет в справочнике"


def test_color_map_targets_exist_in_color_dictionary():
    doc = load_categories()
    for stem, avito in doc.color_map.items():
        assert avito in doc.allowed("Color"), f"{stem} -> {avito!r} нет в справочнике"


def test_is_allowed_is_permissive_only_for_tags_without_dictionary():
    doc = load_categories()
    assert doc.is_allowed("Delivery", "что угодно")  # справочника нет
    assert not doc.is_allowed("Condition", "Б/у")  # справочник есть


def test_adstatus_is_promotion_not_archiving():
    """AdStatus — платные услуги. Архивация идёт через DateEnd; если это
    перепутать, затирка (Э7) купит продвижение на боевом аккаунте."""
    doc = load_categories()
    assert "Free" in doc.allowed("AdStatus")
    assert doc.feed["archive_tag"] == "DateEnd"


def test_candidates_are_not_treated_as_a_dictionary():
    """Ответ заказчика по смыслу («доставка — авито») не должен ни
    разблокировать публикацию, ни попасть в справочник: Авито сверяет
    строкой, а дословное написание нам никто не подтверждал."""
    doc = load_categories()
    assert doc.candidates["Delivery"]  # подсказка записана
    assert "Delivery" not in doc.enums  # но справочником не стала
    assert "Delivery" in doc.unresolved_required_fields
    with pytest.raises(CategoriesNotVerifiedError, match="Delivery"):
        doc.require_verified()


def test_resolve_field_unblocks_publication(tmp_path):
    """Ровно та операция, которой закрывается B-024."""
    path = tmp_path / "categories.yaml"
    shutil.copy(DATA_PATH, path)

    resolve_field("Delivery", ["Авито доставка"], path=path)

    doc = load_categories(path)
    assert doc.allowed("Delivery") == ["Авито доставка"]
    assert doc.unresolved_required_fields == []
    assert "Delivery" not in doc.candidates
    doc.require_verified()  # больше не блокирует


def test_resolve_field_refuses_unknown_tag(tmp_path):
    path = tmp_path / "categories.yaml"
    shutil.copy(DATA_PATH, path)

    with pytest.raises(ValueError, match="обязательным"):
        resolve_field("НеТег", ["значение"], path=path)


def test_resolve_field_refuses_empty_values(tmp_path):
    path = tmp_path / "categories.yaml"
    shutil.copy(DATA_PATH, path)

    with pytest.raises(ValueError):
        resolve_field("Delivery", [], path=path)


def test_render_markdown_reports_blocked_status_and_dictionaries():
    md = render_markdown(load_categories())
    assert "Delivery" in md
    assert "Кофты и футболки" in md
    assert "48 (M)" in md
