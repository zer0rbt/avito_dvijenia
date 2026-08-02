from __future__ import annotations

from core.models import GeoCity, Listing, ListingState, Product, ProductStatus
from lifecycle.planner import plan_next_batch


def _make_product(session, **overrides) -> Product:
    defaults = dict(
        supplier_item_id=1,
        title="Товар",
        status=ProductStatus.APPROVED,
        price_purchase=1000.0,
        price_final=2500.0,
    )
    defaults.update(overrides)
    product = Product(**defaults)
    session.add(product)
    session.commit()
    session.refresh(product)
    return product


def _make_listing(session, product_id: int, **overrides) -> Listing:
    defaults = dict(
        product_id=product_id,
        city=GeoCity.MSK,
        internal_id=f"{product_id}-{overrides.get('city', GeoCity.MSK).value}-g1",
        state=ListingState.DRAFT,
    )
    defaults.update(overrides)
    listing = Listing(**defaults)
    session.add(listing)
    session.commit()
    session.refresh(listing)
    return listing


def test_plan_selects_draft_listings_within_budget(session):
    product = _make_product(session)
    listing = _make_listing(session, product.id)

    plan = plan_next_batch(session, max_active_listings=10, already_active_count=0)

    assert plan.selected_listing_ids == [listing.id]
    assert plan.skipped_over_budget == []


def test_plan_ignores_non_approved_products(session):
    product = _make_product(session, status=ProductStatus.NEEDS_REVIEW)
    _make_listing(session, product.id)

    plan = plan_next_batch(session, max_active_listings=10, already_active_count=0)

    assert plan.selected_listing_ids == []


def test_plan_ignores_non_draft_listings(session):
    product = _make_product(session)
    _make_listing(session, product.id, state=ListingState.PUBLISHED)

    plan = plan_next_batch(session, max_active_listings=10, already_active_count=0)

    assert plan.selected_listing_ids == []


def test_plan_ranks_higher_margin_product_first(session):
    cheap = _make_product(session, price_final=1100.0, price_purchase=1000.0)  # маржа 100
    rich = _make_product(session, price_final=3000.0, price_purchase=1000.0)  # маржа 2000

    cheap_listing = _make_listing(session, cheap.id)
    rich_listing = _make_listing(session, rich.id)

    plan = plan_next_batch(session, max_active_listings=1, already_active_count=0)

    assert plan.selected_listing_ids == [rich_listing.id]
    assert plan.skipped_over_budget == [cheap_listing.id]


def test_plan_returns_nothing_when_budget_already_exhausted(session):
    product = _make_product(session)
    listing = _make_listing(session, product.id)

    plan = plan_next_batch(session, max_active_listings=5, already_active_count=5)

    assert plan.selected_listing_ids == []
    assert plan.skipped_over_budget == [listing.id]
