"""Образцы отчётов для лендинга — из боевого пайплайна M3 (spec §4.1.3).

Когда заказчик заменит тестовые рисунки финальными, достаточно перегенерировать
отчёты CLI-скриптом и поправить записи здесь.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from config import settings


def _first_sentence(text: str, max_len: int = 220) -> str:
    """Первое предложение, не ломаясь на инициалах («Никиты Н.») — точка
    считается концом предложения только после строчной буквы/скобки/кавычки."""
    m = re.search(r"^(.*?[а-яёa-z»\)])\.(?=\s|$)", text)
    s = (m.group(1) + ".") if m else text
    return s if len(s) <= max_len else s[: max_len - 1] + "…"

# Порядок = порядок карточек в карусели. hero=True → полароид на первом экране
# (первые 3 hero). Сводный отчёт по 2 рисункам — в центре карусели (решение заказчика).
_SAMPLE_DEFS = [
    dict(token="primer-3-goda", report_dir="data/test_reports/Draw-3_5yr-v1-final",
         drawing="projectSpec/testDrawings/Draw-3_5yr-v1.png",
         caption="Алексей, 3,5 года", hero=True, n_drawings=1),
    dict(token="primer-2-risunka", report_dir="data/test_reports/set1-consolidated",
         drawing="projectSpec/testDrawings/set1-img1.png",
         caption="«Стич», Алиса, 6 лет", hero=False, n_drawings=2),
    dict(token="primer-6-let", report_dir="data/test_reports/Draw-6yr-v1-final",
         drawing="projectSpec/testDrawings/Draw-6yr-v1.png",
         caption="«Семья», Никита, 6 лет", hero=True, n_drawings=1),
    dict(token="primer-8-let", report_dir="data/test_reports/Draw-8yr-v1-final",
         drawing="projectSpec/testDrawings/Draw-8yr-v1.png",
         caption="«Кот», Алина, 8 лет", hero=True, n_drawings=1),
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
    hero: bool = True          # участвует ли в полароидах первого экрана
    n_drawings: int = 1        # бейдж карточки: «пример · 2 рисунка»


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
    for sd in _SAMPLE_DEFS:
        rdir = settings.BASE_DIR / sd["report_dir"]
        rjson = rdir / "report.json"
        if not rjson.exists():
            continue
        data = json.loads(rjson.read_text(encoding="utf-8"))
        dims = sorted(data["dimensions"], key=lambda d: -d["score"])
        first_name = data["child"]["name"].split()[0]
        quote = _first_sentence(data["conclusion"].strip())
        thumb_url, tw, th = _thumb_file(settings.BASE_DIR / sd["drawing"], sd["token"])
        samples.append(Sample(
            token=sd["token"],
            name=first_name,
            age_display=data["child"]["age_display"],
            caption=sd["caption"],
            thumb_url=thumb_url, thumb_w=tw, thumb_h=th,
            top_scores=[{"title": d["title"], "score": d["score"]} for d in dims[:3]],
            badge=f"{dims[0]['title'].lower()} {dims[0]['score']}/10",
            quote=quote,
            html_path=rdir / "report.html",
            hero=sd["hero"],
            n_drawings=sd["n_drawings"],
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
