"""Приоритизация фида: какие DRAFT-Listing перевести в QUEUED в рамках
бюджета активных карточек (план, "Приоритизация фида" — score = спрос ×
маржа × конверсия_в_контакты / цена_просмотра).

Конверсии и цены просмотра пока нет данных (Э6 — стата ещё не собирается),
поэтому формула сейчас упрощена до demand_score × маржа. Как появится
стата, здесь добавится делитель — сигнатура функции не изменится, только
_score().

Сама функция ничего не пишет в БД и не публикует — она только выбирает
кандидатов. Перевод DRAFT -> QUEUED делает lifecycle/publish.py, и только
после подтверждения оператора через core.approval (план, "Режим оператора"
— сквозной, publish не исключение).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from core.models import Listing, ListingState, Product, ProductStatus

DEFAULT_DEMAND_SCORE = 1.0  # нейтральный вес, пока "Аналитика спроса" не подключена


@dataclass
class PlanResult:
    selected_listing_ids: list[int] = field(default_factory=list)
    skipped_over_budget: list[int] = field(default_factory=list)


def _score(product: Product) -> float:
    demand = product.demand_score if product.demand_score is not None else DEFAULT_DEMAND_SCORE
    cost = product.price_purchase if product.price_purchase is not None else product.price_rrc
    margin = (product.price_final or 0.0) - (cost or 0.0)
    return demand * max(margin, 0.0)


def plan_next_batch(
    session: Session, *, max_active_listings: int, already_active_count: int
) -> PlanResult:
    """DRAFT-листинги одобренных товаров, отранжированные по score, обрезанные
    под оставшийся бюджет (max_active_listings - already_active_count)."""
    result = PlanResult()
    budget_left = max_active_listings - already_active_count
    if budget_left <= 0:
        draft_ids = list(
            session.exec(
                select(Listing.id)
                .where(Listing.state == ListingState.DRAFT)
                .where(Listing.product_id == Product.id)
                .where(Product.status == ProductStatus.APPROVED)
            )
        )
        result.skipped_over_budget = draft_ids
        return result

    rows = list(
        session.exec(
            select(Listing, Product)
            .where(Listing.state == ListingState.DRAFT)
            .where(Listing.product_id == Product.id)
            .where(Product.status == ProductStatus.APPROVED)
        )
    )
    ranked = sorted(rows, key=lambda pair: _score(pair[1]), reverse=True)

    result.selected_listing_ids = [listing.id for listing, _product in ranked[:budget_left]]
    result.skipped_over_budget = [listing.id for listing, _product in ranked[budget_left:]]
    return result
