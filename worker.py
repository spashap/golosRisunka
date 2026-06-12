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
from config import settings


def setup_logging() -> None:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    file_h = logging.FileHandler(settings.WORKER_LOG, encoding="utf-8")
    file_h.setFormatter(fmt)
    console_h = logging.StreamHandler()
    console_h.setFormatter(fmt)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(file_h)
    root.addHandler(console_h)
    # болтливые библиотеки — только предупреждения (наши jobs/mailer/worker — INFO)
    for noisy in ("fontTools", "weasyprint", "httpx", "google_genai", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def main() -> int:
    ap = argparse.ArgumentParser(description="report generation worker")
    ap.add_argument("--once", action="store_true",
                    help="process pending orders and exit")
    args = ap.parse_args()
    setup_logging()
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
