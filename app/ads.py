"""Реклама: расход и результат по кампании / объявлению / ключевой фразе.

Расход и клики присылает рекламный агент через API (app/ads_api.py -> ad_stats),
кампании — справочник ad_campaigns. Результат — НАШИ визиты, анкеты фремиума и заказы.
Один и тот же отчёт видят агент (GET /api/ads/v1/report) и владелец (/admin/ads),
поэтому все определения живут здесь и только здесь.

АТРИБУЦИЯ (правило; меняешь — меняй и docs в ads_api.SITE_INFO):
  * КЛИК = визит с рекламной меткой (yclid/gclid, UTM с платным utm_medium или канал
    ads/meta), пришедший НЕ с нашего сайта. Возврат после паузы наследует метки прошлого
    визита (track._touch_visit, правило A1) — это тот же клик, второй раз его не считаем.
  * ШАГИ ВНУТРИ визита (мастер /free/, форма заказа) — по событиям самого клика.
  * РЕЗУЛЬТАТЫ (анкета, лид, разбор, заказ, оплата) приписываются ПОСЛЕДНЕМУ рекламному
    клику того же посетителя не раньше чем за ATTRIBUTION_DAYS до результата. Так покупка,
    сделанная позже по ссылке из письма, остаётся за рекламой, а не уходит в «Письма».
  * Результат засчитывается в ДЕНЬ КЛИКА (когорта): последние дни дозаполняются.
  * Ключи: кампания = первые 6+ цифр utm_campaign (иначе вся строка), объявление =
    цифры в начале utm_content, фраза = utm_term после нормализации (norm_keyword).
"""
from __future__ import annotations

import datetime
import json
import re

from config import settings

MSK = datetime.timezone(datetime.timedelta(hours=3))
ATTRIBUTION_DAYS = 30
QUICK_EXIT_SEC = 10
NOT_BOT = "(v.device IS NULL OR v.device NOT IN ('bot', 'owner'))"

LEVELS = {
    "campaign": ("source", "campaign_id"),
    "ad": ("source", "campaign_id", "ad_id"),
    "keyword": ("source", "campaign_id", "keyword"),
    "ad_keyword": ("source", "campaign_id", "ad_id", "keyword"),
    "day": ("day", "source", "campaign_id"),
    "landing": ("source", "campaign_id", "landing"),
}
CELLS = ("free", "paid", "other")
AUTOTARGETING = "---autotargeting"

_AD_MEDIUMS = {"cpc", "ppc", "paid", "cpm", "banner", "ads", "direct"}
_META_SOURCES = {"meta", "facebook", "fb", "instagram", "ig"}
_YANDEX_SOURCES = {"yandex", "ya", "yandex_direct", "yandexdirect", "direct"}


# --- Нормализация ключей (одинаково для визитов и для присланного расхода) ----------

def norm_source(s: str | None) -> str:
    s = (s or "").strip().lower()
    if s in _META_SOURCES:
        return "meta"
    if s in _YANDEX_SOURCES:
        return "yandex"
    return re.sub(r"[^a-z0-9_]", "", s)[:20]


def norm_keyword(s: str | None) -> str:
    """Фраза Директа -> ключ сравнения. Операторы (+ ! " [ ]) и минус-слова не меняют
    смысла фразы, а в отчёте Директа и в {keyword} они пишутся по-разному."""
    s = (s or "").strip().lower().replace("ё", "е")
    if s in (AUTOTARGETING, "автотаргетинг", "autotargeting", "---autotargeting"):
        return AUTOTARGETING
    s = re.sub(r"\s-\S+", " ", " " + s)
    s = re.sub(r'[+!\[\]"]', "", s)
    return re.sub(r"\s+", " ", s).strip()[:200]


