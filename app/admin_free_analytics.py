"""Аналитика фремиума `/free`: глубина прохождения, выбор в анкете, покупки после.

Отдельный модуль, а не ещё сто строк в admin.py: здесь только СЧЁТ (SQL + агрегация),
маршрут в admin.py остаётся тонким.

Две единицы измерения, и их НЕЛЬЗЯ смешивать в одной колонке:
  * посетители — шаги мастера, которые не оставляют строки в БД (клики по кнопкам
    приходят маяком /t/e и лежат в events как 'click:<goal>');
  * анкеты — строки free_analyses (одна строка = один пройденный опрос; один человек
    может пройти его дважды).
Поэтому воронка разбита на две таблицы, а не склеена в одну «красивую».

Период = дата АНКЕТЫ (когорта). Покупки когорты считаются БЕЗ ограничения по дате:
вопрос «купил ли он вообще», а не «купил ли он в тот же день».
"""
from __future__ import annotations

import json

from config import free_texts as T

# Клики UI приходят в events с префиксом (см. routes.track_beacon).
CLICK = "click:"

# Боты не считаются нигде (как и в остальной админ-аналитике).
NOT_BOT = "(device IS NULL OR device <> 'bot')"

# Статусы, означающие «рисунок загружен» (анкета дошла до разбора).
UPLOADED = ("queued", "running", "done", "rejected", "failed")


# --- Дешёвые счётчики -------------------------------------------------------------

def _visitors(db, type_sql: str, params: tuple, since: str) -> int:
    """Уникальные ЛЮДИ с таким событием за период."""
    return db.execute(
        "SELECT COUNT(DISTINCT visitor_id) c FROM events"
        f" WHERE visitor_id IS NOT NULL AND {NOT_BOT} AND {type_sql}"
        " AND created_at >= ?", (*params, since)).fetchone()["c"]


def dashboard_counters(db, since: str) -> dict:
    """Блок фремиума на главной вкладке админки.

    Разделение, о котором просил заказчик: анкету прошли N, из них часть оставила
    ТОЛЬКО почту («нет рисунка под рукой»), а часть реально принесла рисунок.
    """
    row = db.execute(
        "SELECT COUNT(*) total,"
        " SUM(CASE WHEN status = 'answers' AND email IS NOT NULL THEN 1 ELSE 0 END) email_only,"
        " SUM(CASE WHEN status <> 'answers' THEN 1 ELSE 0 END) requested,"
        " SUM(CASE WHEN status = 'done' THEN 1 ELSE 0 END) done,"
        " SUM(CASE WHEN status = 'answers' AND email IS NULL THEN 1 ELSE 0 END) dropped"
        " FROM free_analyses WHERE created_at >= ?", (since,)).fetchone()
    total = row["total"] or 0
    return {
        "total": total,
        "email_only": row["email_only"] or 0,
        "requested": row["requested"] or 0,
        "done": row["done"] or 0,
        "dropped": row["dropped"] or 0,
        "openers": _visitors(db, "type = ?", ("free_view",), since),
    }


# --- Атрибуция «фремиум -> покупка» ------------------------------------------------

# Точность источника по убыванию: прямой переход из разбора (orders.free_token,
# пишется в routes.order_submit) точен; email и visitor_id — склейка по совпадению,
# она может ошибаться (общий компьютер, чужая почта), поэтому показывается отдельно.
ATTR_LABELS = {"direct": "перешёл из разбора",
               "email": "тот же email",
               "visitor": "тот же посетитель"}


