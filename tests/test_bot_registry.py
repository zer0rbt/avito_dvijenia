from __future__ import annotations

import pytest

from bot.registry import build_executor, register
from core.models import OperationKind


def test_unregistered_kind_raises_not_implemented():
    executor = build_executor(OperationKind.PUBLISH, [1, 2])
    with pytest.raises(NotImplementedError):
        executor()


def test_registered_factory_is_used():
    calls = []
    register(OperationKind.WIPE, lambda ids: lambda: calls.append(ids))

    executor = build_executor(OperationKind.WIPE, [3, 4])
    executor()

    assert calls == [[3, 4]]
