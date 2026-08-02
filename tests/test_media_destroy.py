from __future__ import annotations

import io

import numpy as np
from PIL import Image, ImageDraw

from media.destroy import destroy


def _sample_photo_bytes() -> bytes:
    img = Image.new("RGB", (200, 200), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.ellipse((40, 40, 160, 160), fill=(30, 80, 180))
    draw.rectangle((0, 0, 60, 200), fill=(200, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def _mean_abs_pixel_diff(a: bytes, b: bytes) -> float:
    with Image.open(io.BytesIO(a)) as ia, Image.open(io.BytesIO(b)) as ib:
        arr_a = np.asarray(ia.convert("RGB")).astype(int)
        arr_b = np.asarray(ib.convert("RGB")).astype(int)
        return float(np.abs(arr_a - arr_b).mean())


def test_destroy_returns_valid_jpeg_of_same_size():
    data = _sample_photo_bytes()
    out = destroy(data, seed=1)
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG"
        assert img.size == (200, 200)  # затирка не кадрирует, только убивает содержимое


def test_destroy_makes_image_unrecognizable():
    """Смысл затирки — предмет на фото нельзя опознать (см. план). pHash тут
    неудачная метрика: он устойчив к блюру, потому что берёт только низкие
    частоты DCT (в отличие от media/variate.py, где блюра и цветосдвига
    нет). Поэтому проверяем прямо — среднее попиксельное отличие от
    оригинала должно быть большим: цвет и детали основательно убиты."""
    data = _sample_photo_bytes()
    out = destroy(data, seed=1)
    assert _mean_abs_pixel_diff(data, out) > 20


def test_destroy_is_deterministic_for_same_seed():
    data = _sample_photo_bytes()
    assert destroy(data, seed=7) == destroy(data, seed=7)
