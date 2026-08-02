from __future__ import annotations

import io

from PIL import Image, ImageDraw

from media.phash import compute_phash, hamming_distance, is_duplicate


def _solid_image_bytes(color: tuple[int, int, int], size: tuple[int, int] = (64, 64)) -> bytes:
    img = Image.new("RGB", size, color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _two_corners_image_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), color=(240, 240, 240))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 20, 20), fill=(10, 10, 10))
    draw.rectangle((44, 44, 64, 64), fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _center_circle_image_bytes() -> bytes:
    img = Image.new("RGB", (64, 64), color=(240, 240, 240))
    ImageDraw.Draw(img).ellipse((16, 16, 48, 48), fill=(10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def test_compute_phash_is_stable_for_same_image():
    data = _solid_image_bytes((200, 50, 50))
    assert compute_phash(data) == compute_phash(data)


def test_hamming_distance_zero_for_identical_hash():
    data = _solid_image_bytes((10, 10, 200))
    h = compute_phash(data)
    assert hamming_distance(h, h) == 0
    assert is_duplicate(h, h)


def test_different_images_are_not_duplicates():
    corners = compute_phash(_two_corners_image_bytes())
    circle = compute_phash(_center_circle_image_bytes())
    assert not is_duplicate(corners, circle)
