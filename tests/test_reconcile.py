from __future__ import annotations

from sqlmodel import select

from core.models import SupplierItem
from sources.base import RawRow
from sources.reconcile import reconcile_source


def _row(key: str, title: str, price: float, sizes=("S", "M")) -> RawRow:
    return RawRow(
        source_key=key,
        source_type="gsheets",
        raw_title=title,
        sizes_available=list(sizes),
        price_purchase=price,
    )


def test_dry_run_reports_new_but_does_not_write(session):
    rows = [_row("s:1", "Товар A", 1000.0)]
    summary = reconcile_source(session, source_name="s", fresh_rows=rows, dry_run=True)

    assert summary.new == ["s:1"]
    assert session.exec(select(SupplierItem)).all() == []


def test_write_persists_new_items(session):
    rows = [_row("s:1", "Товар A", 1000.0), _row("s:2", "Товар B", 2000.0)]
    summary = reconcile_source(session, source_name="s", fresh_rows=rows, dry_run=False)

    assert sorted(summary.new) == ["s:1", "s:2"]
    saved = session.exec(select(SupplierItem)).all()
    assert len(saved) == 2
    assert all(item.is_available for item in saved)


def test_second_sync_with_same_data_reports_unchanged(session):
    rows = [_row("s:1", "Товар A", 1000.0)]
    reconcile_source(session, source_name="s", fresh_rows=rows, dry_run=False)

    summary = reconcile_source(session, source_name="s", fresh_rows=rows, dry_run=False)
    assert summary.new == []
    assert summary.changed == []
    assert summary.unchanged_count == 1


def test_price_change_is_detected_and_applied(session):
    reconcile_source(
        session, source_name="s", fresh_rows=[_row("s:1", "Товар A", 1000.0)], dry_run=False
    )

    summary = reconcile_source(
        session, source_name="s", fresh_rows=[_row("s:1", "Товар A", 1200.0)], dry_run=False
    )
    assert summary.changed == ["s:1"]

    item = session.exec(select(SupplierItem).where(SupplierItem.source_key == "s:1")).one()
    assert item.price_purchase == 1200.0


def test_disappeared_item_marked_unavailable_not_deleted(session):
    reconcile_source(
        session,
        source_name="s",
        fresh_rows=[_row("s:1", "Товар A", 1000.0), _row("s:2", "Товар B", 2000.0)],
        dry_run=False,
    )

    summary = reconcile_source(
        session, source_name="s", fresh_rows=[_row("s:1", "Товар A", 1000.0)], dry_run=False
    )
    assert summary.disappeared == ["s:2"]

    item_b = session.exec(select(SupplierItem).where(SupplierItem.source_key == "s:2")).one()
    assert item_b.is_available is False  # не удалён, просто помечен пропавшим


def test_reappeared_item_flips_back_to_available(session):
    reconcile_source(
        session, source_name="s", fresh_rows=[_row("s:1", "Товар A", 1000.0)], dry_run=False
    )
    reconcile_source(session, source_name="s", fresh_rows=[], dry_run=False)

    item = session.exec(select(SupplierItem).where(SupplierItem.source_key == "s:1")).one()
    assert item.is_available is False

    reconcile_source(
        session, source_name="s", fresh_rows=[_row("s:1", "Товар A", 1000.0)], dry_run=False
    )
    session.refresh(item)
    assert item.is_available is True


def test_warning_when_row_count_suspiciously_low(session):
    summary = reconcile_source(
        session,
        source_name="s",
        fresh_rows=[_row("s:1", "Товар A", 1000.0)],
        min_expected_rows=10,
        dry_run=True,
    )
    assert summary.warning is not None
    assert "10" in summary.warning
