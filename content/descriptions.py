"""Рендер описания карточки под конкретный город: свой шаблон, свои факты,
прогон через humanize (план, "Эталоны контента" + "Ключевые решения" —
гео-копии жёстко привязаны к своему шаблону, иначе 5 карточек читаются как
самодубль).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from content.humanize import humanize
from core.models import GeoCity

TEMPLATES_DIR = Path(__file__).parent / "templates"

TEMPLATE_BY_CITY: dict[GeoCity, str] = {
    GeoCity.MSK: "msk.j2",
    GeoCity.SPB: "spb.j2",
    GeoCity.EKB: "ekb.j2",
    GeoCity.KRD: "krd.j2",
    GeoCity.KRSK: "krsk.j2",
}

_env = Environment(
    loader=FileSystemLoader(TEMPLATES_DIR),
    autoescape=select_autoescape(enabled_extensions=()),  # обычный текст, не HTML
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_description(
    city: GeoCity, *, title: str, brand: str | None, color: str | None, sizes: list[str]
) -> str:
    template = _env.get_template(TEMPLATE_BY_CITY[city])
    rendered = template.render(
        title=title,
        brand=brand or "",
        color=color or "не указан",
        sizes=sizes,
    )
    return humanize(rendered)
