"""Очередь модерации (Э2): SupplierItem -> Product, авто-правила по
статусам, применение решений оператора из таблицы-пульта.

Гранулярность Product = SupplierItem (товар x цвет уже задан строкой
источника, см. sources/). Гео-копии (x5 городов) появляются позже, на
публикации (Э4-Э5), это не забота очереди модерации.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from avito.classify import classify_goods_subtype
from avito.sizes import map_sizes
from core.approval import log_audit
from core.models import AuditLogEntry, Product, ProductStatus, SupplierItem, SyncState, utcnow
from pricing import compute_final_price

LOG_WATERMARK_KEY = "admin_sheet_last_pushed_log_id"

# Решения оператора в колонке "Решение" таблицы-пульта -> статус Product.
# Всё, что не входит в этот словарь (в т.ч. пустая ячейка), решением не
# считается — обрабатывать нечего, статус не трогаем.
DECISION_TO_STATUS: dict[str, ProductStatus] = {
    "публиковать": ProductStatus.APPROVED,
    "пропустить": ProductStatus.REJECTED,
    "отложить": ProductStatus.HOLD,
}

# Статусы, которые считаются "ещё не решённые системой окончательно" —
# только у них авто-правила и синк из SupplierItem могут менять состояние.
# Ручное решение оператора (через DECISION_TO_STATUS) либо более поздний
# этап жизненного цикла (QUEUED/PUBLISHED, Э5+) авто-правилами не трогаем.
AUTO_MANAGED_STATUSES = {ProductStatus.NEW, ProductStatus.NEEDS_REVIEW, ProductStatus.APPROVED}


@dataclass
class QueueSyncSummary:
    created: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)
    auto_approved: list[int] = field(default_factory=list)
    needs_review: list[int] = field(default_factory=list)
    disappeared_rejected: list[int] = field(default_factory=list)
    decisions_applied: dict[int, str] = field(default_factory=dict)


def evaluate_auto_status(item: SupplierItem) -> tuple[ProductStatus, str | None]:
    """Правила из плана ("Админ-панель: очередь модерации"), в объёме,
    для которого есть реальный сигнал в данных.

    Наличие фото по-прежнему НЕ проверяем: фото есть у одной позиции из 82
    (B-018), проверка увела бы весь каталог в NEEDS_REVIEW — это не фильтр,
    а его отсутствие. Вернётся, когда телетон-выгрузка даст фото.

    Размеры проверяем дважды: сначала что они вообще есть, потом что они
    маппятся в справочник Авито (avito/sizes.py). Размер, которого нет в
    справочнике, — это карточка, которую Автозагрузка отклонит, и узнать
    об этом лучше здесь, а не из отчёта после публикации.
    """
    sizes = [s for s in item.sizes_available.split(",") if s]
    if not sizes:
        return ProductStatus.NEEDS_REVIEW, "no_sizes"

    _mapped, unmapped = map_sizes(sizes)
    if unmapped:
        return ProductStatus.NEEDS_REVIEW, f"size_unmapped:{','.join(unmapped)}"

    if not item.brand:
        return ProductStatus.NEEDS_REVIEW, "brand_unknown"

    price = compute_final_price(price_rrc=item.price_rrc, price_purchase=item.price_purchase)
    if price is None:
        return ProductStatus.NEEDS_REVIEW, "price_missing"

    subtype, _matched = classify_goods_subtype(item.raw_title)
    if subtype is None:
        return ProductStatus.NEEDS_REVIEW, "goods_subtype_unknown"

    return ProductStatus.APPROVED, None


def _product_differs_from_supplier_item(product: Product, item: SupplierItem) -> bool:
    """Есть ли реальные изменения — чтобы не считать "обновлено" на каждом
    прогоне, когда SupplierItem не менялся (см. sources/reconcile.py,
    тот же принцип: различать факт изменения от повторного применения).
    """
    return (
        product.title != item.raw_title
        or product.brand != item.brand
        or product.color != item.color
        or product.sizes_supplier != item.sizes_available
        or product.price_purchase != item.price_purchase
        or product.price_rrc != item.price_rrc
        or product.avito_category != classify_goods_subtype(item.raw_title)[0]
    )


def _sync_fields_from_supplier_item(product: Product, item: SupplierItem) -> None:
    product.title = item.raw_title
    product.brand = item.brand
    product.color = item.color
    product.sizes_supplier = item.sizes_available
    product.price_purchase = item.price_purchase
    product.price_rrc = item.price_rrc
    product.price_final = compute_final_price(
        price_rrc=item.price_rrc, price_purchase=item.price_purchase
    )
    # GoodsSubType Авито ("Худи"/"Футболка"/...) — то, что уедет в фид тегом
    # <GoodsSubType>, см. avito/feed.py. Держим на Product, а не пересчитываем
    # при сборке фида: оператор должен видеть категорию в таблице-пульте и
    # иметь возможность поправить её руками.
    product.avito_category = classify_goods_subtype(item.raw_title)[0]
    product.updated_at = utcnow()


def sync_products_from_supplier_items(session: Session) -> QueueSyncSummary:
    """Довести Product до состояния, соответствующего текущим SupplierItem.

    Порядок важен: вызывать ПОСЛЕ apply_operator_decisions(), иначе свежий
    авто-статус может затереть то, что оператор только что выставил руками
    в этом же прогоне.
    """
    summary = QueueSyncSummary()

    items = list(session.exec(select(SupplierItem)))
    products = list(session.exec(select(Product)))
    product_by_supplier_item_id = {p.supplier_item_id: p for p in products if p.supplier_item_id}

    for item in items:
        product = product_by_supplier_item_id.get(item.id)

        if not item.is_available:
            # Пропавший у поставщика товар: если решение по нему ещё не
            # принято окончательно (сам ещё не в QUEUED/PUBLISHED/HOLD/REJECTED
            # вручную) — снимаем с рассмотрения автоматически. Опубликованные
            # карточки такое не трогает, это забота lifecycle/planner.py (Э5+).
            if product and product.status in AUTO_MANAGED_STATUSES:
                product.status = ProductStatus.REJECTED
                product.review_reason = "disappeared_from_source"
                product.updated_at = utcnow()
                session.add(product)
                summary.disappeared_rejected.append(product.id)
            continue

        if product is None:
            product = Product(
                supplier_item_id=item.id,
                title=item.raw_title,
                brand=item.brand,
                goods_type=item.goods_type,
                color=item.color,
                sizes_supplier=item.sizes_available,
                price_purchase=item.price_purchase,
                price_rrc=item.price_rrc,
                price_final=compute_final_price(
                    price_rrc=item.price_rrc, price_purchase=item.price_purchase
                ),
                avito_category=classify_goods_subtype(item.raw_title)[0],
            )
            status, reason = evaluate_auto_status(item)
            product.status = status
            product.review_reason = reason
            session.add(product)
            session.flush()  # получить product.id для отчёта
            summary.created.append(product.id)
            if status == ProductStatus.APPROVED:
                summary.auto_approved.append(product.id)
            else:
                summary.needs_review.append(product.id)
            continue

        if product.status not in AUTO_MANAGED_STATUSES:
            continue  # решение оператора или более поздний этап — не трогаем

        status, reason = evaluate_auto_status(item)
        if (
            not _product_differs_from_supplier_item(product, item)
            and product.status == status
            and product.review_reason == reason
        ):
            continue  # реальных изменений нет — не считаем "обновлено"

        _sync_fields_from_supplier_item(product, item)
        product.status = status
        product.review_reason = reason
        session.add(product)
        summary.updated.append(product.id)
        if status == ProductStatus.APPROVED:
            summary.auto_approved.append(product.id)
        else:
            summary.needs_review.append(product.id)

    session.commit()
    return summary


def apply_operator_decisions(session: Session, decisions: dict[int, str]) -> dict[int, str]:
    """decisions: {product_id: "публиковать"/"пропустить"/"отложить"/...}
    из колонки "Решение" таблицы-пульта. Возвращает применённые решения
    (product_id -> новый статус.value) для отчёта/лога.

    Каждое применённое решение пишется в AuditLogEntry — иначе вкладка
    "Лог" таблицы-пульта (см. admin/sheet.py push_log) никогда бы не
    наполнялась содержимым из очереди модерации.

    Повторное решение, ничего не меняющее (товар уже в этом статусе),
    применённым не считается: не пишет ни updated_at, ни строку в лог.
    Иначе каждый прогон над не вычищенной колонкой "Решение" заново
    перекладывает в лог всю её историю — на Э5 так набралось 44 записи
    аудита на 10 реальных решений, и лог стал выглядеть как чья-то
    посторонняя активность в БД (B-020).
    """
    applied: dict[int, str] = {}
    for product_id, raw_decision in decisions.items():
        decision = raw_decision.strip().lower()
        new_status = DECISION_TO_STATUS.get(decision)
        if new_status is None:
            continue  # пустая ячейка или нераспознанный текст — не решение

        product = session.get(Product, product_id)
        if product is None:
            continue

        new_reason = None if new_status == ProductStatus.APPROVED else "operator_decision"
        if product.status == new_status and product.review_reason == new_reason:
            continue  # то же самое решение уже применено — менять нечего

        product.status = new_status
        product.review_reason = new_reason
        product.updated_at = utcnow()
        session.add(product)
        applied[product_id] = new_status.value
        log_audit(
            session,
            actor="operator:sheet",
            action=f"PRODUCT_DECISION {new_status.value}",
            details=f"product_id={product_id} title={product.title!r} decision={decision!r}",
        )

    session.commit()
    return applied


def fetch_new_log_entries(session: Session) -> list[AuditLogEntry]:
    """Записи AuditLogEntry, ещё не дописанные в таблицу-пульт — по
    водяному знаку в SyncState, чтобы не дублировать строки при каждом
    прогоне cli.py admin sync.
    """
    state = session.get(SyncState, LOG_WATERMARK_KEY)
    last_id = int(state.value) if state and state.value else 0

    entries = list(
        session.exec(
            select(AuditLogEntry).where(AuditLogEntry.id > last_id).order_by(AuditLogEntry.id)
        )
    )
    return entries


def mark_log_entries_pushed(session: Session, entries: list[AuditLogEntry]) -> None:
    if not entries:
        return
    last_id = max(e.id for e in entries)
    state = session.get(SyncState, LOG_WATERMARK_KEY)
    if state is None:
        state = SyncState(key=LOG_WATERMARK_KEY, value=str(last_id))
    else:
        state.value = str(last_id)
    session.add(state)
    session.commit()
