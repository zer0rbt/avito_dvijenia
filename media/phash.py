"""Реестр перцептивных хэшей: находим визуально одинаковые/похожие фото.

Нужен в двух местах: content/dedup.py (Э4) сверяет перезалив с прошлыми
версиями той же карточки, media/pipeline.py — чтобы не тащить в реестр
фото, которое по факту уже там лежит под другим URL (поставщик отдаёт
одну и ту же картинку с разных ссылок чаще, чем кажется).
"""

from __future__ import annotations

import io

import imagehash
from PIL import Image

# 64-битный phash, порог подобран по документации imagehash: единицы бит
# расхождения — то же фото после recompress/лёгкого кропа, десятки —
# разные фото. Не научная величина, калибруется по реальным дублям на Э4.
DEFAULT_MAX_DISTANCE = 6


def compute_phash(data: bytes) -> str:
    with Image.open(io.BytesIO(data)) as img:
        return str(imagehash.phash(img))


def hamming_distance(a: str, b: str) -> int:
    return imagehash.hex_to_hash(a) - imagehash.hex_to_hash(b)


def is_duplicate(a: str, b: str, *, max_distance: int = DEFAULT_MAX_DISTANCE) -> bool:
    return hamming_distance(a, b) <= max_distance
