"""Хендлеры Telegram-бота. Единственный оператор — TG_OPERATOR_CHAT_ID
из .env; любой другой chat_id получает отказ и ничего больше (бот
управляет боевым аккаунтом и деньгами, посторонним тут делать нечего).
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from avito.client import AvitoApiError, AvitoClient
from bot.registry import build_executor
from core.approval import confirm_and_execute, list_pending, reject_operation
from core.config import get_settings
from core.db import get_session

router = Router()


def _is_operator(message_or_callback) -> bool:
    settings = get_settings()
    if not settings.tg_operator_chat_id:
        # оператор ещё не настроен в .env — по умолчанию отказываем всем,
        # чтобы бот не оказался открыт для первого встречного
        return False
    chat = (
        message_or_callback.chat
        if isinstance(message_or_callback, Message)
        else message_or_callback.message.chat
    )
    return str(chat.id) == str(settings.tg_operator_chat_id)


@router.message(Command("whoami"))
async def cmd_whoami(message: Message) -> None:
    """Без проверки _is_operator — единственный способ узнать свой chat_id
    и вписать его в TG_OPERATOR_CHAT_ID при первой настройке."""
    await message.answer(f"chat_id: {message.chat.id}")


@router.message(Command("start", "help"))
async def cmd_start(message: Message) -> None:
    if not _is_operator(message):
        await message.answer(
            "Доступ только для оператора. Если это ты — /whoami покажет "
            "chat_id, впиши его в TG_OPERATOR_CHAT_ID в .env."
        )
        return
    await message.answer(
        "avito_dvijenia — управление автоматизацией.\n\n"
        "/pending — операции, ждущие подтверждения\n"
        "/balance — текущий баланс/аванс Авито\n"
        "/queue — очередь модерации товаров (появится в Э2)"
    )


@router.message(Command("balance"))
async def cmd_balance(message: Message) -> None:
    if not _is_operator(message):
        return
    settings = get_settings()
    if not settings.avito_user_id:
        await message.answer("AVITO_USER_ID не задан в .env.")
        return
    try:
        with AvitoClient() as client:
            balance = client.get_balance(settings.avito_user_id)
    except AvitoApiError as e:
        await message.answer(f"Не удалось получить баланс: {e}")
        return
    await message.answer(f"Баланс: {balance}")


@router.message(Command("queue"))
async def cmd_queue(message: Message) -> None:
    if not _is_operator(message):
        return
    await message.answer(
        "Очередь модерации товаров ещё не реализована (план, этап Э2). "
        "Сейчас доступны только операции над уже существующими Listing "
        "через /pending."
    )


@router.message(Command("pending"))
async def cmd_pending(message: Message) -> None:
    if not _is_operator(message):
        return
    with get_session() as session:
        ops = list_pending(session)

    if not ops:
        await message.answer("Нет операций, ждущих подтверждения.")
        return

    for op in ops:
        kb = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm:{op.id}"),
                    InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{op.id}"),
                ]
            ]
        )
        await message.answer(
            f"#{op.id} [{op.kind.value}]\n{op.summary}\n"
            f"listings: {op.listing_ids}\nзапрошено: {op.requested_at}",
            reply_markup=kb,
        )


@router.callback_query(F.data.startswith("confirm:"))
async def on_confirm(callback: CallbackQuery) -> None:
    if not _is_operator(callback):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    op_id = int(callback.data.split(":", 1)[1])
    with get_session() as session:
        from core.models import PendingOperation

        op = session.get(PendingOperation, op_id)
        if op is None:
            await callback.answer("Операция не найдена", show_alert=True)
            return
        listing_ids = [int(x) for x in op.listing_ids.split(",") if x]
        executor = build_executor(op.kind, listing_ids)
        try:
            confirm_and_execute(session, op_id, executor, decided_by=str(callback.from_user.id))
            await callback.message.edit_text(
                callback.message.text + "\n\n✅ ПОДТВЕРЖДЕНО И ИСПОЛНЕНО"
            )
        except NotImplementedError as e:
            await callback.message.edit_text(callback.message.text + f"\n\n⚠️ {e}")
        except Exception as e:
            await callback.message.edit_text(callback.message.text + f"\n\n❌ ОШИБКА: {e}")
    await callback.answer()


@router.callback_query(F.data.startswith("reject:"))
async def on_reject(callback: CallbackQuery) -> None:
    if not _is_operator(callback):
        await callback.answer("Доступ запрещён", show_alert=True)
        return
    op_id = int(callback.data.split(":", 1)[1])
    with get_session() as session:
        reject_operation(session, op_id, decided_by=str(callback.from_user.id))
    await callback.message.edit_text(callback.message.text + "\n\n❌ ОТКЛОНЕНО")
    await callback.answer()
