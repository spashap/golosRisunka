"""Образцы отчётов для лендинга — из боевого пайплайна (spec §4.1.3).

Когда заказчик заменит тестовые рисунки финальными, достаточно перегенерировать
отчёты CLI-скриптом и поправить записи здесь.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from config import settings

log = logging.getLogger("samples")


def _first_sentence(text: str, max_len: int = 220) -> str:
    """Первое предложение, не ломаясь на инициалах («Никиты Н.») — точка
    считается концом предложения только после строчной буквы/скобки/кавычки."""
    m = re.search(r"^(.*?[а-яёa-z»\)])\.(?=\s|$)", text)
    s = (m.group(1) + ".") if m else text
    return s if len(s) <= max_len else s[: max_len - 1] + "…"

# Порядок = порядок карточек в карусели. hero=True → полароид на первом экране
# (первые 3 hero). drawings — все рисунки заказа (для сводного отчёта по 2 рисункам
# показываем оба полароида веером). Сводный отчёт по 2 рисункам — в центре карусели.
_SAMPLE_DEFS = [
    dict(token="primer-3-goda", report_dir="data/test_reports/Draw-3_5yr-v1-final",
         drawings=["projectSpec/testDrawings/Draw-3_5yr-v1.png"],
         caption="Алексей, 3,5 года", hero=True, n_drawings=1),
    dict(token="primer-2-risunka", report_dir="data/test_reports/set1-consolidated",
         drawings=["projectSpec/testDrawings/set1-img1.png",
                   "projectSpec/testDrawings/set1-img2.png"],
         caption="«Стич», Алиса, 6 лет", hero=False, n_drawings=2),
    dict(token="primer-6-let", report_dir="data/test_reports/Draw-6yr-v1-final",
         drawings=["projectSpec/testDrawings/Draw-6yr-v1.png"],
         caption="«Семья», Никита, 6 лет", hero=True, n_drawings=1),
    dict(token="primer-8-let", report_dir="data/test_reports/Draw-8yr-v1-final",
         drawings=["projectSpec/testDrawings/Draw-8yr-v1.png"],
         caption="«Кот», Алина, 8 лет", hero=True, n_drawings=1),
]


@dataclass
class Sample:
    token: str
    name: str
    age_display: str
    caption: str
    thumbs: list[dict]         # [{url, w, h}, ...] — один или несколько полароидов
    top_scores: list[dict]     # [{title, score}] — 3 строки для карточки
    badge: str                 # «креативность 8/10»
    quote: str                 # короткая цитата из отчёта (из портрета about_child)
    html_path: Path            # hosted html
    hero: bool = True          # участвует ли в полароидах первого экрана
    n_drawings: int = 1        # бейдж карточки: «пример · 2 рисунка»

    @property
    def thumb_url(self) -> str:        # совместимость: первый рисунок
        return self.thumbs[0]["url"] if self.thumbs else ""


def _thumb_file(path: Path, token: str, idx: int = 0,
                size: int = 560, quality: int = 74) -> dict:
    """Webp-миниатюра в static (spec §4.2: WebP, lazy ниже фолда).
    idx>0 — второй+ рисунок сводного отчёта (имя файла со суффиксом).
    Если миниатюра уже есть (закоммичена/сгенерирована) — отдаём как есть, НЕ
    перезаписываем: иначе на проде git-pull кладёт файлы от root, а веб-процесс
    (www-data) падает при попытке записи → 500 (UseCase: см. ниже)."""
    out_dir = settings.BASE_DIR / "static" / "img" / "samples"
    name = f"{token}.webp" if idx == 0 else f"{token}-{idx}.webp"
    out = out_dir / name
    url = f"/static/img/samples/{name}"
    if out.exists():
        try:
            with Image.open(out) as im0:
                return {"url": url, "w": im0.width, "h": im0.height}
        except Exception:
            pass  # битый файл — перегенерируем ниже
    out_dir.mkdir(parents=True, exist_ok=True)
    im = Image.open(path)
    if im.mode != "RGB":
        bg = Image.new("RGB", im.size, (255, 255, 255))
        bg.paste(im.convert("RGBA"), mask=im.convert("RGBA").split()[-1])
        im = bg
    im.thumbnail((size, size), Image.LANCZOS)
    im.save(out, format="WEBP", quality=quality)
    return {"url": url, "w": im.width, "h": im.height}


def _load() -> list[Sample]:
    samples = []
    for sd in _SAMPLE_DEFS:
        try:
            rdir = settings.BASE_DIR / sd["report_dir"]
            rjson = rdir / "report.json"
            if not rjson.exists():
                continue
            data = json.loads(rjson.read_text(encoding="utf-8"))
            # Карточка ведёт личностью (2.3): первые 3 направления в ПОРЯДКЕ отчёта
            # (личностные впереди), цитата — из портрета about_child, бейдж — сильнейшее.
            dims_order = data["dimensions"]
            dims_top = sorted(data["dimensions"], key=lambda d: -d["score"])
            first_name = data["child"]["name"].split()[0]
            quote = _first_sentence((data.get("about_child") or data["conclusion"]).strip())
            thumbs = [_thumb_file(settings.BASE_DIR / d, sd["token"], i)
                      for i, d in enumerate(sd["drawings"])]
            samples.append(Sample(
                token=sd["token"],
                name=first_name,
                age_display=data["child"]["age_display"],
                caption=sd["caption"],
                thumbs=thumbs,
                top_scores=[{"title": d["title"], "score": d["score"]} for d in dims_order[:3]],
                badge=f"{dims_top[0]['title'].lower()} {dims_top[0]['score']}/10",
                quote=quote,
                html_path=rdir / "report.html",
                hero=sd["hero"],
                n_drawings=sd["n_drawings"],
            ))
        except Exception:  # один сломанный образец не должен ронять страницу (500)
            log.exception("sample %s failed to load — skipped", sd.get("token"))
    return samples


_cache: list[Sample] | None = None


def get_samples() -> list[Sample]:
    global _cache
    if _cache is None:
        _cache = _load()
    return _cache


def get_sample_by_token(token: str) -> Sample | None:
    return next((s for s in get_samples() if s.token == token), None)
