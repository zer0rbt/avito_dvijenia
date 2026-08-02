from __future__ import annotations

import pytest

from core.approval import (
    ApprovalRequiredError,
    confirm_and_execute,
    list_pending,
    reject_operation,
    request_operation,
)
from core.models import OperationKind, OperationStatus


def test_dry_run_does_not_create_pending_and_does_not_execute(session):
    executed = []

    result = request_operation(
        session,
        kind=OperationKind.PUBLISH,
        listing_ids=[1, 2, 3],
        summary="test dry run",
        executor=lambda: executed.append(True),
        dry_run=True,
    )

    assert result.listing_ids == [1, 2, 3]
    assert executed == []
    assert list_pending(session) == []


def test_non_dry_run_without_auto_confirm_raises_and_leaves_pending(session):
    executed = []

    with pytest.raises(ApprovalRequiredError) as exc_info:
        request_operation(
            session,
            kind=OperationKind.WIPE,
            listing_ids=[5],
            summary="test wipe",
            executor=lambda: executed.append(True),
            dry_run=False,
            auto_confirm=False,
        )

    op = exc_info.value.operation
    assert op.status == OperationStatus.PENDING
    assert executed == []

    pending = list_pending(session)
    assert len(pending) == 1
    assert pending[0].id == op.id


def test_confirm_and_execute_runs_executor_and_marks_executed(session):
    executed = []

    with pytest.raises(ApprovalRequiredError) as exc_info:
        request_operation(
            session,
            kind=OperationKind.ARCHIVE,
            listing_ids=[7],
            summary="test archive",
            executor=lambda: executed.append(True),
            dry_run=False,
        )
    op_id = exc_info.value.operation.id

    result = confirm_and_execute(session, op_id, lambda: executed.append(True), decided_by="tester")

    assert result.status == OperationStatus.EXECUTED
    assert executed == [True]
    assert list_pending(session) == []


def test_confirm_and_execute_marks_failed_on_executor_error(session):
    with pytest.raises(ApprovalRequiredError) as exc_info:
        request_operation(
            session,
            kind=OperationKind.REISSUE,
            listing_ids=[9],
            summary="test failing reissue",
            executor=lambda: None,
            dry_run=False,
        )
    op_id = exc_info.value.operation.id

    def _boom():
        raise RuntimeError("Автозагрузка недоступна")

    with pytest.raises(RuntimeError):
        confirm_and_execute(session, op_id, _boom, decided_by="tester")

    from sqlmodel import select

    from core.models import PendingOperation

    op = session.exec(select(PendingOperation).where(PendingOperation.id == op_id)).one()
    assert op.status == OperationStatus.FAILED
    assert "Автозагрузка недоступна" in op.error


def test_reject_operation(session):
    with pytest.raises(ApprovalRequiredError) as exc_info:
        request_operation(
            session,
            kind=OperationKind.PUBLISH,
            listing_ids=[11],
            summary="test reject",
            executor=lambda: None,
            dry_run=False,
        )
    op_id = exc_info.value.operation.id

    op = reject_operation(session, op_id, decided_by="tester")
    assert op.status == OperationStatus.REJECTED
    assert list_pending(session) == []


def test_auto_confirm_executes_immediately(session):
    executed = []
    op = request_operation(
        session,
        kind=OperationKind.PUBLISH,
        listing_ids=[13],
        summary="cli --yes path",
        executor=lambda: executed.append(True),
        dry_run=False,
        auto_confirm=True,
    )
    assert op.status == OperationStatus.EXECUTED
    assert executed == [True]
