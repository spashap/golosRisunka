"""Ручной перезапуск отчёта: scripts/regenerate_report.py ORDER_ID

Работает из любого статуса, кроме 'created' (failed / insufficient /
delivered / paid): прогоняет пайплайн заново тем же кодом, что воркер.
public_token существующего отчёта сохраняется — ссылка /r/<token> не меняется.
Перед запуском остановите воркер ИЛИ убедитесь, что заказ не в очереди
(двойная генерация безвредна, но тратит вызов Gemini).
"""
import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import jobs
from app.db import connect, init_db


def main() -> int:
    ap = argparse.ArgumentParser(description="regenerate a report for an order")
    ap.add_argument("order_id", type=int)
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    init_db()
    conn = connect()
    order = conn.execute("SELECT id, status FROM orders WHERE id = ?",
                         (args.order_id,)).fetchone()
    if order is None:
        print(f"order {args.order_id}: not found")
        return 1
    print(f"order {args.order_id}: status '{order['status']}' -> regenerating")
    # ручной перезапуск = осознанный свежий старт: обнуляем счётчик авто-перезапусков,
    # чтобы заказ снова получил полный набор попыток самовосстановления.
    conn.execute("UPDATE orders SET retry_count = 0, next_retry_at = NULL WHERE id = ?",
                 (args.order_id,))
    conn.commit()
    status = jobs.run_order(conn, args.order_id)
    print(f"order {args.order_id}: final status '{status}'")
    return 0 if status == "delivered" else 1


if __name__ == "__main__":
    raise SystemExit(main())
