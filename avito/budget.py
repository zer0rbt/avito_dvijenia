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
    """wallet_rub и advance_rub — РАЗНЫЕ деньги, и путать их дорого.

    wallet_rub — кошелёк аккаунта из `/core/v1/accounts/{id}/balance/`.
    advance_rub — аванс, с которого списываются просмотры; API его не отдаёт,
    значение ведёт оператор через ADVANCE_RUB (см. B-003).
    Решение о публикации принимается по advance_rub.
    """

    wallet_rub: float
    advance_rub: float | None
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

    wallet_rub = float(balance.get("real", 0) or 0) + float(balance.get("bonus", 0) or 0)

    # B-003 закрыт по факту: заказчик подтвердил, что кошелёк действительно 0,
    # а аванс за просмотры (~900 ₽) живёт отдельно и через этот эндпоинт не
    # виден. Значит сверять порог с wallet_rub бессмысленно: он всегда 0 и
    # всегда заблокирует публикацию.
    #
    # Подтверждённого эндпоинта под аванс у нас нет, поэтому источник правды —
    # то, что оператор увидел в ЛК и вписал в ADVANCE_RUB. Пока значение не
    # выставлено, публикация заблокирована: это безопасная сторона ошибки.
    if settings.advance_rub is None:
        return BudgetStatus(
            wallet_rub=wallet_rub,
            advance_rub=None,
            min_balance_rub=settings.min_balance_rub,
            publish_allowed=False,
            reason=(
                f"кошелёк {wallet_rub:.0f} ₽; аванс за просмотры этот эндпоинт не "
                "показывает, а ADVANCE_RUB в .env не задан — публиковать вслепую "
                "нельзя. Посмотреть остаток аванса в ЛК и вписать ADVANCE_RUB."
            ),
        )

    if settings.advance_rub < settings.min_balance_rub:
        return BudgetStatus(
            wallet_rub=wallet_rub,
            advance_rub=settings.advance_rub,
            min_balance_rub=settings.min_balance_rub,
            publish_allowed=False,
            reason=(f"аванс {settings.advance_rub:.0f} ₽ ниже порога {settings.min_balance_rub} ₽"),
        )

    return BudgetStatus(
        wallet_rub=wallet_rub,
        advance_rub=settings.advance_rub,
        min_balance_rub=settings.min_balance_rub,
        publish_allowed=True,
    )
