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


def _settings(**kwargs) -> Settings:
    defaults = dict(min_balance_rub=300, advance_rub=None)
    defaults.update(kwargs)
    return Settings(**defaults)


ZERO_WALLET = {"real": 0, "bonus": 0}


def test_blocks_when_advance_is_unknown():
    """Главный случай на этом аккаунте: кошелёк 0, аванс API не отдаёт.
    Не зная аванса, публиковать нельзя (B-003)."""
    status = check_budget(user_id="1", settings=_settings(), client=_FakeClient(ZERO_WALLET))

    assert status.publish_allowed is False
    assert status.advance_rub is None
    assert "ADVANCE_RUB" in status.reason


def test_zero_wallet_does_not_block_when_advance_is_sufficient():
    """Кошелёк и аванс — разные деньги: нулевой кошелёк сам по себе не повод
    блокировать, если оператор указал остаток аванса."""
    status = check_budget(
        user_id="1", settings=_settings(advance_rub=900), client=_FakeClient(ZERO_WALLET)
    )

    assert status.publish_allowed is True
    assert status.wallet_rub == 0
    assert status.advance_rub == 900


def test_blocks_when_advance_below_threshold():
    status = check_budget(
        user_id="1",
        settings=_settings(advance_rub=100, min_balance_rub=300),
        client=_FakeClient(ZERO_WALLET),
    )

    assert status.publish_allowed is False
    assert "100" in status.reason and "300" in status.reason


def test_wallet_sums_real_and_bonus_for_reporting():
    status = check_budget(
        user_id="1",
        settings=_settings(advance_rub=900),
        client=_FakeClient({"real": 200, "bonus": 150}),
    )
    assert status.wallet_rub == 350


def test_raises_on_api_error():
    with pytest.raises(BudgetCheckError):
        check_budget(user_id="1", settings=_settings(), client=_FailingClient())


def test_does_not_close_externally_provided_client():
    client = _FakeClient(ZERO_WALLET)
    check_budget(user_id="1", settings=_settings(advance_rub=900), client=client)
    assert client.closed is False
