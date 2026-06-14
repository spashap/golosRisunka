"""Build our own compact offline IP->geo DB (data/geoip.db) from free DB-IP City Lite.

DB-IP "IP to City Lite" is free (no account), monthly, CC BY 4.0 (attribution
required, shown in admin). Download the CSV from:
    https://db-ip.com/db/download/ip-to-city-lite
then run:
    venv\\Scripts\\python.exe scripts\\build_geoip.py path\\to\\dbip-city-lite-YYYY-MM.csv.gz

CSV rows (no header): ip_start, ip_end, continent, country, stateprov, city, lat, lon

We only need COUNTRY for everyone and REGION for Russia (per product requirement),
so we keep region only when country == RU and DROP city entirely, then MERGE adjacent
ranges that share the same (country, region). That collapses the city-level splits
(~8M rows / 534 MB) into a compact DB (tens of MB) — important on a small VPS.

Run monthly to refresh. ASCII-only stdout (Windows cp1252 console rule).
"""
from __future__ import annotations

import csv
import gzip
import ipaddress
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402

DB_PATH = settings.DATA_DIR / "geoip.db"
BATCH = 50_000

SCHEMA = """
DROP TABLE IF EXISTS ranges_v4;
DROP TABLE IF EXISTS ranges_v6;
CREATE TABLE ranges_v4 (
    end_int   INTEGER PRIMARY KEY,
    start_int INTEGER NOT NULL,
    country   TEXT,
    region    TEXT
);
CREATE TABLE ranges_v6 (
    end_blob   BLOB PRIMARY KEY,
    start_blob BLOB NOT NULL,
    country    TEXT,
    region     TEXT
);
"""


def _open(path: Path):
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8", newline="")
    return open(path, "rt", encoding="utf-8", newline="")


def _parse_row(parts: list[str]):
    """-> (version, start_int, end_int, country, region) or None.
    region kept only for RU; city dropped."""
    if len(parts) < 3:
        return None
    start_s, end_s = parts[0].strip(), parts[1].strip()
    if len(parts) >= 5:
        country = parts[3].strip()
        region = parts[4].strip() if country.upper() == "RU" else ""
    else:                                   # country-lite: start,end,country
        country, region = parts[2].strip(), ""
    try:
        a, b = ipaddress.ip_address(start_s), ipaddress.ip_address(end_s)
    except ValueError:
        return None
    if a.version != b.version:
        return None
    return (a.version, int(a), int(b), country or None, region or None)


class Merger:
    """Coalesces adjacent ranges with identical (country, region)."""

    def __init__(self):
        self.start = None
        self.end = None
        self.key = None
        self.out: list[tuple] = []

    def add(self, start: int, end: int, country, region):
        key = (country, region)
        if self.key == key and start == self.end + 1:
            self.end = end                  # contiguous + same label -> extend
        else:
            self.flush()
            self.start, self.end, self.key = start, end, key

    def flush(self):
        if self.start is not None:
            self.out.append((self.start, self.end, self.key[0], self.key[1]))
        self.start = self.end = self.key = None

    def take(self) -> list[tuple]:
        rows, self.out = self.out, []
        return rows


def build(csv_path: Path) -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(SCHEMA)

    m4, m6 = Merger(), Merger()
    n4 = n6 = skipped = read = 0
    with _open(csv_path) as fh:
        for parts in csv.reader(fh):
            row = _parse_row(parts)
            if row is None:
                skipped += 1
                continue
            read += 1
            ver, start, end, country, region = row
            if ver == 4:
                m4.add(start, end, country, region)
                if len(m4.out) >= BATCH:
                    n4 += _flush4(conn, m4.take())
            else:
                m6.add(start, end, country, region)
                if len(m6.out) >= BATCH:
                    n6 += _flush6(conn, m6.take())
    m4.flush(); m6.flush()
    n4 += _flush4(conn, m4.take())
    n6 += _flush6(conn, m6.take())
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    size_mb = DB_PATH.stat().st_size / 1_048_576
    print(f"OK: {DB_PATH}")
    print(f"  source rows: {read}  (skipped {skipped})")
    print(f"  IPv4 ranges after merge: {n4}")
    print(f"  IPv6 ranges after merge: {n6}")
    print(f"  db size: {size_mb:.1f} MB")


def _flush4(conn, rows) -> int:
    # rows: (start_int, end_int, country, region)
    conn.executemany(
        "INSERT OR REPLACE INTO ranges_v4 (start_int, end_int, country, region)"
        " VALUES (?, ?, ?, ?)", rows)
    return len(rows)


def _flush6(conn, rows) -> int:
    packed = [(s.to_bytes(16, "big"), e.to_bytes(16, "big"), c, r)
              for (s, e, c, r) in rows]
    conn.executemany(
        "INSERT OR REPLACE INTO ranges_v6 (start_blob, end_blob, country, region)"
        " VALUES (?, ?, ?, ?)", packed)
    return len(packed)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python scripts/build_geoip.py <dbip-city-lite-YYYY-MM.csv[.gz]>")
        raise SystemExit(2)
    src = Path(sys.argv[1])
    if not src.exists():
        print(f"not found: {src}")
        raise SystemExit(2)
    build(src)
