"""Заголовок карточки: "Бренд Модель", коротко, без воды (план, "Эталоны
контента", пример — "Balenciaga Arena").

Product.title хранит сырое название поставщика как есть (часто с шумом
разметки таблицы: тип товара, перенос строк, дублирующийся бренд другим
регистром) — заголовок для публикации собираем отдельно, не трогая
Product.title, чтобы не терять исходные данные при повторных синках
(см. admin/queue.py _product_differs_from_supplier_item).
"""

from __future__ import annotations

import re

MAX_TITLE_LENGTH = 50  # ограничение Автозагрузки на длину Title


def render_title(*, brand: str | None, raw_title: str) -> str:
    model = _strip_brand(raw_title, brand)
    if brand and model:
        title = f"{brand} {model}"
    elif brand:
        title = brand
    else:
        title = raw_title.strip()

    title = re.sub(r"\s+", " ", title).strip()
    return title[:MAX_TITLE_LENGTH].strip()


def _strip_brand(raw_title: str, brand: str | None) -> str:
    if not brand:
        return raw_title.strip()
    pattern = re.compile(re.escape(brand), re.IGNORECASE)
    stripped = pattern.sub("", raw_title)
    return re.sub(r"\s+", " ", stripped).strip(" -xX×")
