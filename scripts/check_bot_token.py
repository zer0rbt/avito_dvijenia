"""Разовая проверка TG_BOT_TOKEN через getMe — без запуска polling,
без ожидания взаимодействия от оператора."""

import asyncio

from aiogram import Bot

from core.config import get_settings


async def main() -> None:
    settings = get_settings()
    if not settings.tg_bot_token:
        print("TG_BOT_TOKEN не задан")
        return
    bot = Bot(token=settings.tg_bot_token)
    try:
        me = await bot.get_me()
        print(f"OK: @{me.username} (id={me.id}, name={me.first_name})")
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
