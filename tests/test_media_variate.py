from __future__ import annotations

import io

from PIL import Image, ImageDraw

from media.phash import compute_phash, hamming_distance
from media.variate import variate


def _sample_photo_bytes() -> bytes:
    """Не однотонная заглушка — с структурой (иначе phash вырожденный и не
    отличит "то же фото" от "случайный шум")."""
    img = Image.new("RGB", (200, 200), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.ellipse((40, 40, 160, 160), fill=(30, 80, 180))
    draw.rectangle((0, 0, 60, 200), fill=(200, 60, 60))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_variate_returns_valid_jpeg_of_similar_size():
    data = _sample_photo_bytes()
    out = variate(data, seed=1)
    with Image.open(io.BytesIO(out)) as img:
        assert img.format == "JPEG"
        assert img.size[0] > 150 and img.size[1] > 150  # лёгкий кроп, не разгром


def test_variate_changes_bytes_but_keeps_recognizable_image():
    data = _sample_photo_bytes()
    out = variate(data, seed=1)
    assert out != data

    original_hash = compute_phash(data)
    variated_hash = compute_phash(out)
    # мягкая уникализация — не должна разрушать сходство настолько, чтобы
    # антидубль перестал видеть то же фото, если это фото первой публикации
    assert hamming_distance(original_hash, variated_hash) <= 20


def test_variate_is_deterministic_for_same_seed():
    data = _sample_photo_bytes()
    assert variate(data, seed=42) == variate(data, seed=42)


def test_variate_differs_between_seeds():
    data = _sample_photo_bytes()
    assert variate(data, seed=1) != variate(data, seed=2)
