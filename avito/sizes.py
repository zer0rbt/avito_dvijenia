"""Маппинг сетки размеров поставщика (буквенная: XS/S/M/L/XL/XXL/...) в
значение Size Автозагрузки.

Дерево категорий и точные допустимые значения атрибутов не подтверждены
(avito/categories.py, verified: false — см. docs/BACKLOG.md B-002).
Буквенная сетка, которую отдают оба источника (Э1), формально совпадает с
тем, что Авито в открытых примерах фида принимает для верхней одежды — но
это не сверено с ЛК реального аккаунта. Поэтому маппинг здесь ПРОЗРАЧНЫЙ
(тот же токен на входе и выходе, только нормализация регистра/пробелов),
а не переименовывающий: если ЛК потребует другой формат, это обнаружится
явно на первой публикации, а не потеряется за тихой подменой значений.

Неизвестный размер не публикуется молча — попадает в unmapped, и вызывающий
код (content/build.py) должен на это отреагировать (план, "Категории
Авито": "неизвестный размер не уезжает в Авито, а поднимает карточку в
очередь на решение").
"""

from __future__ import annotations

KNOWN_SIZES = {"XS", "S", "M", "L", "XL", "XXL", "XXXL", "2XL", "3XL"}


def map_sizes(sizes_supplier: list[str]) -> tuple[list[str], list[str]]:
    """Возвращает (mapped, unmapped). Порядок mapped сохраняет порядок
    появления во входном списке, дубликаты схлопываются."""
    mapped: list[str] = []
    unmapped: list[str] = []
    seen: set[str] = set()

    for raw in sizes_supplier:
        token = raw.strip().upper()
        if not token:
            continue
        if token in KNOWN_SIZES:
            if token not in seen:
                mapped.append(token)
                seen.add(token)
        else:
            unmapped.append(raw)

    return mapped, unmapped
