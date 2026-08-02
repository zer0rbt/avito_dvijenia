from __future__ import annotations

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


def test_publish_executor_factory_marks_queued_via_get_session(session):
    # session-фикстура (tests/conftest.py) уже подменила core.db.engine на
    # ту же in-memory БД, что использует get_session() внутри исполнителя —
    # проверяем именно путь bot/registry.py -> lifecycle/publish.py целиком.
    from bot.registry import build_executor
    from core.models import OperationKind

    product = _make_product(session)
    listing = _make_listing(session, product.id, GeoCity.MSK)

    executor = build_executor(OperationKind.PUBLISH, [listing.id])
    executor()

    session.refresh(listing)
    assert listing.state == ListingState.QUEUED
