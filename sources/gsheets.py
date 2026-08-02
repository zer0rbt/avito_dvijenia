"""Источники на базе публичного CSV-экспорта Google Sheets.

Обе таблицы читаются анонимно через `.../export?format=csv` — сервис-аккаунт
им не нужен (он нужен только для таблицы-пульта в Э2, см. admin/sheet.py).

Структура каждой таблицы разобрана вручную по реальному содержимому
(Э1, 2026-08-02) и зафиксирована здесь фиксированными индексами колонок —
таблицы поставщика без версионирования, ломаются молча при изменении
структуры. sources/reconcile.py логирует, если после парсинга строк
подозрительно мало (см. MIN_EXPECTED_ROWS) — это сигнал, что раскладка
таблицы поменялась и парсер надо чинить, а не что товар кончился.
"""

from __future__ import annotations

import csv
import io
import time

import httpx

from sources.base import RawRow
from sources.normalizer import clean_title, guess_brand, parse_price_rub

CSV_EXPORT_URL = "https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"


def fetch_csv_rows(sheet_id: str, timeout: float = 20.0, retries: int = 3) -> list[list[str]]:
    """WSL у этого проекта периодически теряет IPv6-маршрут к Google на
    отдельные запросы (curl рядом с этим отрабатывает нормально — похоже
    на локальную сетевую особенность окружения, не на проблему источника).
    Три попытки с бэкоффом вместо падения всей синхронизации на одном сбое.
    """
    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            resp = httpx.get(
                CSV_EXPORT_URL.format(sheet_id=sheet_id),
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
            return list(csv.reader(io.StringIO(resp.text)))
        except httpx.HTTPError as e:
            last_error = e
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_error  # type: ignore[misc]


class SolikaDropSource:
    """"Наличие и прайс Дроп СОЛИКА".

    Раскладка: строка 0 — заголовок таблицы, строки 1-2 пустые, строка 3 —
    шапка колонок, строка 4 — подписи размеров (XS,S,M,L,XL,XXL) под
    объединённой колонкой "Размеры", данные — с строки 5.

    Колонки (0-based): 0 фото (пусто в CSV, картинка не выгружается),
    1 название, 2-7 доступность размеров (✅/❌), 8 цвет,
    9 "Дроп цена / ВЫКУП", 10 "Дроп цена / БЕЗ ВЫКУПА", 11 город отправки.

    РРЦ в этой таблице нет вообще — pricing.py (Э4) для товаров из этого
    источника всегда идёт по фоллбэку "закупка + 1500".

    За price_purchase берём колонку "ВЫКУП" (9), а не "БЕЗ ВЫКУПА" (10) —
    не подтверждено с заказчиком, какая из двух схем реально используется;
    отмечено в docs/sources_snapshot.md как открытый вопрос.
    """

    name = "gsheets:solika_drop"
    SHEET_ID = "1OLviwwUxBYsK19_lqsMrfkzxCCDH39FActXHfn27_Ck"
    SIZE_LABELS = ["XS", "S", "M", "L", "XL", "XXL"]
    HEADER_ROW = 3
    SIZE_SUBHEADER_ROW = 4
    DATA_START_ROW = 5
    MIN_EXPECTED_ROWS = 10

    def fetch(self) -> list[RawRow]:
        rows = fetch_csv_rows(self.SHEET_ID)
        out: list[RawRow] = []
        for idx, row in enumerate(rows[self.DATA_START_ROW :], start=self.DATA_START_ROW):
            row = row + [""] * (12 - len(row))  # подстраховка от укороченных строк
            title = clean_title(row[1])
            if not title:
                continue  # пустая строка-заполнитель, не товар

            sizes = [
                label
                for label, cell in zip(self.SIZE_LABELS, row[2:8])
                if cell.strip() == "✅"
            ]
            color = clean_title(row[8]) or None
            price_purchase = parse_price_rub(row[9])
            ship_city = clean_title(row[11]) or None

            out.append(
                RawRow(
                    source_key=f"{self.name}:{idx}",
                    source_type="gsheets",
                    raw_title=title,
                    brand=guess_brand(title),
                    color=color,
                    sizes_available=sizes,
                    price_purchase=price_purchase,
                    price_rrc=None,
                    ship_city=ship_city,
                )
            )
        return out


class BestDropshipHoodiesSource:
    """Прайс-таблица best_dropship — раздел "ХУДИ".

    Раскладка: строка 0 — служебная (когда обновлено), строка 1 —
    заголовок раздела "ХУДИ", строка 2 — шапка колонок, строка 3 — подписи
    размеров (S,M,L,XL,2XL,3XL), данные — с строки 4.

    Колонки: 0 фото (пусто), 1 название (часто многострочное — модель +
    бренд на разных строках одной ячейки), 2-7 остаток по размеру
    (число = штук в наличии, 💎 = распродано), 8 "ЦЕНА ДРОП" (price_purchase),
    9 "РРЦ" (часто пусто), 10 ссылка на пост в Telegram-канале — источник
    фото для media/fetch.py (Э3), сюда фото не резолвим.

    Многострочные названия — намеренно НЕ схлопываем переносы в пробел
    (в отличие от clean_title для однострочных полей): "ЗИП ХУДИ\\nMARTINE
    ROSE\\nx\\nSUPREME" при склейке пробелами теряет читаемость меньше,
    чем при потере структуры "тип x бренд1 x бренд2" — поэтому здесь
    перенос сохраняем как " " через ту же clean_title (она это и делает).
    """

    name = "gsheets:best_dropship_hoodies"
    SHEET_ID = "1xpkVr3iIZ_PeXRswfLpsHtKtfiKF5mZUQzfXyvVWw3A"
    SIZE_LABELS = ["S", "M", "L", "XL", "XXL", "XXXL"]
    DATA_START_ROW = 4
    MIN_EXPECTED_ROWS = 10

    def fetch(self) -> list[RawRow]:
        rows = fetch_csv_rows(self.SHEET_ID)
        out: list[RawRow] = []
        for idx, row in enumerate(rows[self.DATA_START_ROW :], start=self.DATA_START_ROW):
            row = row + [""] * (11 - len(row))
            title = clean_title(row[1])
            if not title:
                continue

            sizes = []
            for label, cell in zip(self.SIZE_LABELS, row[2:8]):
                cell = cell.strip()
                if cell and cell != "💎":
                    sizes.append(label)

            price_purchase = parse_price_rub(row[8])
            price_rrc = parse_price_rub(row[9])
            post_url = row[10].strip() or None

            out.append(
                RawRow(
                    source_key=f"{self.name}:{idx}",
                    source_type="gsheets",
                    raw_title=title,
                    brand=guess_brand(title),
                    sizes_available=sizes,
                    price_purchase=price_purchase,
                    price_rrc=price_rrc,
                    post_url=post_url,
                )
            )
        return out


ALL_SOURCES: list = [SolikaDropSource(), BestDropshipHoodiesSource()]
