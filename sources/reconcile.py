"""Сведение свежих RawRow с тем, что уже лежит в SupplierItem.

Ключ сравнения — source_key (стабилен между синками одного товара).
Логика: не нашли source_key в свежем срезе -> товар пропал у поставщика ->
is_available=False (план: "позиция кончилась -> снимаем объявление", это
подхватит lifecycle/planner.py на Э5, здесь только фиксируем факт).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from core.models import SupplierItem, utcnow
from sources.base import RawRow


@dataclass
class ReconcileSummary:
    source_name: str
    new: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    unchanged_count: int = 0
    disappeared: list[str] = field(default_factory=list)
    warning: str | None = None


def _row_changed(existing: SupplierItem, fresh: RawRow) -> bool:
    return (
        existing.raw_title != fresh.raw_title
        or existing.color != fresh.color
        or existing.sizes_available != ",".join(fresh.sizes_available)
        or existing.price_purchase != fresh.price_purchase
        or existing.price_rrc != fresh.price_rrc
    )


def _apply(existing: SupplierItem, fresh: RawRow) -> None:
    existing.raw_title = fresh.raw_title
    existing.brand = fresh.brand
    existing.goods_type = fresh.goods_type
    existing.color = fresh.color
    existing.sizes_available = ",".join(fresh.sizes_available)
    existing.price_purchase = fresh.price_purchase
    existing.price_rrc = fresh.price_rrc
    existing.photo_urls = ",".join(fresh.photo_urls)
    existing.ship_city = fresh.ship_city
    existing.post_url = fresh.post_url
    existing.last_seen_at = utcnow()
    existing.is_available = True


def reconcile_source(
    session: Session,
    *,
    source_name: str,
    fresh_rows: list[RawRow],
    min_expected_rows: int = 1,
    dry_run: bool = True,
) -> ReconcileSummary:
    summary = ReconcileSummary(source_name=source_name)

    if len(fresh_rows) < min_expected_rows:
        summary.warning = (
            f"Получено {len(fresh_rows)} строк, ожидалось от {min_expected_rows}. "
            f"Похоже, раскладка таблицы поменялась — парсер мог сломаться молча, "
            f"а не просто товар кончился."
        )

    existing_rows = list(
        session.exec(
            select(SupplierItem).where(SupplierItem.source_type == "gsheets")
        )
    )
    existing_by_key = {r.source_key: r for r in existing_rows if r.source_key.startswith(source_name)}
    fresh_by_key = {r.source_key: r for r in fresh_rows}

    for key, fresh in fresh_by_key.items():
        existing = existing_by_key.get(key)
        if existing is None:
            summary.new.append(key)
            if not dry_run:
                item = SupplierItem(
                    source_key=key,
                    source_type=fresh.source_type,
                    raw_title=fresh.raw_title,
                    brand=fresh.brand,
                    goods_type=fresh.goods_type,
                    color=fresh.color,
                    sizes_available=",".join(fresh.sizes_available),
                    price_purchase=fresh.price_purchase,
                    price_rrc=fresh.price_rrc,
                    photo_urls=",".join(fresh.photo_urls),
                    ship_city=fresh.ship_city,
                    post_url=fresh.post_url,
                )
                session.add(item)
        elif _row_changed(existing, fresh):
            summary.changed.append(key)
            if not dry_run:
                _apply(existing, fresh)
                session.add(existing)
        else:
            summary.unchanged_count += 1
            if not dry_run:
                existing.last_seen_at = utcnow()
                existing.is_available = True
                session.add(existing)

    for key, existing in existing_by_key.items():
        if key not in fresh_by_key and existing.is_available:
            summary.disappeared.append(key)
            if not dry_run:
                existing.is_available = False
                session.add(existing)

    if not dry_run:
        session.commit()

    return summary
