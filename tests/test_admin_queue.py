from __future__ import annotations

from sqlmodel import select

from admin.queue import (
    apply_operator_decisions,
    evaluate_auto_status,
    sync_products_from_supplier_items,
)
from core.models import AuditLogEntry, Product, ProductStatus, SupplierItem


def _supplier_item(**kwargs) -> SupplierItem:
    defaults = dict(
        source_key="s:1",
        source_type="gsheets",
        raw_title="Balenciaga Arena",
        brand="Balenciaga",
        color="Чёрный",
        sizes_available="S,M,L",
        price_purchase=3000.0,
        price_rrc=None,
    )
    defaults.update(kwargs)
    return SupplierItem(**defaults)


def test_evaluate_auto_status_needs_review_when_no_sizes():
    item = _supplier_item(sizes_available="")
    status, reason = evaluate_auto_status(item)
    assert status == ProductStatus.NEEDS_REVIEW
    assert reason == "no_sizes"


def test_evaluate_auto_status_needs_review_when_brand_unknown():
    item = _supplier_item(brand=None)
    status, reason = evaluate_auto_status(item)
    assert status == ProductStatus.NEEDS_REVIEW
    assert reason == "brand_unknown"


def test_evaluate_auto_status_needs_review_when_price_missing():
    item = _supplier_item(price_purchase=None, price_rrc=None)
    status, reason = evaluate_auto_status(item)
    assert status == ProductStatus.NEEDS_REVIEW
    assert reason == "price_missing"


def test_evaluate_auto_status_approved_when_all_signals_present():
    item = _supplier_item()
    status, reason = evaluate_auto_status(item)
    assert status == ProductStatus.APPROVED
    assert reason is None


def test_sync_creates_product_per_supplier_item(session):
    session.add(_supplier_item(source_key="s:1"))
    session.add(_supplier_item(source_key="s:2", brand=None))
    session.commit()

    summary = sync_products_from_supplier_items(session)

    assert len(summary.created) == 2
    assert len(summary.auto_approved) == 1
    assert len(summary.needs_review) == 1

    products = session.exec(select(Product)).all()
    assert len(products) == 2


def test_sync_is_idempotent_when_nothing_changed(session):
    session.add(_supplier_item(source_key="s:1"))
    session.commit()

    sync_products_from_supplier_items(session)
    summary = sync_products_from_supplier_items(session)

    assert summary.created == []
    assert summary.updated == []  # regression: раньше "обновлялось" всё подряд


def test_sync_updates_only_when_supplier_data_actually_changed(session):
    session.add(_supplier_item(source_key="s:1", price_purchase=3000.0))
    session.commit()
    sync_products_from_supplier_items(session)

    item = session.exec(select(SupplierItem)).one()
    item.price_purchase = 3500.0
    session.add(item)
    session.commit()

    summary = sync_products_from_supplier_items(session)
    assert len(summary.updated) == 1

    product = session.exec(select(Product)).one()
    assert product.price_purchase == 3500.0
    assert product.price_final == 5000.0  # 3500 + 1500


def test_sync_does_not_touch_products_with_operator_decision(session):
    session.add(_supplier_item(source_key="s:1"))
    session.commit()
    sync_products_from_supplier_items(session)

    product = session.exec(select(Product)).one()
    product.status = ProductStatus.REJECTED
    product.review_reason = "operator_decision"
    session.add(product)
    session.commit()

    item = session.exec(select(SupplierItem)).one()
    item.price_purchase = 9999.0  # источник поменялся
    session.add(item)
    session.commit()

    sync_products_from_supplier_items(session)

    refreshed = session.get(Product, product.id)
    assert refreshed.status == ProductStatus.REJECTED  # решение оператора не тронуто
    assert refreshed.price_purchase != 9999.0  # и данные тоже не подтянулись


def test_disappeared_supplier_item_auto_rejects_pending_product(session):
    item = _supplier_item(source_key="s:1")
    session.add(item)
    session.commit()
    sync_products_from_supplier_items(session)

    item.is_available = False
    session.add(item)
    session.commit()

    summary = sync_products_from_supplier_items(session)
    assert len(summary.disappeared_rejected) == 1

    product = session.exec(select(Product)).one()
    assert product.status == ProductStatus.REJECTED
    assert product.review_reason == "disappeared_from_source"


def test_disappeared_supplier_item_does_not_touch_already_queued_product(session):
    item = _supplier_item(source_key="s:1")
    session.add(item)
    session.commit()
    sync_products_from_supplier_items(session)

    product = session.exec(select(Product)).one()
    product.status = ProductStatus.QUEUED  # уже пошёл дальше по жизненному циклу
    session.add(product)
    session.commit()

    item.is_available = False
    session.add(item)
    session.commit()

    summary = sync_products_from_supplier_items(session)
    assert summary.disappeared_rejected == []

    refreshed = session.get(Product, product.id)
    assert refreshed.status == ProductStatus.QUEUED


def test_apply_operator_decisions_maps_russian_text_to_status(session):
    session.add(_supplier_item(source_key="s:1", brand=None))  # -> NEEDS_REVIEW
    session.commit()
    sync_products_from_supplier_items(session)
    product = session.exec(select(Product)).one()

    applied = apply_operator_decisions(session, {product.id: "публиковать"})
    assert applied[product.id] == "APPROVED"

    refreshed = session.get(Product, product.id)
    assert refreshed.status == ProductStatus.APPROVED
    assert refreshed.review_reason is None


def test_apply_operator_decisions_ignores_unknown_text(session):
    session.add(_supplier_item(source_key="s:1"))
    session.commit()
    sync_products_from_supplier_items(session)
    product = session.exec(select(Product)).one()
    original_status = product.status

    applied = apply_operator_decisions(session, {product.id: "какая-то ерунда"})
    assert applied == {}

    refreshed = session.get(Product, product.id)
    assert refreshed.status == original_status


def test_apply_operator_decisions_ignores_empty_and_unknown_product_id(session):
    applied = apply_operator_decisions(session, {999: "публиковать", 1: ""})
    assert applied == {}


def test_apply_operator_decisions_writes_audit_log(session):
    session.add(_supplier_item(source_key="s:1"))
    session.commit()
    sync_products_from_supplier_items(session)
    product = session.exec(select(Product)).one()

    apply_operator_decisions(session, {product.id: "пропустить"})

    entries = session.exec(select(AuditLogEntry)).all()
    assert len(entries) == 1
    assert entries[0].actor == "operator:sheet"
    assert "REJECTED" in entries[0].action
    assert str(product.id) in entries[0].details
