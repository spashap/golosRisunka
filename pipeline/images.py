"""Подготовка изображений: jpg/png/heic → RGB JPEG, длинная сторона ≤ 2000px (spec §6)."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image
from pillow_heif import register_heif_opener

from config import settings

register_heif_opener()  # после этого PIL открывает .heic как обычные файлы


def prepare_image(path: Path, max_side: int = settings.IMAGE_MAX_LONG_SIDE) -> bytes:
    """Возвращает JPEG-байты, готовые и для Gemini, и для data URI отчёта."""
    im = Image.open(path)
    if im.mode != "RGB":
        # RGBA/P на белом фоне, не на чёрном
        background = Image.new("RGB", im.size, (255, 255, 255))
        background.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = background
    if max(im.size) > max_side:
        im.thumbnail((max_side, max_side), Image.LANCZOS)
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=90)
    return buf.getvalue()
