"""Линтер отчёта: программный бэкстоп правил подачи V17 (PROMPT_VERSION 3.0).

Промпт сам по себе не даёт 100% — сэмплинг при temp 0.5 дрейфует. Поэтому после
валидации JSON отчёт прогоняется через линтер; найденные нарушения чинятся
повторным текстовым вызовом Gemini (repair pass в gemini.py). Линтер НЕ запрещает
тёплый/личный язык (это новый голос продукта) — он ловит юридически чувствительные
утверждения (диагноз/черты/будущий талант) и брендовые запреты (см. промпт).
"""
from __future__ import annotations

import re

# (паттерн, пояснение для repair-запроса). Паттерны консервативные (границы слов /
# многословные), текст сканируется только в полях отчёта — ложных срабатываний мало.
BANNED_PATTERNS: list[tuple[str, str]] = [
    # дословно запрещённые формулировки
    (r"эмоциональн\w*\s+интеллект\w*", "запрещено «эмоциональный интеллект»"),
    (r"хорош\w+\s+вкус\w*", "запрещено «хороший вкус»"),
    (r"баз\w+\s+для\s+красив\w+\s+почерк\w*", "запрещено «база для красивого почерка»"),
    (r"лайнер\w*", "пиши «линер», не «лайнер»"),
    # командный тон (повелительные советы)
    (r"\b(?:купите|подарите|приобретите|купи|подари)\b", "командный тон — пиши «можно предложить»"),
    (r"\bобязательно\b", "«обязательно» — командный/давящий тон, смягчи"),
    # диагнозы / черты личности / состояния / будущий талант
    (r"тревожност\w+", "диагноз/состояние запрещены"),
    (r"самооценк\w+", "суждение о самооценке запрещено"),
    (r"\bдиагноз\w*", "это не диагностика"),
    (r"внутренн\w+\s+сил\w+", "trait-claim «внутренняя сила» запрещён"),
    (r"(?:станет|будет)\s+(?:художник\w+|артист\w+|дизайнер\w+)", "прогноз будущего таланта запрещён"),
    # символическое преувеличение (приписывание смысла вместо настроения)
    (r"преодолева\w+", "символическое преувеличение — описывай настроение, не смысл"),
]

# контексты, в которых совпадение НЕ считается нарушением
ALLOWED_CONTEXTS = [
    "не является", "не ставим диагноз", "не диагноз", "без диагноз",
    "не оценива", "образовательное наблюдение",
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
