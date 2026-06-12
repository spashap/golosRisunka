"""Образцы отчётов для лендинга — из боевого пайплайна M3 (spec §4.1.3).

Когда заказчик заменит тестовые рисунки финальными, достаточно перегенерировать
отчёты CLI-скриптом и поправить записи здесь.
"""
from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from config import settings

# (token, каталог отчёта, файл рисунка, подпись полароида, бейдж берётся из top-оценки)
_SAMPLE_DEFS = [
    ("primer-3-goda", "data/test_reports/Draw-3_5yr-v1-final",
     "projectSpec/testDrawings/Draw-3_5yr-v1.png", "Алексей, 3,5 года"),
    ("primer-6-let", "data/test_reports/Draw-6yr-v1-final",
     "projectSpec/testDrawings/Draw-6yr-v1.png", "«Семья», Никита, 6 лет"),
    ("primer-8-let", "data/test_reports/Draw-8yr-v1-final",
     "projectSpec/testDrawings/Draw-8yr-v1.png", "«Кот», Алина, 8 лет"),
]


@dataclass
class Sample:
    token: str
    name: str
    age_display: str
    caption: str
    thumb_url: str             # /static/img/samples/<token>.webp (кэшируемо, lazy)
    thumb_w: int
    thumb_h: int
    top_scores: list[dict]     # [{title, score}] — 3 строки для карточки
    badge: str                 # «креативность 8/10»
    quote: str                 # короткая цитата из отчёта
    html_path: Path            # hosted html


def _thumb_file(path: Path, token: str, size: int = 480, quality: int = 72) -> tuple[str, int, int]:
    """Webp-миниатюра в static (spec §4.2: WebP с width/height, lazy ниже фолда)."""
    out_dir = settings.BASE_DIR / "static" / "img" / "samples"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{token}.webp"
    im = Image.open(path)
    if im.mode != "RGB":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
    im.thumbnail((size, size), Image.LANCZOS)
    im.save(out, format="WEBP", quality=quality)
    return f"/static/img/samples/{token}.webp", im.width, im.height


def _load() -> list[Sample]:
    samples = []
    for token, report_dir, drawing, caption in _SAMPLE_DEFS:
        rdir = settings.BASE_DIR / report_dir
        rjson = rdir / "report.json"
        if not rjson.exists():
            continue
        data = json.loads(rjson.read_text(encoding="utf-8"))
        dims = sorted(data["dimensions"], key=lambda d: -d["score"])
        first_name = data["child"]["name"].split()[0]
        quote = data["conclusion"].split(". ")[0].strip() + "."
        thumb_url, tw, th = _thumb_file(settings.BASE_DIR / drawing, token)
        samples.append(Sample(
            token=token,
            name=first_name,
            age_display=data["child"]["age_display"],
            caption=caption,
            thumb_url=thumb_url, thumb_w=tw, thumb_h=th,
            top_scores=[{"title": d["title"], "score": d["score"]} for d in dims[:3]],
            badge=f"{dims[0]['title'].lower()} {dims[0]['score']}/10",
            quote=quote if len(quote) < 220 else quote[:217] + "…",
            html_path=rdir / "report.html",
        ))
    return samples


_cache: list[Sample] | None = None


def get_samples() -> list[Sample]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def get_sample_by_token(token: str) -> Sample | None:
    return next((s for s in get_samples() if s.token == token), None)
