"""Централизованная конфигурация. Всё читается из .env / переменных окружения.

Один и тот же Settings работает и локально, и на VPS — разница только
в значениях APP_PROFILE / PUBLIC_BASE_URL / MEDIA_STORE_BACKEND.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- Avito API ---
    avito_client_id: str = ""
    avito_client_secret: str = ""
    avito_user_id: str = ""  # резолвится через /core/v1/accounts/self, если пусто

    # --- Профиль запуска ---
    app_profile: str = "local"  # local | vps

    # --- БД ---
    database_url: str = f"sqlite:///{BASE_DIR / 'data' / 'avito_dvijenia.db'}"

    # --- Медиа ---
    media_store_backend: str = "local"  # local | s3
    media_store_local_path: Path = BASE_DIR / "media_store"
    media_store_public_base_url: str = ""

    s3_endpoint_url: str = ""
    s3_bucket: str = ""
    s3_access_key: str = ""
    s3_secret_key: str = ""
    s3_region: str = ""

    # --- Публичный URL для фида и медиа (Cloudflare Tunnel / домен VPS) ---
    public_base_url: str = ""

    # --- Telegram-бот управления ---
    tg_bot_token: str = ""
    tg_operator_chat_id: str = ""

    # --- Google Sheets ---
    google_service_account_json: str = ""
    admin_sheet_id: str = ""

    # --- Режим оператора / предохранители ---
    dry_run_default: bool = True
    min_balance_rub: int = Field(default=300, ge=0)
    max_active_listings: int = Field(default=100, ge=1)

    @property
    def feed_url(self) -> str:
        base = self.public_base_url.rstrip("/")
        return f"{base}/feed.xml" if base else ""

    @property
    def is_configured_for_avito(self) -> bool:
        return bool(self.avito_client_id and self.avito_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
