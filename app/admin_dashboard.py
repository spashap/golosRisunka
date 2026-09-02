"""Главная страница админки — пять вопросов владельца, в этом порядке:

  1. Заработали ли?          выручка (за вычетом возвратов), оплат, средний чек, по каналам
  2. Что-то сломано сейчас?  полоса проблем: зависшие заказы, сбои, тишина воркеров, письма
  3. Трафик настоящий и откуда?  РЕАЛЬНЫЕ визиты по каналам/устройствам + график по дням
  4. Продаёт ли бесплатная дверь?  недельные когорты анкета → рисунок → разбор → покупка
  5. Сколько это стоит?      расход на рекламу (вводится руками) → цена лида и продажи

Что здесь НАМЕРЕННО не так, как в старой «Аналитике»:
  * единица — ВИЗИТ из web_visits, и только тот, где браузер выполнил track.js
    (screen_w IS NOT NULL): сканеры с Mozilla-UA открывают главную и раньше считались людьми;
  * дни — МОСКОВСКИЕ календарные (UTC+3), а не скользящие 24 часа в UTC;
  * тестовые заказы/клиенты/разборы (is_test) и браузер владельца (device='owner') не считаются;
  * у каждого числа есть «предыдущий период» — без сравнения число ничего не говорит.
"""
from __future__ import annotations

import datetime
import json
import statistics

from app import admin_free_analytics as fa
from config import settings

MSK = datetime.timezone(datetime.timedelta(hours=3))
NOT_BOT = "(v.device IS NULL OR v.device NOT IN ('bot', 'owner'))"
REAL_VISIT = "v.screen_w IS NOT NULL"
REAL_ORDER = "COALESCE(o.is_test, 0) = 0"

CHANNEL_LABELS = {
    "ads": "Реклама (Директ)", "meta": "Реклама (Meta)", "organic": "Поиск",
    "email": "Письма", "social": "Соцсети", "referral": "Переходы с сайтов",
    "direct": "Прямые", "internal": "Внутренние", "none": "Не привязан к визиту",
}
SPEND_CHANNELS = [("ads", "Яндекс.Директ"), ("meta", "Meta / Instagram"),
                  ("social", "Соцсети / посевы"), ("referral", "Площадки и каталоги")]

PERIODS = [("1", "сегодня"), ("7", "7 дней"), ("30", "30 дней"), ("90", "90 дней")]


# --- Время ---------------------------------------------------------------------------

