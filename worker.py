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
from app.db import connect, init_db
from app.logging_setup import configure_logging
from config import settings


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
        row = conn.execute(
            "SELECT id FROM orders WHERE status = 'paid' ORDER BY paid_at, id LIMIT 1"
        ).fetchone()
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
