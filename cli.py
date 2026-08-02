"""Единая точка входа. `python -m cli --help` или `avito-dvijenia --help`
после `pip install -e .`.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from avito.auth import AvitoAuthError, fetch_access_token
from avito.categories import DATA_PATH, load_categories, render_markdown
from avito.client import AvitoClient, AvitoApiError
from core.config import get_settings
from core.db import get_session, init_db
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
        console.print(
            "[red]AVITO_CLIENT_ID / AVITO_CLIENT_SECRET не заданы в .env[/red]"
        )
        raise typer.Exit(1)

    console.print("Запрашиваю OAuth-токен...")
    try:
        fetch_access_token()
    except AvitoAuthError as e:
        console.print(f"[red]Не удалось получить токен: {e}[/red]")
        raise typer.Exit(1)
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
        f"Прогнано: {dt.datetime.now().isoformat(timespec='seconds')}",
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
    (DOCS_DIR / "api_notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


@app.command("categories")
def categories_dump(
    action: str = typer.Argument("dump", help="dump — сгенерировать docs/categories.md")
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
    )
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
            except Exception as e:  # noqa: BLE001
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
        console.print("\n[yellow]dry-run: БД не изменена. Повторить с --write, чтобы сохранить.[/yellow]")


if __name__ == "__main__":
    app()
