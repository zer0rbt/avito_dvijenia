from __future__ import annotations

from content.descriptions import render_description
from content.respin import respin
from core.models import GeoCity

BASE = render_description(
    GeoCity.MSK, title="Balenciaga Arena", brand="Balenciaga", color="Черный", sizes=["S", "M", "L"]
)


def test_respin_keeps_facts_intact():
    out = respin(BASE, seed=1)
    assert "Balenciaga Arena" in out
    assert "Черный" in out
    assert "Balenciaga" in out
    assert "S" in out and "M" in out and "L" in out


def test_respin_is_deterministic_for_same_seed():
    assert respin(BASE, seed=7) == respin(BASE, seed=7)


def test_respin_produces_different_text_for_different_seeds():
    versions = {respin(BASE, seed=i) for i in range(5)}
    assert len(versions) > 1


def test_respin_output_passes_humanize():
    # respin() уже прогоняет через humanize внутри, но проверим явно —
    # ни один из вариантов не должен содержать запрещённых слов
    for i in range(5):
        out = respin(BASE, seed=i).lower()
        assert "оригинал" not in out
        assert "реплик" not in out
