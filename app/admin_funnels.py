"""Воронки по ВИЗИТАМ: две двери сайта.

Что было не так раньше. Старая воронка (`FUNNEL_STEPS` в admin.py) считала девять
НЕЗАВИСИМЫХ множеств уникальных посетителей за период и делила одно на другое.
Из этого следовало три беды: шаг мог оказаться больше предыдущего; человек, пришедший
пять раз за месяц, был единицей; а последние шаги (оплата, доставка отчёта) приходят
от воркера без visitor_id и попадали в ту же таблицу через COALESCE-трюк.

Здесь единица — ВИЗИТ (web_visits, окно 30 минут), и шаги двух РАЗНЫХ видов:

  * ШАГ-НАБЛЮДЕНИЕ (`path`) — «доскроллил до цен». Пропуск такого шага ЗНАЧИМ:
    человек мог прийти по прямой ссылке сразу на форму заказа, и записывать ему
    «видел цены» только ради красивой убывающей таблицы — враньё. Такие шаги
    считаются как есть, без достройки.
  * ШАГ-ВОРОТА (`gate`) — «открыл форму», «дошёл до оплаты», «оплатил». Через них
    нельзя пройти, минуя предыдущие, поэтому здесь достраиваем по самым дальним
    достигнутым воротам: недолетевший маяк не должен рвать воронку. Внутри блока
    ворот вложенность гарантирована по построению.

Из-за этого блок наблюдений и блок ворот считаются отдельно, а переход между ними
может быть и больше 100% — это не ошибка, а находка: столько людей пришло к
оформлению, минуя лендинг.

«Оплатил» берётся из ЗАКАЗА (orders.visit_id + paid_at), а не из события: оплату
подтверждает вебхук ЮKassa, в котором браузера и визита нет вообще.
"""
from __future__ import annotations

NOT_BOT = "(v.device IS NULL OR v.device <> 'bot')"

PATH, GATE = "path", "gate"

# (подпись, признак, вид). Признак: имя события либо префикс с '*'.
PAID_STEPS: list[tuple[str, str, str]] = [
    ("Открыл лендинг", "landing_view", PATH),
    ("Задержался (скролл/15 c)", "engaged", PATH),
    ("Прокрутил половину", "click:scroll_50", PATH),
    ("Досмотрел до цен", "click:sec_prices", PATH),
    ("Открыл форму заказа", "order_form_view", GATE),
    ("Начал заполнять", "form_started", GATE),
    ("Создал заказ", "order_created", GATE),
    ("Дошёл до оплаты", "checkout_view", GATE),
]

FREE_STEPS: list[tuple[str, str, str]] = [
    ("Открыл /free", "free_view", GATE),
    ("Ввёл имя и возраст", "click:free_step1", GATE),
    ("Выбрал, что зацепило", "click:free_concern_*", GATE),
    ("Дошёл до вывода", "free_summary", GATE),
    ("Отправил рисунок", "free_upload", GATE),
    ("Открыл готовый разбор", "free_result_view", GATE),
    ("Нажал «заказать отчёт»", "click:free_to_order", GATE),
    ("Создал заказ", "order_created", GATE),
]


def _visit_types(db, since: str) -> dict[str, dict]:
    """{visit_id: {types, device, channel, screen_w}} за период, без ботов."""
    out: dict[str, dict] = {}
    for r in db.execute(
            "SELECT v.visit_id, v.device, v.channel, v.screen_w FROM web_visits v"
            f" WHERE v.started_at >= ? AND {NOT_BOT}", (since,)):
        out[r["visit_id"]] = {"types": set(), "device": r["device"] or "—",
                              "channel": r["channel"] or "direct",
                              "screen_w": r["screen_w"]}
    if not out:
        return out
    for r in db.execute(
            "SELECT DISTINCT visit_id, type FROM events"
            " WHERE visit_id IS NOT NULL AND created_at >= ?", (since,)):
        v = out.get(r["visit_id"])
        if v is not None:
            v["types"].add(r["type"])
    return out


