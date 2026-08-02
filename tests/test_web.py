from __future__ import annotations

from fastapi.testclient import TestClient

import web.app as web_app_module
from avito.categories import CategoriesDoc
from core.models import GeoCity, Listing, ListingState, Product, ProductStatus

UNVERIFIED = CategoriesDoc(
    verified=False,
    verified_at=None,
    source_note="черновик",
    category_path="x",
    common_fields={},
    goods_types=[],
    open_questions=[],
)

VERIFIED = CategoriesDoc(
    verified=True,
    verified_at="2026-08-02",
    source_note="test",
    category_path="x",
    common_fields={"Category": {"required": True, "value": "Личные вещи"}},
    goods_types=[
        {
            "key": "mens_outerwear",
            "label_ru": "x",
            "avito_goods_type": "Мужская одежда",
            "extra_fields": {},
        }
    ],
    open_questions=[],
)


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


def test_feed_xml_returns_xml_when_categories_verified(monkeypatch, session):
    # session-фикстура уже подменила core.db.engine; web.app.get_session —
    # тот же объект core.db.get_session, так что дополнительный monkeypatch
    # не нужен, БД внутри запроса будет той же in-memory.
    monkeypatch.setattr(web_app_module, "load_categories", lambda: VERIFIED)

    product = Product(
        id=1,
        supplier_item_id=1,
        title="Товар",
        status=ProductStatus.APPROVED,
        avito_category="mens_outerwear",
        price_final=2500.0,
    )
    session.add(product)
    listing = Listing(
        product_id=1,
        city=GeoCity.MSK,
        internal_id="1-MSK-g1",
        state=ListingState.QUEUED,
        title_rendered="Товар",
        description_rendered="Описание",
        price_rendered=2500.0,
        photo_urls_rendered="https://cdn.example.com/a.jpg",
    )
    session.add(listing)
    session.commit()

    client = TestClient(web_app_module.app)
    resp = client.get("/feed.xml")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/xml")
    assert b"<Id>1-MSK-g1</Id>" in resp.content


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
