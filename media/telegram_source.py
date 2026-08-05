"""Фото из истории TG-канала поставщика через Telethon (B-018).

Зачем, если есть media/fetch.py. Публичное веб-превью `t.me/s/<channel>`
отдаёт последние ~20 постов канала — на живом прогоне из 82 позиций фото
нашлось у одной. Ссылки на посты в прайсе ведут глубоко в историю, и
достать их можно только настоящим клиентом Telegram.

Почему это отдельный модуль, а не ветка в media/fetch.py. Telethon — это
авторизованная сессия реального аккаунта: файл сессии, api_id/api_hash,
интерактивный вход по коду при первом запуске. Веб-превью работает
анонимно и без состояния. Смешивать их в одном модуле — значит тащить
требование авторизации в путь, которому она не нужна.

Что нужно до первого запуска (руками, один раз):
  1. https://my.telegram.org → API development tools → создать приложение,
     получить api_id и api_hash;
  2. вписать в .env: TG_API_ID, TG_API_HASH, TG_SESSION_NAME;
  3. `python -m media.telegram_source login` — Telethon спросит телефон и
     код из Telegram, после чего положит файл сессии в secrets/.
Файл сессии — это доступ к аккаунту. Он лежит в secrets/ (в .gitignore),
в репозиторий не попадает и через api-redirecter не гоняется.

Прод-путь остаётся синхронным (media/pipeline.py), поэтому async-клиент
Telethon прячется за синхронными функциями через asyncio.run().
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from core.config import get_settings

logger = logging.getLogger(__name__)


class TelethonNotConfiguredError(RuntimeError):
    pass


def _require_config() -> tuple[int, str, Path]:
    settings = get_settings()
    if not settings.tg_api_id or not settings.tg_api_hash:
        raise TelethonNotConfiguredError(
            "TG_API_ID / TG_API_HASH не заданы в .env. Получить на "
            "https://my.telegram.org → API development tools, затем "
            "`python -m media.telegram_source login` для входа."
        )
    session_path = settings.tg_session_path
    session_path.parent.mkdir(parents=True, exist_ok=True)
    return int(settings.tg_api_id), settings.tg_api_hash, session_path


def _client():
    """Импорт Telethon внутри функции: пакет нужен только этому пути, и
    без настроенных кредов его вообще незачем требовать при импорте
    media/*, который тянется в CLI на каждой команде."""
    try:
        from telethon import TelegramClient
    except ImportError as e:  # pragma: no cover - зависит от окружения
        raise TelethonNotConfiguredError(
            "Пакет telethon не установлен. `pip install -e .` подтянет его из зависимостей проекта."
        ) from e

    api_id, api_hash, session_path = _require_config()
    return TelegramClient(str(session_path), api_id, api_hash)


def login() -> None:
    """Интерактивный первый вход: телефон + код из Telegram. Делается один
    раз, дальше живёт файл сессии."""

    async def _run() -> None:
        client = _client()
        await client.start()  # спросит телефон/код, если сессии ещё нет
        me = await client.get_me()
        logger.info("Telethon авторизован как %s (id=%s)", me.username, me.id)
        await client.disconnect()

    asyncio.run(_run())


def fetch_post_photo_bytes(post_url: str, *, limit: int = 10) -> list[bytes]:
    """Байты фото конкретного поста. Возвращает [] , если пост не найден или
    без фото — так же, как media/fetch.py, чтобы вызывающий код не различал
    источники.

    Отдаём именно байты, а не URL: у Telegram media-ссылки подписанные и
    временные, качать их потом отдельным httpx-запросом бессмысленно.
    """
    from media.fetch import parse_post_url

    parsed = parse_post_url(post_url)
    if parsed is None:
        return []
    channel, msg_id = parsed

    async def _run() -> list[bytes]:
        client = _client()
        await client.start()
        try:
            message = await client.get_messages(channel, ids=int(msg_id))
            if message is None:
                logger.warning("Пост %s не найден в канале %s", msg_id, channel)
                return []

            # Пост с несколькими фото — это альбом: у сообщений общий
            # grouped_id, а get_messages(ids=...) отдаёт только одно из них.
            messages = [message]
            if getattr(message, "grouped_id", None):
                around = await client.get_messages(
                    channel,
                    limit=limit,
                    ids=None,
                    min_id=int(msg_id) - limit,
                    max_id=int(msg_id) + limit,
                )
                messages = [
                    m for m in around if getattr(m, "grouped_id", None) == message.grouped_id
                ] or [message]

            out: list[bytes] = []
            for m in messages:
                if m.photo is None:
                    continue
                data = await client.download_media(m, file=bytes)
                if data:
                    out.append(data)
            return out
        finally:
            await client.disconnect()

    return asyncio.run(_run())


if __name__ == "__main__":  # pragma: no cover - ручной вход
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) > 1 and sys.argv[1] == "login":
        login()
    else:
        print("Использование: python -m media.telegram_source login")
