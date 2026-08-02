from __future__ import annotations

import sources.gsheets as gsheets_module
from sources.gsheets import BestDropshipHoodiesSource, SolikaDropSource

SOLIKA_FIXTURE = [
    ["Наличие и прайс Дроп СОЛИКА", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    ["", "", "", "", "", "", "", "", "", "", "", ""],
    [
        "Фото товара",
        "Название",
        "Размеры",
        "",
        "",
        "",
        "",
        "",
        "Цвета",
        "Дроп цена / ВЫКУП",
        "Дроп цена / БЕЗ ВЫКУПА",
        "ГОРОД ОТПРАВКИ ",
    ],
    ["", "", "XS", "S", "M", "L", "XL", "ХХL", "", "", "", ""],
    [
        "",
        "Stone_Island ",
        "❌",
        "✅",
        "❌",
        "✅",
        "✅",
        "❌",
        "Черные",
        "3650₽  3500₽",
        "3650₽  3500₽",
        "СОЛНЕЧНОГОРСК ",
    ],
    ["", "", "", "", "", "", "", "", "", "", "", ""],  # пустая строка-заполнитель
    [
        "",
        "Костюм Corteiz Велюр",
        "✅",
        "✅",
        "❌",
        "❌",
        "❌",
        "❌",
        "ЧЕРНЫЙ",
        "4500Р",
        "4650₽",
        "СОЛНЕЧНОГОРСК ",
    ],
]

BEST_DROPSHIP_FIXTURE = [
    ["ФОТО", "Обновлено 20:25 МСК 31.07", "", "", "", "", "", "", "", "", ""],
    ["", "Х     У     Д     И", "", "", "", "", "", "", "", "", ""],
    ["", "НАЗВАНИЕ", "", "", "", "", "", "", "ЦЕНА ДРОП", "РРЦ", "ССЫЛКА НА ПОСТ"],
    ["", "", "S", "M", "L", "XL", "2XL", "3XL", "", "", ""],
    [
        "",
        "ХУДИ \nALEXANDER MCQUEEN",
        "💎",
        "4",
        "6",
        "7",
        "4",
        "💎",
        "2500",
        "3000",
        "https://t.me/best_dropship/1545",
    ],
    [
        "",
        "ХУДИ CHAMPION",
        "💎",
        "💎",
        "💎",
        "💎",
        "💎",
        "💎",
        "2300",
        "",
        "https://t.me/best_dropship/2791",
    ],
]


def test_solika_drop_source_parses_titles_sizes_and_price(monkeypatch):
    monkeypatch.setattr(gsheets_module, "fetch_csv_rows", lambda sheet_id: SOLIKA_FIXTURE)
    rows = SolikaDropSource().fetch()

    assert len(rows) == 2  # пустая строка-заполнитель пропущена

    stone = rows[0]
    assert stone.raw_title == "Stone_Island"
    assert stone.brand == "Stone Island"
    assert stone.sizes_available == ["S", "L", "XL"]
    assert stone.color == "Черные"
    assert stone.price_purchase == 3500.0  # актуальная (вторая) цена
    assert stone.price_rrc is None  # в этой таблице РРЦ нет вообще
    assert stone.ship_city == "СОЛНЕЧНОГОРСК"
    assert stone.source_key == "gsheets:solika_drop:5"

    corteiz = rows[1]
    assert corteiz.sizes_available == ["XS", "S"]
    assert corteiz.price_purchase == 4500.0


def test_best_dropship_hoodies_source_treats_diamond_as_sold_out(monkeypatch):
    monkeypatch.setattr(gsheets_module, "fetch_csv_rows", lambda sheet_id: BEST_DROPSHIP_FIXTURE)
    rows = BestDropshipHoodiesSource().fetch()

    assert len(rows) == 2

    mcqueen = rows[0]
    assert "ALEXANDER MCQUEEN" in mcqueen.raw_title
    assert mcqueen.brand == "Alexander McQueen"
    assert mcqueen.sizes_available == ["M", "L", "XL", "XXL"]  # 💎 (S и XXXL) исключены
    assert mcqueen.price_purchase == 2500.0
    assert mcqueen.price_rrc == 3000.0
    assert mcqueen.post_url == "https://t.me/best_dropship/1545"

    champion = rows[1]
    assert champion.sizes_available == []  # всё распродано — сигнал на NEEDS_REVIEW в Э2
    assert champion.price_rrc is None
