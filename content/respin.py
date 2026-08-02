"""Синонимизация текста поверх уже отрендеренного описания города — под
перезалив (план, "Синонимизация при перезаливе"). Не трогает шаблон и не
трогает факты (размеры/цвет/бренд/цена уже вписаны в текст до вызова
respin и остаются как есть) — только формулировки обвязки и порядок строк
внутри списков/инструкции.
"""

from __future__ import annotations

import random
import re

from content.humanize import humanize

# Синонимичные варианты связок/вводных фраз. Каждый список — взаимозаменяемые
# формулировки одного смысла; ключ ищется как подстрока, без учёта регистра.
_SYNONYMS: dict[str, list[str]] = {
    "в наличии": ["в наличии", "есть в наличии", "доступно к заказу", "можно заказать"],
    "напишите нам": ["напишите нам", "пишите нам", "напишите", "оставьте сообщение"],
    "по всей россии": ["по всей России", "во все регионы России", "в любой регион РФ"],
    "будем рады": ["будем рады", "будем признательны", "рады"],
}


def _resynonymize(text: str, rng: random.Random) -> str:
    for phrase, variants in _SYNONYMS.items():
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        text = pattern.sub(lambda _m, v=variants: rng.choice(v), text)
    return text


def _shuffle_longest_line_block(text: str, rng: random.Random) -> str:
    """Перемешивает порядок строк внутри самого длинного непрерывного блока
    непустых строк (обычно это и есть список пунктов/инструкция, которую
    план просит разводить перестановкой) — не трогает пустые строки-разделители
    между абзацами, поэтому структура текста не разваливается."""
    lines = text.split("\n")
    best_start, best_len = None, 0
    run_start = None
    for i, line in enumerate([*lines, ""]):
        if line.strip():
            if run_start is None:
                run_start = i
        else:
            if run_start is not None:
                run_len = i - run_start
                if run_len > best_len:
                    best_start, best_len = run_start, run_len
            run_start = None

    if best_start is None or best_len < 3:
        return text

    block = lines[best_start : best_start + best_len]
    rng.shuffle(block)
    lines[best_start : best_start + best_len] = block
    return "\n".join(lines)


def respin(text: str, *, seed: int) -> str:
    rng = random.Random(seed)
    text = _resynonymize(text, rng)
    text = _shuffle_longest_line_block(text, rng)
    return humanize(text)