def _utc(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def period(days: str) -> dict:
    """Границы периода по МОСКОВСКИМ дням. «сегодня» = с полуночи МСК; «7 дней» = сегодня
    и шесть предыдущих. Возвращает ISO-UTC строки для сравнения с created_at."""
    days = days if days in {p[0] for p in PERIODS} else "7"
    n = int(days)
    today = datetime.datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    since = today - datetime.timedelta(days=n - 1)
    until = today + datetime.timedelta(days=1)
    prev_since = since - datetime.timedelta(days=n)
    return {"days": days, "n": n, "since": _utc(since), "until": _utc(until),
            "prev_since": _utc(prev_since), "prev_until": _utc(since),
            "label": dict(PERIODS)[days],
            "since_day": since.strftime("%Y-%m-%d"), "until_day": until.strftime("%Y-%m-%d"),
            "since_msk": since.strftime("%d.%m"), "until_msk": (until - datetime.timedelta(days=1)).strftime("%d.%m")}


def msk(ts: str | None, fmt: str = "%d.%m %H:%M") -> str:
    """ISO-UTC из БД -> московское время для людей."""
    if not ts:
        return ""
    try:
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(MSK).strftime(fmt)
    except ValueError:
        return ts[:16].replace("T", " ")


def msk_day(ts: str) -> str:
    return msk(ts, "%Y-%m-%d")


def delta(cur: float, prev: float) -> dict:
    """Сравнение с предыдущим периодом: знак, процент, подпись."""
    if prev == 0:
        return {"dir": "flat" if cur == 0 else "up", "pct": "" if cur == 0 else "новое",
                "prev": prev}
    ch = (cur - prev) / prev * 100
    return {"dir": "up" if ch > 2 else "down" if ch < -2 else "flat",
            "pct": f"{ch:+.0f}%", "prev": prev}


# --- 1. Деньги -----------------------------------------------------------------------

def _money_window(db, since: str, until: str) -> dict:
    r = db.execute(
        "SELECT COUNT(*) n, COALESCE(SUM(o.price_kopecks), 0) gross,"
        " COALESCE(SUM(CASE WHEN o.refunded_at IS NOT NULL THEN COALESCE(o.refund_kopecks, o.price_kopecks) ELSE 0 END), 0) refunds,"
        " SUM(CASE WHEN o.refunded_at IS NOT NULL THEN 1 ELSE 0 END) refunded_n"
        f" FROM orders o WHERE o.paid_at >= ? AND o.paid_at < ? AND {REAL_ORDER}",
        (since, until)).fetchone()
    net = (r["gross"] or 0) - (r["refunds"] or 0)
    n = r["n"] or 0
    return {"paid": n, "gross": (r["gross"] or 0) // 100, "refunds": (r["refunds"] or 0) // 100,
            "refunded_n": r["refunded_n"] or 0, "net": net // 100,
            "avg": (net // n) // 100 if n else 0}


def _order_channel_sql() -> str:
    """Канал заказа: визит, в котором он оформлен; иначе по UTM заказа; иначе «не привязан»."""
    return ("COALESCE(v.channel, CASE WHEN o.utm_json LIKE '%cpc%' OR o.utm_json LIKE '%yclid%'"
            " THEN 'ads' WHEN o.utm_json IS NOT NULL AND o.utm_json <> '' THEN 'referral' END, 'none')")


def money(db, p: dict) -> dict:
    cur = _money_window(db, p["since"], p["until"])
    prev = _money_window(db, p["prev_since"], p["prev_until"])
    by_channel = []
    for r in db.execute(
            f"SELECT {_order_channel_sql()} ch, COUNT(*) n,"
            " COALESCE(SUM(o.price_kopecks - CASE WHEN o.refunded_at IS NOT NULL"
            " THEN COALESCE(o.refund_kopecks, o.price_kopecks) ELSE 0 END), 0) net"
            " FROM orders o LEFT JOIN web_visits v ON v.visit_id = o.visit_id"
            f" WHERE o.paid_at >= ? AND o.paid_at < ? AND {REAL_ORDER}"
            " GROUP BY ch ORDER BY net DESC", (p["since"], p["until"])):
        by_channel.append({"key": r["ch"], "label": CHANNEL_LABELS.get(r["ch"], r["ch"]),
                           "paid": r["n"], "net": r["net"] // 100})
    # Брошенные: создан, не оплачен, есть почта — с ними можно связаться.
    abandoned = db.execute(
        "SELECT COUNT(*) c FROM orders o WHERE o.status = 'created' AND o.email <> ''"
        f" AND o.created_at >= ? AND o.created_at < ? AND {REAL_ORDER}",
        (p["since"], p["until"])).fetchone()["c"]
    return {"cur": cur, "prev": prev,
            "d_net": delta(cur["net"], prev["net"]), "d_paid": delta(cur["paid"], prev["paid"]),
            "d_avg": delta(cur["avg"], prev["avg"]), "by_channel": by_channel,
            "abandoned": abandoned}


# --- 2. Проблемы ---------------------------------------------------------------------

def problems(db, heartbeats: list[dict]) -> list[dict]:
    """Полоса «что сломано сейчас». Пустой список = всё зелёное."""
    now = datetime.datetime.now(datetime.timezone.utc)
    out: list[dict] = []

    def add(n: int, label: str, url: str, level: str = "crit") -> None:
        if n:
            out.append({"n": n, "label": label, "url": url, "level": level})

    hour_ago = _utc(now - datetime.timedelta(hours=1))
    week_ago = _utc(now - datetime.timedelta(days=7))
    ten_min_ago = _utc(now - datetime.timedelta(minutes=10))
    add(db.execute("SELECT COUNT(*) c FROM orders o WHERE o.status IN ('paid','generating')"
                   f" AND o.paid_at < ? AND {REAL_ORDER}", (hour_ago,)).fetchone()["c"],
        "оплачено, отчёт не доставлен больше часа", "/admin/orders?days=7")
    add(db.execute("SELECT COUNT(*) c FROM orders o WHERE o.status = 'failed'"
                   f" AND o.created_at >= ? AND {REAL_ORDER}", (week_ago,)).fetchone()["c"],
        "сбой генерации за 7 дней", "/admin/orders?days=7")
    add(db.execute("SELECT COUNT(*) c FROM orders o WHERE o.status = 'insufficient'"
                   f" AND o.created_at >= ? AND {REAL_ORDER}", (week_ago,)).fetchone()["c"],
        "«нужны другие фото» за 7 дней (клиент ждёт ответа)", "/admin/orders?days=7", "warn")
    add(db.execute("SELECT COUNT(*) c FROM free_analyses WHERE status IN ('queued','running')"
                   " AND created_at < ? AND COALESCE(is_test,0) = 0", (ten_min_ago,)).fetchone()["c"],
        "бесплатных разборов зависло дольше 10 минут", "/admin/free?days=7")
    add(db.execute("SELECT COUNT(*) c FROM free_analyses WHERE status = 'failed'"
                   " AND created_at >= ? AND COALESCE(is_test,0) = 0", (week_ago,)).fetchone()["c"],
        "бесплатных разборов упало за 7 дней", "/admin/free?days=7")
    for h in heartbeats:
        if not h.get("ok"):
            out.append({"n": 1, "label": f"воркер молчит: {h['label']}", "url": "/admin/free", "level": "crit"})
    # Письма, которые Unisender не принял, падают в outbox файлами (в проде это и есть
    # список НЕотправленных писем).
    try:
        cutoff = now.timestamp() - 7 * 86400
        n_out = sum(1 for f in settings.OUTBOX_DIR.glob("*.html") if f.stat().st_mtime >= cutoff)
        if settings.MAIL_BACKEND != "outbox":
            add(n_out, "писем не ушло за 7 дней (лежат в outbox)", "/admin/emails")
    except OSError:
        pass
    add(db.execute("SELECT COUNT(*) c FROM events WHERE type = 'error_500' AND created_at >= ?",
                   (week_ago,)).fetchone()["c"], "ошибок 500 за 7 дней", "/admin/actions?days=7")
    return out


# --- 3. Трафик -----------------------------------------------------------------------

def _visits_window(db, since: str, until: str) -> dict:
    rows = db.execute(
        "SELECT v.channel, v.screen_w, v.device, v.engaged, v.entry_path, v.started_at, v.last_at"
        f" FROM web_visits v WHERE v.started_at >= ? AND v.started_at < ? AND {NOT_BOT} AND {REAL_VISIT}",
        (since, until)).fetchall()
    by_ch: dict[str, int] = {}
    mobile = 0
    entries: dict[str, int] = {}
    engaged = 0
    for r in rows:
        ch = r["channel"] or "direct"
        by_ch[ch] = by_ch.get(ch, 0) + 1
        sw = r["screen_w"] or 0
        if (0 < sw < 640) or (not sw and r["device"] == "mobile"):
            mobile += 1
        e = r["entry_path"] or "/"
        e = "/blog/…" if e.startswith("/blog/") else "/free/r/…" if e.startswith("/free/r/") \
            else "/r/…" if e.startswith("/r/") else e.split("?")[0]
        entries[e] = entries.get(e, 0) + 1
        engaged += 1 if r["engaged"] else 0
    n = len(rows)
    return {"n": n, "mobile": mobile, "desktop": n - mobile, "engaged": engaged,
            "by_channel": sorted(by_ch.items(), key=lambda kv: -kv[1]),
            "entries": sorted(entries.items(), key=lambda kv: -kv[1])[:6]}


def traffic(db, p: dict) -> dict:
    cur = _visits_window(db, p["since"], p["until"])
    prev = _visits_window(db, p["prev_since"], p["prev_until"])
    # Конверсия визит -> оплата: только визиты, начавшиеся с дверей (главная, посадочная,
    # мастер), и заказы, оформленные в визите периода.
    doors = db.execute(
        "SELECT COUNT(*) c FROM web_visits v WHERE v.started_at >= ? AND v.started_at < ?"
        f" AND {NOT_BOT} AND {REAL_VISIT} AND (v.entry_path = '/' OR v.entry_path LIKE '/free-check%'"
        " OR v.entry_path LIKE '/free/%' OR v.entry_path = '/free')", (p["since"], p["until"])).fetchone()["c"]
    paid_from_visits = db.execute(
        "SELECT COUNT(*) c FROM orders o JOIN web_visits v ON v.visit_id = o.visit_id"
        f" WHERE v.started_at >= ? AND v.started_at < ? AND o.paid_at IS NOT NULL AND {REAL_ORDER}",
        (p["since"], p["until"])).fetchone()["c"]
    conv = f"{paid_from_visits / doors * 100:.1f}%" if doors else "—"
    return {"cur": cur, "prev": prev, "d_n": delta(cur["n"], prev["n"]),
            "doors": doors, "paid_from_visits": paid_from_visits, "conversion": conv,
            "channels": [(CHANNEL_LABELS.get(k, k), k, n) for k, n in cur["by_channel"]]}


def daily_series(db, days: int = 30) -> dict:
    """Визиты по МОСКОВСКИМ дням (реклама / поиск / остальное) + оплаты по дням."""
    today = datetime.datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    start = today - datetime.timedelta(days=days - 1)
    since = _utc(start)
    day_keys = [(start + datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days)]
    ser = {k: {"ads": 0, "organic": 0, "other": 0, "paid": 0, "free": 0} for k in day_keys}
    for r in db.execute(
            "SELECT v.started_at, v.channel FROM web_visits v WHERE v.started_at >= ?"
            f" AND {NOT_BOT} AND {REAL_VISIT}", (since,)):
        d = ser.get(msk_day(r["started_at"]))
        if d is None:
            continue
        ch = r["channel"] or "direct"
        d["ads" if ch in ("ads", "meta") else "organic" if ch == "organic" else "other"] += 1
    for r in db.execute(
            f"SELECT o.paid_at FROM orders o WHERE o.paid_at >= ? AND {REAL_ORDER}", (since,)):
        d = ser.get(msk_day(r["paid_at"]))
        if d is not None:
            d["paid"] += 1
    for r in db.execute(
            "SELECT created_at FROM free_analyses WHERE created_at >= ? AND status <> 'answers'"
            " AND COALESCE(is_test,0) = 0", (since,)):
        d = ser.get(msk_day(r["created_at"]))
        if d is not None:
            d["free"] += 1
    points = [{"day": k, "label": k[8:10] + "." + k[5:7], **ser[k]} for k in day_keys]
    peak = max((pt["ads"] + pt["organic"] + pt["other"] for pt in points), default=0)
    return {"points": points, "peak": max(peak, 1), "days": days}


# --- 4. Бесплатная дверь: когорты по неделям --------------------------------------

def free_cohorts(db, weeks: int = 8) -> dict:
    today = datetime.datetime.now(MSK).replace(hour=0, minute=0, second=0, microsecond=0)
    monday = today - datetime.timedelta(days=today.weekday())
    first = monday - datetime.timedelta(weeks=weeks - 1)
    rows = db.execute(
        "SELECT * FROM free_analyses WHERE created_at >= ? AND COALESCE(is_test,0) = 0"
        " ORDER BY id", (_utc(first),)).fetchall()
    per_analysis, pairs = fa._attribute_orders(db, rows)
    lag_days: list[int] = []
    for pr in pairs:
        try:
            a = datetime.datetime.fromisoformat(pr["free_at"].replace(" ", "T"))
            b = datetime.datetime.fromisoformat(pr["order_at"].replace(" ", "T"))
            lag_days.append(max(0, (b - a).days))
        except ValueError:
            pass
    cohorts = []
    for i in range(weeks):
        w_start = first + datetime.timedelta(weeks=i)
        w_end = w_start + datetime.timedelta(weeks=1)
        lo, hi = _utc(w_start), _utc(w_end)
        rs = [r for r in rows if lo <= r["created_at"] < hi]
        with_email = sum(1 for r in rs if r["email"])
        uploaded = sum(1 for r in rs if r["status"] != "answers")
        done = sum(1 for r in rs if r["status"] == "done")
        orders = sum(1 for r in rs if per_analysis.get(r["id"]))
        paid = sum(1 for r in rs if any(o["paid_at"] for o in per_analysis.get(r["id"], [])))
        cohorts.append({"week": w_start.strftime("%d.%m"), "n": len(rs), "email": with_email,
                        "uploaded": uploaded, "done": done, "orders": orders, "paid": paid,
                        "conv": f"{paid / len(rs) * 100:.0f}%" if rs else "—"})
    total = {"n": sum(c["n"] for c in cohorts), "email": sum(c["email"] for c in cohorts),
             "uploaded": sum(c["uploaded"] for c in cohorts), "done": sum(c["done"] for c in cohorts),
             "orders": sum(c["orders"] for c in cohorts), "paid": sum(c["paid"] for c in cohorts)}
    total["conv"] = f"{total['paid'] / total['n'] * 100:.1f}%" if total["n"] else "—"
    return {"cohorts": cohorts, "total": total, "weeks": weeks,
            "median_lag": (f"{statistics.median(lag_days):.0f} дн." if lag_days else "—"),
            "pairs_n": len(pairs)}


# --- 5. Расход и цена результата --------------------------------------------------

def spend(db, p: dict) -> dict:
    """Расход по каналам за период (ad_spend, руками) против визитов, лидов и оплат."""
    rows = db.execute(
        "SELECT channel, COALESCE(SUM(rub), 0) rub FROM ad_spend WHERE day >= ? AND day < ?"
        " GROUP BY channel", (p["since_day"], p["until_day"])).fetchall()
    spend_by = {r["channel"]: float(r["rub"] or 0) for r in rows}
    visits_by = {k: n for k, n in _visits_window(db, p["since"], p["until"])["by_channel"]}
    # Лид = анкета с почтой; канал — визит того же visitor_id, ближайший до анкеты.
    leads_by: dict[str, int] = {}
    for r in db.execute(
            "SELECT f.visitor_id, f.created_at FROM free_analyses f WHERE f.email IS NOT NULL"
            " AND f.created_at >= ? AND f.created_at < ? AND COALESCE(f.is_test,0) = 0",
            (p["since"], p["until"])):
        v = db.execute("SELECT channel FROM web_visits WHERE visitor_id = ? AND started_at <= ?"
                       " ORDER BY started_at DESC LIMIT 1", (r["visitor_id"], r["created_at"])).fetchone()
        ch = (v["channel"] if v else None) or "direct"
        leads_by[ch] = leads_by.get(ch, 0) + 1
    paid_by: dict[str, int] = {}
    for r in db.execute(
            f"SELECT {_order_channel_sql()} ch, COUNT(*) n FROM orders o"
            " LEFT JOIN web_visits v ON v.visit_id = o.visit_id"
            f" WHERE o.paid_at >= ? AND o.paid_at < ? AND {REAL_ORDER} GROUP BY ch",
            (p["since"], p["until"])):
        paid_by[r["ch"]] = r["n"]
    table = []
    for key, label in SPEND_CHANNELS:
        s = spend_by.get(key, 0.0)
        vis, leads, paid = visits_by.get(key, 0), leads_by.get(key, 0), paid_by.get(key, 0)
        table.append({
            "key": key, "label": label, "spend": round(s), "visits": vis, "leads": leads, "paid": paid,
            "cpv": f"{s / vis:.0f} ₽" if s and vis else "—",
            "cpl": f"{s / leads:.0f} ₽" if s and leads else "—",
            "cpa": f"{s / paid:.0f} ₽" if s and paid else "—",
        })
    recent = db.execute(
        "SELECT id, day, channel, rub, note FROM ad_spend ORDER BY day DESC, id DESC LIMIT 12").fetchall()
    return {"table": table, "total": round(sum(spend_by.values())),
            "recent": [dict(r) for r in recent], "channels": SPEND_CHANNELS,
            "today": datetime.datetime.now(MSK).strftime("%Y-%m-%d")}


# --- Сборка --------------------------------------------------------------------------

def build(db, days: str, heartbeats: list[dict]) -> dict:
    p = period(days)
    return {
        "p": p,
        "money": money(db, p),
        "problems": problems(db, heartbeats),
        "traffic": traffic(db, p),
        "series": daily_series(db, 30),
        "free": free_cohorts(db),
        "spend": spend(db, p),
        "model_since": "14.08.2026",
    }
