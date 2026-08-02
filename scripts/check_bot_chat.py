"""Разовая проверка: может ли бот писать в TG_OPERATOR_CHAT_ID."""

import asyncio

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from core.config import get_settings


async def main() -> None:
    settings = get_settings()
    bot = Bot(token=settings.tg_bot_token)
    try:
        msg = await bot.send_message(
            settings.tg_operator_chat_id,
            "avito_dvijenia: тестовое сообщение при настройке Э0. "
            "Если видно это — бот подключён к чату верно.",
        )
        print(f"OK: message_id={msg.message_id} chat={msg.chat.id} title={msg.chat.title}")
    except TelegramAPIError as e:
        print(f"FAIL: {e}")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
