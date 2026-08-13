"""Воркер бесплатных разборов (фремиум-бета). Отдельный systemd-юнит.

Почему отдельный процесс, а не поток в вебе:
  * gunicorn держит всего 3 sync-воркера — 40-секундная генерация в запросе заняла бы
    треть сайта, три одновременные загрузки положили бы его целиком;
  * `deploy.sh` перезапускает golosrisunka-web, и потоки умирали бы при каждом деплое
    вместе с недоделанными разборами;
  * Pillow декодирует присланную пользователем картинку ВНЕ процесса, который обслуживает
    трафик: бокс 3.8 ГБ без swap и делит его с другим сайтом, поэтому декомпресионная
    бомба не должна ронять живые запросы.

Запуск: venv/bin/python free_worker.py [--once]
"""
from __future__ import annotations

import datetime
import json
import logging
import sys
import time

from app.db import connect, init_db, now, track
from app.free_retention import sweep_expired
from app.logging_setup import configure_logging
from config import settings

log = logging.getLogger("free_worker")

STAGES = ["prepare", "looking", "detail", "lint", "almost"]
HEARTBEAT = "free_worker"


def _beat(conn) -> None:
    """Признак живости для админки: deploy.sh новый юнит не поднимает, мониторинга нет,
    и после перезагрузки бокса разборы молча перестали бы генерироваться."""
    conn.execute(
        "INSERT INTO service_heartbeat (name, last_seen_at) VALUES (?, ?)"
        " ON CONFLICT(name) DO UPDATE SET last_seen_at = excluded.last_seen_at",
        (HEARTBEAT, now()))
    conn.commit()


def _stage(conn, aid: int, stage: str) -> None:
    conn.execute("UPDATE free_analyses SET stage = ? WHERE id = ?", (stage, aid))
    conn.commit()


def _reap(conn) -> None:
    """Зависшие 'running' возвращаем в очередь: деплой/падение не должны оставлять
    родителя перед вечным спиннером."""
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(seconds=settings.FREE_STALL_SECONDS)
              ).isoformat(timespec="seconds")
    n = conn.execute(
        "UPDATE free_analyses SET status = 'queued', stage = 'prepare'"
        " WHERE status = 'running' AND (started_at IS NULL OR started_at < ?)",
        (cutoff,)).rowcount
    conn.commit()
    if n:
        log.warning("reaped %d stalled analysis(es) back to queue", n)


def _running(conn) -> int:
    return conn.execute(
        "SELECT COUNT(*) c FROM free_analyses WHERE status = 'running'").fetchone()["c"]


