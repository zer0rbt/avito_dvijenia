"""Точка входа Telegram-бота. Требует TG_BOT_TOKEN и TG_OPERATOR_CHAT_ID в .env:
создать бота через @BotFather, затем написать ему что угодно и выполнить
/whoami — бот ответит chat_id (эта команда работает без проверки оператора,
она для первичной настройки).

Запуск: `python -m bot.main` (внутри активированного venv).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher

from bot.handlers import router
from core.config import get_settings
from core.db import init_db


async def _run() -> None:
    settings = get_settings()
    if not settings.tg_bot_token:
        raise SystemExit(
            "TG_BOT_TOKEN не задан в .env. Создать бота через @BotFather и "
            "вписать токен перед запуском."
        )
    if not settings.tg_operator_chat_id:
        logging.warning(
            "TG_OPERATOR_CHAT_ID не задан — бот отвечает всем отказом. "
            "Напишите боту /start, chat_id придёт в логах ниже, впишите его в .env."
        )

    init_db()

    logging.basicConfig(level=logging.INFO)

    bot = Bot(token=settings.tg_bot_token)
    dp = Dispatcher()
    dp.include_router(router)
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
