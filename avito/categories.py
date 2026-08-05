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
            raise CategoriesNotVerifiedError(
                f"{DATA_PATH.name}: обязательные поля без известных допустимых "
                f"значений: {missing}. Подставлять сюда догадку нельзя — Авито "
                "либо отклонит объявление, либо примет не то. Выписать значения "
                "из шаблона (лист «Объявления», соответствующий столбец) в enums "
                "и очистить unresolved_required_fields."
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
        defaults=raw.get("defaults") or {},
        size_map=raw.get("size_map") or {},
        color_map=raw.get("color_map") or {},
        open_questions=raw.get("open_questions") or [],
    )


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
