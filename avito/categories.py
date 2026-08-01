"""Категории и обязательные поля Автозагрузки для «Одежда, обувь, аксессуары».

Источник данных — avito/data/categories_draft.yaml. Пока в нём verified: false,
это ЧЕРНОВИК по открытым источникам, а не факт из ЛК аккаунта или API — см.
комментарий в начале YAML-файла. avito/feed.py обязан звать require_verified()
перед первой боевой публикацией, чтобы не выгрузить в Авито поле или значение,
которого в реальности не существует.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DATA_PATH = Path(__file__).parent / "data" / "categories_draft.yaml"


class CategoriesNotVerifiedError(RuntimeError):
    pass


@dataclass
class CategoriesDoc:
    verified: bool
    verified_at: str | None
    source_note: str
    category_path: str
    common_fields: dict
    goods_types: list[dict]
    open_questions: list[str]

    def goods_type_by_key(self, key: str) -> dict:
        for gt in self.goods_types:
            if gt["key"] == key:
                return gt
        raise KeyError(f"Неизвестный goods_type key: {key}")

    def require_verified(self) -> None:
        if not self.verified:
            raise CategoriesNotVerifiedError(
                "avito/data/categories_draft.yaml всё ещё verified: false. "
                "Это черновик по открытым источникам, не сверенный с ЛК Авито. "
                "Сверить категории и обязательные поля через ЛК → Автозагрузка → "
                "Правила и шаблоны, обновить файл и выставить verified: true, "
                "прежде чем публиковать реальные объявления."
            )


def load_categories(path: Path = DATA_PATH) -> CategoriesDoc:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return CategoriesDoc(
        verified=raw.get("verified", False),
        verified_at=raw.get("verified_at"),
        source_note=raw.get("source_note", ""),
        category_path=raw.get("category_path", ""),
        common_fields=raw.get("common_fields", {}),
        goods_types=raw.get("goods_types", []),
        open_questions=raw.get("open_questions", []),
    )


def render_markdown(doc: CategoriesDoc) -> str:
    """Человекочитаемый дамп для docs/categories.md — то, что заказчик
    сверяет и отмечает "берём в работу", см. план, раздел "Категории Авито".
    """
    lines: list[str] = []
    status = "✅ сверено с ЛК" if doc.verified else "⚠️ ЧЕРНОВИК — не сверено с ЛК"
    lines.append(f"# Категории Авито: {doc.category_path}")
    lines.append("")
    lines.append(f"**Статус:** {status}")
    if doc.source_note:
        lines.append(f"**Источник:** {doc.source_note}")
    lines.append("")

    lines.append("## Общие поля")
    for name, meta in doc.common_fields.items():
        req = "обязательное" if meta.get("required") else "опциональное"
        note = f" — {meta['note']}" if meta.get("note") else ""
        value = f" (значение: `{meta['value']}`)" if meta.get("value") else ""
        lines.append(f"- `{name}` — {req}{value}{note}")
    lines.append("")

    lines.append("## Типы товара")
    for gt in doc.goods_types:
        lines.append(f"### {gt['label_ru']} (`{gt['key']}`)")
        lines.append(f"- `GoodsType` = `{gt['avito_goods_type']}`")
        for name, meta in gt.get("extra_fields", {}).items():
            req = "обязательное" if meta.get("required") else "опциональное"
            note = f" — {meta['note']}" if meta.get("note") else ""
            value = f" (значение: `{meta['value']}`)" if meta.get("value") else ""
            lines.append(f"- `{name}` — {req}{value}{note}")
        lines.append("")

    if doc.open_questions:
        lines.append("## Открытые вопросы (закрыть перед verified: true)")
        for q in doc.open_questions:
            lines.append(f"- [ ] {q}")
        lines.append("")

    return "\n".join(lines)