def _orders_by_visit(db, since: str) -> dict[str, dict]:
    """Заказы, оформленные В ВИЗИТЕ. Оплата приходит позже и вне визита — берём её
    из самого заказа, поэтому «оплатил» не зависит от того, был ли браузер открыт."""
    out: dict[str, dict] = {}
    for r in db.execute(
            "SELECT visit_id, COUNT(*) n,"
            " SUM(CASE WHEN paid_at IS NOT NULL THEN 1 ELSE 0 END) paid,"
            " COALESCE(SUM(CASE WHEN paid_at IS NOT NULL THEN price_kopecks ELSE 0 END), 0) k"
            " FROM orders WHERE visit_id IS NOT NULL AND created_at >= ?"
            " GROUP BY visit_id", (since,)):
        out[r["visit_id"]] = {"n": r["n"], "paid": r["paid"] or 0,
                              "rub": (r["k"] or 0) // 100}
    return out


def _has(types: set[str], marker: str) -> bool:
    if marker.endswith("*"):
        return any(t.startswith(marker[:-1]) for t in types)
    return marker in types


def _is_mobile(v: dict) -> bool:
    """По УЗКОМУ ЭКРАНУ, если клиент его прислал, иначе по user-agent: верстка ломается
    по ширине, а UA не знает ни про узкое окно, ни про планшет в режиме десктопа."""
    sw = v["screen_w"] or 0
    return (0 < sw < 640) if sw else (v["device"] == "mobile")


def _funnel(visits: dict, orders: dict, steps: list, entry_marker: str) -> dict:
    """Одна дверь. entry_marker — что делает визит частью этой воронки."""
    rows = [{"label": label, "kind": kind, "n": 0, "mobile": 0, "desktop": 0}
            for label, _m, kind in steps]
    rows.append({"label": "Оплатил", "kind": GATE, "n": 0, "mobile": 0, "desktop": 0})
    gate_idx = [i for i, (_l, _m, k) in enumerate(steps) if k == GATE]
    total, revenue = 0, 0

    for vid, v in visits.items():
        if not _has(v["types"], entry_marker):
            continue
        total += 1
        mob = _is_mobile(v)
        o = orders.get(vid)

        def hit(i: int) -> None:
            rows[i]["n"] += 1
            rows[i]["mobile" if mob else "desktop"] += 1

        # 1. Наблюдения — как есть, без достройки.
        for i, (_l, marker, kind) in enumerate(steps):
            if kind == PATH and _has(v["types"], marker):
                hit(i)
        # 2. Ворота — по самым дальним достигнутым; заказ сам по себе доказывает,
        #    что пройдены все ворота до «создал заказ» включительно.
        deepest = -1
        for i in gate_idx:
            if _has(v["types"], steps[i][1]):
                deepest = i
        if o:
            created = [i for i in gate_idx if steps[i][1] == "order_created"]
            if created:
                deepest = max(deepest, created[0])
        for i in gate_idx:
            if i <= deepest:
                hit(i)
        # 3. Оплата — только из заказа.
        if o and o["paid"]:
            hit(len(rows) - 1)
            revenue += o["rub"]

    out, prev = [], None
    first = rows[0]["n"] if rows else 0
    for r in rows:
        out.append({
            **r,
            "pct_prev": f"{r['n'] / prev * 100:.0f}%" if prev else "",
            "pct_top": f"{r['n'] / first * 100:.1f}%" if first else "",
            "lost": (prev - r["n"]) if prev is not None and prev > r["n"] else 0,
        })
        prev = r["n"] or None
    return {"steps": out, "visits": total, "revenue": revenue}


def build(db, since: str) -> dict:
    """Обе двери + сводка по визитам за период."""
    visits = _visit_types(db, since)
    orders = _orders_by_visit(db, since)

    devices: dict[str, int] = {}
    channels: dict[str, dict] = {}
    for vid, v in visits.items():
        devices[v["device"]] = devices.get(v["device"], 0) + 1
        ch = channels.setdefault(v["channel"], {"visits": 0, "orders": 0,
                                                "paid": 0, "rub": 0})
        ch["visits"] += 1
        o = orders.get(vid)
        if o:
            ch["orders"] += o["n"]
            ch["paid"] += o["paid"]
            ch["rub"] += o["rub"]
    return {
        "paid": _funnel(visits, orders, PAID_STEPS, "landing_view"),
        "free": _funnel(visits, orders, FREE_STEPS, "free_view"),
        "visits_total": len(visits),
        "devices": sorted(devices.items(), key=lambda kv: -kv[1]),
        "channels": sorted(channels.items(), key=lambda kv: -kv[1]["visits"]),
    }
