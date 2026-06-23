"""Вызов Gemini: изображения + контекст → валидированный JSON отчёта.

Отказоустойчивость (spec §7.2): до 5 попыток, невалидный JSON = неудачная
попытка; все сырые ответы сохраняются для отладки.
"""
from __future__ import annotations

import json
import logging
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

log = logging.getLogger("gemini")


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
Ты редактируешь готовый JSON-отчёт о детском рисунке в тёплом, личном стиле «Голос \
рисунка» (философия 2.3: портрет ребёнка как личности). Глубина про самого ребёнка — \
ценность продукта, её НЕЛЬЗЯ выхолащивать. Найдены места, где интерпретация подана без \
безопасной оправы или нарушает жёсткие запреты.

КАК ЧИНИТЬ:
- Где речь об эмоции/настроении/состоянии/темпераменте/характере ребёнка стоит БЕЗ \
оправы — НЕ удаляй смысл, а ДОБАВЬ безопасную оправу из четырёх условий: \
(1) атрибуция к реальной традиции/автору («в проективной традиции (Маховер, 1949) это \
связывают с…», «согласно Ловенфельду…»); (2) гипотезный оборот («может говорить о», \
«иногда связывают с», «можно прочитать как», «похоже на»); (3) привязка к видимой \
детали рисунка; (4) возврат к ребёнку («лучше всего спросить саму [имя]…», «по одному \
рисунку нельзя сказать, устойчиво ли это — серия покажет точнее»). Не выдумывай источники.
- Если оправу добавить нельзя — мягко смягчи формулировку, сохранив тёплый личный тон.

ЗАПРЕЩЕНО ВСЕГДА (оправа не спасает — здесь именно переписывай/убирай):
- голый диагноз и состояние-как-факт («у ребёнка тревожность», «рисунок показывает, что \
ребёнок несчастен», «это означает, что ребёнок…»);
- катастрофизация и пугающие трактовки («серьёзная проблема», «срочно к врачу», «скрытая травма»);
- командный тон («купите», «подарите», «приобретите», «обязательно») — пиши «можно \
предложить / можно попробовать / хорошо подойдёт / если есть возможность»;
- предсказание таланта как факт («станет художником»);
- дословно «эмоциональный интеллект», «хороший вкус», «база для красивого почерка»; \
инструмент тонкой линии — «линер», не «лайнер».

