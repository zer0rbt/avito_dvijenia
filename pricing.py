"""Ценообразование карточки. Формула согласована с заказчиком (см.
docs/ROADMAP.md, "Согласованные параметры"): РРЦ + 1500 ₽, а если РРЦ
у источника нет — закупка + 1500 ₽.

Полноценный pricing.py (наценки по категориям, акции и т.п.) относится
к Э4, но сама формула уже полностью определена и нужна раньше — очереди
модерации (Э2) есть что показать оператору только если есть цена.
"""

from __future__ import annotations

MARKUP_RUB = 1500.0


def compute_final_price(*, price_rrc: float | None, price_purchase: float | None) -> float | None:
    """РРЦ + 1500, фоллбэк — закупка + 1500. Ни того ни другого нет — None,
    вызывающий код обязан считать это поводом для NEEDS_REVIEW, а не для
    публикации с пустой ценой.
    """
    base = price_rrc if price_rrc is not None else price_purchase
    if base is None:
        return None
    return base + MARKUP_RUB
