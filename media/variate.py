"""Мягкая уникализация фото: поворот, отражение, кроп, лёгкий шум,
пересборка EXIF, recompress — чтобы файл того же фото не совпадал байт в
байт при повторной публикации/перезаливе (антидубль Авито матчит и по
фото, см. план "Уникализация при перезаливе"). Не для затирки — для этого
media/destroy.py, там задача обратная: сделать товар неопознаваемым.
"""

from __future__ import annotations

import io
import random

import numpy as np
from PIL import Image, ImageOps

ROTATE_DEGREES = (-4.0, 4.0)
CROP_FRACTION = (0.02, 0.05)
NOISE_AMPLITUDE = 6
JPEG_QUALITY = (82, 93)


def variate(data: bytes, *, seed: int | None = None) -> bytes:
    """Возвращает новый JPEG. Детерминировано при заданном seed — удобно
    для тестов и для устойчивого дифа между версиями одного фото."""
    rng = random.Random(seed)

    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")

        angle = rng.uniform(*ROTATE_DEGREES)
        img = img.rotate(angle, resample=Image.BICUBIC, expand=False, fillcolor=(255, 255, 255))

        if rng.random() < 0.5:
            img = ImageOps.mirror(img)

        img = _light_crop(img, rng)
        img = _add_light_noise(img, rng)

        # EXIF намеренно не переносим (PIL по умолчанию не пишет его без
        # exif=) — исходные метаданные устройства/даты съёмки сюда не попадают.
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=rng.randint(*JPEG_QUALITY))
        return buf.getvalue()


def _light_crop(img: Image.Image, rng: random.Random) -> Image.Image:
    width, height = img.size
    frac = rng.uniform(*CROP_FRACTION)
    left = int(width * frac * rng.random())
    top = int(height * frac * rng.random())
    right = width - int(width * frac * rng.random())
    bottom = height - int(height * frac * rng.random())
    if right <= left or bottom <= top:
        return img
    return img.crop((left, top, right, bottom))


def _add_light_noise(img: Image.Image, rng: random.Random) -> Image.Image:
    arr = np.asarray(img).astype(np.int16)
    noise_rng = np.random.default_rng(rng.randint(0, 2**31 - 1))
    noise = noise_rng.integers(-NOISE_AMPLITUDE, NOISE_AMPLITUDE + 1, size=arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype("uint8")
    return Image.fromarray(arr)
