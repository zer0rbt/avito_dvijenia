from __future__ import annotations

import pytest

from bot.registry import build_executor, register
from core.models import OperationKind


def test_unregistered_kind_raises_not_implemented():
    # ARCHIVE — до Э7 намеренно без исполнителя. PUBLISH теперь регистрирует
    # lifecycle/publish.py (Э5), больше не годится как пример "пусто".
    executor = build_executor(OperationKind.ARCHIVE, [1, 2])
    with pytest.raises(NotImplementedError):
        executor()


def test_registered_factory_is_used():
    calls = []
    register(OperationKind.WIPE, lambda ids: lambda: calls.append(ids))

    executor = build_executor(OperationKind.WIPE, [3, 4])
    executor()

    assert calls == [[3, 4]]
