"""Хранилище медиа-файлов: сейчас диск, потом S3 — переключается
`media_store_backend` в .env без правки вызывающего кода (media/pipeline.py,
avito/feed.py на Э5 знают только про интерфейс MediaStore).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Protocol

from core.config import get_settings


class MediaStore(Protocol):
    def save(self, key: str, data: bytes) -> str:
        """Сохранить данные под key, вернуть публичный URL."""
        ...

    def load(self, key: str) -> bytes: ...

    def exists(self, key: str) -> bool: ...

    def public_url(self, key: str) -> str: ...


class LocalFSStore:
    """Бэкенд по умолчанию: файлы на диске под media_store_local_path.

    Публичный URL строится из media_store_public_base_url (домен туннеля/VPS,
    см. план "Фид и медиа отдаёт FastAPI"); пока он не настроен — отдаём
    file://-путь, этого достаточно для тестов и локальной проверки глазами.
    """

    def __init__(self, root: Path, public_base_url: str = ""):
        self.root = root.resolve()
        self.public_base_url = public_base_url.rstrip("/")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise ValueError(f"key выходит за пределы media_store: {key!r}")
        return path

    def save(self, key: str, data: bytes) -> str:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return self.public_url(key)

    def load(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).exists()

    def public_url(self, key: str) -> str:
        if not self.public_base_url:
            return f"file://{self._path(key)}"
        return f"{self.public_base_url}/{key}"


class S3Store:
    """Заглушка под будущий переезд на VPS (Э10).

    core/config.py уже держит s3_* настройки, но реализацию поднимать
    сейчас смысла нет — boto3 в зависимостях нет, а формат клиента (boto3
    против S3-совместимого httpx) решится по факту переезда. Явный отказ
    вместо тихой заглушки — тот же приём, что в avito/categories.py.
    """

    def __init__(self, *_args, **_kwargs) -> None:
        raise NotImplementedError(
            "S3-бэкенд не реализован (см. docs/BACKLOG.md). "
            "Использовать media_store_backend=local до переезда на VPS (Э10)."
        )


def get_media_store() -> MediaStore:
    settings = get_settings()
    if settings.media_store_backend == "local":
        return LocalFSStore(settings.media_store_local_path, settings.media_store_public_base_url)
    if settings.media_store_backend == "s3":
        return S3Store()
    raise ValueError(f"Неизвестный media_store_backend: {settings.media_store_backend!r}")


def content_key(data: bytes, *, prefix: str, ext: str = "jpg") -> str:
    """Ключ по хэшу содержимого — одинаковые байты не сохраняются дважды
    и не задваивают запись в реестре MediaAsset при повторном синке."""
    digest = hashlib.sha256(data).hexdigest()[:24]
    return f"{prefix}/{digest}.{ext}"
