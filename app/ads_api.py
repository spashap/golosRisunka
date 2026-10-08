"""API для рекламного агента: /api/ads/v1/*.

Агент (Claude Code партнёра, который ведёт Директ/Meta) присылает сюда расход и клики
до уровня «день × кампания × объявление × фраза» и забирает обратно отчёт: что эти
клики сделали на сайте (app/ads.py). Без этого расход вводился руками раз в неделю,
а агент не видел результата своих кликов вообще.

Доступ: заголовок `Authorization: Bearer <ADS_API_TOKEN>` (серверный .env). Пустой или
короткий токен = API выключен (404). Токен НЕ даёт доступа ни к чему, кроме этого API.
Персональных данных API не отдаёт: ни почт, ни имён, ни текстов родителей — только счётчики.

Запись идемпотентна: POST /stats ЗАМЕНЯЕТ все строки каждой присланной тройки
(день, источник, кампания). Повторная отправка того же отчёта не удваивает расход,
а исправленный отчёт целиком вытесняет прежний — в том числе другой уровень разбивки.
"""
from __future__ import annotations

import datetime
import hmac
import re

from flask import Blueprint, jsonify, request

from app import ads
from app.db import get_db, now
from config import settings

bp_ads_api = Blueprint("ads_api", __name__, url_prefix="/api/ads/v1")

API_VERSION = 1
MIN_TOKEN_LEN = 24
RATE_PER_MIN = 120
MAX_ROWS = 5000
MAX_DAYS_BACK = 400
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_STATUSES = ("active", "paused", "archived", "")

SITE_INFO = {
    "landings": {
        "free": {"url": "/free-check", "purpose": "free door for cold paid traffic; one action -> /free/"},
        "paid": {"url": "/", "purpose": "main sales page of the paid report"},
    },
    "paid_sitelinks": {"/#primery": "sample reports", "/#ceny": "prices",
                       "/#kak": "how it works", "/#faq": "questions"},
    "sample_reports": ["/r/primer-3-goda", "/r/primer-6-let", "/r/primer-8-let", "/r/primer-2-risunka"],
    "never_land_on": ["/blog/*", "/order", "/free/ (go via /free-check)"],
    "utm_template_yandex": ("?utm_source=yandex&utm_medium=cpc&utm_campaign=<free|paid>_{campaign_id}"
                            "&utm_content={ad_id}_{source_type}&utm_term={keyword}"),
    "utm_template_meta": ("?utm_source=meta&utm_medium=cpc&utm_campaign=free_<name>"
                          "&utm_content=<ad_name>&utm_term=<adset_name>"),
    "utm_rules": "utm_medium must be cpc; campaign id = first 6+ digits of utm_campaign; "
                 "ad id = leading digits of utm_content; keyword = utm_term",
    "attribution": {"model": "last paid click of the same visitor", "window_days": ads.ATTRIBUTION_DAYS,
                    "credited_to": "the Moscow day of the click (recent days keep filling in)"},
    "funnel_definitions": {
        "visits": "ad clicks that reached the site (return visits after a pause are not re-counted)",
        "real_visits": "browser ran our script (bots and instant exits mostly don't)",
        "suspect_visits": "yandex-tagged visit without yclid (manual link or robot)",
        "quick_exits": f"visit shorter than {ads.QUICK_EXIT_SEC} s",
        "free_wizard": "opened /free/ in the click visit",
        "free_started": "answered the free questions (credited)",
        "free_leads": "free analysis with an email (credited) = LEAD",
        "free_results": "free analysis delivered (credited)",
        "order_form": "opened /order in the click visit",
        "orders": "order created = reached payment page (credited)",
        "paid": "order paid, from the payment provider, not the browser (credited)",
        "revenue_rub": "paid minus refunds",
    },
}


# --- Ответы / журнал -----------------------------------------------------------------

def _log(status: int, rows: int = 0, note: str = "") -> None:
    try:
        db = get_db()
        db.execute("INSERT INTO ad_api_log (created_at, method, path, status, rows, note)"
                   " VALUES (?,?,?,?,?,?)",
                   (now(), request.method, request.path[:120], status, rows, note[:300] or None))
        db.commit()
    except Exception:
        try:
            get_db().rollback()
        except Exception:
            pass


