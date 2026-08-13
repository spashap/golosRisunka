"""Вызов Gemini для БЕСПЛАТНОГО разбора одного рисунка (фремиум-бета).

Отдельный от pipeline/gemini.py по трём причинам: другая схема (validate_free вместо
validate_report), другой линтер (free_lint вместо lint) и другая repair-инструкция —
платная написана про about_child и семь направлений и на коротком разборе вредна
(см. шапку free_lint.py). Платный путь этим модулем НЕ затрагивается.

Блок создания клиента ниже ДУБЛИРУЕТ pipeline/gemini.py:125-131 сознательно, а не по
недосмотру: generate_report — денежный путь, и его рефакторинг ради переиспользования
восьми строк должен быть отдельным коммитом с проверкой перегенерацией отчёта.
Оба урока, зашитых в эти строки, обязательны и здесь:
  * СТРИМ, а не блокирующий вызов — при нестриме по соединению десятки секунд не идёт
    ни байта, и промежуточный узел рвёт простаивающее соединение (см. подробный
    комментарий pipeline/gemini.py:158 и UseCase #27);
  * base_url прокси надо переподать ЯВНО, иначе HttpOptions с таймаутом затрёт его.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import ValidationError

from config import settings
from pipeline.free_lint import (FREE_REPAIR_INSTRUCTION, can_downgrade,
                                drop_hypothesis, find_free_violations)
from pipeline.free_prompt import (CONCERNS_WITHOUT_CORRELATE, FREE_PROMPT_VERSION,
                                  FREE_SYSTEM_PROMPT, build_free_user_prompt)
from pipeline.free_schema import FreeAnalysis, FreeInsufficient, validate_free
from pipeline.images import prepare_image

log = logging.getLogger("free_gemini")


class FreeGenerationError(Exception):
    """Все попытки исчерпаны. attempts_log — ошибки по попыткам (для _is_transient)."""

    def __init__(self, message: str, attempts_log: list[str]):
        super().__init__(message)
        self.attempts_log = attempts_log


@dataclass
class FreeResult:
    analysis: FreeAnalysis | FreeInsufficient
    raw_json_text: str
    prompt_version: str = FREE_PROMPT_VERSION
    model: str = settings.FREE_GEMINI_MODEL
    attempts_used: int = 1
    repair_rounds: int = 0
    lint_hits_left: int = 0
    hypothesis_dropped: bool = False   # сработал даунгрейд вместо провала
    prompt_tokens: int = 0
    output_tokens: int = 0
    elapsed_s: float = 0.0
    image_jpeg: bytes = b""
    lint_hits: list[dict] = field(default_factory=list)


def _make_client(timeout_ms: int) -> "genai.Client":
    http_kwargs: dict = {"timeout": timeout_ms}
    base = os.getenv("GOOGLE_GEMINI_BASE_URL")
    if base:
        http_kwargs["base_url"] = base
    return genai.Client(api_key=settings.GEMINI_API_KEY,
                        http_options=types.HttpOptions(**http_kwargs))


def _strip_fence(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _stream_json(client: "genai.Client", contents, config) -> tuple[str, int, int]:
    """Стримящий вызов -> (текст, prompt_tokens, output_tokens).

    Токены снимаем здесь и нигде больше: без них пункт «стоимость одного бесплатного
    разбора» остаётся догадкой, а он в задаче требуется числом.
    """
    chunks: list[str] = []
    p_tok = o_tok = 0
    for chunk in client.models.generate_content_stream(
            model=settings.FREE_GEMINI_MODEL, contents=contents, config=config):
        if chunk.text:
            chunks.append(chunk.text)
        um = getattr(chunk, "usage_metadata", None)
        if um:   # итоговые значения приходят в последних чанках — берём последние непустые
            p_tok = getattr(um, "prompt_token_count", None) or p_tok
            o_tok = getattr(um, "candidates_token_count", None) or o_tok
    return "".join(chunks), p_tok, o_tok


def _repair(client: "genai.Client", data: dict, violations: list[dict]) -> tuple[dict, int, int]:
    issues = "\n".join(
        f"- {v['where']}: «{v['match']}» — {v['why']}" for v in violations
    )
    prompt = (f"{FREE_REPAIR_INSTRUCTION}\n\nНайденные нарушения:\n{issues}\n\n"
              f"JSON разбора:\n{json.dumps(data, ensure_ascii=False)}")
    cfg = types.GenerateContentConfig(
        response_mime_type="application/json", temperature=0.2)
    raw, p, o = _stream_json(client, prompt, cfg)
    return json.loads(_strip_fence(raw)), p, o


def generate_free_analysis(image_path: Path, *, child_name: str, age: int,
                           address_form: str, concern_key: str,
                           age_band_label: str = "",
                           duration_label: str = "", parent_text: str = "",
                           max_attempts: int = settings.FREE_MAX_ATTEMPTS,
                           raw_dump_dir: Path | None = None,
                           system_prompt: str | None = None,
                           enable_lint: bool = True) -> FreeResult:
    """Один рисунок -> валидированный и очищенный линтером бесплатный разбор."""
    client = _make_client(settings.FREE_GEMINI_TIMEOUT_MS)

    jpeg = prepare_image(image_path)
    user_prompt = build_free_user_prompt(
        child_name=child_name, age=age, address_form=address_form,
        age_band_label=age_band_label,
        concern_key=concern_key, duration_label=duration_label,
        parent_text=parent_text)
    parts = [types.Part.from_bytes(data=jpeg, mime_type="image/jpeg"), user_prompt]

    config = types.GenerateContentConfig(
        system_instruction=system_prompt or FREE_SYSTEM_PROMPT,
        response_mime_type="application/json",
        temperature=0.5,
    )
    log.info("free: ready (model=%s, timeout=%dms, prompt v%s, concern=%s, lint=%s)",
             settings.FREE_GEMINI_MODEL, settings.FREE_GEMINI_TIMEOUT_MS,
             FREE_PROMPT_VERSION, concern_key, enable_lint)

    attempts_log: list[str] = []
    for attempt in range(1, max_attempts + 1):
        try:
            t0 = time.time()
            log.info("free: attempt %d/%d -> streaming...", attempt, max_attempts)
            raw, p_tok, o_tok = _stream_json(client, parts, config)
            elapsed = time.time() - t0
            log.info("free: attempt %d <- %.1fs, %d chars, tokens in/out %d/%d",
                     attempt, elapsed, len(raw), p_tok, o_tok)
            if raw_dump_dir is not None:
                raw_dump_dir.mkdir(parents=True, exist_ok=True)
                (raw_dump_dir / f"attempt_{attempt}.txt").write_text(raw, encoding="utf-8")

            analysis = validate_free(json.loads(_strip_fence(raw)))
            if isinstance(analysis, FreeInsufficient):
                log.info("free: insufficient (%s)", analysis.reason_key)
                return FreeResult(analysis=analysis, raw_json_text=raw,
                                  attempts_used=attempt, prompt_tokens=p_tok,
                                  output_tokens=o_tok, elapsed_s=elapsed,
                                  image_jpeg=jpeg)

            # Тревоги, у которых коррелята на одном листе не существует физически
            # (нейтральный путь, «одно и то же», «перестал рисовать»). Промпт просит
            # null, но подстраховываемся здесь: «true на всякий случай» — это уверенный
            # мусор в данных беты, а ещё он ложно включил бы абзац несовпадения.
            if concern_key in CONCERNS_WITHOUT_CORRELATE:
                analysis = analysis.model_copy(update={
                    "concern_correlate_visible": None, "concern_correlate_note": ""})

            repairs = 0
            dropped = False
            hits = find_free_violations(analysis, child_name) if enable_lint else []
            log.info("free: lint found %d violation(s)", len(hits))

            if hits and enable_lint:
                for _ in range(settings.FREE_REPAIR_ROUNDS):
                    repairs += 1
                    try:
                        fixed, rp, ro = _repair(client, analysis.model_dump(), hits)
                        p_tok, o_tok = p_tok + rp, o_tok + ro
                        cand = validate_free(fixed)
                        if isinstance(cand, FreeAnalysis):
                            new_hits = find_free_violations(cand, child_name)
                            log.info("free: repair %d (%d -> %d)", repairs,
                                     len(hits), len(new_hits))
                            if len(new_hits) < len(hits):
                                analysis, hits = cand, new_hits
                                if not hits:
                                    break
                                continue
                    except (json.JSONDecodeError, ValidationError) as e:
                        log.info("free: repair produced invalid JSON (%s) — kept original", e)
                    break

                # Даунгрейд вместо провала: если осталась только гипотеза — снимаем её.
                # §7 прямо называет разбор без трактовки законным исходом, поэтому
                # отгруженный менее глубокий текст лучше потерянного родителя.
                if hits and can_downgrade(hits):
                    demoted = drop_hypothesis(analysis)
                    if demoted is not None:
                        after = find_free_violations(demoted, child_name)
                        if not after:
                            analysis, hits, dropped = demoted, after, True
                            log.info("free: hypothesis dropped (downgrade) — clean")

            if hits:
                # Не отдаём родителю текст с нарушениями: считаем попытку неудачной.
                raise ValueError(f"lint: {len(hits)} нарушений не вычищено "
                                 f"({hits[0]['where']}: {hits[0]['why'][:60]})")

            elapsed = time.time() - t0
            log.info("free: SUCCESS (attempts=%d, repairs=%d, dropped=%s, words=%d)",
                     attempt, repairs, dropped, analysis.word_count())
            return FreeResult(analysis=analysis, raw_json_text=raw,
                              attempts_used=attempt, repair_rounds=repairs,
                              lint_hits_left=0, hypothesis_dropped=dropped,
                              prompt_tokens=p_tok, output_tokens=o_tok,
                              elapsed_s=elapsed, image_jpeg=jpeg)

        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            attempts_log.append(f"attempt {attempt}: invalid output: {e}")
            log.warning("free: attempt %d INVALID: %s", attempt, e)
        except Exception as e:      # сеть/API/таймаут — тоже неудачная попытка
            attempts_log.append(f"attempt {attempt}: {type(e).__name__}: {e}")
            log.warning("free: attempt %d ERROR: %s: %s", attempt, type(e).__name__, e)
        if attempt < max_attempts:
            time.sleep(2)           # родитель ждёт на экране — бэкоф короткий

    log.error("free: ALL %d attempts exhausted", max_attempts)
    raise FreeGenerationError(f"free: {max_attempts} попыток исчерпано", attempts_log)
