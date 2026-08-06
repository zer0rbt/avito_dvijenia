"""Регистрирует исполнителя OperationKind.PUBLISH (Э5) в bot/registry.py —
единственное место, где подтверждённая планировщиком (lifecycle/planner.py)
пачка Listing реально переходит DRAFT -> QUEUED.

Реального вызова Авито здесь нет и не будет: подтверждённого эндпоинта
"опубликовать" не существует (см. avito/client.py, план "Статус") —
Автозагрузка сама заберёт /feed.xml по расписанию из ЛК, когда карточка
попадёт в QUEUED. Импортировать этот модуль нужно один раз при старте
процесса (bot/main.py, cli.py) — иначе register() не вызовется и
build_executor() честно упадёт NotImplementedError.
"""

from __future__ import annotations

from sqlmodel import Session, select

from avito.budget import BudgetCheckError, check_budget
from bot.registry import register
from core.config import get_settings
from core.db import get_session
from core.models import Listing, ListingState, OperationKind, Product, ProductStatus, utcnow


def _publish_executor_factory(listing_ids: list[int]):
    def _execute() -> None:
        _require_budget()
        with get_session() as session:
            mark_queued(session, listing_ids)

    return _execute


def _require_budget() -> None:
    """Последний рубеж перед переводом карточек в QUEUED.

    Проверка есть и в `cli.py planner run`, но там она защищает только один
    путь. Сюда приходит и подтверждение из бота, и будущий планировщик (Э9),
    а QUEUED означает «карточка уедет в фид при следующем опросе Авито» —
    то есть начнёт тратить аванс. Между планированием и нажатием кнопки
    может пройти сколько угодно времени, за которое аванс успевает
    кончиться, так что спрашивать надо здесь, а не только на входе.
    """
    settings = get_settings()
    if not settings.avito_user_id:
        raise BudgetCheckError("AVITO_USER_ID не задан — бюджет не проверить, публикация отменена")

    status = check_budget(user_id=settings.avito_user_id)
    if not status.publish_allowed:
        raise BudgetCheckError(f"публикация отменена: {status.reason}")


def mark_queued(session: Session, listing_ids: list[int]) -> None:
    affected_product_ids: set[int] = set()

    for listing_id in listing_ids:
        listing = session.get(Listing, listing_id)
        if listing is None or listing.state != ListingState.DRAFT:
            continue
        listing.state = ListingState.QUEUED
        listing.updated_at = utcnow()
        session.add(listing)
        affected_product_ids.add(listing.product_id)

    for product_id in affected_product_ids:
        product = session.get(Product, product_id)
        if product is None:
            continue
        still_draft = session.exec(
            select(Listing.id)
            .where(Listing.product_id == product_id)
            .where(Listing.state == ListingState.DRAFT)
            .limit(1)
        ).first()
        if still_draft is None:
            product.status = ProductStatus.QUEUED
            product.updated_at = utcnow()
            session.add(product)

    session.commit()


register(OperationKind.PUBLISH, _publish_executor_factory)
