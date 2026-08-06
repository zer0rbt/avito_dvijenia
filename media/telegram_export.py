"""Фото из выгрузки канала Telegram Desktop («Экспорт истории чата», HTML).

Зачем это в дополнение к media/telegram_source.py: Telethon требует
`api_id`/`api_hash` и живой сессии аккаунта (B-018), а выгрузка — папка на
диске, которую заказчик делает руками в клиенте за минуту. Для наполнения
`MediaAsset` этого достаточно, и никаких кредов не нужно.

Что даёт клиент: `messages.html` + папка `photos/`. Альбом разложен на
несколько подряд идущих `div.message`: текст лежит на первом, у остальных
стоит класс `joined` и текста нет. Поэтому пост здесь — не `div.message`,
а «сообщение с текстом плюс приклеенные к нему безтекстовые фото-сообщения
рядом по времени».

Привязка постов к позициям прайса — двумя способами, и разница между ними
принципиальная:

- **по id поста** — когда у позиции есть `post_url` (`t.me/<канал>/1545`).
  `1545` — это id сообщения, и в выгрузке он же стоит в `id="message1545"`.
  Совпадение точное, гадать не о чем. Так устроен источник
  `best_dropship_hoodies` — все 19 одобренных товаров оттуда;
- **по названию** — когда `post_url` нет (источник `solika_drop`, в таблице
  такой колонки просто не завели). Способ ненадёжный, поэтому неоднозначные
  совпадения не привязываются, а уходят оператору.
"""

from __future__ import annotations

import html
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import Path
from urllib.parse import urlparse

from selectolax.parser import HTMLParser

# Фото-сообщения альбома идут той же секундой или на пару секунд позже.
# Порог с запасом: если между текстовым постом и безтекстовым фото прошло
# больше, это отдельная публикация, а не хвост альбома.
ALBUM_GAP = timedelta(seconds=120)

_DATE_FORMAT = "%d.%m.%Y %H:%M:%S"

_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_MESSAGE_ID_RE = re.compile(r"message(\d+)")
_PRICE_RE = re.compile(r"(\d[\d\s]{2,})\s*₽")
_SIZES_RE = re.compile(r"размер[ыа]?\s*:?\s*(.+)", re.IGNORECASE)


@dataclass
class ExportPost:
    """Один пост канала: текст плюс все фото его альбома."""

    message_id: int | None
    text: str
    dt: datetime | None = None
    photos: list[Path] = field(default_factory=list)
    # Все id сообщений альбома. Ссылка в прайсе может указывать на любое из
    # них (`t.me/ch/2473?single` — на конкретное фото), поэтому в индекс
    # кладём каждое, а не только первое.
    member_ids: list[int] = field(default_factory=list)

    @property
    def title(self) -> str:
        """Первая непустая строка поста — у этого поставщика там название."""
        for line in self.text.splitlines():
            if cleaned := line.strip():
                return cleaned
        return ""

    @property
    def price_opt_rub(self) -> float | None:
        """Первая сумма в ₽ — у этого канала это оптовая цена.

        Ниже по тексту идёт «Рынок 2.5-5.5к₽», но там сумма записана в
        тысячах с буквой «к» и под регексп с ₽ не попадает.
        """
        m = _PRICE_RE.search(self.text)
        return float(m.group(1).replace(" ", "")) if m else None

    @property
    def sizes(self) -> list[str]:
        """Числа из строки «Размеры: ...».

        Берём именно числа, а не слова целиком: поставщик лепит эмодзи
        вплотную («46⚠️»), и split по запятым такой размер теряет. Диапазон
        «37-41» отдаётся концами (37 и 41) — поле справочное, для сверки
        глазами, в маппинг размеров Авито оно не идёт.
        """
        m = _SIZES_RE.search(self.text)
        return re.findall(r"\d+", m.group(1)) if m else []


