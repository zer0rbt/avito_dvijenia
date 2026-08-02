"""Проверка текста на самодубль между версиями одной карточки (план,
"Синонимизация при перезаливе": "каждая версия... проверяется шинглами
против всех предыдущих версий этого товара, а не только против
последней"). Текстовый аналог media/phash.py.
"""

from __future__ import annotations

import re

SHINGLE_SIZE = 5  # слов в шингле
DEFAULT_MAX_SIMILARITY = 0.6


def shingles(text: str, size: int = SHINGLE_SIZE) -> set[str]:
    words = re.findall(r"\w+", text.lower())
    if len(words) < size:
        return {" ".join(words)} if words else set()
    return {" ".join(words[i : i + size]) for i in range(len(words) - size + 1)}


def jaccard_similarity(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def is_too_similar(
    new_text: str, previous_texts: list[str], *, max_similarity: float = DEFAULT_MAX_SIMILARITY
) -> bool:
    new_shingles = shingles(new_text)
    return any(
        jaccard_similarity(new_shingles, shingles(prev)) > max_similarity for prev in previous_texts
    )
