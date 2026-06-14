"""Офлайн IP→гео по собственной базе data/geoip.db (строится scripts/build_geoip.py
из бесплатных данных DB-IP City Lite, CC BY 4.0).

Возвращает страну для всех и регион/город там, где они есть (для РФ — регион).
Сам IP нигде не сохраняется: track.py резолвит гео при записи события и кладёт в БД
только производную метку (страна/регион/город).

Деградирует мягко: если data/geoip.db ещё не собран — lookup() возвращает None,
и в админке гео просто показывается как «—».
"""
from __future__ import annotations

import ipaddress
import sqlite3
import threading
from functools import lru_cache

from config import settings

_DB_PATH = settings.DATA_DIR / "geoip.db"
_conn: sqlite3.Connection | None = None
_conn_tried = False
_lock = threading.Lock()

# Коды стран -> русские названия (частые для нас); для остальных показываем код.
COUNTRY_RU = {
    "RU": "Россия", "UA": "Украина", "BY": "Беларусь", "KZ": "Казахстан",
    "UZ": "Узбекистан", "AM": "Армения", "AZ": "Азербайджан", "GE": "Грузия",
    "KG": "Киргизия", "TJ": "Таджикистан", "MD": "Молдова", "TM": "Туркмения",
    "US": "США", "DE": "Германия", "GB": "Великобритания", "FR": "Франция",
    "NL": "Нидерланды", "PL": "Польша", "IL": "Израиль", "TR": "Турция",
    "FI": "Финляндия", "EE": "Эстония", "LV": "Латвия", "LT": "Литва",
    "CN": "Китай", "IN": "Индия", "CA": "Канада", "ES": "Испания",
    "IT": "Италия", "CZ": "Чехия", "TH": "Таиланд", "AE": "ОАЭ",
}


def country_name(code: str | None) -> str:
    if not code:
        return ""
    return COUNTRY_RU.get(code.upper(), code.upper())


def _get_conn() -> sqlite3.Connection | None:
    """Ленивое read-only соединение с гео-базой (одно на процесс)."""
    global _conn, _conn_tried
    if _conn is not None:
        return _conn
    if _conn_tried:
        return None
    with _lock:
        if _conn is not None:
            return _conn
        _conn_tried = True
        if not _DB_PATH.exists():
            return None
        try:
            uri = f"file:{_DB_PATH.as_posix()}?mode=ro"
            _conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
            _conn.row_factory = sqlite3.Row
        except Exception:
            _conn = None
        return _conn


@lru_cache(maxsize=4096)
def lookup(ip: str | None) -> dict | None:
    """{'country','region'} или None (нет базы / приватный IP / не найден).
    region заполнен только для РФ (так собрана база — см. build_geoip.py)."""
    if not ip:
        return None
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return None
    if not addr.is_global:           # приватные/loopback/reserved — без гео
        return None
    conn = _get_conn()
    if conn is None:
        return None
    try:
        with _lock:
            if addr.version == 4:
                row = conn.execute(
                    "SELECT start_int, country, region FROM ranges_v4"
                    " WHERE end_int >= ? ORDER BY end_int LIMIT 1", (int(addr),)).fetchone()
                if row and row["start_int"] <= int(addr):
                    return _row(row)
            else:
                key = addr.packed
                row = conn.execute(
                    "SELECT start_blob, country, region FROM ranges_v6"
                    " WHERE end_blob >= ? ORDER BY end_blob LIMIT 1", (key,)).fetchone()
                if row and row["start_blob"] <= key:
                    return _row(row)
    except Exception:
        return None
    return None


def _row(row: sqlite3.Row) -> dict:
    return {"country": row["country"] or None,
            "region": row["region"] or None}


def geo_label(country: str | None, region: str | None) -> str:
    """Человекочитаемая метка для админки: РФ -> «Россия, <регион>», иначе страна."""
    if not country:
        return "—"
    name = country_name(country)
    if country.upper() == "RU" and region:
        return f"{name}, {region}"
    return name
