"""Админка /admin: левый сайдбар, раздел = один экран.

Разделы: analytics (KPI/воронка/источники/события), orders, clients,
coupons (создание/вкл-выкл), settings (цены и продукты -> config/products.json),
emails (исходящие из data/outbox/ до Unisender).

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

from app.db import get_db
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
    ("admin.site_settings", "Настройки сайта"),
    ("admin.emails", "Письма"),
]

FUNNEL_STEPS = [
    ("landing_view", "Лендинг"),
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

@bp_admin.get("/analytics")
def analytics():
    _guard()
    days, since = _period()
    db = get_db()

    visitors = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ?", (since,)).fetchone()["c"]
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

    funnel, prev = [], None
    for ev, label in FUNNEL_STEPS:
        n = db.execute(
            "SELECT COUNT(DISTINCT COALESCE(visitor_id, 'c' || customer_id)) c"
            f" FROM events WHERE type = ? AND {NOT_BOT} AND created_at >= ?", (ev, since)).fetchone()["c"]
        funnel.append({
            "label": label, "n": n,
            "pct_prev": f"{n / prev * 100:.0f}%" if prev else "",
            "pct_top": (f"{n / funnel[0]['n'] * 100:.1f}%"
                        if funnel and funnel[0]["n"] else ""),
        })
        prev = n or None

    sources: dict[str, dict] = {}
    for row in db.execute(
            "SELECT utm_json, COUNT(DISTINCT visitor_id) c FROM events"
            f" WHERE type = 'landing_view' AND {NOT_BOT} AND created_at >= ? GROUP BY utm_json", (since,)):
        s = sources.setdefault(_utm_label(row["utm_json"]),
                               {"visitors": 0, "orders": 0, "paid": 0, "rub": 0})
        s["visitors"] += row["c"]
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
        "SELECT type, visitor_id, customer_id, payload_json, created_at FROM events"
        f" WHERE {NOT_BOT} AND created_at >= ? ORDER BY id DESC LIMIT 60", (since,)).fetchall()
    events_view = [{
        "time": e["created_at"][:19].replace("T", " "),
        "type": e["type"],
        "who": (e["visitor_id"] or "")[:8] or (f"c{e['customer_id']}" if e["customer_id"] else ""),
        "payload": (e["payload_json"] or "")[:90],
    } for e in events]

    return _render("admin.analytics", "admin/analytics.html",
                   days=days, periods=PERIODS, kpi=kpi, funnel=funnel,
                   sources=sorted(sources.items(), key=lambda kv: -kv[1]["visitors"]),
                   events=events_view, bots=bots,
                   metrika_configured=bool(settings.YANDEX_METRIKA_ID))


@bp_admin.get("/visits")
def visits():
    """Визиты: устройства, источники (UTM), последние посетители с origin."""
    _guard()
    days, since = _period()
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

    rows = db.execute(
        "SELECT visitor_id, COUNT(*) n, MIN(created_at) first_seen, MAX(created_at) last_seen,"
        " MAX(device) device, MAX(referer) referer, MAX(utm_json) utm_json,"
        " MAX(customer_id) customer_id"
        f" FROM events WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ?"
        " GROUP BY visitor_id ORDER BY last_seen DESC LIMIT 200", (since,)).fetchall()
    visitors_view = [{
        "id": (r["visitor_id"] or "")[:10],
        "device": r["device"] or "—",
        "utm": _utm_label(r["utm_json"]),
        "referer": (r["referer"] or "")[:60] or "(прямой)",
        "events": r["n"],
        "customer": f"c{r['customer_id']}" if r["customer_id"] else "",
        "first": r["first_seen"][:16].replace("T", " "),
        "last": r["last_seen"][:16].replace("T", " "),
    } for r in rows]

    total_visitors = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND created_at >= ?", (since,)).fetchone()["c"]
    bots = db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        " WHERE visitor_id IS NOT NULL AND device = 'bot' AND created_at >= ?", (since,)).fetchone()["c"]

    return _render("admin.visits", "admin/visits.html",
                   days=days, periods=PERIODS, devices=devices_view,
                   sources=sources, visitors=visitors_view, total=total_visitors, bots=bots)


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


@bp_admin.get("/orders")
def orders():
    _guard()
    days, since = _period()
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
                   days=days, periods=PERIODS, orders=orders_view)


@bp_admin.get("/clients")
def clients():
    _guard()
    rows = get_db().execute(
        "SELECT c.id, c.email, c.created_at,"
        " (SELECT GROUP_CONCAT(name, ', ') FROM children ch WHERE ch.customer_id = c.id) kids,"
        " (SELECT COUNT(*) FROM orders o WHERE o.customer_id = c.id) n_orders,"
        " (SELECT COALESCE(SUM(price_kopecks), 0) FROM orders o"
        "   WHERE o.customer_id = c.id AND o.paid_at IS NOT NULL) paid_k"
        " FROM customers c ORDER BY c.id DESC LIMIT 500").fetchall()
    clients_view = [{
        "id": r["id"], "email": r["email"],
        "created": r["created_at"][:10], "kids": r["kids"] or "",
        "orders": r["n_orders"], "rub": r["paid_k"] // 100,
    } for r in rows]
    return _render("admin.clients", "admin/clients.html", clients=clients_view)


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


@bp_admin.get("/settings")
def site_settings():
    _guard()
    return _render("admin.site_settings", "admin/settings.html",
                   products=settings.get_products(),
                   metrika_id=settings.YANDEX_METRIKA_ID,
                   saved=request.args.get("saved"))


@bp_admin.post("/settings/products")
def settings_products_save():
    """Правка продуктов поверх текущего products.json: меняем только
    редактируемые поля, незнакомые ключи сохраняются как есть."""
    _guard()
    path = settings.BASE_DIR / "config" / "products.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for code, p in data.items():
        f = lambda k: request.form.get(f"{code}_{k}", "").strip()
        p["enabled"] = bool(request.form.get(f"{code}_enabled"))
        if f("title"):
            p["title"] = f("title")
        p["subtitle"] = f("subtitle")
        try:
            p["price_rub"] = int(f("price_rub"))
            p["old_price_rub"] = int(f("old_price_rub"))
        except ValueError:
            return redirect(url_for("admin.site_settings", saved="err"))
        p["features"] = [ln.strip() for ln in
                         request.form.get(f"{code}_features", "").splitlines() if ln.strip()]
    if not any(p["enabled"] for p in data.values()):
        return redirect(url_for("admin.site_settings", saved="err"))  # сайт без продуктов нельзя
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return redirect(url_for("admin.site_settings", saved="ok"))


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
