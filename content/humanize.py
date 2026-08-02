"""Линтер и авто-фиксер сгенерированного/синонимизированного текста (Э4).

Два независимых списка правил (план, "Эталоны контента"):
1. GPT-маркеры — характерные обороты нейросетевого текста. Длинное/среднее
   тире чинится автозаменой (в русском тексте норма — дефис), остальное —
   жёсткий запрет: автоматическая переформулировка потребовала бы ещё одной
   генерации текста, а не работы линтера.
2. Деny-list "оригинал"/"реплика" — жёсткое бизнес-правило ("ни слова про
   оригинал и реплику — ни в заголовке, ни в описании, ни в переписке"),
   исключений нет и автозамены нет: если слово просочилось, это баг
   генератора/словаря синонимов, который надо найти, а не скрыть.
"""

from __future__ import annotations

import re


class HumanizeViolationError(ValueError):
    def __init__(self, violations: list[str]):
        self.violations = violations
        super().__init__("; ".join(violations))


# Автозамена: символ -> замена.
_AUTO_FIX = {
    "—": "-",
    "–": "-",
}

# Не чинится автоматически — наличие означает, что текст съехал в
# характерный ИИ-канцелярит. Лечится правкой шаблона/словаря синонимов,
# не автоподстановкой (заменить "важно отметить" не на что без потери смысла).
_GPT_PHRASE_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"не просто [^,]+, а ",
        r"это не только[^.]*,?\s*но и",
        r"важно отметить",
        r"стоит подчеркнуть",
        r"в современном мире",
        r"хочется отметить",
    ]
]

# План: ни слова про оригинал/реплику нигде в тексте. Основа слова, а не
# точная форма — русский язык склоняет ("реплику", "репликам", "оригинала").
_BANNED_TERMS = [
    "оригинал",
    "original",
    "реплик",
    "replica",
    "копия",
    "люкс-копия",
    "люкс копия",
    "aaa класс",
]


def autofix(text: str) -> str:
    for bad, good in _AUTO_FIX.items():
        text = text.replace(bad, good)
    return text


def lint(text: str) -> list[str]:
    """Список нарушений, не устранённых автозаменой. Пустой список — текст чист."""
    violations = []
    for pattern in _GPT_PHRASE_PATTERNS:
        if pattern.search(text):
            violations.append(f"похоже на ИИ-канцелярит: {pattern.pattern!r}")

    lowered = text.lower()
    for term in _BANNED_TERMS:
        if term in lowered:
            violations.append(f"запрещённое слово: {term!r}")

    return violations


def humanize(text: str) -> str:
    """Автозамена + жёсткая проверка. Бросает HumanizeViolationError, если
    что-то не лечится подстановкой — вызывающий код (content/descriptions.py,
    content/respin.py) не должен публиковать текст, не прошедший линтер."""
    text = autofix(text)
    violations = lint(text)
    if violations:
        raise HumanizeViolationError(violations)
    return text
