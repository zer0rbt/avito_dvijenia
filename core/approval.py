"""Режим оператора — сквозной предохранитель (см. план, раздел "Два
ограничителя, определяющие всю конструкцию").

Любая операция, меняющая что-то на Авито (публикация, затирка, архивация,
перезалив), проходит через этот модуль: создаётся PendingOperation,
и реально исполняется (`executor`) только после подтверждения. Подтверждение
даёт либо оператор через бота (`confirm`/`reject`), либо CLI с флагом
--yes (`auto_confirm=True`) — только для ручной отладки, планировщик
auto_confirm никогда не передаёт.

dry_run — отдельный, более грубый рубильник: если он True, операция вообще
не создаёт PendingOperation для боевого исполнения, а только печатает/логирует
итог. По умолчанию dry_run включён (Settings.dry_run_default), см. .env.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlmodel import Session, select

from core.config import get_settings
from core.models import (
    AuditLogEntry,
    OperationKind,
    OperationStatus,
    PendingOperation,
    utcnow,
)


class ApprovalRequiredError(RuntimeError):
    """Операция создана как PENDING и ждёт подтверждения — не исполнена сейчас."""

    def __init__(self, operation: PendingOperation):
        self.operation = operation
        super().__init__(
            f"Операция #{operation.id} ({operation.kind}) ждёт подтверждения: {operation.summary}"
        )


@dataclass
class DryRunResult:
    kind: OperationKind
    listing_ids: list[int]
    summary: str


def log_audit(session: Session, actor: str, action: str, details: str = "") -> None:
    session.add(AuditLogEntry(actor=actor, action=action, details=details))
    session.commit()


def request_operation(
    session: Session,
    *,
    kind: OperationKind,
    listing_ids: list[int],
    summary: str,
    executor: Callable[[], None],
    dry_run: bool | None = None,
    auto_confirm: bool = False,
    actor: str = "system",
) -> PendingOperation | DryRunResult:
    """Единая точка входа для любой боевой операции над Авито.

    - dry_run=True (или Settings.dry_run_default, если не передан явно):
      ничего не пишем в БД как операцию, просто логируем намерение и
      возвращаем DryRunResult. executor НЕ вызывается.
    - dry_run=False, auto_confirm=False (обычный путь для планировщика):
      создаём PendingOperation(status=PENDING) и бросаем ApprovalRequiredError —
      исполнение продолжится позже через confirm_and_execute() по нажатию
      кнопки в боте.
    - dry_run=False, auto_confirm=True (только CLI --yes, ручная отладка):
      создаём операцию, сразу помечаем CONFIRMED и исполняем.
    """
    settings = get_settings()
    effective_dry_run = settings.dry_run_default if dry_run is None else dry_run

    if effective_dry_run:
        log_audit(
            session,
            actor,
            f"DRY_RUN {kind.value}",
            f"listings={listing_ids} summary={summary}",
        )
        return DryRunResult(kind=kind, listing_ids=listing_ids, summary=summary)

    op = PendingOperation(
        kind=kind,
        listing_ids=",".join(str(i) for i in listing_ids),
        summary=summary,
        status=OperationStatus.PENDING,
    )
    session.add(op)
    session.commit()
    session.refresh(op)
    log_audit(session, actor, f"REQUEST {kind.value}", summary)

    if not auto_confirm:
        raise ApprovalRequiredError(op)

    return _execute(session, op, executor, decided_by=f"{actor}:auto_confirm")


def confirm_and_execute(
    session: Session,
    operation_id: int,
    executor: Callable[[], None],
    *,
    decided_by: str,
) -> PendingOperation:
    op = session.get(PendingOperation, operation_id)
    if op is None:
        raise ValueError(f"Операция #{operation_id} не найдена")
    if op.status != OperationStatus.PENDING:
        raise ValueError(f"Операция #{operation_id} уже в статусе {op.status}")

    op.status = OperationStatus.CONFIRMED
    op.decided_at = utcnow()
    op.decided_by = decided_by
    session.add(op)
    session.commit()
    log_audit(session, decided_by, f"CONFIRM {op.kind.value}", op.summary)

    return _execute(session, op, executor, decided_by=decided_by)


def reject_operation(session: Session, operation_id: int, *, decided_by: str) -> PendingOperation:
    op = session.get(PendingOperation, operation_id)
    if op is None:
        raise ValueError(f"Операция #{operation_id} не найдена")
    op.status = OperationStatus.REJECTED
    op.decided_at = utcnow()
    op.decided_by = decided_by
    session.add(op)
    session.commit()
    log_audit(session, decided_by, f"REJECT {op.kind.value}", op.summary)
    return op


def list_pending(session: Session) -> list[PendingOperation]:
    return list(
        session.exec(
            select(PendingOperation).where(PendingOperation.status == OperationStatus.PENDING)
        )
    )


def _execute(
    session: Session,
    op: PendingOperation,
    executor: Callable[[], None],
    *,
    decided_by: str,
) -> PendingOperation:
    try:
        executor()
    except Exception as e:
        op.status = OperationStatus.FAILED
        op.error = str(e)[:2000]
        session.add(op)
        session.commit()
        log_audit(session, decided_by, f"FAIL {op.kind.value}", str(e)[:500])
        raise

    op.status = OperationStatus.EXECUTED
    op.executed_at = utcnow()
    session.add(op)
    session.commit()
    log_audit(session, decided_by, f"EXECUTE {op.kind.value}", op.summary)
    return op
