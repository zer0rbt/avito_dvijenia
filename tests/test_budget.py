from __future__ import annotations

import pytest

from avito.budget import BudgetCheckError, check_budget
from avito.client import AvitoApiError
from core.config import Settings


class _FakeClient:
    def __init__(self, balance: dict):
        self._balance = balance
        self.closed = False

    def get_balance(self, user_id: str) -> dict:
        return self._balance

    def close(self) -> None:
        self.closed = True


class _FailingClient:
    def get_balance(self, user_id: str) -> dict:
        raise AvitoApiError("GET", "/balance", 500, "boom")

    def close(self) -> None:
        pass


def _settings(min_balance_rub: int = 300) -> Settings:
    return Settings(min_balance_rub=min_balance_rub)


def test_check_budget_blocks_publish_below_threshold():
    client = _FakeClient({"real": 0, "bonus": 0})
    status = check_budget(user_id="1", settings=_settings(300), client=client)

    assert status.publish_allowed is False
    assert status.balance_rub == 0
    assert "300" in status.reason


def test_check_budget_allows_publish_above_threshold():
    client = _FakeClient({"real": 900, "bonus": 0})
    status = check_budget(user_id="1", settings=_settings(300), client=client)

    assert status.publish_allowed is True
    assert status.balance_rub == 900
    assert status.reason is None


def test_check_budget_sums_real_and_bonus():
    client = _FakeClient({"real": 200, "bonus": 150})
    status = check_budget(user_id="1", settings=_settings(300), client=client)

    assert status.balance_rub == 350
    assert status.publish_allowed is True


def test_check_budget_raises_on_api_error():
    with pytest.raises(BudgetCheckError):
        check_budget(user_id="1", settings=_settings(300), client=_FailingClient())


def test_check_budget_does_not_close_externally_provided_client():
    client = _FakeClient({"real": 500, "bonus": 0})
    check_budget(user_id="1", settings=_settings(300), client=client)
    assert client.closed is False
