"""Админка /admin: левый сайдбар, раздел = один экран.

Разделы: analytics (KPI/воронка/источники/события), orders, clients,
coupons (создание/вкл-выкл), prices (цены до/после скидки -> data/products.json),
settings (тексты продуктов -> data/products.json), emails (исходящие из data/outbox/).
Редактируемые json пишутся в data/ (владелец www-data), config/*.json — только дефолт.

Доступ ОТДЕЛЬНЫЙ от клиентского /login: пароль из .env (ADMIN_PASS).
Кука gr_a = HMAC от пароля (stateless; смена пароля разлогинивает).
Пустой ADMIN_PASS = админка выключена (404).
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import json
import re

from flask import (Blueprint, abort, redirect, render_template, request,
                   Response, url_for)

from app import admin_free_analytics as fa
from app import geoip, jobs
from app.db import get_db, now
from config import settings

bp_admin = Blueprint("admin", __name__, url_prefix="/admin")

ADMIN_COOKIE = "gr_a"

# сайдбар: (endpoint, подпись)
SECTIONS = [
    ("admin.analytics", "Аналитика"),
    ("admin.visits", "Визиты"),
    ("admin.actions", "Действия"),
    ("admin.orders", "Заказы"),
    ("admin.clients", "Клиенты"),
    ("admin.coupons", "Промокоды"),
    ("admin.prices", "Цены"),
    ("admin.site_settings", "Настройки сайта"),
    ("admin.report_texts", "Тексты отчёта"),
    ("admin.emails", "Письма"),
    ("admin.free_analytics", "Фремиум"),
    ("admin.free", "Бета"),
]

FUNNEL_STEPS = [
    ("landing_view", "Лендинг"),
    ("engaged", "Вовлёкся (скролл/15с)"),
    ("sample_view", "Смотрел примеры"),
    ("order_form_view", "Открыл форму"),
    ("form_started", "Начал заполнять"),
    ("order_created", "Создал заказ"),
    ("checkout_view", "Дошёл до оплаты"),
    ("order_paid", "Оплатил"),
    ("report_delivered", "Получил отчёт"),
]

PERIODS = [("1", "сегодня"), ("7", "7 дней"), ("30", "30 дней"), ("all", "всё время")]

# Аналитика показывает ТОЛЬКО людей: боты (device='bot', см. app/track.parse_device)
# отсекаются во всех человеко-ориентированных запросах. device IS NULL — серверные
# события воркера (оплата/доставка отчёта) — это не бот, оставляем.
NOT_BOT = "(device IS NULL OR device <> 'bot')"


# --- Авторизация ---

def _admin_token() -> str:
    return hmac.new(settings.ADMIN_PASS.encode(), b"gr-admin-v1",
                    hashlib.sha256).hexdigest()


def _is_admin() -> bool:
    if not settings.ADMIN_PASS:
        return False
    return hmac.compare_digest(request.cookies.get(ADMIN_COOKIE, ""), _admin_token())


def _guard():
    """404 если админка выключена; редирект на пароль если не залогинен."""
    if not settings.ADMIN_PASS:
        abort(404)
    if not _is_admin():
        abort(redirect(url_for("admin.login_form")))


def _render(section_endpoint: str, template: str, **ctx):
    return render_template(template, sections=SECTIONS, active=section_endpoint, **ctx)


@bp_admin.get("/login")
def login_form():
    if not settings.ADMIN_PASS:
        abort(404)
    if _is_admin():
        return redirect(url_for("admin.analytics"))
    return render_template("admin/login.html", error=None)


@bp_admin.post("/login")
def login_submit():
    if not settings.ADMIN_PASS:
        abort(404)
    if not hmac.compare_digest(request.form.get("password", ""), settings.ADMIN_PASS):
        return render_template("admin/login.html", error="Неверный пароль"), 401
    resp = redirect(url_for("admin.analytics"))
    resp.set_cookie(ADMIN_COOKIE, _admin_token(), max_age=30 * 24 * 3600,
                    httponly=True, samesite="Lax")
    return resp


@bp_admin.post("/logout")
def logout():
    resp = redirect("/")
    resp.delete_cookie(ADMIN_COOKIE)
    return resp


@bp_admin.get("/")
def index():
    _guard()
    return redirect(url_for("admin.analytics"))


# --- Помощники периода ---

def _period():
    days = request.args.get("days", "7")
    if days not in {p[0] for p in PERIODS}:
        days = "7"
    if days == "all":
        return days, "0000"
    since = (datetime.datetime.now(datetime.timezone.utc)
             - datetime.timedelta(days=int(days))).isoformat(timespec="seconds")
    return days, since


def _utm_label(j: str | None) -> str:
    try:
        u = json.loads(j) if j else None
    except ValueError:
        u = None
    if not u:
        return "(прямые / без UTM)"
    return " / ".join(filter(None, [u.get("utm_source"), u.get("utm_medium"),
                                    u.get("utm_campaign")]))


# --- Разделы ---

# Дрилл-даун: сколько посетителей раскрывать под каждым шагом воронки / источником.
DRILL_CAP = 60


def _drill_member(row) -> dict:
    """Строка посетителя для раскрытия (воронка/источник): кто + дешёвое гео/устройство."""
    vid = row["visitor_id"]
    cid = row["cid"]
    return {
        "id": (vid or (f"c{cid}" if cid else ""))[:12],
        "geo": geoip.geo_label(row["gc"], row["gr"]),
        "device": row["dev"] or "—",
        "customer": f"c{cid}" if cid else "",
        "time": row["last"][:16].replace("T", " "),
    }


@bp_admin.get("/analytics")
def analytics():
    _guard()
    days, since = _period()
    # По умолчанию считаем только ВОВЛЕЧЁННЫХ (был engaged): landing-only (отказы)
    # отсекаются как и боты. ?show=all — вернуть всех людей. Серверные события
    # (NULL visitor_id: оплата/доставка) — это конверсии, их фильтр не трогает.
    show_all = request.args.get("show") == "all"
    if show_all:
        eng, eng_p = "", []
    else:
        eng = (" AND (visitor_id IS NULL OR visitor_id IN"
               " (SELECT visitor_id FROM events WHERE type='engaged' AND created_at >= ?))")
        eng_p = [since]
    db = get_db()

    # «Все люди» и «вовлечённые» нужны всегда — чтобы показать размер отказов.
    humans = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ?", (since,)).fetchone()["c"]
    engaged = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND type = 'engaged' AND created_at >= ?",
        (since,)).fetchone()["c"]
    landing_only = humans - engaged
    visitors = humans if show_all else engaged
    bots = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        " WHERE visitor_id IS NOT NULL AND device = 'bot' AND created_at >= ?", (since,)).fetchone()["c"]
    orders_total = db.execute(
        "SELECT COUNT(*) c FROM orders WHERE created_at >= ?", (since,)).fetchone()["c"]
    paid = db.execute(
        "SELECT COUNT(*) c, COALESCE(SUM(price_kopecks), 0) s FROM orders"
        " WHERE paid_at IS NOT NULL AND paid_at >= ?", (since,)).fetchone()
    kpi = {
        "visitors": visitors, "orders": orders_total, "paid": paid["c"],
        "revenue_rub": paid["s"] // 100,
        "conversion": f"{paid['c'] / visitors * 100:.1f}%" if visitors else "—",
    }

    # Воронка: счётчики одним grouped-запросом + посетители для раскрытия (capped).
    ftypes = [ev for ev, _ in FUNNEL_STEPS]
    ph = ",".join("?" * len(ftypes))
    counts = {r["type"]: r["c"] for r in db.execute(
        "SELECT type, COUNT(DISTINCT COALESCE(visitor_id, 'c' || customer_id)) c FROM events"
        f" WHERE type IN ({ph}) AND {NOT_BOT} AND created_at >= ?{eng} GROUP BY type",
        (*ftypes, since, *eng_p))}
    fmembers: dict[str, list] = {}
    for row in db.execute(
            "SELECT type, COALESCE(visitor_id, 'c' || customer_id) who, visitor_id,"
            " MAX(geo_country) gc, MAX(geo_region) gr, MAX(device) dev,"
            " MAX(customer_id) cid, MAX(created_at) last FROM events"
            f" WHERE type IN ({ph}) AND {NOT_BOT} AND created_at >= ?{eng}"
            " GROUP BY type, who ORDER BY last DESC", (*ftypes, since, *eng_p)):
        lst = fmembers.setdefault(row["type"], [])
        if len(lst) < DRILL_CAP:
            lst.append(_drill_member(row))
    funnel, prev = [], None
    for ev, label in FUNNEL_STEPS:
        n = counts.get(ev, 0)
        funnel.append({
            "label": label, "n": n, "type": ev,
            "members": fmembers.get(ev, []),
            "pct_prev": f"{n / prev * 100:.0f}%" if prev else "",
            "pct_top": (f"{n / funnel[0]['n'] * 100:.1f}%"
                        if funnel and funnel[0]["n"] else ""),
        })
        prev = n or None

    # Источники: посетители по landing_view (с раскрытием) + заказы/оплаты из orders.
    sources: dict[str, dict] = {}
    src_members: dict[str, list] = {}
    for row in db.execute(
            "SELECT utm_json, visitor_id, MAX(geo_country) gc, MAX(geo_region) gr,"
            " MAX(device) dev, MAX(customer_id) cid, MAX(created_at) last FROM events"
            f" WHERE type = 'landing_view' AND {NOT_BOT} AND created_at >= ?{eng}"
            " GROUP BY utm_json, visitor_id ORDER BY last DESC", (since, *eng_p)):
        label = _utm_label(row["utm_json"])
        s = sources.setdefault(label, {"visitors": 0, "orders": 0, "paid": 0, "rub": 0})
        s["visitors"] += 1
        lst = src_members.setdefault(label, [])
        if len(lst) < DRILL_CAP:
            lst.append(_drill_member(row))
    for row in db.execute(
            "SELECT utm_json, paid_at, price_kopecks FROM orders"
            " WHERE created_at >= ?", (since,)):
        s = sources.setdefault(_utm_label(row["utm_json"]),
                               {"visitors": 0, "orders": 0, "paid": 0, "rub": 0})
        s["orders"] += 1
        if row["paid_at"]:
            s["paid"] += 1
            s["rub"] += row["price_kopecks"] // 100

    events = db.execute(
        "SELECT type, visitor_id, customer_id, device, geo_country, geo_region,"
        f" payload_json, created_at FROM events WHERE {NOT_BOT} AND created_at >= ?{eng}"
        " ORDER BY id DESC LIMIT 60", (since, *eng_p)).fetchall()
    events_view = [{
        "time": e["created_at"][:19].replace("T", " "),
        "type": e["type"],
        "geo": geoip.geo_label(e["geo_country"], e["geo_region"]),
        "device": e["device"] or ("—" if e["visitor_id"] else "сервер"),
        "who": f"c{e['customer_id']}" if e["customer_id"] else (e["visitor_id"] or "")[:8],
        "payload": (e["payload_json"] or "")[:90],
    } for e in events]

    sources_view = [(name, s, src_members.get(name, []))
                    for name, s in sorted(sources.items(), key=lambda kv: -kv[1]["visitors"])]
    # Фремиум на главной вкладке: сколько прошли анкету и чем это кончилось.
    # Фильтр «вовлечённых» сюда не применяем — анкета сама по себе и есть вовлечение.
    return _render("admin.analytics", "admin/analytics.html",
                   days=days, periods=PERIODS, show=request.args.get("show"),
                   kpi=kpi, funnel=funnel, sources=sources_view,
                   free=fa.dashboard_counters(db, since),
                   events=events_view, bots=bots,
                   humans=humans, engaged=engaged, landing_only=landing_only,
                   metrika_configured=bool(settings.YANDEX_METRIKA_ID))


@bp_admin.get("/visits")
def visits():
    """Визиты: устройства, источники (UTM), гео, последние посетители.
    По умолчанию показываем НЕ вовлечённых (отказы); ?show=all — всех.
    Каждая строка раскрывается inline в полную ленту событий посетителя."""
    _guard()
    days, since = _period()
    show = request.args.get("show")          # None/'' = не вовлечённые; 'all' = все
    db = get_db()

    devices = db.execute(
        "SELECT COALESCE(device, '—') d, COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ? GROUP BY device"
        " ORDER BY c DESC", (since,)).fetchall()
    devices_view = [{"device": r["d"], "n": r["c"]} for r in devices]

    src: dict[str, int] = {}
    for row in db.execute(
            "SELECT utm_json, COUNT(DISTINCT visitor_id) c FROM events"
            f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ? GROUP BY utm_json", (since,)):
        src[_utm_label(row["utm_json"])] = src.get(_utm_label(row["utm_json"]), 0) + row["c"]
    sources = sorted(src.items(), key=lambda kv: -kv[1])

    geo_rows = db.execute(
        "SELECT geo_country, COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND geo_country IS NOT NULL"
        " AND created_at >= ? GROUP BY geo_country ORDER BY c DESC LIMIT 15", (since,)).fetchall()
    geo_view = [{"country": geoip.country_name(r["geo_country"]), "n": r["c"]} for r in geo_rows]

    engaged_expr = "MAX(CASE WHEN type = 'engaged' THEN 1 ELSE 0 END)"
    having = "" if show == "all" else f" HAVING {engaged_expr} = 0"
    rows = db.execute(
        "SELECT visitor_id, COUNT(*) n, MIN(created_at) first_seen, MAX(created_at) last_seen,"
        " MAX(device) device, MAX(referer) referer, MAX(utm_json) utm_json,"
        " MAX(customer_id) customer_id, MAX(geo_country) geo_country,"
        " MAX(geo_region) geo_region,"
        f" {engaged_expr} engaged"
        f" FROM events WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ?"
        f" GROUP BY visitor_id{having} ORDER BY last_seen DESC LIMIT 200", (since,)).fetchall()

    ids = [r["visitor_id"] for r in rows]
    timeline = _visitor_timelines(db, ids, since)
    orders_by_vis = _visitor_orders(db, ids)

    visitors_view = [{
        "id": (r["visitor_id"] or "")[:10],
        "full_id": r["visitor_id"],
        "device": r["device"] or "—",
        "utm": _utm_label(r["utm_json"]),
        "referer": (r["referer"] or "")[:60] or "(прямой)",
        "events": r["n"],
        "engaged": bool(r["engaged"]),
        "customer": f"c{r['customer_id']}" if r["customer_id"] else "",
        "geo": geoip.geo_label(r["geo_country"], r["geo_region"]),
        "first": r["first_seen"][:16].replace("T", " "),
        "last": r["last_seen"][:16].replace("T", " "),
        "timeline": timeline.get(r["visitor_id"], []),
        "orders": orders_by_vis.get(r["visitor_id"], []),
    } for r in rows]

    total_visitors = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ?", (since,)).fetchone()["c"]
    engaged = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND type = 'engaged' AND created_at >= ?",
        (since,)).fetchone()["c"]
    bots = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        " WHERE visitor_id IS NOT NULL AND device = 'bot' AND created_at >= ?", (since,)).fetchone()["c"]
    bounce = f"{(total_visitors - engaged) / total_visitors * 100:.0f}%" if total_visitors else "—"

    return _render("admin.visits", "admin/visits.html",
                   days=days, periods=PERIODS, show=show, shown=len(rows),
                   devices=devices_view, sources=sources, geo=geo_view,
                   visitors=visitors_view, total=total_visitors,
                   engaged=engaged, bounce=bounce, bots=bots)


def _visitor_timelines(db, ids: list[str], since: str,
                       cap: int = 100) -> dict[str, list[dict]]:
    """Полная лента событий для показанных посетителей (до cap на каждого)."""
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    rows = db.execute(
        "SELECT visitor_id, type, payload_json, device, referer,"
        " geo_country, geo_region, created_at"
        f" FROM events WHERE visitor_id IN ({ph}) AND created_at >= ?"
        " ORDER BY id DESC", (*ids, since)).fetchall()
    out: dict[str, list[dict]] = {}
    for e in rows:
        lst = out.setdefault(e["visitor_id"], [])
        if len(lst) >= cap:
            continue
        lst.append({
            "time": e["created_at"][:19].replace("T", " "),
            "type": e["type"],
            "payload": (e["payload_json"] or ""),
            "device": e["device"] or "",
            "referer": (e["referer"] or ""),
            "geo": geoip.geo_label(e["geo_country"], e["geo_region"]),
        })
    return out


def _visitor_orders(db, ids: list[str]) -> dict[str, list[dict]]:
    """Заказы, привязанные к показанным посетителям (orders.visitor_id)."""
    if not ids:
        return {}
    ph = ",".join("?" * len(ids))
    out: dict[str, list[dict]] = {}
    try:
        rows = db.execute(
            f"SELECT id, visitor_id, status FROM orders WHERE visitor_id IN ({ph})",
            tuple(ids)).fetchall()
    except Exception:
        return {}
    for r in rows:
        out.setdefault(r["visitor_id"], []).append(
            {"id": r["id"], "status": r["status"]})
    return out


@bp_admin.get("/actions")
def actions():
    """Действия: количество сработавших событий (с фильтром по имени)."""
    _guard()
    days, since = _period()
    q = (request.args.get("q") or "").strip()
    db = get_db()

    params: list = [since]
    where = f"created_at >= ? AND {NOT_BOT}"
    if q:
        where += " AND type LIKE ?"
        params.append(f"%{q}%")

    bots = db.execute(
        "SELECT COUNT(*) c FROM events WHERE created_at >= ? AND device = 'bot'"
        + (" AND type LIKE ?" if q else ""),
        [since] + ([f"%{q}%"] if q else [])).fetchone()["c"]

    summary = db.execute(
        f"SELECT type, COUNT(*) n, COUNT(DISTINCT visitor_id) u, MAX(created_at) last"
        f" FROM events WHERE {where} GROUP BY type ORDER BY n DESC", params).fetchall()
    summary_view = [{
        "type": r["type"], "n": r["n"], "users": r["u"],
        "last": r["last"][:16].replace("T", " ") if r["last"] else "",
    } for r in summary]
    total = sum(r["n"] for r in summary)

    recent = db.execute(
        f"SELECT type, visitor_id, device, payload_json, created_at"
        f" FROM events WHERE {where} ORDER BY id DESC LIMIT 100", params).fetchall()
    recent_view = [{
        "time": e["created_at"][:19].replace("T", " "),
        "type": e["type"],
        "who": (e["visitor_id"] or "")[:8],
        "device": e["device"] or "—",
        "payload": (e["payload_json"] or "")[:80],
    } for e in recent]

    return _render("admin.actions", "admin/actions.html",
                   days=days, periods=PERIODS, q=q,
                   summary=summary_view, total=total, recent=recent_view, bots=bots)


# --- Бета фремиума: разборы, библиотека трактовок, воронка ------------------------

# Сколько минут в очереди считаем зависанием: free_worker опрашивает раз в секунду,
# генерация ~минута. Пять минут в 'queued' означают, что воркер не работает.
FREE_STUCK_MINUTES = 5

FREE_VERDICTS = [("confirmed", "подтверждено источником"),
                 ("narrow", "только в узком контексте"),
                 ("folklore", "фольклор")]


def _heartbeats(db) -> list[dict]:
    """Живы ли фоновые юниты. deploy.sh новый юнит не поднимает, мониторинга нет —
    без этой строки после перезагрузки бокса разборы молча перестали бы делаться."""
    now = datetime.datetime.now(datetime.timezone.utc)
    out = []
    seen = {r["name"]: r["last_seen_at"] for r in
            db.execute("SELECT name, last_seen_at FROM service_heartbeat")}
    for name, label in (("free_worker", "free_worker (бесплатные разборы)"),
                        ("worker", "worker (платные отчёты)")):
        ts = seen.get(name)
        ago = None
        if ts:
            try:
                ago = int((now - datetime.datetime.fromisoformat(ts)).total_seconds())
            except ValueError:
                ago = None
        out.append({"name": name, "label": label, "ago": ago,
                    "ok": ago is not None and ago < 120})
    return out


@bp_admin.get("/free-analytics")
def free_analytics():
    """Отдельная страница аналитики фремиума: глубина прохождения, выбор в анкете,
    покупки после разбора. «Бета» рядом — про КАЧЕСТВО текстов (библиотека трактовок),
    здесь — про ПОВЕДЕНИЕ; смешивать их в одном экране означало бы не читать ни одно."""
    _guard()
    days, since = _period()
    return _render("admin.free_analytics", "admin/free_analytics.html",
                   days=days, periods=PERIODS, **fa.page_data(get_db(), since))


@bp_admin.get("/free")
def free():
    _guard()
    days, since = _period()
    db = get_db()

    rows = db.execute(
        "SELECT * FROM free_analyses WHERE created_at >= ?"
        " ORDER BY id DESC LIMIT 300", (since,)).fetchall()
    items = []
    for r in rows:
        interps = db.execute(
            "SELECT * FROM free_interpretations WHERE analysis_id = ? ORDER BY id",
            (r["id"],)).fetchall()
        items.append({
            "id": r["id"], "token": r["token"],
            "created": (r["created_at"] or "")[:16].replace("T", " "),
            "child": r["child_name"], "age": r["child_age"],
            "concern": r["concern_key"], "duration": r["duration_key"],
            "status": r["status"], "reject": r["reject_reason"],
            "flags": r["flags_json"] or "", "correlate": r["correlate"],
            "ask_variant": r["ask_variant"], "email": r["email"] or "",
            "seconds": r["gen_seconds"], "tok_in": r["prompt_tokens"],
            "tok_out": r["output_tokens"], "repairs": r["repair_rounds"],
            "dropped": r["hypothesis_dropped"],
            "image_deleted": bool(r["deleted_at"]),
            "parent_text": r["parent_text"] or "",
            "interps": [dict(i) for i in interps],
        })

    # Библиотека: группировка по ключу + голоса родителей + текущая разметка.
    lib = db.execute(
        "SELECT i.key, COUNT(*) AS n,"
        " SUM(CASE WHEN i.parent_vote = 'yes' THEN 1 ELSE 0 END) AS yes_n,"
        " SUM(CASE WHEN i.parent_vote = 'no' THEN 1 ELSE 0 END) AS no_n,"
        " MIN(i.created_at) AS first_at, k.verdict, k.note"
        " FROM free_interpretations i"
        " LEFT JOIN free_interpretation_keys k ON k.key = i.key"
        " GROUP BY i.key ORDER BY n DESC").fetchall()
    library = []
    for k in lib:
        examples = db.execute(
            "SELECT phrase, new_key_description, age_scope FROM free_interpretations"
            " WHERE key = ? ORDER BY id DESC LIMIT 3", (k["key"],)).fetchall()
        library.append({**dict(k), "examples": [dict(e) for e in examples]})

    funnel = []
    for status, label in (("answers", "дошли до вывода"), ("queued", "загрузили рисунок"),
                          ("running", "в работе"), ("done", "получили разбор"),
                          ("rejected", "отказ (непригодно)"), ("failed", "сбой")):
        n = db.execute("SELECT COUNT(*) c FROM free_analyses"
                       " WHERE status = ? AND created_at >= ?",
                       (status, since)).fetchone()["c"]
        funnel.append({"status": status, "label": label, "n": n})
    voted = db.execute(
        "SELECT COUNT(*) c FROM free_interpretations WHERE parent_vote IS NOT NULL"
    ).fetchone()["c"]
    with_email = db.execute(
        "SELECT COUNT(*) c FROM free_analyses WHERE email IS NOT NULL"
        " AND created_at >= ?", (since,)).fetchone()["c"]

    stuck = db.execute(
        "SELECT COUNT(*) c FROM free_analyses WHERE status IN ('queued','running')"
        " AND created_at < ?",
        ((datetime.datetime.now(datetime.timezone.utc)
          - datetime.timedelta(minutes=FREE_STUCK_MINUTES)).isoformat(timespec="seconds"),
         )).fetchone()["c"]

    return _render("admin.free", "admin/free.html", days=days, periods=PERIODS,
                   items=items, library=library, funnel=funnel, voted=voted,
                   with_email=with_email, stuck=stuck, verdicts=FREE_VERDICTS,
                   heartbeats=_heartbeats(db), stuck_minutes=FREE_STUCK_MINUTES,
                   msg=request.args.get("msg"))


@bp_admin.post("/free/key/<path:key>")
def free_key_verdict(key: str):
    """Разметка трактовки ПО КЛЮЧУ — это и есть главный результат беты."""
    _guard()
    verdict = (request.form.get("verdict") or "").strip()
    note = (request.form.get("note") or "").strip()
    if verdict not in {v[0] for v in FREE_VERDICTS}:
        return redirect(url_for("admin.free", msg="Неизвестный вердикт"))
    db = get_db()
    db.execute(
        "INSERT INTO free_interpretation_keys (key, verdict, note, first_seen_at,"
        " verdict_at) VALUES (?, ?, ?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET verdict = excluded.verdict,"
        " note = excluded.note, verdict_at = excluded.verdict_at",
        (key, verdict, note, now(), now()))
    db.commit()
    return redirect(url_for("admin.free", msg=f"Ключ {key}: {verdict}"))


@bp_admin.post("/free/<int:analysis_id>/delete-image")
def free_delete_image(analysis_id: int):
    """Удалить фото по просьбе родителя. В проекте не было НИ ОДНОГО пути удаления,
    а первый такой запрос неизбежен: мы храним рисунки чужих детей."""
    _guard()
    from app.free_retention import delete_image
    ok = delete_image(get_db(), analysis_id)
    return redirect(url_for("admin.free",
                            msg="Фото удалено" if ok else "Файла уже нет"))


@bp_admin.post("/free/<int:analysis_id>/allow-replace")
def free_allow_replace(analysis_id: int):
    """Разрешить ещё одну бесплатную попытку в спорном случае (§9)."""
    _guard()
    db = get_db()
    db.execute("UPDATE free_analyses SET allow_replace = 1 WHERE id = ?", (analysis_id,))
    db.commit()
    return redirect(url_for("admin.free", msg="Разрешена повторная загрузка"))


# Вкладки «Заказы»: платные заказы и бесплатные разборы лежат в РАЗНЫХ таблицах
# (orders / free_analyses) и меряются разным — сводить их в один список нельзя,
# но искать «кто у нас был» заказчик приходит на один экран.
ORDER_TABS = [("paid", "Платные заказы"), ("free", "Бесплатные разборы")]


def _free_leads(db, since: str) -> list[dict]:
    """Бесплатные разборы, где родитель оставил почту, — это лиды, а не просто строки
    беты: с ними можно связаться. Без почты разбор виден в разделах «Фремиум»/«Бета»."""
    rows = db.execute(
        "SELECT * FROM free_analyses WHERE email IS NOT NULL AND created_at >= ?"
        " ORDER BY id DESC LIMIT 300", (since,)).fetchall()
    bought = fa.purchases_index(db, rows)
    out = []
    for r in rows:
        buys = bought.get(r["id"], [])
        out.append({
            "id": r["id"], "token": r["token"],
            "created": (r["created_at"] or "")[:16].replace("T", " "),
            "email": r["email"], "child": r["child_name"], "age": r["child_age"],
            "concern": fa.concern_label(r["concern_key"]),
            "status": r["status"], "reject": r["reject_reason"],
            # «Только почта» = ветка «нет рисунка под рукой»: анкета есть, файла нет.
            "email_only": r["status"] == "answers",
            "orders": buys,
            "paid": any(b["paid"] for b in buys),
        })
    return out


@bp_admin.get("/orders")
def orders():
    _guard()
    days, since = _period()
    tab = request.args.get("tab") if request.args.get("tab") in \
        {t[0] for t in ORDER_TABS} else "paid"
    db = get_db()
    free_n = db.execute(
        "SELECT COUNT(*) c FROM free_analyses WHERE email IS NOT NULL"
        " AND created_at >= ?", (since,)).fetchone()["c"]
    if tab == "free":
        return _render("admin.orders", "admin/orders.html",
                       days=days, periods=PERIODS, tab=tab, tabs_items=ORDER_TABS,
                       orders=[], free_leads=_free_leads(db, since),
                       free_n=free_n, msg=request.args.get("msg"))
    rows = get_db().execute(
        "SELECT o.*, r.public_token,"
        " (SELECT COUNT(*) FROM drawings d WHERE d.order_id = o.id) AS drawings_n"
        " FROM orders o LEFT JOIN reports r ON r.order_id = o.id"
        " WHERE o.created_at >= ? ORDER BY o.id DESC LIMIT 300", (since,)).fetchall()
    orders_view = []
    for o in rows:
        child = json.loads(o["child_json"] or "{}")
        orders_view.append({
            "id": o["id"], "created": o["created_at"][:16].replace("T", " "),
            "email": o["email"], "child": child.get("name", ""),
            "product": o["product_code"], "rub": o["price_kopecks"] // 100,
            "coupon": o["coupon_code"] or "", "status": o["status"],
            "drawings": o["drawings_n"], "token": o["public_token"],
            "utm": _utm_label(o["utm_json"]) if o["utm_json"] else "",
        })
    return _render("admin.orders", "admin/orders.html",
                   days=days, periods=PERIODS, tab=tab, tabs_items=ORDER_TABS,
                   orders=orders_view, free_leads=[], free_n=free_n,
                   msg=request.args.get("msg"))


@bp_admin.post("/orders/<int:order_id>/resend")
def order_resend(order_id: int):
    """Кнопка «выслать заново» для проблемных заказов.
    Отчёт уже есть на диске → просто пересылаем письмо (без Gemini).
    Отчёта нет → ставим обратно в 'paid', воркер перегенерирует и доставит."""
    _guard()
    days = request.form.get("days", "7")
    conn = get_db()
    order = conn.execute("SELECT id, status FROM orders WHERE id = ?",
                         (order_id,)).fetchone()
    if order is None:
        abort(404)
    if order["status"] == "created":
        msg = f"Заказ {order_id}: не оплачен — нечего высылать"
    elif order["status"] in ("paid", "generating"):
        msg = f"Заказ {order_id}: уже в обработке"
    elif jobs.report_pdf_path(conn, order_id):
        jobs.resend_report_email(conn, order_id)
        msg = f"Заказ {order_id}: письмо с отчётом отправлено повторно"
    else:
        conn.execute("UPDATE orders SET status = 'paid' WHERE id = ?", (order_id,))
        conn.commit()
        msg = f"Заказ {order_id}: поставлен в очередь на перегенерацию"
    return redirect(url_for("admin.orders", days=days, msg=msg))


@bp_admin.post("/orders/<int:order_id>/regenerate")
def order_regenerate(order_id: int):
    """«Жёсткая» перегенерация (для теста промпта): ставим заказ обратно в очередь
    (paid) ВНЕ зависимости от наличия готового отчёта. Воркер заново сгенерирует
    отчёт ТЕКУЩИМ промптом на тех же загруженных изображениях и отправит письмо.
    public_token (ссылка /r/...) сохраняется."""
    _guard()
    days = request.form.get("days", "7")
    conn = get_db()
    order = conn.execute("SELECT id, status FROM orders WHERE id = ?",
                         (order_id,)).fetchone()
    if order is None:
        abort(404)
    if order["status"] == "created":
        msg = f"Заказ {order_id}: не оплачен — нечего перегенерировать"
    elif order["status"] == "generating":
        msg = f"Заказ {order_id}: уже генерируется"
    else:
        conn.execute("UPDATE orders SET status = 'paid', retry_count = 0,"
                     " next_retry_at = NULL WHERE id = ?", (order_id,))
        conn.commit()
        msg = (f"Заказ {order_id}: перегенерация запущена (текущий промпт) — "
               f"воркер сгенерирует заново и отправит письмо")
    return redirect(url_for("admin.orders", days=days, msg=msg))


CLIENT_TABS = [("all", "Все"), ("buyers", "Покупатели"), ("free", "Из фремиума")]

# Клиент фремиума создаётся в app/free._link_customer, как только родитель оставил почту,
# — то есть в списке он БЫЛ и раньше, но выглядел пустой строкой без детей и заказов.
# Детей фремиум намеренно не заводит (у него полоса возраста, а не birth_ym), поэтому
# имя ребёнка для таких строк берём из самих разборов.
_CLIENTS_SQL = (
    "SELECT c.id, c.email, c.created_at,"
    " (SELECT GROUP_CONCAT(name, ', ') FROM children ch WHERE ch.customer_id = c.id) kids,"
    " (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id) n_orders,"
    " (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id"
    "   AND o.paid_at IS NOT NULL) n_paid,"
    " (SELECT COALESCE(SUM(price_kopecks), 0) FROM orders o"
    "   WHERE o.customer_id = c.id AND o.paid_at IS NOT NULL) paid_k,"
    " (SELECT COUNT(*) FROM free_analyses f WHERE f.customer_id = c.id) n_free,"
    " (SELECT COUNT(*) FROM free_analyses f WHERE f.customer_id = c.id"
    "   AND f.status = 'done') n_free_done,"
    " (SELECT GROUP_CONCAT(DISTINCT f.child_name) FROM free_analyses f"
    "   WHERE f.customer_id = c.id) free_kids"
    " FROM customers c")


@bp_admin.get("/clients")
def clients():
    _guard()
    tab = request.args.get("tab") if request.args.get("tab") in \
        {t[0] for t in CLIENT_TABS} else "all"
    # Фильтр по вычисленным колонкам — во ВНЕШНЕМ запросе: в WHERE самого SELECT
    # алиасы подзапросов не видны, а лимит 500 должен применяться уже после фильтра.
    where = {"buyers": " WHERE n_paid > 0", "free": " WHERE n_free > 0"}.get(tab, "")
    db = get_db()
    rows = db.execute(
        f"SELECT * FROM ({_CLIENTS_SQL}){where} ORDER BY id DESC LIMIT 500").fetchall()
    counts = db.execute(
        f"SELECT COUNT(*) all_n, SUM(CASE WHEN n_paid > 0 THEN 1 ELSE 0 END) buyers_n,"
        f" SUM(CASE WHEN n_free > 0 THEN 1 ELSE 0 END) free_n"
        f" FROM ({_CLIENTS_SQL})").fetchone()
    clients_view = [{
        "id": r["id"], "email": r["email"],
        "created": r["created_at"][:10],
        "kids": r["kids"] or "",
        "free_kids": (r["free_kids"] or "").replace(",", ", "),
        "orders": r["n_orders"], "paid": r["n_paid"], "rub": r["paid_k"] // 100,
        "free": r["n_free"], "free_done": r["n_free_done"],
        # «Только фремиум» — лид без единого заказа: с ним ещё предстоит работа.
        "lead": r["n_free"] > 0 and r["n_orders"] == 0,
    } for r in rows]
    return _render("admin.clients", "admin/clients.html", clients=clients_view,
                   tab=tab, tabs_items=CLIENT_TABS,
                   counts={"all": counts["all_n"], "buyers": counts["buyers_n"] or 0,
                           "free": counts["free_n"] or 0})


@bp_admin.get("/coupons")
def coupons():
    _guard()
    rows = get_db().execute(
        "SELECT * FROM coupons ORDER BY rowid DESC").fetchall()
    return _render("admin.coupons", "admin/coupons.html",
                   coupons=rows, error=request.args.get("err"))


@bp_admin.post("/coupons/create")
def coupons_create():
    _guard()
    code = re.sub(r"[^A-Za-z0-9_-]", "", request.form.get("code", "")).upper()
    try:
        percent = int(request.form.get("percent", ""))
    except ValueError:
        percent = 0
    multi = 1 if request.form.get("multi_use") else 0
    if not code or not (1 <= percent <= 100):
        return redirect(url_for("admin.coupons", err="Код и скидка 1–100% обязательны"))
    db = get_db()
    if db.execute("SELECT 1 FROM coupons WHERE upper(code) = ?", (code,)).fetchone():
        return redirect(url_for("admin.coupons", err=f"Код {code} уже существует"))
    db.execute("INSERT INTO coupons (code, percent_off, multi_use, active)"
               " VALUES (?, ?, ?, 1)", (code, percent, multi))
    db.commit()
    return redirect(url_for("admin.coupons"))


@bp_admin.post("/coupons/<code>/toggle")
def coupons_toggle(code: str):
    _guard()
    db = get_db()
    db.execute("UPDATE coupons SET active = 1 - active WHERE code = ?", (code,))
    db.commit()
    return redirect(url_for("admin.coupons"))


# Редактируемые из админки json живут в data/ (пишет www-data, git pull не трогает);
# config/*.json — read-only дефолт из репозитория (на проде принадлежит root).

def _load_products_for_edit() -> dict:
    src = settings.PRODUCTS_RUNTIME_FILE if settings.PRODUCTS_RUNTIME_FILE.exists() \
        else settings.PRODUCTS_DEFAULT_FILE
    return json.loads(src.read_text(encoding="utf-8"))


def _atomic_write_json(path, data: dict):
    """Пишем во временный файл + rename: читатель никогда не увидит пол-JSON."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


