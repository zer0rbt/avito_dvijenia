from __future__ import annotations

import pytest

from content.humanize import HumanizeViolationError, autofix, humanize, lint


def test_autofix_replaces_em_and_en_dash_with_hyphen():
    assert autofix("Размер — М, доставка – быстро") == "Размер - М, доставка - быстро"


def test_humanize_returns_clean_text_unchanged_except_dashes():
    text = "Бренд Balenciaga. Размеры S M L. Цвет черный - в наличии."
    assert humanize(text) == text


def test_lint_flags_banned_original_word():
    violations = lint("Продаём только оригинал, не реплику")
    assert any("оригинал" in v for v in violations)
    assert any("реплик" in v for v in violations)


def test_lint_flags_gpt_phrase_markers():
    violations = lint("Важно отметить, что этот товар качественный")
    assert violations


def test_humanize_raises_on_banned_terms():
    with pytest.raises(HumanizeViolationError):
        humanize("Это точная реплика культовой модели")


def test_humanize_raises_on_gpt_phrase():
    with pytest.raises(HumanizeViolationError):
        humanize("Стоит подчеркнуть отличное качество пошива")


def test_lint_is_case_insensitive():
    assert lint("ОРИГИНАЛ")