def _attribute_orders(db, rows) -> tuple[dict, list]:
    """Кто из когорты дошёл до платного заказа.

    Возвращает ({analysis_id: [заказы]}, [плоский список пар для таблицы]).
    Заказ достаётся ОДНОЙ анкете — последней, созданной не позже заказа: иначе
    один человек с двумя разборами дал бы две «покупки» из одной.
    """
    by_token = {r["token"]: r for r in rows}
    by_email: dict[str, list] = {}
    by_visitor: dict[str, list] = {}
    for r in rows:
        if r["email"]:
            by_email.setdefault(r["email"].strip().lower(), []).append(r)
        if r["visitor_id"]:
            by_visitor.setdefault(r["visitor_id"], []).append(r)
    if not rows:
        return {}, []

    orders = db.execute(
        "SELECT id, email, visitor_id, free_token, product_code, price_kopecks,"
        " status, created_at, paid_at FROM orders ORDER BY id").fetchall()

    def _latest_before(candidates, when):
        pick = None
        for c in candidates:
            if c["created_at"] <= when and (pick is None
                                            or c["created_at"] > pick["created_at"]):
                pick = c
        return pick

    per_analysis: dict[int, list] = {}
    pairs: list[dict] = []
    for o in orders:
        analysis, kind = None, ""
        if o["free_token"] and o["free_token"] in by_token:
            analysis, kind = by_token[o["free_token"]], "direct"
        elif o["email"] and o["email"].strip().lower() in by_email:
            analysis = _latest_before(by_email[o["email"].strip().lower()],
                                      o["created_at"])
            kind = "email"
        elif o["visitor_id"] and o["visitor_id"] in by_visitor:
            analysis = _latest_before(by_visitor[o["visitor_id"]], o["created_at"])
            kind = "visitor"
        if analysis is None:
            continue
        per_analysis.setdefault(analysis["id"], []).append(o)
        pairs.append({
            "analysis_id": analysis["id"],
            "child": analysis["child_name"],
            "concern": _label(T.CONCERNS, analysis["concern_key"]),
            "free_at": (analysis["created_at"] or "")[:16].replace("T", " "),
            "kind": kind, "kind_label": ATTR_LABELS[kind],
            "order_id": o["id"], "product": o["product_code"],
            "order_at": (o["created_at"] or "")[:16].replace("T", " "),
            "status": o["status"],
            "paid": bool(o["paid_at"]),
            "rub": o["price_kopecks"] // 100,
            "lag_days": _lag_days(analysis["created_at"], o["created_at"]),
        })
    pairs.sort(key=lambda p: p["order_id"], reverse=True)
    return per_analysis, pairs


def _lag_days(a: str | None, b: str | None) -> str:
    """Сколько прошло между анкетой и заказом. Считаем по датам — часовой пояс
    у обеих меток один (UTC ISO), а точность до часа здесь не нужна."""
    if not a or not b:
        return ""
    import datetime
    try:
        d = (datetime.date.fromisoformat(b[:10]) - datetime.date.fromisoformat(a[:10])).days
    except ValueError:
        return ""
    return "в тот же день" if d <= 0 else f"+{d} дн."


def _label(options: list[dict], key: str | None) -> str:
    for o in options:
        if o["key"] == key:
            return T.g(o["label"], "он")
    return key or "—"


# --- Разбивка по вариантам анкеты ---------------------------------------------------

def _breakdown(rows, key_fn, order: list[tuple[str, str]], buyers: dict,
               paid_ids: set) -> list[dict]:
    """Одна таблица «вариант -> сколько выбрали и куда дошли».

    order задаёт ПОРЯДОК и подписи (как на экране мастера), а не только перевод:
    варианты, которые никто не выбрал, обязаны остаться видимыми — ноль здесь тоже ответ.
    """
    buckets = {k: {"key": k, "label": lbl, "n": 0, "uploaded": 0, "done": 0,
                   "orders": 0, "paid": 0} for k, lbl in order}
    for r in rows:
        k = key_fn(r)
        if k is None:
            continue
        b = buckets.get(k)
        if b is None:
            b = buckets[k] = {"key": k, "label": k, "n": 0, "uploaded": 0,
                              "done": 0, "orders": 0, "paid": 0}
        b["n"] += 1
        if r["status"] in UPLOADED:
            b["uploaded"] += 1
        if r["status"] == "done":
            b["done"] += 1
        got = buyers.get(r["id"]) or []
        if got:
            b["orders"] += 1
            if any(o["id"] in paid_ids for o in got):
                b["paid"] += 1
    total = sum(b["n"] for b in buckets.values()) or 1
    out = []
    for b in buckets.values():
        out.append({**b,
                    "share": f"{b['n'] / total * 100:.0f}%",
                    "to_upload": f"{b['uploaded'] / b['n'] * 100:.0f}%" if b["n"] else "—"})
    return out