def _err(status: int, msg: str, **extra):
    _log(status, note=msg)
    return jsonify({"ok": False, "error": msg, **extra}), status


@bp_ads_api.before_request
def _auth():
    token = settings.ADS_API_TOKEN
    if len(token) < MIN_TOKEN_LEN:
        return jsonify({"ok": False, "error": "not_found"}), 404
    h = request.headers.get("Authorization", "")
    given = h[7:].strip() if h.lower().startswith("bearer ") else ""
    if not given or not hmac.compare_digest(given, token):
        return _err(401, "unauthorized")
    db = get_db()
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(seconds=60)).isoformat(timespec="seconds")
    n = db.execute("SELECT COUNT(*) c FROM ad_api_log WHERE created_at >= ?", (since,)).fetchone()["c"]
    if n >= RATE_PER_MIN:
        return jsonify({"ok": False, "error": "rate_limited", "retry_after_sec": 60}), 429
    return None


def _json_body() -> dict | None:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else None


def _day_range():
    """?from=YYYY-MM-DD&to=YYYY-MM-DD (московские дни, включительно); по умолчанию 14 дней."""
    t = ads.today_msk()
    d_to = ads.parse_day(request.args.get("to")) or t
    d_from = ads.parse_day(request.args.get("from")) or (d_to - datetime.timedelta(days=13))
    if d_from > d_to:
        d_from, d_to = d_to, d_from
    if (d_to - d_from).days > MAX_DAYS_BACK:
        d_from = d_to - datetime.timedelta(days=MAX_DAYS_BACK)
    return d_from, d_to


# --- Служебное -----------------------------------------------------------------------

@bp_ads_api.get("/ping")
def ping():
    _log(200)
    return jsonify({"ok": True, "api_version": API_VERSION, "site_version": settings.APP_VERSION,
                    "today_msk": ads.today_msk().isoformat()})


@bp_ads_api.get("/site")
def site():
    """Живые цены и правила посадок: цены меняются в админке, в объявлении — только отсюда."""
    products = []
    for code, p in settings.get_products().items():
        if p.get("enabled"):
            products.append({"code": code, "title": p.get("title"), "price_rub": p.get("price_rub"),
                             "old_price_rub": p.get("old_price_rub") or None,
                             "drawings_max": p.get("drawings_max")})
    _log(200)
    return jsonify({"ok": True, "base_url": f"https://{settings.SITE_DOMAIN}",
                    "products": products, **SITE_INFO})


# --- Кампании ------------------------------------------------------------------------

@bp_ads_api.get("/campaigns")
def campaigns_list():
    rows = [dict(r) for r in get_db().execute(
        "SELECT * FROM ad_campaigns ORDER BY source, campaign_id")]
    _log(200, len(rows))
    return jsonify({"ok": True, "campaigns": rows})


@bp_ads_api.route("/campaigns", methods=["PUT", "POST"])
def campaigns_upsert():
    body = _json_body()
    items = body.get("campaigns") if body else None
    if not isinstance(items, list) or not 1 <= len(items) <= 500:
        return _err(400, "body must be {\"campaigns\": [ ... 1..500 items ]}")
    errors, clean = [], []
    for i, c in enumerate(items):
        if not isinstance(c, dict):
            errors.append({"i": i, "error": "item must be an object"})
            continue
        src = ads.norm_source(str(c.get("source") or ""))
        cid = str(c.get("campaign_id") or "").strip()
        cell = str(c.get("cell") or "").strip().lower()
        status = str(c.get("status") or "").strip().lower()
        landing = str(c.get("landing") or "").strip()[:200]
        e = []
        if not src:
            e.append("source required (yandex | meta | ...)")
        if not _ID_RE.match(cid):
            e.append("campaign_id required: 1-64 of [A-Za-z0-9_.-]")
        if cell and cell not in ads.CELLS:
            e.append(f"cell must be one of {list(ads.CELLS)}")
        if status not in _STATUSES:
            e.append(f"status must be one of {[s for s in _STATUSES if s]}")
        if landing and not landing.startswith(("/", "https://")):
            e.append("landing must be a path (/free-check) or https URL")
        if e:
            errors.append({"i": i, "error": "; ".join(e)})
            continue
        clean.append((src, cid, str(c.get("name") or "").strip()[:200] or None, cell or None,
                      landing or None, status or None, str(c.get("notes") or "").strip()[:1000] or None))
    if errors:
        return _err(400, "validation failed", errors=errors)
    db = get_db()
    for src, cid, name, cell, landing, status, notes in clean:
        db.execute(
            "INSERT INTO ad_campaigns (source, campaign_id, name, cell, landing, status, notes, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(source, campaign_id) DO UPDATE SET"
            " name = excluded.name, cell = excluded.cell, landing = excluded.landing,"
            " status = excluded.status, notes = excluded.notes, updated_at = excluded.updated_at",
            (src, cid, name, cell, landing, status, notes, now()))
    db.commit()
    warnings = [f"{src}/{cid}: landing {landing} is not one of the two allowed landings"
                for src, cid, _n, _c, landing, _s, _no in clean
                if landing and landing.split("?")[0].replace(f"https://{settings.SITE_DOMAIN}", "")
                not in ("/", "/free-check")]
    _log(200, len(clean))
    return jsonify({"ok": True, "upserted": len(clean), "warnings": warnings})


