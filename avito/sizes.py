"""Размеры и цвет: сетка поставщика -> строки Авито.

Раньше этот модуль был «прозрачным» (S -> S) с оговоркой «формат не сверен».
Теперь он сверен, и формат оказался другой: Авито хочет `48 (M)`, а не `M`
(avito/data/categories.yaml, enums.Size). Прозрачный маппинг отправил бы в
фид значение, которого в справочнике нет.

Ключевое ограничение, которое меняет схему карточки: **Size у Авито —
одно значение на объявление** («Одно значение из выпадающего списка», лист
«Объявления», столбец AS). Товар с сеткой S/M/L одной карточкой все три
размера в Size не отдаст. План (гранулярность товар × цвет × город,
«размеры в описании») с этим совместим только так: в Size уходит один
представительный размер, весь список — в описании. Какой именно размер
считать представительным — `pick_primary_size()`, см. B-022.
"""

from __future__ import annotations

from avito.categories import CategoriesDoc, load_categories


def map_sizes(
    sizes_supplier: list[str], *, categories: CategoriesDoc | None = None
) -> tuple[list[str], list[str]]:
    """(mapped, unmapped). mapped — строки Авито в порядке появления, без
    дублей; unmapped — то, чего нет в size_map (публиковать нельзя, карточка
    уходит оператору)."""
    categories = categories or load_categories()
    size_map = categories.size_map

    mapped: list[str] = []
    unmapped: list[str] = []
    seen: set[str] = set()

    for raw in sizes_supplier:
        token = raw.strip().upper()
        if not token:
            continue
        avito_size = size_map.get(token)
        if avito_size is None:
            unmapped.append(raw)
        elif avito_size not in seen:
            mapped.append(avito_size)
            seen.add(avito_size)

    return mapped, unmapped


def pick_primary_size(mapped_sizes: list[str]) -> str | None:
    """Один размер для тега Size из нескольких доступных.

    Берём медиану по порядку размерной сетки (не первый и не последний):
    ходовые M/L оказываются в середине сетки, и по ним карточку найдёт
    больше покупателей, чем по краю. Это компромисс, а не истина: покупатель,
    который фильтрует по «XL», карточку с Size=«48 (M)» не увидит, хотя XL
    есть в наличии и указан в описании.

    Альтернатива — отдельная карточка на каждый размер: точный поиск, но
    ×N карточек, а тариф — оплата за просмотры и аванс конечен. Решение
    за заказчиком, см. B-022 в docs/BACKLOG.md.
    """
    if not mapped_sizes:
        return None
    ordered = sorted(mapped_sizes, key=_size_sort_key)
    return ordered[(len(ordered) - 1) // 2]


def _size_sort_key(avito_size: str) -> tuple[int, str]:
    """Строки вида «48 (M)» сортируем по числовой части, а не лексикографически
    (иначе «50 (L)» < «54 (XL)» < «60 (3XL)» ломается на «One size»)."""
    head = avito_size.split(" ", 1)[0].rstrip("+")
    return (int(head), avito_size) if head.isdigit() else (10**6, avito_size)


def map_color(supplier_color: str | None, *, categories: CategoriesDoc | None = None) -> str | None:
    """Свободный текст поставщика («Черные», «ЧЕРНЫЙ») -> значение из
    справочника Color. Не опознали — None, и это не ошибка: Color у Авито
    «может быть обязательным», карточка без него собирается."""
    if not supplier_color:
        return None
    categories = categories or load_categories()
    lowered = supplier_color.strip().lower()
    if not lowered:
        return None

    # Сначала точное совпадение с самим справочником, потом по основе слова.
    for value in categories.allowed("Color"):
        if lowered == value.lower():
            return value

    # Длинные основы вперёд, чтобы «зелён» не проиграл «зел» и т.п.
    for stem in sorted(categories.color_map, key=len, reverse=True):
        if stem in lowered:
            return categories.color_map[stem]
    return None
