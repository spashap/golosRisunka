"""Вызов Gemini: изображения + контекст → валидированный JSON отчёта.

Отказоустойчивость (spec §7.2): до 5 попыток, невалидный JSON = неудачная
попытка; все сырые ответы сохраняются для отладки.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import ValidationError

from config import settings
from pipeline.images import prepare_image
from pipeline.lint import find_violations
from pipeline.prompt import PROMPT_VERSION, SYSTEM_PROMPT, build_user_prompt
from pipeline.schema import InsufficientReport, Report, validate_report


class ReportGenerationError(Exception):
    """Все попытки исчерпаны. attempts_log — список ошибок по попыткам."""

    def __init__(self, message: str, attempts_log: list[str]):
        super().__init__(message)
        self.attempts_log = attempts_log


@dataclass
class GenerationResult:
    report: Report | InsufficientReport
    raw_json_text: str          # сырой ответ модели — хранить обязательно (spec §5)
    prompt_version: str = PROMPT_VERSION
    model: str = settings.GEMINI_MODEL
    attempts_used: int = 1
    repair_rounds: int = 0      # сколько repair-проходов линтера потребовалось
    lint_hits_left: int = 0     # нарушений осталось после repair (0 = чисто)
    image_jpegs: list[bytes] = field(default_factory=list)  # подготовленные картинки


_REPAIR_INSTRUCTION = """\
Ты редактируешь готовый JSON-отчёт о детском рисунке. В нём найдены формулировки, \
нарушающие правило: запрещены выводы о внутренних состояниях и качествах ребёнка \
(желания, интересы, страхи, смелость, воображение, замысел, эмоции, самооценка).

Перепиши ТОЛЬКО проблемные места, заменив их языком видимых навыков и приёмов \
(например: «не боится листа» -> «уверенно использует всю площадь листа»; \
«интерес к изображению людей» -> «в рисунке появляется фигура человека — важный \
этап для возраста»). Смысл, объём и все остальные части отчёта сохрани без изменений.

Верни ПОЛНЫЙ исправленный JSON той же структуры, без markdown-обёрток."""


def _repair_report(client: "genai.Client", report_dict: dict,
                   violations: list[dict]) -> dict:
    """Текстовый repair-вызов: переписать места, найденные линтером."""
    issues = "\n".join(
        f"- {v['where']}: «{v['match']}» — {v['why']} (контекст: …{v['context']}…)"
        for v in violations
    )
    prompt = (f"{_REPAIR_INSTRUCTION}\n\nНайденные нарушения:\n{issues}\n\n"
              f"JSON отчёта:\n{json.dumps(report_dict, ensure_ascii=False)}")
    resp = client.models.generate_content(
        model=settings.GEMINI_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json", temperature=0.2,
        ),
    )
    return json.loads(_strip_markdown_fence(resp.text or ""))


def _strip_markdown_fence(text: str) -> str:
    """Модель иногда оборачивает JSON в ```json ... ``` вопреки инструкции."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[: -3]
    return t.strip()


def generate_report(image_paths: list[Path], contexts: list[str] | str,
                    common_context: str = "",
                    max_attempts: int = settings.GEMINI_MAX_ATTEMPTS,
                    raw_dump_dir: Path | None = None) -> GenerationResult:
    """contexts: список историй по каждому рисунку (по порядку image_paths);
    строка = один контекст на все рисунки (легаси/один рисунок)."""
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    if isinstance(contexts, str):
        contexts = [contexts] * len(image_paths) if len(image_paths) > 1 else [contexts]
    if len(contexts) != len(image_paths):
        raise ValueError(f"contexts ({len(contexts)}) != images ({len(image_paths)})")

    jpegs = [prepare_image(p) for p in image_paths]
    parts: list = [types.Part.from_bytes(data=j, mime_type="image/jpeg") for j in jpegs]
    parts.append(build_user_prompt(contexts, common_context))

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.5,
    )

    attempts_log: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL, contents=parts, config=config,
            )
            raw = resp.text or ""
            if raw_dump_dir is not None:
                raw_dump_dir.mkdir(parents=True, exist_ok=True)
                (raw_dump_dir / f"attempt_{attempt}.txt").write_text(raw, encoding="utf-8")
            data = json.loads(_strip_markdown_fence(raw))
            report = validate_report(data)

            # лингвистический линтер + repair-проходы (не для insufficient)
            repair_rounds = 0
            violations: list[dict] = []
            if isinstance(report, Report):
                violations = find_violations(report.model_dump())
                while violations and repair_rounds < 2:
                    repair_rounds += 1
                    try:
                        fixed = _repair_report(client, report.model_dump(), violations)
                        candidate = validate_report(fixed)
                        if isinstance(candidate, Report):
                            new_violations = find_violations(candidate.model_dump())
                            if len(new_violations) < len(violations):
                                report, violations = candidate, new_violations
                                continue
                    except (json.JSONDecodeError, ValidationError):
                        pass  # неудачный repair не портит уже валидный отчёт
                    break

            return GenerationResult(
                report=report, raw_json_text=raw,
                attempts_used=attempt, image_jpegs=jpegs,
                repair_rounds=repair_rounds, lint_hits_left=len(violations),
            )
        except (json.JSONDecodeError, ValidationError) as e:
            attempts_log.append(f"attempt {attempt}: invalid output: {e}")
        except Exception as e:  # сетевые/API ошибки — тоже неудачная попытка
            attempts_log.append(f"attempt {attempt}: {type(e).__name__}: {e}")
        if attempt < max_attempts:
            time.sleep(min(5 * attempt, 30))

    raise ReportGenerationError(
        f"Gemini: {max_attempts} попыток исчерпано", attempts_log,
    )