# --- Расход ----------------------------------------------------------------------------

def _num(v, kind, lo, hi):
    if v is None or v == "":
        return None, None
    try:
        x = kind(v)
    except (TypeError, ValueError):
        return None, "not a number"
    if kind is int and isinstance(v, float) and not v.is_integer():
        return None, "must be an integer"
    if not lo <= x <= hi:
        return None, f"out of range {lo}..{hi}"
    return x, None


@bp_ads_api.post("/stats")
def stats_write():
    body = _json_body()
    items = body.get("rows") if body else None
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ROWS:
        return _err(400, f"body must be {{\"rows\": [ ... 1..{MAX_ROWS} items ], \"dry_run\": false}}")
    dry = bool(body.get("dry_run"))
    today = ads.today_msk()
    oldest = today - datetime.timedelta(days=MAX_DAYS_BACK)
    errors, merged, warnings = [], {}, []
    for i, r in enumerate(items):
        if not isinstance(r, dict):
            errors.append({"i": i, "error": "row must be an object"})
            continue
        e = []
        day = ads.parse_day(str(r.get("day") or ""))
        if day is None:
            e.append("day must be YYYY-MM-DD (Moscow date)")
        elif not oldest <= day <= today:
            e.append(f"day must be within {oldest}..{today}")
        src = ads.norm_source(str(r.get("source") or ""))
        if not src:
            e.append("source required")
        cid = str(r.get("campaign_id") or "").strip()
        if not _ID_RE.match(cid):
            e.append("campaign_id required: 1-64 of [A-Za-z0-9_.-]")
        ad_id = str(r.get("ad_id") or "").strip()
        if ad_id and not _ID_RE.match(ad_id):
            e.append("ad_id: 1-64 of [A-Za-z0-9_.-] or omit")
        raw_kw = r.get("keyword")
        kw = ads.norm_keyword(str(raw_kw)) if raw_kw else ""
        imp, e1 = _num(r.get("impressions"), int, 0, 10 ** 9)
        clk, e2 = _num(r.get("clicks"), int, 0, 10 ** 8)
        cost, e3 = _num(r.get("cost_rub"), float, 0, 10 ** 7)
        for name, err in (("impressions", e1), ("clicks", e2), ("cost_rub", e3)):
            if err:
                e.append(f"{name}: {err}")
        if cost is None and not e3:
            e.append("cost_rub required (0 is fine)")
        if e:
            errors.append({"i": i, "error": "; ".join(e)})
            continue
        k = (day.isoformat(), src, cid, ad_id, kw)
        if k in merged:
            m = merged[k]
            for f, v in (("impressions", imp), ("clicks", clk)):
                if v is not None:
                    m[f] = (m[f] or 0) + v
            m["cost_rub"] += cost
            warnings.append(f"row {i}: same day/campaign/ad/keyword as an earlier row after"
                            f" normalisation ('{kw}') — summed")
        else:
            merged[k] = {"impressions": imp, "clicks": clk, "cost_rub": cost}
    if errors:
        return _err(400, "validation failed", errors=errors[:200], error_count=len(errors))

    groups = sorted({k[:3] for k in merged})
    db = get_db()
    known = {(r["source"], r["campaign_id"]) for r in db.execute("SELECT source, campaign_id FROM ad_campaigns")}
    for g in {(s, c) for _d, s, c in groups} - known:
        warnings.append(f"campaign {g[0]}/{g[1]} is not registered: PUT /campaigns with its name and cell")
    for g in groups:
        ad_levels = {k[3] == "" for k in merged if k[:3] == g}
        if len(ad_levels) > 1:
            warnings.append(f"{'/'.join(g)}: rows with and without ad_id mixed — they are"
                            " stored side by side, make sure costs don't overlap")
    if not dry:
        try:
            for d, s, c in groups:
                db.execute("DELETE FROM ad_stats WHERE day = ? AND source = ? AND campaign_id = ?",
                           (d, s, c))
            ts = now()
            for (d, s, c, a, kw), m in merged.items():
                db.execute(
                    "INSERT INTO ad_stats (day, source, campaign_id, ad_id, keyword, impressions,"
                    " clicks, cost_rub, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (d, s, c, a, kw, m["impressions"], m["clicks"], round(m["cost_rub"], 2), ts))
            db.commit()
        except Exception as exc:
            db.rollback()
            return _err(500, f"write failed: {type(exc).__name__}")
    total = round(sum(m["cost_rub"] for m in merged.values()), 2)
    _log(200, len(merged), ("dry_run " if dry else "") + f"groups={len(groups)} cost={total}")
    return jsonify({"ok": True, "dry_run": dry, "groups_replaced": len(groups),
                    "rows_written": 0 if dry else len(merged), "rows_valid": len(merged),
                    "cost_rub_total": total, "warnings": warnings[:100]})


@bp_ads_api.get("/stats")
def stats_read():
    d_from, d_to = _day_range()
    q = "SELECT day, source, campaign_id, ad_id, keyword, impressions, clicks, cost_rub, updated_at" \
        " FROM ad_stats WHERE day >= ? AND day <= ?"
    args: list = [d_from.isoformat(), d_to.isoformat()]
    if request.args.get("source"):
        q += " AND source = ?"
        args.append(ads.norm_source(request.args["source"]))
    if request.args.get("campaign_id"):
        q += " AND campaign_id = ?"
        args.append(request.args["campaign_id"])
    rows = [dict(r) for r in get_db().execute(q + " ORDER BY day, source, campaign_id, ad_id, keyword"
                                              " LIMIT 20000", args)]
    _log(200, len(rows))
    return jsonify({"ok": True, "from": d_from.isoformat(), "to": d_to.isoformat(), "rows": rows})


@bp_ads_api.delete("/stats")
def stats_delete():
    day = ads.parse_day(request.args.get("day"))
    src = ads.norm_source(request.args.get("source"))
    cid = (request.args.get("campaign_id") or "").strip()
    if not day or not src or not _ID_RE.match(cid):
        return _err(400, "day, source and campaign_id are all required")
    db = get_db()
    n = db.execute("DELETE FROM ad_stats WHERE day = ? AND source = ? AND campaign_id = ?",
                   (day.isoformat(), src, cid)).rowcount
    db.commit()
    _log(200, n, f"delete {day}/{src}/{cid}")
    return jsonify({"ok": True, "deleted": n})


# --- Отчёт -----------------------------------------------------------------------------

@bp_ads_api.get("/report")
def report():
    level = request.args.get("level", "campaign")
    if level not in ads.LEVELS:
        return _err(400, f"level must be one of {list(ads.LEVELS)}")
    cell = (request.args.get("cell") or "").strip().lower() or None
    if cell and cell not in ads.CELLS:
        return _err(400, f"cell must be one of {list(ads.CELLS)}")
    d_from, d_to = _day_range()
    rep = ads.report(get_db(), d_from, d_to, level=level,
                     source=request.args.get("source") or None,
                     campaign_id=request.args.get("campaign_id") or None, cell=cell)
    _log(200, len(rep["rows"]))
    return jsonify({"ok": True, **rep, "definitions": SITE_INFO["funnel_definitions"]})


def recent_log(db, limit: int = 30) -> list[dict]:
    return [dict(r) for r in db.execute(
        "SELECT * FROM ad_api_log ORDER BY id DESC LIMIT ?", (limit,))]


def enabled() -> bool:
    return len(settings.ADS_API_TOKEN) >= MIN_TOKEN_LEN
