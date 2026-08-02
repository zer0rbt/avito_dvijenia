"""FastAPI: отдаёт фид Автозагрузке и медиа-файлы (план, "Фид и медиа
отдаёт FastAPI, не файловая система" — переезд на VPS = смена домена в
настройке профиля Автозагрузки, код не трогаем).

/feed.xml требует avito/categories.py verified: true — отдавать реальному
Авито черновичную непроверенную схему полей нельзя (см. avito/feed.py).
Локально/в dry-run проверка XML идёт через `cli.py feed build`, который
этот рубильник сознательно обходит (см. его докстринг).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from sqlmodel import select

from avito.categories import CategoriesNotVerifiedError, load_categories
from avito.feed import build_feed_xml
from core.config import get_settings
from core.db import get_session
from core.models import Listing, ListingState, Product

app = FastAPI(title="avito_dvijenia")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/feed.xml")
def feed_xml() -> Response:
    categories = load_categories()
    try:
        categories.require_verified()
    except CategoriesNotVerifiedError as e:
        # 503, не 500: это ожидаемое временное состояние ("ещё не сверено
        # с ЛК"), а не поломка сервиса.
        raise HTTPException(status_code=503, detail=str(e)) from e

    with get_session() as session:
        listings = list(
            session.exec(
                select(Listing).where(
                    Listing.state.in_([ListingState.QUEUED, ListingState.PUBLISHED])
                )
            )
        )
        products_by_id = {p.id: p for p in session.exec(select(Product))}

    result = build_feed_xml(listings, products_by_id, categories=categories)
    return Response(content=result.xml, media_type="application/xml")


@app.get("/media/{path:path}")
def media(path: str) -> FileResponse:
    settings = get_settings()
    if settings.media_store_backend != "local":
        raise HTTPException(
            status_code=501, detail="Раздача медиа настроена только для media_store_backend=local"
        )

    root = settings.media_store_local_path.resolve()
    full_path = (root / path).resolve()
    if full_path != root and root not in full_path.parents:
        raise HTTPException(status_code=400, detail="некорректный путь")
    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="файл не найден")
    return FileResponse(full_path)
