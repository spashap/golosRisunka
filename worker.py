"""Фоновый воркер: orders со status='paid' → пайплайн отчёта → delivered/failed.

Запуск:  venv\\Scripts\\python.exe worker.py [--once]
  --once  обработать всю очередь и выйти (тесты, cron); без флага — вечный цикл.

Один экземпляр на машину: зависшие 'generating' (убитый воркер) при старте
сбрасываются обратно в 'paid'. Лог: консоль (только ASCII, cp1252!) +
data/worker.log (UTF-8). На VPS станет systemd-юнитом (Phase 9).
"""
import argparse
import logging
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app import jobs
from app.db import connect, init_db, now as db_now
from app.logging_setup import configure_logging
from config import settings


def _beat(conn) -> None:
    """Признак живости для админки. Раздел «Бета» показывал строку про этого воркера
    с самого начала, но писал её только free_worker — платный воркер всегда выглядел
    мёртвым, и настоящая остановка была бы неотличима от нормы."""
    try:
        conn.execute(
            "INSERT INTO service_heartbeat (name, last_seen_at) VALUES ('worker', ?)"
            " ON CONFLICT(name) DO UPDATE SET last_seen_at = excluded.last_seen_at",
            (db_now(),))
        conn.commit()
    except Exception:              # мониторинг не должен ронять генерацию отчётов
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description="report generation worker")
    ap.add_argument("--once", action="store_true",
                    help="process pending orders and exit")
    args = ap.parse_args()
    configure_logging(settings.WORKER_LOG)
    log = logging.getLogger("worker")

    init_db()
    conn = connect()
    stale = conn.execute(
        "UPDATE orders SET status = 'paid' WHERE status = 'generating'").rowcount
    conn.commit()
    if stale:
        log.warning("reset %d stale 'generating' order(s) back to 'paid'", stale)
    log.info("worker started (poll=%ds, once=%s)",
             settings.WORKER_POLL_SECONDS, args.once)

    while True:
        _beat(conn)
        row = conn.execute(
            "SELECT id FROM orders WHERE status = 'paid' ORDER BY paid_at, id LIMIT 1"
        ).fetchone()
        if not row:
            # самовосстановление: транзитно упавшие заказы, у которых подошло время
            # авто-перезапуска (next_retry_at <= now). Новые оплаты — в приоритете.
            row = conn.execute(
                "SELECT id FROM orders WHERE status = 'failed'"
                " AND next_retry_at IS NOT NULL AND next_retry_at <= ?"
                " ORDER BY next_retry_at LIMIT 1", (db_now(),)).fetchone()
            if row:
                log.info("order %s: auto-retry due - requeuing", row["id"])
        if row:
            jobs.run_order(conn, row["id"])
            continue                      # сразу к следующему в очереди
        if args.once:
            log.info("queue empty - exiting (--once)")
            return 0
        time.sleep(settings.WORKER_POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
