"""Почему форма заказа не доходит до оплаты — и доходит ли бесплатный разбор до формы.

Один расчёт на два места: раздел «Реклама» (/admin/ads) и API рекламного агента
(GET /api/ads/v1/order-diagnostics). Только счётчики и анонимные сессии: ни почт, ни
значений полей (их мы и не собираем — order.js шлёт только ИМЕНА полей).

Откуда данные (все — events):
  order_form_view / form_started / order_form_from_free   — сервер и маяк формы;
  order_form_state   — снимок формы от order.js: поля, последнее поле, фото, секунды,
                       ссылка ухода, свои блокировки (берём ПОСЛЕДНИЙ снимок визита);
  click:order_*      — блокировки и отправка (цели track.js);
  order_form_errors  — отказ серверной проверки (какие поля);
  upload_too_large   — 413: файлы больше лимита;
  order_created / checkout_view / pay_init_* / pay_* — заказ и оплата в визите;
  pay_canceled       — отказ платежа с причиной от ЮKassa (вебхук, без визита: по order_id);
  orders.paid_at     — оплата (из заказа, не из браузера).
Визит учитывается, если браузер выполнил track.js (screen_w): иначе это сканеры,
открывающие /order. Такие показываются отдельной цифрой.
"""
from __future__ import annotations

import json

from app import ads
from config.form_fields import CHILD_FIELDS, DRAWING_FIELDS

NOT_BOT = "(v.device IS NULL OR v.device NOT IN ('bot', 'owner'))"

FIELD_ORDER = ([f"child_{f['key']}" for f in CHILD_FIELDS]
               + [x for i in (1, 2, 3) for x in
                  ([f"d{i}_file"] + [f"d{i}_{f['key']}" for f in DRAWING_FIELDS])]
               + ["email", "coupon"])
_LABELS = {f"child_{f['key']}": f["label"] for f in CHILD_FIELDS}
for _i in (1, 2, 3):
    _LABELS[f"d{_i}_file"] = f"Рисунок {_i}: фото"
    for _f in DRAWING_FIELDS:
        _LABELS[f"d{_i}_{_f['key']}"] = f"Рисунок {_i}: {_f['label']}"
_LABELS.update({"email": "Email для отчёта", "coupon": "Промокод"})

_TYPES = ("order_form_view", "form_started", "order_form_from_free", "order_form_state",
          "order_form_errors", "upload_too_large", "order_created", "checkout_view",
          "pay_init_desktop_widget", "pay_init_mobile_redirect", "pay_create_failed",
          "pay_no_confirmation", "pay_widget_error", "pay_widget_render_failed",
          "pay_status_timeout", "pay_return_pending", "pay_return", "pay_retry_existing",
          "click:order_block_incomplete", "click:order_file_too_big",
          "click:order_blocked_email_typo", "click:order_submit_form",
          "free_result_view", "click:sec_fr_offer", "click:free_to_order",
          "click:free_sample_open", "click:header_order")
_PAY_FAIL = ("pay_create_failed", "pay_no_confirmation", "pay_widget_error",
             "pay_widget_render_failed", "pay_status_timeout")
_TIME_BUCKETS = [(10, "<10 с"), (30, "10–30 с"), (60, "30–60 с"), (180, "1–3 мин"),
                 (600, "3–10 мин"), (10 ** 9, "10+ мин")]


def label(field: str) -> str:
    return _LABELS.get(field, field)


def _bucket(sec: int) -> str:
    for lim, name in _TIME_BUCKETS:
        if sec < lim:
            return name
    return _TIME_BUCKETS[-1][1]


def _payload(p: str | None) -> dict:
    try:
        return json.loads(p) if p else {}
    except ValueError:
        return {}


def _inc(d: dict, k: str, n: int = 1) -> None:
    d[k] = d.get(k, 0) + n


