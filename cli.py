"""Единая точка входа. `python -m cli --help` или `avito-dvijenia --help`
после `pip install -e .`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from sqlmodel import select

from admin.queue import (
    apply_operator_decisions,
    fetch_new_log_entries,
    mark_log_entries_pushed,
    sync_products_from_supplier_items,
)
from admin.sheet import AdminSheet, AdminSheetNotConfiguredError
from avito.auth import AvitoAuthError, fetch_access_token
from avito.categories import DATA_PATH, load_categories, render_markdown
from avito.client import AvitoApiError, AvitoClient
from avito.sizes import map_sizes
from content.build import build_listings_for_product
from content.dedup import is_too_similar
from content.descriptions import render_description
from content.humanize import HumanizeViolationError
from content.respin import respin
from content.titles import render_title
from core.config import get_settings
from core.db import get_session, init_db
from core.models import GeoCity, Product, ProductStatus
from media.pipeline import sync_media_for_supplier_items
from media.store import get_media_store
from sources.gsheets import ALL_SOURCES
from sources.reconcile import reconcile_source

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()

DOCS_DIR = Path(__file__).parent / "docs"


@app.command("check-access")
def check_access() -> None:
    """Э0: проверить OAuth-токен и прогнать read-only методы Avito API
    по реальному аккаунту. Пишет docs/api_notes.md с фактическим статусом
    каждого эндпоинта — этим фиксируем правду по конкретному аккаунту,
    а не документацию из сторонних источников.
    """
    init_db()
    settings = get_settings()

    if not settings.is_configured_for_avito:
        console.print("[red]AVITO_CLIENT_ID / AVITO_CLIENT_SECRET не заданы в .env[/red]")
        raise typer.Exit(1)

    console.print("Запрашиваю OAuth-токен...")
    try:
        fetch_access_token()
    except AvitoAuthError as e:
        console.print(f"[red]Не удалось получить токен: {e}[/red]")
        raise typer.Exit(1) from e
    console.print("[green]Токен получен.[/green]")

    user_id: str | None = settings.avito_user_id or None
    self_info: dict | None = None

    with AvitoClient() as client:
        try:
            self_info = client.get_self()
            user_id = str(self_info.get("id") or self_info.get("user_id") or user_id or "")
            console.print(f"[green]get_self() OK[/green], user_id={user_id!r}")
        except AvitoApiError as e:
            console.print(f"[yellow]get_self() не сработал: {e}[/yellow]")
            if not user_id:
                console.print(
                    "[yellow]AVITO_USER_ID не задан в .env и определить его не удалось — "
                    "часть проверок ниже будет пропущена.[/yellow]"
                )

        results = client.probe_all(user_id)

    table = Table(title="Avito API — фактический статус эндпоинтов")
    table.add_column("Метод")
    table.add_column("Уверенность")
    table.add_column("HTTP")
    table.add_column("Путь")
    table.add_column("Результат")
    for r in results:
        status_str = "[green]OK[/green]" if r.ok else f"[red]FAIL {r.status}[/red]"
        table.add_row(r.name, r.confidence, r.method, r.path, status_str)
    console.print(table)

    balance_row = next((r for r in results if r.name == "get_balance"), None)
    if balance_row and balance_row.ok and user_id:
        try:
            with AvitoClient() as client:
                balance = client.get_balance(user_id)
            console.print(f"Баланс/аванс: [bold]{balance}[/bold]")
        except AvitoApiError as e:
            console.print(f"[yellow]Не удалось перечитать баланс отдельно: {e}[/yellow]")

    _write_api_notes(user_id, self_info, results)
    console.print(f"\nОтчёт сохранён: {DOCS_DIR / 'api_notes.md'}")


def _write_api_notes(user_id: str | None, self_info: dict | None, results: list) -> None:
    DOCS_DIR.mkdir(exist_ok=True)
    lines = [
        "# Avito API — фактическая проверка доступа",
        "",
        "<!-- Файл ПЕРЕЗАПИСЫВАЕТСЯ целиком командой `make access`.",
        "     Не дописывай сюда выводы руками — они будут стёрты при следующем",
        "     прогоне. Разбор и решения по находкам живут в docs/BACKLOG.md. -->",
        "",
        f"Прогнано: {dt.datetime.now(dt.UTC).isoformat(timespec='seconds')}",
        f"user_id: `{user_id}`",
        "",
        "Пути собраны из независимых сторонних источников (не из офиц.",
        "спецификации — портал developers.avito.ru отдаёт JS-SPA без",
        "публично читаемого текста). См. avito/client.py про CONFIRMED/CANDIDATE.",
        "",
        "| Метод | Уверенность | HTTP | Путь | Статус | Заметка |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        status = "OK" if r.ok else f"FAIL {r.status}"
        lines.append(
            f"| {r.name} | {r.confidence} | {r.method} | `{r.path}` | {status} | {r.note} |"
        )
    lines += [
        "",
        "## Что с этим делать",
        "",
        "Разбор результатов — в [BACKLOG.md](BACKLOG.md):",
        "",
        "- `B-003` — баланс отдаёт 0 ₽ при озвученных ~900 ₽;",
        "- `B-004` — autoload-эндпоинты дают 404, перепроверить после",
        "  подключения Автозагрузки в ЛК.",
    ]
    (DOCS_DIR / "api_notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.command("categories")
def categories_dump(
    action: str = typer.Argument("dump", help="dump — сгенерировать docs/categories.md"),
) -> None:
    """Черновик категорий/полей Автозагрузки -> docs/categories.md.

    ВАЖНО: пока avito/data/categories_draft.yaml не verified: true, это
    черновик по открытым источникам, а не факт из ЛК аккаунта. См. план,
    раздел "Категории Авито".
    """
    if action != "dump":
        console.print(f"[red]Неизвестное действие: {action}[/red]")
        raise typer.Exit(1)

    doc = load_categories()
    DOCS_DIR.mkdir(exist_ok=True)
    out_path = DOCS_DIR / "categories.md"
    out_path.write_text(render_markdown(doc), encoding="utf-8")

    if doc.verified:
        console.print(f"[green]Категории сверены с ЛК.[/green] -> {out_path}")
    else:
        console.print(
            f"[yellow]ЧЕРНОВИК (verified: false, источник: {DATA_PATH.name}).[/yellow] "
            f"Сгенерировано в {out_path}. Сверить с ЛК → Автозагрузка → "
            "Правила и шаблоны перед боевой публикацией."
        )


sources_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(sources_app, name="sources")


@sources_app.command("sync")
def sources_sync(
    dry_run: bool = typer.Option(
        True, "--dry-run/--write", help="По умолчанию только печатает диф, БД не трогает."
    ),
) -> None:
    """Э1: стянуть обе известные таблицы поставщика, сравнить с тем, что
    уже в БД, напечатать диф (новые/изменились/пропали). С --write —
    применить диф к SupplierItem.
    """
    init_db()

    with get_session() as session:
        for source in ALL_SOURCES:
            console.print(f"\n[bold]{source.name}[/bold]")
            try:
                rows = source.fetch()
            except Exception as e:
                console.print(f"[red]Не удалось получить данные: {e}[/red]")
                continue

            summary = reconcile_source(
                session,
                source_name=source.name,
                fresh_rows=rows,
                min_expected_rows=getattr(source, "MIN_EXPECTED_ROWS", 1),
                dry_run=dry_run,
            )

            if summary.warning:
                console.print(f"[yellow]⚠️ {summary.warning}[/yellow]")

            console.print(
                f"новых: {len(summary.new)} | изменилось: {len(summary.changed)} | "
                f"без изменений: {summary.unchanged_count} | пропало: {len(summary.disappeared)}"
            )
            for key in summary.new[:5]:
                console.print(f"  [green]+[/green] {key}")
            if len(summary.new) > 5:
                console.print(f"  ... и ещё {len(summary.new) - 5}")
            for key in summary.disappeared[:5]:
                console.print(f"  [red]-[/red] {key}")

    if dry_run:
        console.print(
            "\n[yellow]dry-run: БД не изменена. Повторить с --write, чтобы сохранить.[/yellow]"
        )


content_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(content_app, name="content")


@content_app.command("render")
def content_render(item: int = typer.Option(..., "--item", help="ID Product")) -> None:
    """Э4: напечатать заголовок и описание всех 5 гео-копий товара в
    консоль, без записи в БД и без обращения к MediaStore — быстрая
    проверка шаблонов/humanize на конкретном товаре.
    """
    init_db()
    with get_session() as session:
        product = session.get(Product, item)
        if product is None:
            console.print(f"[red]Product #{item} не найден[/red]")
            raise typer.Exit(1)

        mapped_sizes, unmapped = map_sizes(product.sizes_supplier.split(","))
        if unmapped:
            console.print(f"[yellow]Неразмеченные размеры: {unmapped}[/yellow]")
        if not mapped_sizes:
            console.print("[red]Нет ни одного распознанного размера — рендерить нечего[/red]")
            raise typer.Exit(1)

        title = render_title(brand=product.brand, raw_title=product.title)
        for city in GeoCity:
            try:
                description = render_description(
                    city,
                    title=title,
                    brand=product.brand,
                    color=product.color,
                    sizes=mapped_sizes,
                )
            except HumanizeViolationError as e:
                console.print(f"[red]{city.value}: не прошло humanize — {e}[/red]")
                continue
            console.print(f"\n[bold]{city.value}[/bold] — {title}")
            console.print(description)


@content_app.command("respin")
def content_respin(
    item: int = typer.Option(..., "--item", help="ID Product"),
    times: int = typer.Option(5, "--times", help="Сколько перезаливов сгенерировать"),
    city: str = typer.Option("MSK", "--city", help="Город-шаблон, по умолчанию MSK"),
) -> None:
    """Э4: сгенерировать N синонимизированных версий описания одного
    товара/города, проверить шинглами, что версии не совпадают друг с
    другом выше порога (план: "перезаливы дают пять заметно разных
    описаний, шинглы не пересекаются выше порога").
    """
    init_db()
    with get_session() as session:
        product = session.get(Product, item)
        if product is None:
            console.print(f"[red]Product #{item} не найден[/red]")
            raise typer.Exit(1)

        mapped_sizes, _unmapped = map_sizes(product.sizes_supplier.split(","))
        if not mapped_sizes:
            console.print("[red]Нет ни одного распознанного размера[/red]")
            raise typer.Exit(1)

        title = render_title(brand=product.brand, raw_title=product.title)
        base = render_description(
            GeoCity(city), title=title, brand=product.brand, color=product.color, sizes=mapped_sizes
        )

    versions: list[str] = []
    for i in range(times):
        version = respin(base, seed=i)
        too_similar = is_too_similar(version, versions)
        flag = "[red]похоже на предыдущую версию[/red]" if too_similar else "[green]ок[/green]"
        console.print(f"\n[bold]перезалив {i + 1}[/bold] — {flag}")
        console.print(version)
        versions.append(version)


@content_app.command("build")
def content_build() -> None:
    """Э4: собрать 5 гео-копий (Listing) для каждого APPROVED Product —
    заголовок, описание под город, фото-вариации в MediaStore. Публикации
    не делает, только готовит черновики (Э5).
    """
    init_db()
    store = get_media_store()

    with get_session() as session:
        products = list(
            session.exec(select(Product).where(Product.status == ProductStatus.APPROVED))
        )
        total_created = total_skipped_unmapped = 0
        for product in products:
            summary = build_listings_for_product(session, product, store)
            total_created += len(summary.created)
            total_skipped_unmapped += len(summary.skipped_unmapped_sizes)

    console.print(
        f"товаров APPROVED: {len(products)} | создано Listing: {total_created} | "
        f"без распознанных размеров: {total_skipped_unmapped}"
    )


media_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(media_app, name="media")


@media_app.command("sync")
def media_sync(
    dry_run: bool = typer.Option(
        True, "--dry-run/--write", help="По умолчанию только считает, что скачал бы, не пишет."
    ),
    force: bool = typer.Option(
        False, "--force", help="Перекачать фото даже для позиций, у которых уже есть RAW-ассеты."
    ),
) -> None:
    """Э3: скачать исходные фото под каждый SupplierItem (прямые ссылки из
    таблицы или пост TG-канала) в MediaStore, зарегистрировать в MediaAsset
    с pHash. Идемпотентно — позиции с уже скачанными фото пропускаются,
    если не передан --force.
    """
    init_db()
    store = get_media_store()

    with get_session() as session:
        summary = sync_media_for_supplier_items(session, store, dry_run=dry_run, force=force)

    console.print(
        f"скачано: {len(summary.fetched)} | без источника фото: {len(summary.skipped_no_source)} | "
        f"уже было: {len(summary.skipped_already_fetched)} | ошибок: {len(summary.failed)}"
    )
    for item_id, error in list(summary.failed.items())[:5]:
        console.print(f"  [red]#{item_id}: {error}[/red]")

    if dry_run:
        console.print(
            "\n[yellow]dry-run: файлы не скачаны, MediaAsset не записан. "
            "Повторить с --write.[/yellow]"
        )


admin_app = typer.Typer(no_args_is_help=True, add_completion=False)
app.add_typer(admin_app, name="admin")


@admin_app.command("sync")
def admin_sync() -> None:
    """Э2: двусторонний синк с таблицей-пультом.

    Порядок жёстко фиксирован (см. admin/sheet.py): сначала читаем решения
    оператора ("Решение" в Товарах) и применяем их в БД, только потом
    досоздаём/обновляем Product из SupplierItem авто-правилами и
    перезаписываем вкладку — иначе свежий push затрёт то, что оператор
    только что вписал в этом же прогоне.
    """
    init_db()

    try:
        sheet = AdminSheet()
    except AdminSheetNotConfiguredError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1) from e

    with get_session() as session:
        decisions = sheet.pull_decisions()
        applied = apply_operator_decisions(session, decisions)
        if applied:
            console.print(f"Применено решений оператора: {len(applied)}")
            for product_id, status in list(applied.items())[:10]:
                console.print(f"  #{product_id} -> {status}")

        summary = sync_products_from_supplier_items(session)
        console.print(
            f"создано: {len(summary.created)} | обновлено: {len(summary.updated)} | "
            f"авто-APPROVED: {len(summary.auto_approved)} | "
            f"NEEDS_REVIEW: {len(summary.needs_review)} | "
            f"пропало у поставщика: {len(summary.disappeared_rejected)}"
        )

        all_products = list(session.exec(select(Product)))
        sheet.push_products(all_products)
        sheet.ensure_placeholder_tabs()

        new_log_entries = fetch_new_log_entries(session)
        sheet.push_log(new_log_entries)
        mark_log_entries_pushed(session, new_log_entries)

    console.print(f"\nТаблица-пульт обновлена: {len(all_products)} товаров в очереди.")


if __name__ == "__main__":
    app()
