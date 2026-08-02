"""Затирочное фото — суть затирки (см. AGENTS.md / план): то же изображение,
что и у живой карточки, но убитое размытием, цветовым сдвигом и шумом так,
чтобы товар на нём было невозможно опознать. Используется при переводе
Listing в WIPE_APPLIED (Э7); в отличие от media/variate.py задача здесь не
"немного изменить", а "сделать неузнаваемым".
"""

from __future__ import annotations

import io
import random

import numpy as np
from PIL import Image, ImageFilter

BLUR_RADIUS_PRE = (8.0, 14.0)
BLUR_RADIUS_POST = (3.0, 6.0)
COLOR_SHIFT = (-80, 80)
NOISE_AMPLITUDE = 90
JPEG_QUALITY = (40, 60)


def destroy(data: bytes, *, seed: int | None = None) -> bytes:
    rng = random.Random(seed)

    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(*BLUR_RADIUS_PRE)))
        img = _shift_and_noise(img, rng)
        img = img.filter(ImageFilter.GaussianBlur(radius=rng.uniform(*BLUR_RADIUS_POST)))

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=rng.randint(*JPEG_QUALITY))
        return buf.getvalue()


def _shift_and_noise(img: Image.Image, rng: random.Random) -> Image.Image:
    arr = np.asarray(img).astype(np.int16)

    # Сдвиг по каждому каналу отдельно: блюр съедает форму предмета, а
    # цветовой сдвиг не даёт опознать его даже по силуэту/оттенку.
    shift = np.array([rng.randint(*COLOR_SHIFT) for _ in range(3)], dtype=np.int16)
    arr = np.clip(arr + shift, 0, 255)

    noise_rng = np.random.default_rng(rng.randint(0, 2**31 - 1))
    noise = noise_rng.integers(-NOISE_AMPLITUDE, NOISE_AMPLITUDE + 1, size=arr.shape)
    arr = np.clip(arr + noise, 0, 255).astype("uint8")
    return Image.fromarray(arr)