Перепиши ТОЛЬКО проблемные места, сохранив тёплый тон, объём, ГЛУБИНУ про ребёнка и \
опору на видимые детали. Остальные части отчёта оставь без изменений.

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
                    raw_dump_dir: Path | None = None,
                    system_prompt: str | None = None,
                    enable_lint: bool = True) -> GenerationResult:
    """contexts: список историй по каждому рисунку (по порядку image_paths);
    строка = один контекст на все рисунки (легаси/один рисунок).

    system_prompt / enable_lint — точки расширения для prompt-лаборатории
    (scripts/prompt_lab.py). По умолчанию — боевое поведение без изменений:
    system_prompt=None → SYSTEM_PROMPT; enable_lint=True → линтер+repair как обычно."""
    # Таймаут на запрос (иначе зависший вызов блокирует воркера навсегда). base_url
    # из GOOGLE_GEMINI_BASE_URL переподаём явно — иначе HttpOptions затрёт прод-прокси.
    import os
    _http_kwargs: dict = {"timeout": settings.GEMINI_TIMEOUT_MS}
    _base = os.getenv("GOOGLE_GEMINI_BASE_URL")
    if _base:
        _http_kwargs["base_url"] = _base
    client = genai.Client(api_key=settings.GEMINI_API_KEY,
                          http_options=types.HttpOptions(**_http_kwargs))

    if isinstance(contexts, str):
        contexts = [contexts] * len(image_paths) if len(image_paths) > 1 else [contexts]
    if len(contexts) != len(image_paths):
        raise ValueError(f"contexts ({len(contexts)}) != images ({len(image_paths)})")

    log.info("gemini: preparing %d image(s)", len(image_paths))
    jpegs = [prepare_image(p) for p in image_paths]
    parts: list = [types.Part.from_bytes(data=j, mime_type="image/jpeg") for j in jpegs]
    parts.append(build_user_prompt(contexts, common_context))
    log.info("gemini: ready (model=%s, base_url=%s, timeout=%dms, prompt v%s, lint=%s)",
             settings.GEMINI_MODEL, _base or "default-google",
             settings.GEMINI_TIMEOUT_MS, PROMPT_VERSION, enable_lint)

    config = types.GenerateContentConfig(
        system_instruction=system_prompt or SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.5,
    )

    attempts_log: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            log.info("gemini: attempt %d/%d -> POST generate_content (waiting for model)...",
                     attempt, max_attempts)
            t0 = time.time()
            resp = client.models.generate_content(
                model=settings.GEMINI_MODEL, contents=parts, config=config,
            )
            raw = resp.text or ""
            log.info("gemini: attempt %d <- response in %.1fs (%d chars)",
                     attempt, time.time() - t0, len(raw))
            if raw_dump_dir is not None:
                raw_dump_dir.mkdir(parents=True, exist_ok=True)
                (raw_dump_dir / f"attempt_{attempt}.txt").write_text(raw, encoding="utf-8")
            data = json.loads(_strip_markdown_fence(raw))
            report = validate_report(data)
            log.info("gemini: attempt %d -> JSON validated (%s)", attempt,
                     type(report).__name__)

            # лингвистический линтер + repair-проходы (не для insufficient)
            repair_rounds = 0
            violations: list[dict] = []
            if enable_lint and isinstance(report, Report):
                violations = find_violations(report.model_dump())
                log.info("gemini: lint found %d violation(s)", len(violations))
                while violations and repair_rounds < 2:
                    repair_rounds += 1
                    log.info("gemini: repair round %d -> POST (waiting)...", repair_rounds)
                    try:
                        fixed = _repair_report(client, report.model_dump(), violations)
                        candidate = validate_report(fixed)
                        if isinstance(candidate, Report):
                            new_violations = find_violations(candidate.model_dump())
                            log.info("gemini: repair round %d done (%d -> %d violations)",
                                     repair_rounds, len(violations), len(new_violations))
                            if len(new_violations) < len(violations):
                                report, violations = candidate, new_violations
                                continue
                    except (json.JSONDecodeError, ValidationError):
                        log.info("gemini: repair round %d produced invalid JSON — kept original",
                                 repair_rounds)
                    break

            log.info("gemini: SUCCESS (attempts=%d, repairs=%d, lint_left=%d)",
                     attempt, repair_rounds, len(violations))
            return GenerationResult(
                report=report, raw_json_text=raw,
                attempts_used=attempt, image_jpegs=jpegs,
                repair_rounds=repair_rounds, lint_hits_left=len(violations),
            )
        except (json.JSONDecodeError, ValidationError) as e:
            attempts_log.append(f"attempt {attempt}: invalid output: {e}")
            log.warning("gemini: attempt %d INVALID OUTPUT: %s", attempt, e)
        except Exception as e:  # сетевые/API ошибки/таймаут — тоже неудачная попытка
            attempts_log.append(f"attempt {attempt}: {type(e).__name__}: {e}")
            log.warning("gemini: attempt %d ERROR: %s: %s", attempt, type(e).__name__, e)
        if attempt < max_attempts:
            backoff = min(5 * attempt, 30)
            log.info("gemini: retrying in %ds (attempt %d failed)", backoff, attempt)
            time.sleep(backoff)

    log.error("gemini: ALL %d attempts exhausted", max_attempts)
    raise ReportGenerationError(
        f"Gemini: {max_attempts} попыток исчерпано", attempts_log,
    )
