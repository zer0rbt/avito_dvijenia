from __future__ import annotations

from types import SimpleNamespace

import pytest

import lifecycle.publish as publish_module
from core.models import GeoCity, Listing, ListingState, Product, ProductStatus


def _make_product(session, **overrides) -> Product:
    defaults = dict(supplier_item_id=1, title="Товар", status=ProductStatus.APPROVED)
    defaults.update(overrides)
    product = Product(**defaults)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def _make_listing(session, product_id: int, city: GeoCity, **overrides) -> Listing:
    defaults = dict(
        product_id=product_id,
        city=city,
        internal_id=f"{product_id}-{city.value}-g1",
        state=ListingState.DRAFT,
    )
    defaults.update(overrides)
    listing = Listing(**defaults)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


def test_mark_queued_transitions_listing_state(session):
    product = _make_product(session)
    listing = _make_listing(session, product.id, GeoCity.MSK)

    publish_module.mark_queued(session, [listing.id])

    session.refresh(listing)
    assert listing.state == ListingState.QUEUED


def test_mark_queued_bumps_product_status_when_all_listings_queued(session):
    product = _make_product(session)
    listing = _make_listing(session, product.id, GeoCity.MSK)

    publish_module.mark_queued(session, [listing.id])

    session.refresh(product)
    assert product.status == ProductStatus.QUEUED


def test_mark_queued_keeps_product_approved_while_some_listings_still_draft(session):
    product = _make_product(session)
    msk = _make_listing(session, product.id, GeoCity.MSK)
    _make_listing(session, product.id, GeoCity.SPB)  # остаётся DRAFT

    publish_module.mark_queued(session, [msk.id])

    session.refresh(product)
    assert product.status == ProductStatus.APPROVED


def test_mark_queued_ignores_unknown_listing_id(session):
    # не должно падать — просто нечего делать
    publish_module.mark_queued(session, [999999])


def test_mark_queued_ignores_listing_not_in_draft_state(session):
    product = _make_product(session)
    listing = _make_listing(session, product.id, GeoCity.MSK, state=ListingState.PUBLISHED)

    publish_module.mark_queued(session, [listing.id])

    session.refresh(listing)
    assert listing.state == ListingState.PUBLISHED  # не тронут


def test_publish_kind_is_registered_in_bot_registry():
    from bot.registry import _registry
    from core.models import OperationKind

    assert OperationKind.PUBLISH in _registry


def test_publish_executor_factory_marks_queued_via_get_session(session, monkeypatch):
    # session-фикстура (tests/conftest.py) уже подменила core.db.engine на
    # ту же in-memory БД, что использует get_session() внутри исполнителя —
    # проверяем именно путь bot/registry.py -> lifecycle/publish.py целиком.
    from bot.registry import build_executor
    from core.models import OperationKind

    monkeypatch.setattr(publish_module, "_require_budget", lambda: None)
    product = _make_product(session)
    listing = _make_listing(session, product.id, GeoCity.MSK)

    executor = build_executor(OperationKind.PUBLISH, [listing.id])
    executor()

    session.refresh(listing)
    assert listing.state == ListingState.QUEUED


def test_publish_executor_refuses_when_budget_blocks(session, monkeypatch):
    """Проверка бюджета стоит в самом исполнителе, а не только в CLI.

    Сюда приходит подтверждение из бота и (Э9) планировщик, а QUEUED
    означает «карточка уедет в фид следующим опросом Авито» — то есть
    начнёт тратить аванс. Между планированием и нажатием кнопки аванс
    успевает кончиться.
    """
    from avito.budget import BudgetCheckError
    from bot.registry import build_executor
    from core.models import OperationKind

    def blocked() -> None:
        raise BudgetCheckError("публикация отменена: аванс 0 ₽ ниже порога 300 ₽")

    monkeypatch.setattr(publish_module, "_require_budget", blocked)
    product = _make_product(session)
    listing = _make_listing(session, product.id, GeoCity.MSK)

    executor = build_executor(OperationKind.PUBLISH, [listing.id])
    with pytest.raises(BudgetCheckError):
        executor()

    session.refresh(listing)
    assert listing.state == ListingState.DRAFT  # ничего не перевели


def test_require_budget_blocks_when_advance_not_set(monkeypatch):
    """ADVANCE_RUB не задан — публикуем вслепую, значит не публикуем (B-003)."""
    from avito.budget import BudgetCheckError, BudgetStatus

    monkeypatch.setattr(
        publish_module,
        "check_budget",
        lambda **_kw: BudgetStatus(
            wallet_rub=0.0,
            advance_rub=None,
            min_balance_rub=300,
            publish_allowed=False,
            reason="ADVANCE_RUB не задан",
        ),
    )
    monkeypatch.setattr(
        publish_module, "get_settings", lambda: SimpleNamespace(avito_user_id="123")
    )

    with pytest.raises(BudgetCheckError, match="ADVANCE_RUB"):
        publish_module._require_budget()