@bp_admin.get("/prices")
def prices():
    """Цены продуктов: до скидки (зачёркнутая) и после скидки (к оплате).
    ЮKassa получает цену ПОСЛЕ скидки минус промокод — см. orders.py."""
    _guard()
    return _render("admin.prices", "admin/prices.html",
                   products=settings.get_products(),
                   saved=request.args.get("saved"),
                   err=request.args.get("err"))


@bp_admin.post("/prices/save")
def prices_save():
    """Правка ТОЛЬКО ценовых полей поверх текущего products.json:
    остальные ключи (тексты, фичи, enabled) не трогаем."""
    _guard()
    data = _load_products_for_edit()
    for code, p in data.items():
        f = lambda k: request.form.get(f"{code}_{k}", "").strip()
        try:
            price = int(f("price_rub"))
        except ValueError:
            return redirect(url_for("admin.prices", err="Цена к оплате — целое число, ₽"))
        if price < 1:
            return redirect(url_for("admin.prices", err="Цена к оплате должна быть больше нуля"))
        # Цена до скидки необязательна: пусто => на сайте нет зачёркнутой цены.
        old = f("old_price_rub")
        if old:
            try:
                old_price = int(old)
            except ValueError:
                return redirect(url_for("admin.prices", err="Цена до скидки — целое число, ₽"))
            if old_price <= price:
                return redirect(url_for("admin.prices",
                                        err="Цена до скидки должна быть выше цены к оплате"))
            p["old_price_rub"] = old_price
        else:
            p.pop("old_price_rub", None)
        p["price_rub"] = price
    _atomic_write_json(settings.PRODUCTS_RUNTIME_FILE, data)
    return redirect(url_for("admin.prices", saved="ok"))