def process(conn, row) -> str:
    """Один разбор. Никогда не бросает наружу."""
    from pipeline.free_gemini import FreeGenerationError, generate_free_analysis
    from pipeline.free_schema import FreeInsufficient
    from config import free_texts as T

    aid = row["id"]
    conn.execute("UPDATE free_analyses SET status = 'running', started_at = ?,"
                 " stage = 'prepare' WHERE id = ?", (now(), aid))
    conn.commit()

    out_dir = settings.FREE_DIR / str(aid)
    img = settings.BASE_DIR / row["file_path"]
    dur_label = ("" if row["concern_key"] == "neutral"
                 else T.duration_label(row["concern_key"], row["duration_key"] or "",
                                       row["address_form"] or "он"))
    try:
        _stage(conn, aid, "looking")
        res = generate_free_analysis(
            img, child_name=row["child_name"], age=row["child_age"],
            address_form=row["address_form"] or "он",
            concern_key=row["concern_key"], duration_label=dur_label,
            parent_text=row["parent_text"] or "",
            raw_dump_dir=out_dir / "raw")
    except FreeGenerationError as e:
        log.error("free #%s FAILED: %s", aid, "; ".join(e.attempts_log)[:500])
        conn.execute("UPDATE free_analyses SET status = 'failed' WHERE id = ?", (aid,))
        conn.commit()
        track("free_failed", payload={"id": aid}, conn=conn)
        return "failed"
    except Exception as e:                                   # noqa: BLE001
        log.exception("free #%s crashed: %s", aid, e)
        conn.execute("UPDATE free_analyses SET status = 'failed' WHERE id = ?", (aid,))
        conn.commit()
        return "failed"

    a = res.analysis
    if isinstance(a, FreeInsufficient):
        # Отказ лимит НЕ расходует — строка не станет 'done'.
        conn.execute(
            "UPDATE free_analyses SET status = 'rejected', reject_reason = ?,"
            " gen_seconds = ?, prompt_tokens = ?, output_tokens = ?, model = ?,"
            " prompt_version = ?, attempts = ?, stage = 'almost' WHERE id = ?",
            (a.reason_key, round(res.elapsed_s, 1), res.prompt_tokens,
             res.output_tokens, res.model, res.prompt_version, res.attempts_used, aid))
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "analysis.json").write_text(
            json.dumps({"insufficient_input": True, "reason_key": a.reason_key,
                        "insufficient_reason": a.insufficient_reason},
                       ensure_ascii=False, indent=2), encoding="utf-8")
        conn.commit()
        track("free_rejected", payload={"id": aid, "reason": a.reason_key}, conn=conn)
        return "rejected"

    _stage(conn, aid, "lint")
    out_dir.mkdir(parents=True, exist_ok=True)
    jpath = out_dir / "analysis.json"
    jpath.write_text(json.dumps(a.model_dump(), ensure_ascii=False, indent=2),
                     encoding="utf-8")
    _stage(conn, aid, "almost")

    conn.execute(
        "UPDATE free_analyses SET status = 'done', analysis_json_path = ?,"
        " flags_json = ?, correlate = ?, correlate_note = ?, model = ?,"
        " prompt_version = ?, attempts = ?, repair_rounds = ?,"
        " hypothesis_dropped = ?, prompt_tokens = ?, output_tokens = ?,"
        " gen_seconds = ?, delivered_at = ? WHERE id = ?",
        (jpath.relative_to(settings.BASE_DIR).as_posix(),
         json.dumps(a.flags, ensure_ascii=False),
         None if a.concern_correlate_visible is None else int(a.concern_correlate_visible),
         a.concern_correlate_note or None, res.model, res.prompt_version,
         res.attempts_used, res.repair_rounds, int(res.hypothesis_dropped),
         res.prompt_tokens, res.output_tokens, round(res.elapsed_s, 1), now(), aid))
    if a.hypothesis is not None:
        h = a.hypothesis
        conn.execute(
            "INSERT INTO free_interpretations (analysis_id, phrase, attribution, key,"
            " new_key_description, age_scope, created_at) VALUES (?,?,?,?,?,?,?)",
            (aid, h.phrase, h.attribution, h.key, h.new_key_description or None,
             h.age_scope or None, now()))
        conn.execute(
            "INSERT INTO free_interpretation_keys (key, first_seen_at)"
            " VALUES (?, ?) ON CONFLICT(key) DO NOTHING", (h.key, now()))
    conn.commit()
    track("free_delivered", payload={"id": aid, "key":
                                     a.hypothesis.key if a.hypothesis else None},
          conn=conn)
    log.info("free #%s done in %.1fs (%d words)", aid, res.elapsed_s, a.word_count())
    return "done"


def main() -> int:
    once = "--once" in sys.argv
    configure_logging(settings.FREE_WORKER_LOG)
    init_db()
    conn = connect()
    log.info("free_worker start (poll=1s, cap=%d concurrent)",
             settings.FREE_MAX_CONCURRENT)
    _reap(conn)
    last_sweep = ""
    try:
        while True:
            _beat(conn)
            # Уборщик хранения раз в сутки: free_worker и так долгоживущий процесс,
            # это дешевле cron и не требует ещё одного юнита.
            today = now()[:10]
            if today != last_sweep:
                last_sweep = today
                try:
                    sweep_expired(conn)
                except Exception as e:                       # noqa: BLE001
                    log.warning("retention sweep failed: %s", e)

            if _running(conn) >= settings.FREE_MAX_CONCURRENT:
                time.sleep(1)
                continue
            row = conn.execute(
                "SELECT * FROM free_analyses WHERE status = 'queued'"
                " ORDER BY id LIMIT 1").fetchone()
            if row is None:
                if once:
                    log.info("queue drained")
                    return 0
                time.sleep(1)
                continue
            process(conn, row)
    except KeyboardInterrupt:
        log.info("free_worker stopped")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
