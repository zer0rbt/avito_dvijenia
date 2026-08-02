"""Скачивание исходных фото товара: прямые ссылки (когда таблица их даёт)
и посты Telegram-канала поставщика (t.me/s/<channel> — публичное
веб-превью, фото без Telegram-аккаунта, см. план "Что проверено фактически").

Ретраи скопированы с sources/gsheets.py: то же самое сетевое окружение
WSL (B-013 в BACKLOG), тот же паттерн — 3 попытки с бэкоффом вместо падения
всего синка на одном сбое.
"""

from __future__ import annotations

import re
import time

import httpx
from selectolax.parser import HTMLParser

_POST_URL_RE = re.compile(r"t\.me/(?P<channel>[^/]+)/(?P<msg_id>\d+)")
_BG_IMAGE_RE = re.compile(r"background-image:url\('(.+?)'\)")

DEFAULT_TIMEOUT = 20.0
DEFAULT_RETRIES = 3
USER_AGENT = "Mozilla/5.0"


def parse_post_url(post_url: str) -> tuple[str, str] | None:
    """ "https://t.me/channel/123" -> ("channel", "123"); None, если не похоже
    на ссылку на пост TG (нормализатор источника мог отдать что угодно)."""
    m = _POST_URL_RE.search(post_url)
    if not m:
        return None
    return m.group("channel"), m.group("msg_id")


def fetch_post_photo_urls(
    post_url: str, *, timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES
) -> list[str]:
    """Фото конкретного поста через публичное веб-превью канала.

    Превью t.me/s/<channel> отдаёт одной страницей только последние ~20
    постов канала. Если пост из post_url уже вышел за это окно — вернёт
    пустой список молча (не ошибка, а исчерпание источника; см. BACKLOG
    B-018 — источник фото деградирует со временем, не проверено на живом
    канале, к чему на практике приводит этот лимит).

    Фото в превью зашиты в background-image инлайн-стиля <a>-обёртки, не в
    <img src> — обычная разметка t.me/s/, не догадка.
    """
    parsed = parse_post_url(post_url)
    if parsed is None:
        return []
    channel, msg_id = parsed
    html = _fetch_channel_preview(channel, timeout=timeout, retries=retries)
    return _extract_post_photo_urls(html, channel=channel, msg_id=msg_id)


def _extract_post_photo_urls(html: str, *, channel: str, msg_id: str) -> list[str]:
    tree = HTMLParser(html)
    data_post = f"{channel}/{msg_id}"

    urls: list[str] = []
    for wrap in tree.css("div.tgme_widget_message"):
        if wrap.attributes.get("data-post") != data_post:
            continue
        for photo in wrap.css("a.tgme_widget_message_photo_wrap"):
            style = photo.attributes.get("style", "") or ""
            m = _BG_IMAGE_RE.search(style)
            if m:
                urls.append(m.group(1))
    return urls


def _fetch_channel_preview(channel: str, *, timeout: float, retries: int) -> str:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.get(
                f"https://t.me/s/{channel}",
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            return resp.text
        except httpx.HTTPError as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error  # type: ignore[misc]


def fetch_photo_bytes(
    url: str, *, timeout: float = DEFAULT_TIMEOUT, retries: int = DEFAULT_RETRIES
) -> bytes:
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.get(
                url, timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}
            )
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPError as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error  # type: ignore[misc]
