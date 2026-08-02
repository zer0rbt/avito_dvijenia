"""Мелкие переиспользуемые преобразования сырых значений поставщика.
Специфика разбора конкретной таблицы (какая колонка что значит) живёт
в самом источнике (sources/gsheets.py и т.д.) — здесь только то, что
повторяется между источниками: цена, бренд, чистка текста.
"""

from __future__ import annotations

import re

# Бренды, встреченные в источниках на момент Э1 (см. docs/sources_snapshot.md).
# Список расширяется по ходу подключения новых источников — если бренд не
# нашёлся, товар не отбрасывается, а просто уходит в NEEDS_REVIEW на Э2
# с review_reason="brand_unknown".
KNOWN_BRANDS = [
    "Stone Island",
    "Balenciaga",
    "Rick Owens",
    "Maison Margiela",
    "Undercover",
    "CP Company",
    "C.P. Company",
    "Corteiz",
    "Alexander McQueen",
    "Adidas",
    "Champion",
    "CAV EMPT",
    "Martine Rose",
    "BAPE",
    "Supreme",
]

# Источник вперемешку использует три формата в одной колонке:
#   "3650₽  3500₽"  - старая/новая цена, разделены ₽ (двойной пробел)
#   "5000 3850₽"    - та же пара БЕЗ ₽ между числами, только пробел
#   "2 890₽"        - одно число с пробелом как разделителем тысяч
# Наивный "цифры и пробелы подряд" схлопывает второй и третий случаи в
# одно и на "5000 3850" даёт мусорное "50003850" вместо двух чисел.
# Поэтому сначала пробуем короткую группу "N NNN" (разделитель тысяч:
# 1-2 цифры + пробел + ровно 3 цифры, не продолженные ещё одной цифрой),
# и только если не подошло - берём подряд идущие цифры как число.
_THOUSANDS_GROUPED_RE = r"\d{1,2}\s\d{3}(?!\d)"
_PLAIN_NUMBER_RE = r"\d+"
_PRICE_TOKEN_RE = re.compile(_THOUSANDS_GROUPED_RE + "|" + _PLAIN_NUMBER_RE)
_ANY_WHITESPACE_RE = re.compile(r"\s")


def parse_price_rub(text: str | None) -> float | None:
    """Достаёт цену из текста колонки прайса. Если чисел несколько (старая
    цена/новая цена через пробел или ₽) - берём последнее, оно актуальное.
    Разделитель тысяч у источника - неразрывный пробел (\\xa0), обычный
    re.sub(r"\\s", ...) снимает его так же, как и обычный пробел.
    """
    if not text:
        return None
    matches = _PRICE_TOKEN_RE.findall(text)
    if not matches:
        return None
    last = _ANY_WHITESPACE_RE.sub("", matches[-1])
    if not last:
        return None
    try:
        return float(last)
    except ValueError:
        return None


def clean_title(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\n", " ")).strip(" \"'")


def guess_brand(title: str) -> str | None:
    # источник пишет бренды как попало: "Stone_Island", "CP COMPANY" —
    # нормализуем подчёркивания/дефисы в пробелы перед сравнением
    normalized = re.sub(r"[_\-]+", " ", title.lower())
    for brand in KNOWN_BRANDS:
        if brand.lower() in normalized:
            return brand
    return None
