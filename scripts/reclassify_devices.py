#!/usr/bin/env python3
"""Recompute events.device from user_agent using the current parse_device() logic.

Use after improving bot detection (app/track.parse_device) so historical rows get
re-tagged — otherwise old bot rows stay labelled 'desktop' and slip past the
admin-analytics bot filter. Idempotent; only UPDATEs the `device` column.

Run on the server:
    venv/bin/python scripts/reclassify_devices.py --dry-run   # preview, no writes
    venv/bin/python scripts/reclassify_devices.py             # apply

Output is ASCII-only (safe for the Windows cp1252 console too).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import connect          # noqa: E402
from app.track import parse_device  # noqa: E402


def main() -> None:
    dry = "--dry-run" in sys.argv
    conn = connect()
    try:
        rows = conn.execute("SELECT id, user_agent, device FROM events").fetchall()
        transitions: dict[tuple, int] = {}
        changed = 0
        for r in rows:
            ua = r["user_agent"]
            if not ua or not ua.strip():
                # no UA -> worker/system event; leave device as-is (usually NULL)
                continue
            old = r["device"]
            new = parse_device(ua)
            if new != old:
                changed += 1
                transitions[(old, new)] = transitions.get((old, new), 0) + 1
                if not dry:
                    conn.execute("UPDATE events SET device = ? WHERE id = ?", (new, r["id"]))
        if not dry:
            conn.commit()

        print("total rows : %d" % len(rows))
        print("changed    : %d%s" % (changed, "  (dry-run, nothing written)" if dry else ""))
        for (old, new), c in sorted(transitions.items(), key=lambda kv: -kv[1]):
            print("   %-8s -> %-8s : %d" % (str(old), str(new), c))
        print("device distribution %s:" % ("(would be)" if dry else "now"))
        # recompute live distribution (post-update unless dry-run)
        dist: dict[str, int] = {}
        for r in conn.execute("SELECT user_agent, device FROM events"):
            ua = r["user_agent"]
            if dry and ua and ua.strip():
                d = parse_device(ua)
            else:
                d = r["device"]      # null-UA rows untouched; non-dry already updated
            dist[d or "(null)"] = dist.get(d or "(null)", 0) + 1
        for d, c in sorted(dist.items(), key=lambda kv: -kv[1]):
            print("   %-8s %d" % (d, c))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
