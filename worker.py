"""Фоновый воркер: orders со status='paid' → пайплайн отчёта → delivered/failed.

Запуск:  venv\\Scripts\\python.exe worker.py [--once]
  --once  обработать всю очередь и выйти (тесты, cron); без флага — вечный цикл.

Один экземпляр на машину: зависшие 'generating' (убитый воркер) при старте
сбрасываются обратно в 'paid'. Лог: консоль (только ASCII, cp1252!) +
data/worker.log (UTF-8). На VPS станет systemd-юнитом (Phase 9).
"""
import argparse
import logging
import sqlite3
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from app import jobs
from app.db import connect, init_db, now as db_now
from app.logging_setup import configure_logging
from config import settings


_beat_broken = False


def _beat(conn, log: logging.Logger) -> None:
    """Признак живости для админки. Раздел «Бета» показывал строку про этого воркера
    с самого начала, но писал её только free_worker — платный воркер всегда выглядел
    мёртвым, и настоящая остановка была бы неотличима от нормы.

    Ошибка записи НЕ роняет воркер, но и не глотается молча (UseCase #32): после
    «database is locked» транзакция оставалась открытой, снимок БД замирал, воркер
    40 часов не видел бы новых оплат, а WAL вырос до 650 МБ без чекпоинта.
    """
    global _beat_broken
    try:
        conn.execute(
            "INSERT INTO service_heartbeat (name, last_seen_at) VALUES ('worker', ?)"
            " ON CONFLICT(name) DO UPDATE SET last_seen_at = excluded.last_seen_at",
            (db_now(),))
        conn.commit()
        if _beat_broken:
            _beat_broken = False
            log.info("heartbeat write recovered")
    except sqlite3.Error as e:
        _rollback_quietly(conn)
        if not _beat_broken:          # одна строка на инцидент, не каждые 5 секунд
            _beat_broken = True
            log.warning("heartbeat write failed (%s) - rolled back, will keep trying", e)


def _rollback_quietly(conn) -> None:
    """Закрыть транзакцию, пережившую ошибку. Открытая транзакция на долгоживущем
    соединении = замороженный снимок: SELECT'ы не видят новых строк, чекпоинт WAL
    не может пройти, а каждая новая запись падает с BUSY_SNAPSHOT."""
    try:
        conn.rollback()
    except sqlite3.Error:
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
        if conn.in_transaction:
            # Транзакция, пережившая итерацию (упавший commit где-то ниже), — это
            # замороженный снимок БД: новых оплат воркер не увидит никогда (UseCase #32).
            log.warning("leaked transaction on worker connection - rolling back")
            _rollback_quietly(conn)
        _beat(conn, log)
        try:
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
        except sqlite3.Error as e:
            # 'database is locked' дольше busy_timeout (шумный сосед по диску, долгий
            # чужой commit) — переждать, а не умереть и не зависнуть.
            _rollback_quietly(conn)
            log.warning("sqlite error in poll loop (%s) - rolled back, retrying in %ds",
                        e, settings.WORKER_POLL_SECONDS)
            time.sleep(settings.WORKER_POLL_SECONDS)
            continue
        if args.once:
            log.info("queue empty - exiting (--once)")
            return 0
        time.sleep(settings.WORKER_POLL_SECONDS)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        pass