def parse_export(root: Path) -> list[ExportPost]:
    """Разобрать папку выгрузки в список постов.

    Пути к фото возвращаем абсолютными: выгрузка живёт вне репозитория, и
    относительный путь из `messages.html` за её пределами смысла не имеет.

    Клиент режет длинную историю на `messages.html`, `messages2.html`, … —
    забираем все.
    """
    pages = _export_pages(root)
    if not pages:
        raise FileNotFoundError(f"{root} не похожа на выгрузку Telegram Desktop: нет messages.html")

    posts: list[ExportPost] = []
    for page in pages:
        _parse_page(page, root, posts)
    return posts


def _export_pages(root: Path) -> list[Path]:
    """messages.html, messages2.html, ... по возрастанию номера."""

    def order(path: Path) -> int:
        digits = "".join(ch for ch in path.stem if ch.isdigit())
        return int(digits) if digits else 1

    return sorted(root.glob("messages*.html"), key=order)


def _parse_page(page: Path, root: Path, posts: list[ExportPost]) -> None:
    tree = HTMLParser(page.read_text(encoding="utf-8"))

    for node in tree.css("div.message"):
        classes = node.attributes.get("class", "") or ""
        if "service" in classes:
            continue

        message_id = _extract_message_id(node)
        text = _extract_text(node)
        dt = _extract_dt(node)
        photos = [
            root / href for a in node.css("a.photo_wrap") if (href := a.attributes.get("href"))
        ]
        has_media = node.css_first("div.media_wrap") is not None

        # Хвост альбома: без текста, вплотную по времени к предыдущему посту.
        # Считаем хвостом любое медиа, а не только фото: в альбоме попадаются
        # видео, а выгрузка по умолчанию их не забирает («Not included, change
        # data exporting settings»). Пропустить такое сообщение нельзя — в
        # прайсе ссылка может вести именно на него (`?single`), и тогда пост
        # с фото не находится вовсе.
        if not text and has_media and posts and _is_album_tail(posts[-1], dt):
            posts[-1].photos.extend(photos)
            if message_id is not None:
                posts[-1].member_ids.append(message_id)
            continue

        if not text and not photos:
            continue

        posts.append(
            ExportPost(
                message_id=message_id,
                text=text,
                dt=dt,
                photos=list(photos),
                member_ids=[message_id] if message_id is not None else [],
            )
        )


def _is_album_tail(prev: ExportPost, dt: datetime | None) -> bool:
    if prev.dt is None or dt is None:
        return True  # без времени судить нечем, склейка — меньшее зло
    return abs(dt - prev.dt) <= ALBUM_GAP


def _extract_message_id(node) -> int | None:
    m = _MESSAGE_ID_RE.fullmatch(node.attributes.get("id") or "")
    return int(m.group(1)) if m else None


def _extract_text(node) -> str:
    """Текст поста с сохранением переносов строк.

    `node.text()` склеивает всё в одну строку, а нам нужна первая строка как
    название товара, поэтому разбираем HTML: `<br>` в перенос, теги долой.
    """
    text_node = node.css_first("div.text")
    if text_node is None:
        return ""
    raw = _BR_RE.sub("\n", text_node.html or "")
    raw = _TAG_RE.sub("", raw)
    return html.unescape(raw).replace("﻿", "").strip()


def _extract_dt(node) -> datetime | None:
    date_node = node.css_first("div.date")
    if date_node is None:
        return None
    # title вида "01.07.2026 00:19:59 UTC+03:00". Смещение у всех сообщений
    # выгрузки одинаковое, для склейки альбомов оно роли не играет.
    stamp = (date_node.attributes.get("title") or "").split(" UTC")[0].strip()
    try:
        return datetime.strptime(stamp, _DATE_FORMAT)  # noqa: DTZ007
    except ValueError:
        return None


def build_post_index(posts: list[ExportPost]) -> dict[int, ExportPost]:
    """id сообщения -> пост. В индекс идут все сообщения альбома."""
    index: dict[int, ExportPost] = {}
    for post in posts:
        for member_id in post.member_ids:
            index.setdefault(member_id, post)
    return index