def parse_campaign(s: str | None) -> tuple[str, str]:
    """utm_campaign -> (campaign_id, ячейка-подсказка). 'free_714691347' -> ('714691347', 'free')."""
    s = (s or "").strip()
    cell = ""
    low = s.lower()
    for c in ("free", "paid"):
        if low.startswith(c + "_") or low.startswith(c + "-"):
            cell = c
    m = re.search(r"\d{6,}", s)
    return (m.group(0) if m else s[:64]), cell


def parse_content(s: str | None) -> str:
    """utm_content -> id объявления. '1922151938325889098_search' -> '1922151938325889098'."""
    s = (s or "").strip()
    m = re.match(r"^(\d{6,})(?:[_|-].*)?$", s)
    return m.group(1) if m else s[:64]


def ad_params(utm_json: str | None, yclid: str | None, channel: str | None) -> dict | None:
    """Рекламные параметры визита или None, если визит не рекламный."""
    try:
        utm = json.loads(utm_json) if utm_json else {}
    except ValueError:
        utm = {}
    medium = (utm.get("utm_medium") or "").strip().lower()
    is_ad = bool(yclid) or medium in _AD_MEDIUMS or medium.startswith("paid") \
        or channel in ("ads", "meta")
    if not is_ad:
        return None
    source = norm_source(utm.get("utm_source"))
    if not source:
        source = "meta" if channel == "meta" else "yandex" if yclid else "?"
    campaign_id, cell = parse_campaign(utm.get("utm_campaign"))
    return {"source": source, "campaign_id": campaign_id or "?", "cell_hint": cell,
            "ad_id": parse_content(utm.get("utm_content")),
            "keyword": norm_keyword(utm.get("utm_term")),
            # Директ ставит yclid на каждый клик. Метка Директа без yclid — либо ручная
            # ссылка, либо робот: 97 таких визитов в авг–окт были все <10 c ночью.
            "suspect": source == "yandex" and not yclid}


# --- Время ---------------------------------------------------------------------------

