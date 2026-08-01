"""Регистр исполнителей операций для core.approval.

PendingOperation в БД хранит только kind + CSV listing_ids — функцию-исполнитель
(`executor: Callable[[], None]`) нельзя сериализовать в БД, поэтому вместо
этого модули жизненного цикла (Э5 avito/feed.py, Э7 lifecycle/wiper.py)
регистрируют здесь фабрику: OperationKind -> (list[int] -> Callable[[], None]).

Бот при подтверждении операции достаёт listing_ids из PendingOperation,
восстанавливает executor через эту фабрику и передаёт его в
core.approval.confirm_and_execute().

Пока Э5/Э7 не реализованы, зарегистрированных фабрик нет — попытка
подтвердить операцию честно падает NotImplementedError с понятным текстом,
а не тихо делает вид, что что-то произошло.
"""

from __future__ import annotations

from typing import Callable

from core.models import OperationKind

ExecutorFactory = Callable[[list[int]], Callable[[], None]]

_registry: dict[OperationKind, ExecutorFactory] = {}


def register(kind: OperationKind, factory: ExecutorFactory) -> None:
    _registry[kind] = factory


def build_executor(kind: OperationKind, listing_ids: list[int]) -> Callable[[], None]:
    factory = _registry.get(kind)
    if factory is None:
        def _not_implemented() -> None:
            raise NotImplementedError(
                f"Для операции {kind.value} ещё не зарегистрирован исполнитель "
                f"(bot/registry.py). Модуль, который должен это сделать, ещё "
                f"не реализован по плану."
            )

        return _not_implemented
    return factory(listing_ids)