def build(db, d_from, d_to, scope: str = "all", source: str | None = None,
          campaign_id: str | None = None, cell: str | None = None) -> dict:
    """scope='ads' — только визиты людей, пришедших с рекламного клика (с фильтрами
    кампании/ячейки, правило атрибуции то же, что в отчёте рекламы); 'all' — все."""
    since, until = ads.day_bounds(d_from, d_to)

    # 1. Визиты периода, в которых была форма заказа или готовый бесплатный разбор.
    rows = db.execute(
        "SELECT DISTINCT v.visit_id, v.visitor_id, v.started_at, v.device, v.screen_w"
        " FROM events e JOIN web_visits v ON v.visit_id = e.visit_id"
        " WHERE e.type IN ('order_form_view', 'free_result_view')"
        f" AND e.created_at >= ? AND e.created_at < ? AND {NOT_BOT}",
        (since, until)).fetchall()
    unreal = sum(1 for r in rows if r["screen_w"] is None)
    visits = {r["visit_id"]: dict(r) for r in rows if r["screen_w"] is not None}
    credited = {}
    if scope == "ads":
        credited = ads.credited_clicks(
            db, since, [(v["visit_id"], v["visitor_id"], v["started_at"]) for v in visits.values()],
            source=source, campaign_id=campaign_id, cell=cell)
        visits = {k: v for k, v in visits.items() if k in credited}

    # 2. События этих визитов.
    ev: dict[str, list[dict]] = {k: [] for k in visits}
    ids = list(visits)
    q = ",".join("?" * len(_TYPES))
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        for e in db.execute(
                f"SELECT id, visit_id, type, payload_json, created_at FROM events"
                f" WHERE visit_id IN ({','.join('?' * len(chunk))}) AND type IN ({q})"
                " ORDER BY id", (*chunk, *_TYPES)):
            ev[e["visit_id"]].append(dict(e))

    # 3. Заказы этих визитов и отказы платежей (вебхук — по order_id).
    orders: dict[str, list[dict]] = {}
    order_visit: dict[int, str] = {}
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        for o in db.execute(
                f"SELECT id, visit_id, status, paid_at FROM orders WHERE visit_id IN"
                f" ({','.join('?' * len(chunk))}) AND COALESCE(is_test, 0) = 0", chunk):
            orders.setdefault(o["visit_id"], []).append(dict(o))
            order_visit[o["id"]] = o["visit_id"]
    cancels: dict[str, list[str]] = {}
    if order_visit:
        for e in db.execute("SELECT payload_json FROM events WHERE type = 'pay_canceled'"
                            " AND created_at >= ?", (since,)):
            p = _payload(e["payload_json"])
            vid = order_visit.get(p.get("order_id"))
            if vid:
                cancels.setdefault(vid, []).append(p.get("reason") or "unknown")

    # 4. Разбор по визитам.
    F = {k: 0 for k in ("viewed", "from_free", "started", "photo", "email", "submitted",
                        "server_rejected", "created", "payment_started", "payment_failed",
                        "payment_canceled", "paid")}
    field_reach: dict[str, int] = {}
    last_field: dict[str, int] = {}
    stop: dict[str, int] = {}
    via: dict[str, int] = {}
    time_lost: dict[str, int] = {}
    blocks = {"incomplete_drawing": 0, "file_too_big": 0, "email_typo": 0,
              "server_rejected": 0, "upload_too_large": 0}
    server_fields: dict[str, int] = {}
    cancel_reasons: dict[str, int] = {}
    pay_fail_kinds: dict[str, int] = {}
    device = {"mobile": {"viewed": 0, "created": 0, "paid": 0},
              "desktop": {"viewed": 0, "created": 0, "paid": 0}}
    offer = {"result_views": 0, "offer_seen": 0, "sample_opened": 0, "to_order": 0,
             "header_order": 0, "form_from_free": 0}
    sessions: list[dict] = []

    for vid, v in visits.items():
        es = ev.get(vid, [])
        types = {e["type"] for e in es}
        if "free_result_view" in types:
            offer["result_views"] += 1
            offer["offer_seen"] += "click:sec_fr_offer" in types
            offer["sample_opened"] += "click:free_sample_open" in types
            offer["to_order"] += "click:free_to_order" in types
            offer["header_order"] += "click:header_order" in types
        if "order_form_view" not in types:
            continue
        F["viewed"] += 1
        mob = (0 < (v["screen_w"] or 0) < 640) or (not v["screen_w"] and v["device"] == "mobile")
        dev = device["mobile" if mob else "desktop"]
        dev["viewed"] += 1
        states = [_payload(e["payload_json"]) for e in es if e["type"] == "order_form_state"]
        st = states[-1] if states else {}
        fields: set[str] = set()
        for s in states:
            fields |= set(s.get("fields") or [])
        from_free = "order_form_from_free" in types or any(s.get("from_free") for s in states)
        if from_free:
            F["from_free"] += 1
            offer["form_from_free"] += 1
        files = max([s.get("files") or 0 for s in states] or [0])
        sec = max([s.get("sec") or 0 for s in states] or [0])
        started = "form_started" in types or bool(fields)
        submitted = "click:order_submit_form" in types or any(s.get("k") == "submit" for s in states)
        rejected = [e for e in es if e["type"] == "order_form_errors"]
        os_ = orders.get(vid, [])
        created = "order_created" in types or bool(os_)
        pay_started = any(t.startswith("pay_init_") for t in types)
        pay_failed = [t for t in types if t in _PAY_FAIL]
        paid = any(o["paid_at"] for o in os_)
        canc = cancels.get(vid, [])

        F["started"] += started
        F["photo"] += bool(files or from_free)
        F["email"] += "email" in fields
        F["submitted"] += submitted or created
        F["server_rejected"] += bool(rejected)
        F["created"] += created
        F["payment_started"] += pay_started
        F["payment_failed"] += bool(pay_failed)
        F["payment_canceled"] += bool(canc)
        F["paid"] += paid
        dev["created"] += created
        dev["paid"] += paid
        for f in fields:
            _inc(field_reach, f)
        bi = max([s.get("blocked_incomplete") or 0 for s in states] or [0]) \
            + sum(1 for e in es if e["type"] == "click:order_block_incomplete")
        blocks["incomplete_drawing"] += bool(bi)
        blocks["file_too_big"] += any(s.get("file_too_big") for s in states) \
            or "click:order_file_too_big" in types
        blocks["email_typo"] += any(s.get("email_typo") for s in states) \
            or "click:order_blocked_email_typo" in types
        blocks["server_rejected"] += bool(rejected)
        blocks["upload_too_large"] += "upload_too_large" in types
        for e in rejected:
            for f in _payload(e["payload_json"]).get("fields") or []:
                _inc(server_fields, f)
        for r in canc:
            _inc(cancel_reasons, r)
        for t in pay_failed:
            _inc(pay_fail_kinds, t)

        # Где остановились — только для тех, кто НЕ создал заказ.
        if created:
            outcome = "paid" if paid else ("payment_canceled" if canc else
                                          "payment_failed" if pay_failed else
                                          "payment_started" if pay_started else "order_created")
        else:
            if "upload_too_large" in types:
                reason = "upload_too_large"
            elif rejected:
                reason = "server_rejected"
            elif submitted:
                reason = "submitted_no_order"
            elif not started:
                reason = "left_without_touching"
            elif bi or st.get("email_typo") or st.get("file_too_big"):
                reason = "stopped_by_form_check"
            elif not (files or from_free):
                reason = "left_before_photo"
            else:
                reason = "left_while_filling"
            outcome = reason
            _inc(stop, reason)
            if st.get("last"):
                _inc(last_field, st["last"])
            _inc(via, st.get("via") or "—")
            _inc(time_lost, _bucket(sec))
        if len(sessions) < 40:
            c = credited.get(vid) or {}
            sessions.append({
                "day": ads.msk_day(v["started_at"]), "device": "mobile" if mob else "desktop",
                "from_free": bool(from_free), "campaign_id": c.get("campaign_id"),
                "keyword": c.get("keyword"), "seconds": sec, "fields_touched": len(fields),
                "last_field": st.get("last") or "", "photos": files, "left_via": st.get("via") or "",
                "outcome": outcome})

    order_ = lambda d: dict(sorted(d.items(), key=lambda kv: -kv[1]))  # noqa: E731
    reach = [{"field": f, "label": label(f), "visits": field_reach.get(f, 0)}
             for f in FIELD_ORDER if field_reach.get(f) or f.startswith(("child_", "d1_", "email"))]
    lost = F["viewed"] - F["created"]
    return {
        "from": d_from.isoformat(), "to": d_to.isoformat(), "scope": scope,
        "filters": {"source": source, "campaign_id": campaign_id, "cell": cell},
        "funnel": F,
        "stopped_at": order_(stop),
        "last_field_before_leaving": [{"field": k, "label": label(k), "visits": n}
                                      for k, n in order_(last_field).items()],
        "left_via": order_(via),
        "time_on_form_when_lost": {name: time_lost.get(name, 0) for _l, name in _TIME_BUCKETS},
        "field_reach": reach,
        "form_checks": blocks,
        "server_rejected_fields": order_(server_fields),
        "payment_failures": order_(pay_fail_kinds),
        "payment_cancel_reasons": order_(cancel_reasons),
        "devices": device,
        "free_offer": offer,
        "views_without_browser_signal": unreal,
        "findings": _findings(F, stop, via, last_field, offer, cancel_reasons, lost),
        "sessions": sessions,
    }