def post_id_from_url(url: str | None) -> int | None:
    """`https://t.me/best_dropship/2473?single` -> 2473.

    Приватные ссылки вида `t.me/c/<internal>/<msg>` тоже дают id сообщения —
    это последний числовой сегмент пути.
    """
    if not url:
        return None
    for part in reversed([p for p in urlparse(url).path.split("/") if p]):
        if part.isdigit():
            return int(part)
    return None


# ---------------------------------------------------------------------------
# Привязка постов к позициям прайса
# ---------------------------------------------------------------------------

# Слова, которые есть почти в каждом названии и потому ничего не различают.
_STOPWORDS = frozenset({"худи", "зип", "костюм", "штаны", "джинсы", "шорты", "футболка"})


class MatchWay(StrEnum):
    BY_POST_ID = "по id поста"
    BY_TITLE = "по названию"


@dataclass
class Match:
    post: ExportPost
    way: MatchWay


@dataclass
class MatchResult:
    """Итог привязки. Привязанным считаем только однозначное."""

    matched: dict[int, Match] = field(default_factory=dict)  # supplier_item_id -> совпадение
    ambiguous: dict[int, list[ExportPost]] = field(default_factory=dict)
    unmatched: list[int] = field(default_factory=list)
    # Ссылка на пост есть, но такого поста в выгрузке нет — самый частый
    # случай при выгрузке не за тот период или не того канала.
    missing_in_export: list[int] = field(default_factory=list)

    @property
    def photos_total(self) -> int:
        return sum(len(m.post.photos) for m in self.matched.values())


def normalize_title(title: str) -> str:
    """Название к виду, по которому можно сравнивать.

    Поставщик пишет одно и то же по-разному: «Stone_Island» в таблице и
    «Stone Island 🅰️» в посте, «Костюм ОЛД МАНИ» и «Костюм  Олд Мани⚜️».
    Отсюда: нижний регистр, эмодзи и пунктуация в пробелы, схлопывание.
    """
    text = unicodedata.normalize("NFKC", title).lower()
    chars = [
        ch if ch.isalnum() else " "
        for ch in text
        if ch.isalnum() or ch.isspace() or unicodedata.category(ch)[0] in "PS"
    ]
    return " ".join("".join(chars).split())


def title_tokens(title: str) -> set[str]:
    """Значимые слова названия: короткие и общевидовые выкидываем."""
    return {t for t in normalize_title(title).split() if len(t) > 2 and t not in _STOPWORDS}


@dataclass
class ItemRef:
    """Позиция прайса в том объёме, в каком её видит привязка."""

    item_id: int
    title: str
    post_url: str | None = None


def match_items_to_posts(
    items: list[ItemRef],
    posts: list[ExportPost],
    *,
    min_overlap: int = 1,
) -> MatchResult:
    """Связать позиции прайса с постами выгрузки.

    Сначала точно — по id поста из `post_url`. Если ссылки нет, пробуем по
    названию: пересечение значимых слов, побеждает пост с наибольшим. Если
    лучших несколько — это `ambiguous`, и позиция **не привязывается**:
    подставить чужое фото хуже, чем не подставить никакого.
    """
    result = MatchResult()
    index = build_post_index(posts)
    by_title = [(post, title_tokens(post.title)) for post in posts if post.photos]

    for item in items:
        post_id = post_id_from_url(item.post_url)
        if post_id is not None:
            post = index.get(post_id)
            if post is None:
                result.missing_in_export.append(item.item_id)
            elif post.photos:
                result.matched[item.item_id] = Match(post=post, way=MatchWay.BY_POST_ID)
            else:
                result.unmatched.append(item.item_id)
            continue

        wanted = title_tokens(item.title)
        if not wanted:
            result.unmatched.append(item.item_id)
            continue

        scored = [(len(wanted & tokens), post) for post, tokens in by_title]
        best = max((score for score, _ in scored), default=0)
        if best < min_overlap:
            result.unmatched.append(item.item_id)
            continue

        winners = [post for score, post in scored if score == best]
        if len(winners) == 1:
            result.matched[item.item_id] = Match(post=winners[0], way=MatchWay.BY_TITLE)
        else:
            result.ambiguous[item.item_id] = winners

    return result
