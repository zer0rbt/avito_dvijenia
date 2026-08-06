"""Разбор выгрузки Telegram Desktop и привязка постов к позициям прайса.

Фикстура — не выдуманная: `tests/fixtures/telegram_export/messages.html`
вырезан из настоящей выгрузки канала поставщика (клиент Telegram Desktop,
август 2026), включая альбом из трёх сообщений и эмодзи-мусор в тексте.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from media.telegram_export import (
    ItemRef,
    MatchWay,
    build_post_index,
    match_items_to_posts,
    normalize_title,
    parse_export,
    post_id_from_url,
    title_tokens,
)

FIXTURE = Path(__file__).parent / "fixtures" / "telegram_export"


@pytest.fixture
def posts():
    return parse_export(FIXTURE)


def test_album_becomes_one_post_with_all_photos(posts):
    """Три подряд идущих сообщения одной секундой — это один альбом.

    Текст в выгрузке лежит только на первом сообщении альбома, поэтому
    наивный разбор «сообщение = пост» дал бы один пост с фото и два без.
    """
    album = next(p for p in posts if p.message_id == 4201)
    assert len(album.photos) == 3
    assert all(p.is_absolute() for p in album.photos)


def test_video_inside_album_stays_addressable(posts):
    """Видео в альбоме выгрузка по умолчанию не забирает — но id сообщения
    всё равно должен вести на альбом.

    В прайсе ссылка ставится через «поделиться» на конкретное медиа
    (`?single`), и у трёх позиций она указывает как раз на видео. Пропустив
    такое сообщение, мы теряем весь пост с фото.
    """
    album = next(p for p in posts if p.message_id == 4201)
    assert album.member_ids == [4201, 4202, 4203, 4204]
    assert len(album.photos) == 3  # видео фотографией не притворяется

    index = build_post_index(posts)
    assert index[4204] is album


def test_post_after_album_gap_is_separate(posts):
    """Безтекстовое фото через недели после предыдущего поста — не хвост
    альбома, а самостоятельная публикация."""
    standalone = next(p for p in posts if p.message_id == 4299)
    assert standalone.text == ""
    assert len(standalone.photos) == 1


def test_title_is_first_line_not_whole_text(posts):
    album = next(p for p in posts if p.message_id == 4201)
    assert album.title == "Adidas Samba Pony Tonal x Wales Bonner"


def test_price_and_sizes_parsed_from_post(posts):
    album = next(p for p in posts if p.message_id == 4201)
    # «Рынок 2.5-5.5к₽» ниже по тексту не должен перебить оптовую цену.
    assert album.price_opt_rub == 850.0
    assert album.sizes == ["41", "42", "43", "44", "45", "46"]


def test_index_covers_every_message_of_album(posts):
    """Ссылка в прайсе может указывать на любое фото альбома."""
    index = build_post_index(posts)
    assert index[4201] is index[4202] is index[4203]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://t.me/best_dropship/2473", 2473),
        ("https://t.me/best_dropship/2473?single", 2473),  # ссылка на фото альбома
        ("https://t.me/c/1234567890/1545", 1545),  # приватный канал
        ("https://t.me/best_dropship", None),
        (None, None),
    ],
)
def test_post_id_from_url(url, expected):
    assert post_id_from_url(url) == expected


def test_match_by_post_id_is_exact(posts):
    """Есть post_url — привязка точная, название не участвует."""
    items = [ItemRef(item_id=7, title="что-то совсем другое", post_url="https://t.me/ch/4202")]
    result = match_items_to_posts(items, posts)

    assert result.matched[7].way == MatchWay.BY_POST_ID
    assert len(result.matched[7].post.photos) == 3


def test_missing_post_is_reported_separately(posts):
    """«Пост есть, но в выгрузку не попал» — отдельный случай, не «нет
    совпадения»: он означает не тот период или не тот канал выгрузки."""
    items = [ItemRef(item_id=9, title="ХУДИ CAV EMPT", post_url="https://t.me/ch/999999")]
    result = match_items_to_posts(items, posts)

    assert result.missing_in_export == [9]
    assert not result.matched


def test_match_by_title_when_no_post_url(posts):
    items = [ItemRef(item_id=3, title="Wales Bonner")]
    result = match_items_to_posts(items, posts)

    assert result.matched[3].way == MatchWay.BY_TITLE
    assert result.matched[3].post.message_id == 4201


def test_ambiguous_title_is_not_matched(posts):
    """Два поста про Adidas Samba — привязать нельзя, чужое фото хуже, чем
    никакого. Позиция уходит оператору."""
    items = [ItemRef(item_id=4, title="Adidas Samba")]
    result = match_items_to_posts(items, posts)

    assert 4 not in result.matched
    assert len(result.ambiguous[4]) == 2


def test_normalize_title_survives_supplier_spelling():
    """Одно и то же название поставщик пишет по-разному в таблице и в посте."""
    assert normalize_title("Stone_Island") == normalize_title("Stone Island 🅰️")
    assert normalize_title("Костюм ОЛД МАНИ") == normalize_title("Костюм  Олд Мани⚜️")


def test_title_tokens_drop_generic_words():
    """«Худи» есть у половины каталога и потому ничего не различает."""
    assert title_tokens("ЗИП ХУДИ STONE ISLAND") == {"stone", "island"}


def test_parse_export_fails_loudly_on_wrong_folder(tmp_path):
    with pytest.raises(FileNotFoundError, match=re.escape("messages.html")):
        parse_export(tmp_path)
