from __future__ import annotations

from fastapi.testclient import TestClient

import web.app as web_app_module
from core.models import GeoCity, Listing, ListingState, Product, ProductStatus
from tests.conftest import categories_doc

UNVERIFIED = categories_doc(verified=False)
# Delivery в боевом файле ещё не заполнен, поэтому «полностью готовая» схема
# для теста — это реальная схема с очищенным списком нерешённых полей.
VERIFIED = categories_doc(unresolved_required_fields=[])
UNRESOLVED_FIELD = categories_doc()


def test_health_endpoint():
    client = TestClient(web_app_module.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_feed_xml_returns_503_when_categories_not_verified(monkeypatch):
    monkeypatch.setattr(web_app_module, "load_categories", lambda: UNVERIFIED)
    client = TestClient(web_app_module.app)
    resp = client.get("/feed.xml")
    assert resp.status_code == 503


def test_feed_xml_returns_503_while_required_field_values_unknown(monkeypatch):
    """Схема сверена, но у Delivery нет допустимых значений — наружу такой
    фид не отдаём (см. require_verified)."""
    monkeypatch.setattr(web_app_module, "load_categories", lambda: UNRESOLVED_FIELD)
    client = TestClient(web_app_module.app)
    resp = client.get("/feed.xml")
    assert resp.status_code == 503
    assert "Delivery" in resp.json()["detail"]


def _seed_publishable(session) -> None:
    session.add(
        Product(
            id=1,
            supplier_item_id=1,
            title="Alexander McQueen Худи",
            brand="Alexander McQueen",
            color="Черный",
            sizes_supplier="S,M,L",
            status=ProductStatus.APPROVED,
            avito_category="Худи",
            price_final=2500.0,
        )
    )
    session.add(
        Listing(
            product_id=1,
            city=GeoCity.MSK,
            internal_id="1-MSK-g1",
            state=ListingState.QUEUED,
            title_rendered="Alexander McQueen Худи",
            description_rendered="Описание",
            price_rendered=2500.0,
            photo_urls_rendered="https://cdn.example.com/a.jpg",
        )
    )
    session.commit()


def test_feed_xml_returns_xml_when_schema_fully_resolved(monkeypatch, session):
    # session-фикстура уже подменила core.db.engine; web.app.get_session —
    # тот же объект core.db.get_session, так что дополнительный monkeypatch
    # не нужен, БД внутри запроса будет той же in-memory.
    monkeypatch.setattr(web_app_module, "load_categories", lambda: VERIFIED)
    _seed_publishable(session)

    client = TestClient(web_app_module.app)
    resp = client.get("/feed.xml")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert b"<Id>1-MSK-g1</Id>" in resp.content
    assert "Мужская одежда".encode() in resp.content


def test_media_endpoint_rejects_path_traversal(tmp_path, monkeypatch):
    from core.config import Settings

    settings = Settings(media_store_backend="local", media_store_local_path=tmp_path)
    monkeypatch.setattr(web_app_module, "get_settings", lambda: settings)

    client = TestClient(web_app_module.app)
    resp = client.get("/media/../../etc/passwd")
    assert resp.status_code in (400, 404)


def test_media_endpoint_serves_existing_file(tmp_path, monkeypatch):
    from core.config import Settings

    (tmp_path / "raw").mkdir()
    (tmp_path / "raw" / "photo.jpg").write_bytes(b"fake-jpeg")

    settings = Settings(media_store_backend="local", media_store_local_path=tmp_path)
    monkeypatch.setattr(web_app_module, "get_settings", lambda: settings)

    client = TestClient(web_app_module.app)
    resp = client.get("/media/raw/photo.jpg")
    assert resp.status_code == 200
    assert resp.content == b"fake-jpeg"


def test_media_endpoint_404_for_missing_file(tmp_path, monkeypatch):
    from core.config import Settings

    settings = Settings(media_store_backend="local", media_store_local_path=tmp_path)
    monkeypatch.setattr(web_app_module, "get_settings", lambda: settings)

    client = TestClient(web_app_module.app)
    resp = client.get("/media/nope.jpg")
    assert resp.status_code == 404