def _steps(items: list[tuple[str, int, str]]) -> list[dict]:
    """Шаги воронки с процентами «от предыдущего» и «от первого»."""
    out, prev, top = [], None, None
    for label, n, note in items:
        if top is None:
            top = n
        out.append({
            "label": label, "n": n, "note": note,
            "pct_prev": f"{n / prev * 100:.0f}%" if prev else "",
            "pct_top": f"{n / top * 100:.0f}%" if top else "",
        })
        prev = n or None
    return out


def page_data(db, since: str) -> dict:
    """Всё, что показывает страница «Фремиум»."""
    rows = db.execute(
        "SELECT id, token, visitor_id, email, child_name, child_age, concern_key,"
        " duration_key, address_form, ask_variant, parent_text, status, reject_reason,"
        " flags_json, created_at FROM free_analyses WHERE created_at >= ?"
        " ORDER BY id", (since,)).fetchall()

    voted_ids = {r["analysis_id"] for r in db.execute(
        "SELECT DISTINCT analysis_id FROM free_interpretations"
        " WHERE parent_vote IS NOT NULL")}
    buyers, pairs = _attribute_orders(db, rows)
    paid_ids = {p["order_id"] for p in pairs if p["paid"]}

    n_total = len(rows)
    n_uploaded = sum(1 for r in rows if r["status"] in UPLOADED)
    n_done = sum(1 for r in rows if r["status"] == "done")
    n_voted = sum(1 for r in rows if r["id"] in voted_ids)
    n_ordered = sum(1 for r in rows if buyers.get(r["id"]))
    n_paid = sum(1 for r in rows
                 if any(o["id"] in paid_ids for o in (buyers.get(r["id"]) or [])))

    # Воронка по посетителям: шаги мастера строк в БД не оставляют.
    page_steps = _steps([
        ("Открыли /free", _visitors(db, "type = ?", ("free_view",), since), "free_view"),
        ("Ввели имя и возраст", _visitors(db, "type = ?", (CLICK + "free_step1",), since),
         "кнопка «Дальше»"),
        ("Выбрали, что зацепило",
         _visitors(db, "type LIKE ?", (CLICK + "free_concern_%",), since), "шаг 2"),
        ("Запросили вывод", _visitors(db, "type = ?", (CLICK + "free_summary",), since),
         "кнопка «Показать»"),
        ("Открыли загрузку рисунка",
         _visitors(db, "type = ?", (CLICK + "free_add_drawing",), since), "шаг 4"),
        ("Отправили рисунок",
         _visitors(db, "type = ?", (CLICK + "free_upload_submit",), since), "кнопка загрузки"),
        ("Открыли готовый разбор", _visitors(db, "type = ?", ("free_result_view",), since),
         "free_result_view"),
        ("Нажали «заказать отчёт»",
         _visitors(db, "type = ?", (CLICK + "free_to_order",), since), "продающий блок"),
    ])

    # Воронка по анкетам: одна строка = один пройденный опрос. Оценка трактовки в
    # цепочку не входит намеренно: она необязательна (купить можно и не оценив) и
    # давала бы бессмысленные «300% от предыдущего шага».
    form_steps = _steps([
        ("Прошли анкету", n_total, "строка free_analyses"),
        ("Загрузили рисунок", n_uploaded, "статус ≠ answers"),
        ("Получили разбор", n_done, "статус done"),
        ("Создали платный заказ", n_ordered, "атрибуция ниже"),
        ("Оплатили", n_paid, ""),
    ])

    # Где остановились те, кто не принёс рисунок.
    stalled = [r for r in rows if r["status"] == "answers"]
    stalled_view = {
        "total": len(stalled),
        "email": sum(1 for r in stalled if r["email"]),
        "silent": sum(1 for r in stalled if not r["email"]),
    }

    # Сбои и отказы: они тоже «глубина» — человек дошёл до конца и не получил разбора.
    rejects: dict[str, int] = {}
    for r in rows:
        if r["status"] in ("rejected", "failed"):
            k = r["reject_reason"] or r["status"]
            rejects[k] = rejects.get(k, 0) + 1
    flags: dict[str, int] = {}
    for r in rows:
        for f in json.loads(r["flags_json"] or "[]"):
            flags[f] = flags.get(f, 0) + 1

    # Подписи длительности склоняются под «он»: в общей таблице ветка «перестал рисовать»
    # (DURATION_LABEL_OVERRIDES) не выделяется — вариант тот же, меняется только фраза.
    dur_order = [(d["key"], T.g(d["label"], "он")) for d in T.DURATIONS]
    surveys = [
        {"title": "Что зацепило (шаг 2)", "unit": "тревога",
         "rows": _breakdown(rows, lambda r: r["concern_key"],
                            [(c["key"], c["label"]) for c in T.CONCERNS],
                            buyers, paid_ids)},
        {"title": "Как давно замечают (шаг 3)", "unit": "срок",
         "hint": "Не спрашивается у варианта «ничего не тревожит» — там прочерк.",
         "rows": _breakdown(rows, lambda r: r["duration_key"], dur_order,
                            buyers, paid_ids)},
        {"title": "Возраст ребёнка", "unit": "полоса",
         "rows": _breakdown(rows,
                            lambda r: T.age_band(r["child_age"] or 6),
                            list(T.BAND_LABELS.items()), buyers, paid_ids)},
        {"title": "Обращение в тексте", "unit": "форма",
         "rows": _breakdown(rows, lambda r: r["address_form"],
                            [("он", "он"), ("она", "она")], buyers, paid_ids)},
        {"title": "Свободный текст «что вы уже заметили»", "unit": "ответ",
         "rows": _breakdown(rows,
                            lambda r: "filled" if (r["parent_text"] or "").strip() else "skipped",
                            [("filled", "написали своими словами"),
                             ("skipped", "пропустили")], buyers, paid_ids)},
        {"title": "Какой вариант просьбы о рисунке показан", "unit": "вариант",
         "hint": "Вычисляется из ответов, а не выбирается родителем — видно, какая ветка"
                 " текста работает.",
         "rows": _breakdown(rows, lambda r: r["ask_variant"],
                            [(v, v) for v in T.ASK_VARIANTS], buyers, paid_ids)},
    ]

    revenue = sum(p["rub"] for p in pairs if p["paid"])
    by_kind: dict[str, dict] = {}
    for p in pairs:
        b = by_kind.setdefault(p["kind"], {"label": p["kind_label"], "orders": 0,
                                           "paid": 0, "rub": 0})
        b["orders"] += 1
        if p["paid"]:
            b["paid"] += 1
            b["rub"] += p["rub"]

    # Вовлечённость в готовый разбор — отдельно от воронки (см. коммент к form_steps).
    engagement = {
        "voted": n_voted,
        "voted_pct": f"{n_voted / n_done * 100:.0f}%" if n_done else "—",
        "to_order_clicks": _visitors(db, "type = ?", (CLICK + "free_to_order",), since),
        "retry_clicks": _visitors(db, "type = ?", (CLICK + "free_retry",), since),
        "limit_hits": _visitors(db, "type = ?", (CLICK + "free_limit_open",), since),
    }

    return {
        "total": n_total, "uploaded": n_uploaded, "done": n_done,
        "ordered": n_ordered, "paid": n_paid, "revenue": revenue,
        "engagement": engagement,
        "email_only": stalled_view["email"],
        "conv_done_paid": (f"{n_paid / n_done * 100:.1f}%" if n_done else "—"),
        "conv_total_paid": (f"{n_paid / n_total * 100:.1f}%" if n_total else "—"),
        "page_steps": page_steps, "form_steps": form_steps,
        "stalled": stalled_view, "rejects": sorted(rejects.items(), key=lambda kv: -kv[1]),
        "flags": sorted(flags.items(), key=lambda kv: -kv[1]),
        "surveys": surveys, "pairs": pairs,
        "by_kind": [by_kind[k] for k in ("direct", "email", "visitor") if k in by_kind],
    }
