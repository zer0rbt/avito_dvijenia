"""OAuth client_credentials против api.avito.ru.

Базовый URL `https://api.avito.ru/`, токен — `POST /token/`,
form-urlencoded (grant_type/client_id/client_secret). Проверено вживую
против реального аккаунта 2026-08-02: GET на этот путь отдаёт 404, POST —
200 с access_token. Сторонние источники (covox/avito_api и др.) указывали
GET — не доверяем таким расхождениям вслепую, отсюда и cli.py check-access,
который бьётся о реальный API и фиксирует правду в docs/api_notes.md.
"""

from __future__ import annotations

import time

import httpx

from core.config import get_settings

TOKEN_URL = "https://api.avito.ru/token/"


class AvitoAuthError(RuntimeError):
    pass


class TokenCache:
    """Простой in-memory кеш токена с запасом по времени истечения."""

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get(self) -> str | None:
        if self._token and time.monotonic() < self._expires_at:
            return self._token
        return None

    def set(self, token: str, expires_in: int) -> None:
        self._token = token
        # запас в 60 секунд, чтобы не словить протухание токена в середине запроса
        self._expires_at = time.monotonic() + max(expires_in - 60, 30)


_cache = TokenCache()


def fetch_access_token(client: httpx.Client | None = None) -> str:
    """Получить (и закешировать) access_token по client_credentials."""
    cached = _cache.get()
    if cached:
        return cached

    settings = get_settings()
    if not settings.is_configured_for_avito:
        raise AvitoAuthError(
            "AVITO_CLIENT_ID / AVITO_CLIENT_SECRET не заданы в .env"
        )

    params = {
        "grant_type": "client_credentials",
        "client_id": settings.avito_client_id,
        "client_secret": settings.avito_client_secret,
    }

    owns_client = client is None
    http_client = client or httpx.Client(timeout=15)
    try:
        resp = http_client.post(TOKEN_URL, data=params)
        if resp.status_code in (404, 405):
            # на случай, если Авито поменяет поведение — подстраховка обратной формой
            resp = http_client.get(TOKEN_URL, params=params)
    finally:
        if owns_client:
            http_client.close()

    if resp.status_code != 200:
        raise AvitoAuthError(
            f"Не удалось получить токен: HTTP {resp.status_code} {resp.text[:300]}"
        )

    data = resp.json()
    token = data.get("access_token")
    expires_in = int(data.get("expires_in", 86400))
    if not token:
        raise AvitoAuthError(f"В ответе нет access_token: {data}")

    _cache.set(token, expires_in)
    return token
