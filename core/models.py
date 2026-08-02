"""Схема БД. SQLite сейчас, полями и типами совместима с Postgres при переезде.

Модели соответствуют доменным сущностям из плана:
SupplierItem -> Product/Variant -> Listing (с гео-копиями) -> StatsDaily.
Плюс сквозные механизмы: очередь модерации (Э2) и режим оператора (core/approval.py).
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(UTC)


# ---------------------------------------------------------------------------
# Источники (Э1)
# ---------------------------------------------------------------------------


class SupplierItem(SQLModel, table=True):
    """Сырая строка от поставщика, как она пришла из источника (Э1).

    Один SupplierItem -> после нормализации -> один или несколько Product
    (продукт = товар x цвет).
    """

    id: int | None = Field(default=None, primary_key=True)
    source_key: str = Field(index=True)  # напр. "gsheets:1OLvi...:row42"
    source_type: str  # gsheets | website | telegram
    raw_title: str
    brand: str | None = None
    goods_type: str | None = None  # обувь | верхняя одежда
    color: str | None = None
    sizes_available: str = ""  # CSV сырых размеров поставщика, напр. "S,M,L"
    price_purchase: float | None = None
    price_rrc: float | None = None
    photo_urls: str = ""  # CSV ссылок на исходные фото (посты TG / таблица)
    ship_city: str | None = None
    post_url: str | None = None

    first_seen_at: datetime = Field(default_factory=utcnow)
    last_seen_at: datetime = Field(default_factory=utcnow)
    is_available: bool = True  # снят флаг -> reconcile.py помечает пропажу


# ---------------------------------------------------------------------------
# Товары и варианты (Э2-Э4)
# ---------------------------------------------------------------------------


class ProductStatus(enum.StrEnum):
    NEW = "NEW"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    APPROVED = "APPROVED"
    QUEUED = "QUEUED"
    PUBLISHED = "PUBLISHED"
    REJECTED = "REJECTED"
    HOLD = "HOLD"


class Product(SQLModel, table=True):
    """Товар x цвет — единица принятия решения в очереди модерации.

    Из одного Product на публикации получается до 5 Listing (по одному
    на гео-копию), см. content/geo.py.
    """

    id: int | None = Field(default=None, primary_key=True)
    supplier_item_id: int | None = Field(default=None, foreign_key="supplieritem.id")

    title: str  # "Бренд Модель", напр. "Balenciaga Arena"
    # brand и goods_type — Optional намеренно: у реальных данных (Э1) 47 из 82
    # товаров без опознанного бренда, а goods_type не проставляет вообще ни
    # один источник (см. docs/BACKLOG.md B-010, B-011). Отсутствие значения —
    # ровно то, что должна поймать очередь модерации, а не NOT NULL на уровне
    # схемы, который просто уронит вставку.
    brand: str | None = None
    goods_type: str | None = None  # обувь | верхняя одежда
    avito_category: str | None = None  # значение из avito/categories.py
    # Optional по той же причине: best_dropship_hoodies вообще не хранит цвет
    # отдельным полем (51 из 82 товаров) — не гадать, оставлять пустым.
    color: str | None = None
    sizes_supplier: str = ""  # CSV сырых размеров
    sizes_avito: str = ""  # CSV размеров после sizes.py-маппинга

    price_purchase: float | None = None
    price_rrc: float | None = None
    price_final: float | None = None  # pricing.py: РРЦ+1500 либо закупка+1500

    status: ProductStatus = Field(default=ProductStatus.NEW, index=True)
    review_reason: str | None = None  # почему ушёл в NEEDS_REVIEW
    demand_score: float | None = None  # из "Аналитика спроса"

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class GeoCity(enum.StrEnum):
    MSK = "MSK"
    SPB = "SPB"
    EKB = "EKB"
    KRD = "KRD"
    KRSK = "KRSK"


# Соответствие GeoCity -> адрес/ID локации Авито, см. план "Адреса для гео-копий".
GEO_ADDRESSES: dict[GeoCity, dict[str, str]] = {
    GeoCity.MSK: {"city": "Москва", "address": "Тверская ул., 1", "location_id": "100974375"},
    GeoCity.SPB: {
        "city": "Санкт-Петербург",
        "address": "Морская наб., 15",
        "location_id": "101182505",
    },
    GeoCity.EKB: {"city": "Екатеринбург", "address": "", "location_id": "101182553"},
    GeoCity.KRD: {"city": "Краснодар", "address": "495", "location_id": "101182449"},
    GeoCity.KRSK: {
        "city": "Красноярск",
        "address": "Капитанская ул., 6",
        "location_id": "101174693",
    },
}


# ---------------------------------------------------------------------------
# Медиа (Э3)
# ---------------------------------------------------------------------------


class MediaAssetKind(enum.StrEnum):
    RAW = "RAW"  # как скачано из поста TG / прямой ссылки, без обработки
    VARIATE = "VARIATE"  # мягкая уникализация под публикацию/перезалив
    DESTROY = "DESTROY"  # затирочное фото под WIPE_APPLIED


class MediaAsset(SQLModel, table=True):
    """Одно сохранённое изображение под конкретный SupplierItem.

    storage_key — ключ в MediaStore (media/store.py), не сам файл: файл
    лежит на диске/в S3, здесь только реестр и pHash для поиска дублей
    (media/phash.py). RAW на source_url уникален по content_key — повторный
    прогон синка не скачивает и не сохраняет уже известное фото дважды.
    """

    id: int | None = Field(default=None, primary_key=True)
    supplier_item_id: int = Field(foreign_key="supplieritem.id", index=True)
    kind: MediaAssetKind = Field(default=MediaAssetKind.RAW, index=True)

    source_url: str | None = None  # для RAW — откуда скачано; для VARIATE/DESTROY — пусто
    derived_from_id: int | None = Field(default=None, foreign_key="mediaasset.id")

    storage_key: str = Field(index=True)
    public_url: str = ""
    phash: str = ""

    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Карточки на Авито (Э4-Э7)
# ---------------------------------------------------------------------------


class ListingState(enum.StrEnum):
    DRAFT = "DRAFT"
    QUEUED = "QUEUED"
    PUBLISHED = "PUBLISHED"
    WIPE_PENDING = "WIPE_PENDING"
    WIPE_APPLIED = "WIPE_APPLIED"
    ARCHIVED = "ARCHIVED"
    REISSUED = "REISSUED"


class Listing(SQLModel, table=True):
    """Одна карточка в фиде Автозагрузки: товар x цвет x город.

    internal_id — то, что уходит в тег <Id> фида. Перезалив ВСЕГДА получает
    новый internal_id (см. план, раздел "Ключевые решения").
    """

    id: int | None = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    city: GeoCity

    internal_id: str = Field(index=True, unique=True)  # тег <Id> в XML
    avito_id: str | None = Field(default=None, index=True)  # AvitoId после публикации

    state: ListingState = Field(default=ListingState.DRAFT, index=True)
    generation: int = Field(default=1)  # 1 = первый залив, 2+ = перезалив N-й раз

    title_rendered: str | None = None
    description_rendered: str | None = None
    price_rendered: float | None = None
    photo_urls_rendered: str = ""  # CSV, финальные публичные URL под MediaStore

    published_at: datetime | None = None
    wipe_applied_at: datetime | None = None
    archived_at: datetime | None = None

    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)


class StatsDaily(SQLModel, table=True):
    """Дневная стата по карточке (Э6), вход для decay.py."""

    id: int | None = Field(default=None, primary_key=True)
    listing_id: int = Field(foreign_key="listing.id", index=True)
    date: datetime  # хранится как полночь дня, для простоты группировки

    views: int = 0
    contacts: int = 0
    favorites: int = 0
    spend_rub: float = 0.0

    created_at: datetime = Field(default_factory=utcnow)


# ---------------------------------------------------------------------------
# Режим оператора (core/approval.py) и аудит
# ---------------------------------------------------------------------------


class OperationKind(enum.StrEnum):
    PUBLISH = "PUBLISH"
    WIPE = "WIPE"
    ARCHIVE = "ARCHIVE"
    REISSUE = "REISSUE"


class OperationStatus(enum.StrEnum):
    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    EXECUTED = "EXECUTED"
    FAILED = "FAILED"


class PendingOperation(SQLModel, table=True):
    """Батч операций, ждущий подтверждения оператора перед прогоном Автозагрузки.

    Заполняется planner'ом/wiper'ом, показывается ботом ("опубликовать 5,
    затереть 2, архивировать 2"), исполняется только после CONFIRMED.
    """

    id: int | None = Field(default=None, primary_key=True)
    kind: OperationKind
    listing_ids: str  # CSV id Listing, затронутых операцией
    summary: str  # человекочитаемое описание для бота
    status: OperationStatus = Field(default=OperationStatus.PENDING, index=True)

    requested_at: datetime = Field(default_factory=utcnow)
    decided_at: datetime | None = None
    decided_by: str | None = None  # tg user id/имя оператора
    executed_at: datetime | None = None
    error: str | None = None


class AuditLogEntry(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    at: datetime = Field(default_factory=utcnow)
    actor: str  # "system" | tg user id
    action: str
    details: str = ""


class SyncState(SQLModel, table=True):
    """Небольшой key-value для водяных знаков синка (напр. до какого
    AuditLogEntry.id уже дописано в таблицу-пульт) — не обязательно
    заводить отдельную таблицу под каждый такой счётчик.
    """

    key: str = Field(primary_key=True)
    value: str = ""