@bp_admin.get("/settings")
def site_settings():
    _guard()
    return _render("admin.site_settings", "admin/settings.html",
                   products=settings.get_products(),
                   metrika_id=settings.YANDEX_METRIKA_ID,
                   mail_backend=settings.MAIL_BACKEND,
                   mail_from=settings.MAIL_FROM_EMAIL,
                   unisender_go_key=bool(settings.UNISENDER_GO_API_KEY),
                   saved=request.args.get("saved"))


@bp_admin.post("/settings/products")
def settings_products_save():
    """Правка продуктов поверх текущего products.json: меняем только
    редактируемые поля, незнакомые ключи сохраняются как есть."""
    _guard()
    data = _load_products_for_edit()
    for code, p in data.items():
        f = lambda k: request.form.get(f"{code}_{k}", "").strip()
        p["enabled"] = bool(request.form.get(f"{code}_enabled"))
        if f("title"):
            p["title"] = f("title")
        p["subtitle"] = f("subtitle")
        # Цены редактируются на отдельной странице «Цены» (/admin/prices).
        p["features"] = [ln.strip() for ln in
                         request.form.get(f"{code}_features", "").splitlines() if ln.strip()]
    if not any(p["enabled"] for p in data.values()):
        return redirect(url_for("admin.site_settings", saved="err"))  # сайт без продуктов нельзя
    _atomic_write_json(settings.PRODUCTS_RUNTIME_FILE, data)
    return redirect(url_for("admin.site_settings", saved="ok"))


