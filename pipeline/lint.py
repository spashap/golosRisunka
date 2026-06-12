"""Линтер отчёта: ловит язык внутренних состояний (запрет §7.4 / промпт-правило 6).

Промпт сам по себе не даёт 100% — сэмплинг дрейфует. Поэтому после валидации
JSON отчёт прогоняется через линтер; найденные нарушения чинятся повторным
текстовым вызовом Gemini (repair pass в gemini.py).
"""
from __future__ import annotations

import re

# (паттерн, пояснение для repair-запроса)
BANNED_PATTERNS: list[tuple[str, str]] = [
    (r"желани\w+", "«желание» ребёнка — вывод о внутреннем состоянии"),
    (r"интерес\w*\s+(?:к|ребёнка|ребенка)\s", "«интерес к …» — вывод о внутреннем состоянии"),
    (r"бо(?:ится|язн\w*)|страх\w*", "страх/бесстрашие — вывод о внутреннем состоянии"),
    (r"смелост\w+", "«смелость» — черта характера, не навык"),
    (r"воображени\w+", "«воображение» — внутреннее качество; пиши о видимых приёмах"),
    (r"замыс(?:ел|л\w+)", "«замысел» — недоступен наблюдению"),
    (r"тревож\w+|самооценк\w+|внутренн\w+\s+мир", "психологические состояния запрещены"),
    (r"уверенность в себе|уверен\w* в себе", "самоуверенность — черта личности"),
    (r"свидетельствует о развит\w+", "барнум-формула; привяжи к видимой детали"),
]

# контексты, в которых совпадение НЕ считается нарушением
ALLOWED_CONTEXTS = [
    "не является", "не оценива", "а не эмоциональн", "не делает вывод",
    "выразительность", "образовательное наблюдение",
]

# поля, которые проверяем (activities не проверяем: там «передать настроение
# сцены» и т.п. — легитимные задания, а не выводы о ребёнке)
_CHECK_FIELDS = ("context_summary", "introduction", "conclusion")


def _scan(text: str, where: str) -> list[dict]:
    hits = []
    for pattern, why in BANNED_PATTERNS:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            s, e = max(0, m.start() - 80), min(len(text), m.end() + 80)
            ctx = text[s:e]
            if any(a in ctx.lower() for a in ALLOWED_CONTEXTS):
                continue
            hits.append({"where": where, "match": m.group(0), "why": why, "context": ctx})
    return hits


def find_violations(report_data: dict) -> list[dict]:
    """report_data — dict валидированного отчёта (model_dump)."""
    hits: list[dict] = []
    for f in _CHECK_FIELDS:
        if report_data.get(f):
            hits.extend(_scan(str(report_data[f]), f))
    for i, d in enumerate(report_data.get("dimensions") or []):
        for f in ("observation", "research_note"):
            if d.get(f):
                hits.extend(_scan(str(d[f]), f"dimensions[{i}].{f} ({d.get('title')})"))
    for i, r in enumerate(report_data.get("recommendations") or []):
        hits.extend(_scan(str(r), f"recommendations[{i}]"))
    for i, dd in enumerate(report_data.get("development_directions") or []):
        hits.extend(_scan(str(dd.get("text", "")), f"development_directions[{i}]"))
    return hits
