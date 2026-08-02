"""Проверка аванса перед публикацией (план, "Два ограничителя..." —
оплата за просмотры, аванс конечен, одна залетевшая карточка способна
выжечь его за часы).

БЛОКИРУЕТ только публикацию новых карточек. Затирка и архивация НЕ
блокируются — они бюджет не тратят, а экономят (план, "Режим оператора").
Это разделение — забота вызывающего кода (lifecycle/planner.py считает
только PUBLISH), не этого модуля.
"""

from __future__ import annotations

from dataclasses import dataclass

from avito.client import AvitoApiError, AvitoClient
from core.config import Settings, get_settings


class BudgetCheckError(RuntimeError):
    pass


@dataclass
class BudgetStatus:
    balance_rub: float
    min_balance_rub: int
    publish_allowed: bool
    reason: str | None = None


def check_budget(
    *,
    user_id: str,
    settings: Settings | None = None,
    client: AvitoClient | None = None,
) -> BudgetStatus:
    settings = settings or get_settings()
    owns_client = client is None
    client = client or AvitoClient()
    try:
        balance = client.get_balance(user_id)
    except AvitoApiError as e:
        raise BudgetCheckError(f"не удалось получить баланс: {e}") from e
    finally:
        if owns_client:
            client.close()

    # B-003: с этого эндпоинта на реальном аккаунте оба поля отдают 0 —
    # складываем оба, чтобы не потерять деньги, если это окажется вопросом
    # формата, а не факта отсутствия средств.
    balance_rub = float(balance.get("real", 0) or 0) + float(balance.get("bonus", 0) or 0)

    if balance_rub < settings.min_balance_rub:
        return BudgetStatus(
            balance_rub=balance_rub,
            min_balance_rub=settings.min_balance_rub,
            publish_allowed=False,
            reason=f"баланс {balance_rub:.0f} ₽ ниже порога {settings.min_balance_rub} ₽",
        )

    return BudgetStatus(
        balance_rub=balance_rub, min_balance_rub=settings.min_balance_rub, publish_allowed=True
    )
