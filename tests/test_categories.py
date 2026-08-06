from __future__ import annotations

from pathlib import Path

import pytest
import yaml

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


def test_shipped_schema_no_longer_blocks_publication():
    """Единственное поле без справочника (Delivery) закрыто: официальный
    валидатор Авито принял объявление без него (B-024)."""
    doc = load_categories()
    assert doc.unresolved_required_fields == []
    doc.require_verified()


def test_delivery_is_not_required_despite_the_template():
    """Шаблон помечает Delivery обязательным, валидатор Авито — нет.

    Регресс на живой ответ валидатора (06.08.2026): объявление без тега —
    «Соответствует формату», все шесть проверенных написаний значения —
    «Способ доставки: Значение не найдено». Поэтому тег не отдаём вовсе;
    если кто-то вернёт его в required_tags, фид начнёт требовать значение,
    которого мы не знаем.
    """
    doc = load_categories()
    assert "Delivery" not in doc.required_tags
    assert "Delivery" in doc.conditionally_required_tags
    assert doc.allowed("Delivery") == []


def test_require_verified_still_blocks_on_unresolved_field():
    """Сам рубеж никуда не делся — проверяем на искусственном поле."""
    doc = categories_doc(unresolved_required_fields=["Delivery"])
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
    """Ответ по смыслу не должен ни разблокировать публикацию, ни попасть
    в справочник: Авито сверяет строкой. Проверка не на живой схеме — там
    кандидатов уже не осталось, — а на самом механизме."""
    doc = categories_doc(
        unresolved_required_fields=["Delivery"],
        candidates={"Delivery": ["Авито доставка"]},
    )
    assert doc.allowed("Delivery") == []  # кандидат справочником не стал
    with pytest.raises(CategoriesNotVerifiedError, match="Авито доставка"):
        doc.require_verified()  # но в тексте ошибки подсказан


def _schema_with_unresolved(tmp_path) -> Path:
    """Копия боевой схемы с искусственно нерешённым полем.

    В самой схеме нерешённых полей больше нет (B-024), а механизм закрытия
    проверять надо — иначе следующий такой случай встретим без тестов.
    """
    path = tmp_path / "categories.yaml"
    raw = yaml.safe_load(DATA_PATH.read_text(encoding="utf-8"))
    raw["required_tags"].append("Delivery")
    raw["unresolved_required_fields"] = ["Delivery"]
    raw["candidates"] = {"Delivery": ["Авито доставка"]}
    path.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def test_resolve_field_unblocks_publication(tmp_path):
    path = _schema_with_unresolved(tmp_path)

    resolve_field("Delivery", ["Авито доставка"], path=path)

    doc = load_categories(path)
    assert doc.allowed("Delivery") == ["Авито доставка"]
    assert doc.unresolved_required_fields == []
    assert "Delivery" not in doc.candidates
    doc.require_verified()  # больше не блокирует


def test_resolve_field_refuses_unknown_tag(tmp_path):
    path = _schema_with_unresolved(tmp_path)

    with pytest.raises(ValueError, match="обязательным"):
        resolve_field("НеТег", ["значение"], path=path)


def test_resolve_field_refuses_empty_values(tmp_path):
    path = _schema_with_unresolved(tmp_path)

    with pytest.raises(ValueError):
        resolve_field("Delivery", [], path=path)


def test_render_markdown_reports_blocked_status_and_dictionaries():
    md = render_markdown(load_categories())
    assert "Delivery" in md
    assert "Кофты и футболки" in md
    assert "48 (M)" in md