_STOP_TEXT = {
    "left_without_touching": "ушли, не тронув ни одного поля",
    "left_before_photo": "начали заполнять, но не добавили фото",
    "left_while_filling": "добавили фото и ушли, не отправив",
    "stopped_by_form_check": "уткнулись в нашу проверку (рисунок не заполнен, файл >15 МБ, опечатка в почте)",
    "server_rejected": "отправили, но сервер вернул форму с ошибками",
    "upload_too_large": "отправка оборвалась: файлы больше лимита",
    "submitted_no_order": "нажали «оформить», но заказ не создан (обрыв/таймаут загрузки)",
    # итоги тех, кто заказ создал (для списка сессий)
    "order_created": "создали заказ, оплату не начали",
    "payment_started": "начали оплату, не завершили",
    "payment_failed": "сбой платёжного окна",
    "payment_canceled": "платёж отклонён или отменён",
    "paid": "оплатили",
}


def stop_text(key: str) -> str:
    return _STOP_TEXT.get(key, key)


def _findings(F, stop, via, last_field, offer, cancels, lost) -> list[str]:
    """Человеческие выводы по убыванию веса — то, с чего начинать чинить."""
    out: list[str] = []
    if F["viewed"] == 0:
        return ["За период никто (с живым браузером) не открывал форму заказа."]
    for k, n in sorted(stop.items(), key=lambda kv: -kv[1])[:3]:
        out.append(f"{n} из {F['viewed']} открывших форму {stop_text(k)}.")
    exits = {k: n for k, n in via.items() if k != "—"}
    if exits:
        k, n = max(exits.items(), key=lambda kv: kv[1])
        out.append(f"{n} ушли с формы по ссылке «{k}».")
    if last_field:
        k, n = max(last_field.items(), key=lambda kv: kv[1])
        out.append(f"Чаще всего последним было поле «{label(k)}» ({n}).")
    if F["created"] and F["paid"] < F["created"]:
        out.append(f"Заказ создан {F['created']}, оплачено {F['paid']}"
                   + (f"; причины отказа платежа: {', '.join(cancels)}" if cancels else "") + ".")
    if offer["result_views"]:
        out.append(f"Бесплатный разбор открыли {offer['result_views']}, до оффера доскроллили "
                   f"{offer['offer_seen']}, нажали «к заказу» {offer['to_order']}, "
                   f"открыли пример {offer['sample_opened']}.")
    return out