@bp_admin.get("/report-texts")
def report_texts():
    """Управляемые тексты в КОНЦЕ отчёта (апсейл по числу рисунков + дисклеймеры +
    свободный блок). Pass-through в пайплайн (config/report_texts.json) — без логики."""
    _guard()
    return _render("admin.report_texts", "admin/report_texts.html",
                   texts=settings.get_report_texts(),
                   saved=request.args.get("saved"))


@bp_admin.post("/report-texts/save")
def report_texts_save():
    """Перезапись data/report_texts.json. Пусто = блок не выводится в отчёте."""
    _guard()
    g = lambda k: request.form.get(k, "").strip()
    data = {
        "upsell": {n: g(f"upsell_{n}") for n in ("1", "2", "3")},
        "disclaimer_main": g("disclaimer_main"),
        "disclaimer_by_count": {n: g(f"disclaimer_by_count_{n}") for n in ("1", "2", "3")},
        "free_text": g("free_text"),
    }
    _atomic_write_json(settings.REPORT_TEXTS_RUNTIME_FILE, data)
    return redirect(url_for("admin.report_texts", saved="ok"))


@bp_admin.get("/emails")
def emails():
    _guard()
    files = []
    if settings.OUTBOX_DIR.exists():
        for p in sorted(settings.OUTBOX_DIR.glob("*.html"), reverse=True)[:200]:
            head = p.read_text(encoding="utf-8")[:600]
            to = re.search(r"^To: (.+)$", head, re.M)
            subj = re.search(r"^Subject: (.+)$", head, re.M)
            m = re.match(r"(\d{8})-(\d{6})", p.name)
            when = (f"{m.group(1)[6:8]}.{m.group(1)[4:6]}.{m.group(1)[:4]} "
                    f"{m.group(2)[:2]}:{m.group(2)[2:4]}" if m else "")
            files.append({"name": p.name, "when": when,
                          "to": to.group(1) if to else "",
                          "subject": subj.group(1) if subj else ""})
    return _render("admin.emails", "admin/emails.html", files=files)


@bp_admin.get("/emails/<name>")
def email_view(name: str):
    _guard()
    if not re.fullmatch(r"[\w.-]+\.html", name):
        abort(404)
    p = settings.OUTBOX_DIR / name
    if not p.exists():
        abort(404)
    return Response(p.read_text(encoding="utf-8"), mimetype="text/html")
