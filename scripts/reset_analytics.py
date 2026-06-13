"""Reset pre-launch TEST data from the production DB so analytics shows only real data.

Run on the server, from the project root, as the web user (keeps DB file ownership clean):
  cd /var/www/golosrisunka
  sudo -u www-data venv/bin/python scripts/reset_analytics.py                  # REPORT only (read-only)
  sudo -u www-data venv/bin/python scripts/reset_analytics.py --events --confirm   # wipe analytics events
  sudo -u www-data venv/bin/python scripts/reset_analytics.py --all --confirm      # wipe events + test orders/customers

Default (no flags) changes NOTHING — it only prints what's in the DB.
ASCII-only output. Operates on config.settings.DB_PATH.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.db import connect            # noqa: E402
from config import settings           # noqa: E402

# delete order respects foreign keys (children rows before the rows they reference)
ORDER_RESET = ["drawings", "reports", "orders", "login_codes", "sessions", "children", "customers"]
EVENT_RESET = ["events"]


def _one(conn, sql, *a):
    try:
        return conn.execute(sql, a).fetchone()[0]
    except Exception:
        return "n/a"


def report(conn):
    print("DB:", settings.DB_PATH)
    print("events total      :", _one(conn, "SELECT COUNT(*) FROM events"))
    print("distinct visitors :", _one(conn, "SELECT COUNT(DISTINCT visitor_id) FROM events"
                                             " WHERE visitor_id IS NOT NULL"))
    rng = conn.execute("SELECT MIN(created_at), MAX(created_at) FROM events").fetchone()
    print("events date range :", rng[0], "->", rng[1])
    print("-- events by type --")
    for r in conn.execute("SELECT type, COUNT(*) n FROM events GROUP BY type ORDER BY n DESC"):
        print("   %6d  %s" % (r[1], r[0]))
    print("orders total      :", _one(conn, "SELECT COUNT(*) FROM orders"))
    print("customers total   :", _one(conn, "SELECT COUNT(*) FROM customers"))
    print("-- orders --")
    rows = conn.execute("SELECT id, status, email, created_at FROM orders ORDER BY id").fetchall()
    if not rows:
        print("   (none)")
    for r in rows:
        print("   #%-4s %-11s %-32s %s" % (r[0], r[1], r[2], r[3]))


def wipe(conn, tables):
    for t in tables:
        try:
            n = conn.execute("DELETE FROM %s" % t).rowcount
            print("   deleted %5d from %s" % (n, t))
        except Exception as e:
            print("   skip %s: %s" % (t, e))
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", action="store_true", help="wipe analytics events table")
    ap.add_argument("--orders", action="store_true", help="wipe orders/customers/reports/etc.")
    ap.add_argument("--all", action="store_true", help="events + orders")
    ap.add_argument("--confirm", action="store_true", help="actually delete (required to purge)")
    a = ap.parse_args()

    conn = connect()
    print("=== BEFORE ===")
    report(conn)

    do_events = a.events or a.all
    do_orders = a.orders or a.all
    if not (do_events or do_orders):
        print("\n(report only - no purge flags given. Nothing changed.)")
        return 0
    if not a.confirm:
        print("\nWould purge events=%s orders=%s, but --confirm not given. Nothing changed."
              % (do_events, do_orders))
        return 0

    print("\n=== PURGING ===")
    if do_orders:
        wipe(conn, ORDER_RESET)
    if do_events:
        wipe(conn, EVENT_RESET)

    print("\n=== AFTER ===")
    report(conn)
    print("\nDone. Reload /admin/analytics - it now reflects only post-reset (real) data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
