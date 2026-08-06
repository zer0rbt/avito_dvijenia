"""Схема полей Автозагрузки для «Одежда, обувь, аксессуары».

Источник данных — avito/data/categories.yaml, свёрстанный из официальных
шаблонов Авито (xlsx + XML, скачаны заказчиком из ЛК 03.08.2026). Раньше
здесь лежал черновик по открытым гайдам, и он врал в трёх местах сразу:
`Category` был «Личные вещи» вместо «Одежда, обувь, аксессуары», половина
обязательных тегов отсутствовала, а `AdStatus` считался способом уйти в
архив — хотя это платное продвижение (см. B-002).

Рубильник остался, но стал строже: `require_verified()` падает и когда
`verified: false`, и когда в `unresolved_required_fields` что-то есть.
Второе — про поля, которые Авито считает обязательными, а мы не знаем их
допустимых значений; публиковать с выдуманным значением хуже, чем не
публиковать.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

DATA_PATH = Path(__file__).parent / "data" / "categories.yaml"


class CategoriesNotVerifiedError(RuntimeError):
    pass


@dataclass
class CategoriesDoc:
    verified: bool
    verified_at: str | None
    verified_by: str | None
    source_note: str
    category_path: str
    template_id: int | None = None
    unresolved_required_fields: list[str] = field(default_factory=list)
    feed: dict = field(default_factory=dict)
    required_tags: list[str] = field(default_factory=list)
    conditionally_required_tags: list[str] = field(default_factory=list)
    enums: dict[str, list[str]] = field(default_factory=dict)
    # Ответы заказчика по смыслу, чьё дословное написание не подтверждено.
    # Намеренно отдельно от enums: is_allowed() их не видит, в фид они не
    # попадают, публикацию не разблокируют. Нужны только чтобы подсказка
    # «что скорее всего имелось в виду» не потерялась.
    candidates: dict[str, list[str]] = field(default_factory=dict)
    defaults: dict[str, str] = field(default_factory=dict)
    size_map: dict[str, str] = field(default_factory=dict)
    color_map: dict[str, str] = field(default_factory=dict)
    open_questions: list[str] = field(default_factory=list)

    def allowed(self, tag: str) -> list[str]:
        return self.enums.get(tag, [])

    def is_allowed(self, tag: str, value: str) -> bool:
        """Нет справочника по тегу -> ничего не утверждаем (True). Есть ->
        сверяем строкой, ровно как Авито: регистр и NBSP значимы."""
        allowed = self.enums.get(tag)
        return True if allowed is None else value in allowed

    def require_verified(self) -> None:
        if not self.verified:
            raise CategoriesNotVerifiedError(
                f"{DATA_PATH.name}: verified: false. Схема не сверена с шаблонами "
                "Авито — публиковать нельзя. Сверить с ЛК → Автозагрузка → "
                "Правила и шаблоны и выставить verified: true."
            )
        if self.unresolved_required_fields:
            missing = ", ".join(self.unresolved_required_fields)
            hints = [
                f"{tag}: похоже на {', '.join(repr(v) for v in values)}"
                for tag, values in self.candidates.items()
                if tag in self.unresolved_required_fields
            ]
            hint_text = f" Кандидаты (не подтверждены): {'; '.join(hints)}." if hints else ""
            raise CategoriesNotVerifiedError(
                f"{DATA_PATH.name}: обязательные поля без известных допустимых "
                f"значений: {missing}. Подставлять сюда догадку нельзя — Авито "
                "либо отклонит объявление, либо примет не то."
                f"{hint_text} Узнать точное значение и закрыть одной командой: "
                f"python cli.py categories resolve-field {missing.split(', ')[0]} "
                '"<точное значение>"'
            )


def load_categories(path: Path = DATA_PATH) -> CategoriesDoc:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return CategoriesDoc(
        verified=raw.get("verified", False),
        verified_at=raw.get("verified_at"),
        verified_by=raw.get("verified_by"),
        source_note=raw.get("source_note", ""),
        category_path=raw.get("category_path", ""),
        template_id=raw.get("template_id"),
        unresolved_required_fields=raw.get("unresolved_required_fields") or [],
        feed=raw.get("feed") or {},
        required_tags=raw.get("required_tags") or [],
        conditionally_required_tags=raw.get("conditionally_required_tags") or [],
        enums=raw.get("enums") or {},
        candidates=raw.get("candidates") or {},
        defaults=raw.get("defaults") or {},
        size_map=raw.get("size_map") or {},
        color_map=raw.get("color_map") or {},
        open_questions=raw.get("open_questions") or [],
    )


def resolve_field(tag: str, values: list[str], path: Path = DATA_PATH) -> None:
    """Записать допустимые значения обязательного поля и снять с него блок.

    Правит YAML целиком через yaml.safe_dump — комментарии файла при этом
    теряются, поэтому вызывать это стоит только ради полей из
    `unresolved_required_fields`, а не как общий редактор схемы.

    Значения не выдумываем: сюда попадает то, что человек прочитал в ЛК или
    подтвердил валидатором Авито (https://autoload.avito.ru/format/xmlcheck/).
    """
    if not values:
        raise ValueError("нужно хотя бы одно значение — пустой справочник ничего не разблокирует")

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    unresolved = raw.get("unresolved_required_fields") or []
    if tag not in unresolved and tag not in (raw.get("required_tags") or []):
        raise ValueError(f"{tag} не значится обязательным полем в {path.name}")

    raw.setdefault("enums", {})[tag] = values
    raw["unresolved_required_fields"] = [f for f in unresolved if f != tag]
    candidates = raw.get("candidates") or {}
    candidates.pop(tag, None)
    if candidates:
        raw["candidates"] = candidates
    else:
        raw.pop("candidates", None)

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(raw, f, allow_unicode=True, sort_keys=False, width=100)


def render_markdown(doc: CategoriesDoc) -> str:
    """Человекочитаемый дамп для docs/categories.md — то, что заказчик
    сверяет глазами с ЛК."""
    lines: list[str] = []
    if not doc.verified:
        status = "⚠️ НЕ СВЕРЕНО с шаблонами Авито"
    elif doc.unresolved_required_fields:
        status = "🟡 сверено, но публикация заблокирована: нет значений для " + ", ".join(
            f"`{f}`" for f in doc.unresolved_required_fields
        )
    else:
        status = "✅ сверено с шаблонами Авито"

    lines.append(f"# Категории Авито: {doc.category_path}")
    lines.append("")
    lines.append(f"**Статус:** {status}")
    if doc.verified_by:
        lines.append(f"**Источник:** {doc.verified_by}")
    if doc.verified_at:
        lines.append(f"**Сверено:** {doc.verified_at}")
    if doc.template_id:
        lines.append(f"**Template id:** `{doc.template_id}`")
    lines.append("")

    lines.append("## Обязательные теги")
    for tag in doc.required_tags:
        mark = " ← значений не знаем" if tag in doc.unresolved_required_fields else ""
        lines.append(f"- `{tag}`{mark}")
    lines.append("")

    if doc.conditionally_required_tags:
        lines.append("## Может быть обязательным")
        for tag in doc.conditionally_required_tags:
            lines.append(f"- `{tag}`")
        lines.append("")

    lines.append("## Наши постоянные значения")
    for tag, value in doc.defaults.items():
        lines.append(f"- `{tag}` = `{value}`")
    lines.append("")

    lines.append("## Справочники допустимых значений")
    for tag, values in doc.enums.items():
        lines.append(f"### `{tag}`")
        lines.append(", ".join(f"`{v}`" for v in values))
        lines.append("")

    lines.append("## Размеры: сетка поставщика → Авито")
    for supplier, avito in doc.size_map.items():
        lines.append(f"- `{supplier}` → `{avito}`")
    lines.append("")

    if doc.open_questions:
        lines.append("## Открытые вопросы")
        for q in doc.open_questions:
            lines.append(f"- [ ] {q}")
        lines.append("")

    return "\n".join(lines)
