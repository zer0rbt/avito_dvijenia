"""Общий интерфейс источника товаров поставщика (Э1).

Каждый источник умеет только одно — вернуть список сырых строк в едином
промежуточном виде (RawRow). Дальше sources/normalizer.py доводит их до
core.models.SupplierItem, а sources/reconcile.py сравнивает с прошлым
синком и решает, что новое/изменилось/пропало.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


@dataclass
class RawRow:
    """Сырая строка от источника, ещё не нормализованная.

    source_key должен быть стабилен между синками одного и того же товара
    (напр. "gsheets:<sheet_id>:<row_index>"), иначе reconcile.py не сможет
    отличить "товар пропал" от "это новый товар".
    """

    source_key: str
    source_type: str  # gsheets | website | telegram
    raw_title: str
    color: str | None = None
    sizes_available: list[str] = field(default_factory=list)
    price_purchase: float | None = None
    price_rrc: float | None = None
    photo_urls: list[str] = field(default_factory=list)
    ship_city: str | None = None
    post_url: str | None = None
    brand: str | None = None
    goods_type: str | None = None  # обувь | верхняя одежда, если источник знает


class BaseSource(Protocol):
    name: str

    def fetch(self) -> list[RawRow]: ...