def _utc(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def _ts(s: str | None) -> datetime.datetime | None:
    if not s:
        return None
    try:
        d = datetime.datetime.fromisoformat(s.replace("Z", "+00:00").replace(" ", "T"))
    except ValueError:
        return None
    return d if d.tzinfo else d.replace(tzinfo=datetime.timezone.utc)


def msk_day(s: str | None) -> str:
    d = _ts(s)
    return d.astimezone(MSK).strftime("%Y-%m-%d") if d else ""


def today_msk() -> datetime.date:
    return datetime.datetime.now(MSK).date()


def parse_day(s: str | None) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat((s or "").strip())
    except ValueError:
        return None


def day_bounds(d_from: datetime.date, d_to: datetime.date) -> tuple[str, str]:
    """Московские дни [from, to] включительно -> ISO-UTC [since, until)."""
    since = datetime.datetime.combine(d_from, datetime.time(), MSK)
    until = datetime.datetime.combine(d_to + datetime.timedelta(days=1), datetime.time(), MSK)
    return _utc(since), _utc(until)


# --- Сбор данных ---------------------------------------------------------------------

def _is_return_visit(referer: str | None) -> bool:
    host = (referer or "").split("//", 1)[-1].split("/", 1)[0].lower()
    return bool(host) and settings.SITE_DOMAIN in host


def _clicks(db, since: str) -> list[dict]:
    out = []
    for r in db.execute(
            "SELECT v.visit_id, v.visitor_id, v.started_at, v.last_at, v.entry_path, v.engaged,"
            " v.max_scroll, v.device, v.screen_w, v.channel, v.utm_json, v.yclid, v.referer"
            f" FROM web_visits v WHERE v.started_at >= ? AND {NOT_BOT}"
            " AND (v.yclid IS NOT NULL OR v.utm_json IS NOT NULL OR v.channel IN ('ads', 'meta'))",
            (since,)):
        p = ad_params(r["utm_json"], r["yclid"], r["channel"])
        if p is None or _is_return_visit(r["referer"]):
            continue
        a, b = _ts(r["started_at"]), _ts(r["last_at"])
        sw = r["screen_w"] or 0
        entry = (r["entry_path"] or "/").split("?")[0]
        out.append({
            **p, "visit_id": r["visit_id"], "visitor_id": r["visitor_id"],
            "at": a, "started_at": r["started_at"], "day": msk_day(r["started_at"]),
            "landing": "/blog/…" if entry.startswith("/blog/") else entry,
            "real": r["screen_w"] is not None,
            "quick": ((b - a).total_seconds() if a and b else 0) < QUICK_EXIT_SEC,
            "engaged": bool(r["engaged"]),
            "scroll50": (r["max_scroll"] or 0) >= 50,
            "mobile": (0 < sw < 640) if sw else r["device"] == "mobile",
            "steps": set(), "out": _empty_outcomes(),
        })
    return out


def _empty_outcomes() -> dict:
    return {"free_started": 0, "free_leads": 0, "free_results": 0,
            "orders": 0, "paid": 0, "revenue_kop": 0}


_STEP_EVENTS = ("free_check_view", "landing_view", "free_view", "order_form_view",
                "form_started", "checkout_view")


def _attach_steps(db, clicks: list[dict], since: str) -> None:
    by_visit = {c["visit_id"]: c for c in clicks}
    if not by_visit:
        return
    q = ",".join("?" * len(_STEP_EVENTS))
    for r in db.execute(f"SELECT visit_id, type FROM events WHERE created_at >= ?"
                        f" AND visit_id IS NOT NULL AND type IN ({q})", (since, *_STEP_EVENTS)):
        c = by_visit.get(r["visit_id"])
        if c is not None:
            c["steps"].add(r["type"])


def _crediter(clicks: list[dict]):
    by_visitor: dict[str, list[dict]] = {}
    by_visit = {}
    for c in clicks:
        by_visit[c["visit_id"]] = c
        if c["visitor_id"]:
            by_visitor.setdefault(c["visitor_id"], []).append(c)
    for lst in by_visitor.values():
        lst.sort(key=lambda c: c["started_at"])
    window = datetime.timedelta(days=ATTRIBUTION_DAYS)

    def credit(visitor_id: str | None, visit_id: str | None, at: str | None) -> dict | None:
        """Последний рекламный клик посетителя не позже результата и не раньше окна."""
        t = _ts(at)
        if visitor_id and t:
            best = None
            for c in by_visitor.get(visitor_id, []):
                if c["at"] and t - window <= c["at"] <= t + datetime.timedelta(seconds=5):
                    best = c
            if best:
                return best
        return by_visit.get(visit_id) if visit_id else None
    return credit


def _attach_outcomes(db, clicks: list[dict], since: str) -> None:
    credit = _crediter(clicks)
    by_token: dict[str, dict] = {}
    fcols = {r["name"] for r in db.execute("PRAGMA table_info(free_analyses)")}
    vcol = "visit_id" if "visit_id" in fcols else "NULL AS visit_id"
    for r in db.execute(
            f"SELECT token, visitor_id, {vcol}, email, status, created_at FROM free_analyses"
            " WHERE created_at >= ? AND COALESCE(is_test, 0) = 0", (since,)):
        c = credit(r["visitor_id"], r["visit_id"], r["created_at"])
        if c is None:
            continue
        by_token[r["token"]] = c
        o = c["out"]
        o["free_started"] += 1
        o["free_leads"] += 1 if r["email"] else 0
        o["free_results"] += 1 if r["status"] == "done" else 0
    for r in db.execute(
            "SELECT visitor_id, visit_id, free_token, created_at, paid_at, price_kopecks,"
            " refunded_at, refund_kopecks FROM orders"
            " WHERE created_at >= ? AND COALESCE(is_test, 0) = 0", (since,)):
        c = credit(r["visitor_id"], r["visit_id"], r["created_at"]) \
            or by_token.get(r["free_token"] or "")
        if c is None:
            continue
        o = c["out"]
        o["orders"] += 1
        if r["paid_at"]:
            o["paid"] += 1
            refund = (r["refund_kopecks"] or r["price_kopecks"]) if r["refunded_at"] else 0
            o["revenue_kop"] += (r["price_kopecks"] or 0) - refund


# --- Отчёт ---------------------------------------------------------------------------

_COUNTERS = ("impressions", "clicks", "cost_kop", "visits", "real_visits", "suspect_visits",
             "quick_exits", "engaged", "scroll50", "mobile", "free_check_views",
             "landing_views", "free_wizard", "order_form", "form_started", "checkout",
             "free_started", "free_leads", "free_results", "orders", "paid", "revenue_kop")


def _blank() -> dict:
    return {k: 0 for k in _COUNTERS}


def _ratio(a: float, b: float, nd: int = 1) -> float | None:
    return round(a / b, nd) if b else None


def _finish(r: dict) -> dict:
    cost = r["cost_kop"] / 100
    rev = r["revenue_kop"] / 100
    out = {k: v for k, v in r.items() if k not in ("cost_kop", "revenue_kop")}
    out.update({
        "cost_rub": round(cost, 2), "revenue_rub": round(rev, 2),
        "ctr_pct": _ratio(r["clicks"] * 100, r["impressions"], 2),
        "cpc_rub": _ratio(cost, r["clicks"]),
        "visits_per_click": _ratio(r["visits"], r["clicks"], 2),
        "quick_exit_pct": _ratio(r["quick_exits"] * 100, r["visits"]),
        "cost_per_visit_rub": _ratio(cost, r["visits"]),
        "cost_per_wizard_rub": _ratio(cost, r["free_wizard"]),
        "cost_per_lead_rub": _ratio(cost, r["free_leads"]),
        "cost_per_result_rub": _ratio(cost, r["free_results"]),
        "cost_per_order_rub": _ratio(cost, r["orders"]),
        "cost_per_sale_rub": _ratio(cost, r["paid"]),
        "roas": _ratio(rev, cost, 2),
    })
    return out


def _load_campaigns(db) -> dict[tuple[str, str], dict]:
    return {(r["source"], r["campaign_id"]): dict(r)
            for r in db.execute("SELECT * FROM ad_campaigns")}


def report(db, d_from: datetime.date, d_to: datetime.date, level: str = "campaign",
           source: str | None = None, campaign_id: str | None = None,
           cell: str | None = None) -> dict:
    """Расход + клики (их) против визитов и результатов (наших) на выбранном уровне."""
    level = level if level in LEVELS else "campaign"
    dims = LEVELS[level]
    since, until = day_bounds(d_from, d_to)
    lookback = _utc(_ts(since) - datetime.timedelta(days=ATTRIBUTION_DAYS))
    src = norm_source(source) if source else None
    camps = _load_campaigns(db)

    clicks = _clicks(db, lookback)
    _attach_steps(db, clicks, lookback)
    _attach_outcomes(db, clicks, lookback)

    # Посадочная объявления — куда чаще всего приходят его клики (для уровня landing).
    land_votes: dict[tuple, dict[str, int]] = {}
    for c in clicks:
        k = (c["source"], c["campaign_id"], c["ad_id"])
        land_votes.setdefault(k, {}).setdefault(c["landing"], 0)
        land_votes[k][c["landing"]] += 1
    ad_landing = {k: max(v.items(), key=lambda kv: kv[1])[0] for k, v in land_votes.items()}

    rows: dict[tuple, dict] = {}
    cell_hint: dict[tuple, str] = {}

    def key_of(d: dict) -> tuple:
        return tuple(d.get(x, "") for x in dims)

    def keep(s: str, cid: str) -> bool:
        return (not src or s == src) and (not campaign_id or cid == campaign_id)

    for c in clicks:
        if not (since <= c["started_at"] < until) or not keep(c["source"], c["campaign_id"]):
            continue
        k = key_of(c)
        r = rows.setdefault(k, _blank())
        if c["cell_hint"]:
            cell_hint[(c["source"], c["campaign_id"])] = c["cell_hint"]
        r["visits"] += 1
        r["real_visits"] += c["real"]
        r["suspect_visits"] += c["suspect"]
        r["quick_exits"] += c["quick"]
        r["engaged"] += c["engaged"]
        r["scroll50"] += c["scroll50"]
        r["mobile"] += c["mobile"]
        st = c["steps"]
        r["free_check_views"] += "free_check_view" in st
        r["landing_views"] += "landing_view" in st
        r["free_wizard"] += "free_view" in st
        r["order_form"] += "order_form_view" in st
        r["form_started"] += "form_started" in st
        r["checkout"] += "checkout_view" in st
        for k2, v in c["out"].items():
            r[k2] += v

    q = "SELECT * FROM ad_stats WHERE day >= ? AND day <= ?"
    for s in db.execute(q, (d_from.isoformat(), d_to.isoformat())):
        if not keep(s["source"], s["campaign_id"]):
            continue
        d = dict(s)
        d["landing"] = ad_landing.get((s["source"], s["campaign_id"], s["ad_id"]), "?") \
            if s["ad_id"] else "?"
        k = key_of(d)
        r = rows.setdefault(k, _blank())
        r["impressions"] += s["impressions"] or 0
        r["clicks"] += s["clicks"] or 0
        r["cost_kop"] += round((s["cost_rub"] or 0) * 100)

    out_rows, total = [], _blank()
    for k, r in rows.items():
        dd = dict(zip(dims, k))
        meta = camps.get((dd.get("source", ""), dd.get("campaign_id", "")), {})
        c_cell = meta.get("cell") or cell_hint.get((dd.get("source", ""), dd.get("campaign_id", ""))) or ""
        if cell and c_cell != cell:
            continue
        for x in _COUNTERS:
            total[x] += r[x]
        out_rows.append({**dd, "campaign_name": meta.get("name") or "", "cell": c_cell,
                         **_finish(r)})
    out_rows.sort(key=lambda r: (-r["cost_rub"], -r["visits"]))

    last = db.execute("SELECT MAX(updated_at) u, MAX(day) d FROM ad_stats").fetchone()
    quality = {
        "spend_without_visits": [_label(r, dims) for r in out_rows
                                 if r["cost_rub"] > 0 and r["visits"] == 0][:30],
        "visits_without_spend": [_label(r, dims) for r in out_rows
                                 if r["visits"] > 0 and r["cost_rub"] == 0 and r["clicks"] == 0][:30],
        "suspect_visits": total["suspect_visits"],
        "untagged_ad_visits": sum(r["visits"] for r in out_rows if r.get("campaign_id") == "?"),
        "stats_last_update": last["u"] if last else None,
        "stats_last_day": last["d"] if last else None,
    }
    return {"from": d_from.isoformat(), "to": d_to.isoformat(), "level": level,
            "filters": {"source": src, "campaign_id": campaign_id, "cell": cell},
            "rows": out_rows, "totals": _finish(total), "quality": quality,
            "attribution": {"model": "last_paid_click", "window_days": ATTRIBUTION_DAYS,
                            "credited_to": "click_day_msk"}}


def _label(r: dict, dims: tuple) -> str:
    return " / ".join(str(r.get(d) or "—") for d in dims)


def spend_by_channel(db, since_day: str, until_day_excl: str) -> dict[str, float]:
    """Расход из API по каналам дашборда (yandex -> ads, meta -> meta)."""
    out: dict[str, float] = {}
    for r in db.execute("SELECT source, COALESCE(SUM(cost_rub), 0) rub FROM ad_stats"
                        " WHERE day >= ? AND day < ? GROUP BY source", (since_day, until_day_excl)):
        ch = "meta" if r["source"] == "meta" else "ads" if r["source"] == "yandex" else "referral"
        out[ch] = out.get(ch, 0.0) + float(r["rub"] or 0)
    return out
