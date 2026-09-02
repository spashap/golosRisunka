"""Оценка результата родителем: звёзды 1–5 + необязательный текст.

Один виджет на два продукта — бесплатный разбор (`/free/r/<token>`) и платный отчёт
(`/r/<token>`): у одной семьи один и тот же вопрос «помогло ли», и сравнивать ответы
можно только если они собраны одинаково. Одна оценка на продукт: повторная отправка
ОБНОВЛЯЕТ строку (родитель передумал — видим последнее мнение), история не нужна.

Доступ — по токену продукта, как и у самих страниц: кто открыл разбор, тот и оценивает.
"""
from __future__ import annotations

from flask import Blueprint, abort, g, jsonify, render_template, request

from app.db import get_db, now
from app.track import track_event
from config import settings

bp_feedback = Blueprint("feedback", __name__, url_prefix="/feedback")

KINDS = ("free", "order")
TEXT_LIMIT = 1500

# Подпись под звёздами — чтобы «3» значило одно и то же у всех.
STAR_LABELS = {
    1: "Не помогло",
    2: "Мало полезного",
    3: "Кое-что подметили",
    4: "Полезно",
    5: "Очень точно, узнали ребёнка",
}


def stars_str(n: int | None) -> str:
    """«★★★★☆» для админки и кабинета; пусто, если оценки нет."""
    if not n:
        return ""
    n = max(1, min(5, int(n)))
    return "★" * n + "☆" * (5 - n)


def get_one(db, kind: str, ref_id: int):
    return db.execute("SELECT * FROM feedback WHERE kind = ? AND ref_id = ?",
                      (kind, ref_id)).fetchone()


def index_for(db, kind: str, ids: list[int]) -> dict[int, dict]:
    """{ref_id: {stars, text, at}} одним запросом для списков админки/кабинета."""
    ids = [int(i) for i in ids if i is not None]
    if not ids:
        return {}
    out: dict[int, dict] = {}
    for i in range(0, len(ids), 400):
        chunk = ids[i:i + 400]
        q = ",".join("?" * len(chunk))
        for r in db.execute(
                f"SELECT ref_id, stars, text, COALESCE(updated_at, created_at) at"
                f" FROM feedback WHERE kind = ? AND ref_id IN ({q})", (kind, *chunk)):
            out[r["ref_id"]] = {"stars": r["stars"], "str": stars_str(r["stars"]),
                                "text": r["text"] or "", "at": (r["at"] or "")[:10]}
    return out


def widget_html(kind: str, token: str, existing=None) -> str:
    """HTML виджета — один партиал на обе страницы."""
    return render_template("_feedback_widget.html", kind=kind, token=token,
                           existing=existing, star_labels=STAR_LABELS,
                           version=settings.APP_VERSION)


def inject_into_report(html: str, widget: str) -> str:
    """Платный отчёт хранится готовым HTML-файлом; виджет дописываем при отдаче,
    перед закрывающим </body>, чтобы не перерисовывать отчёты ради формы."""
    i = html.rfind("</body>")
    if i < 0:
        return html + widget
    return html[:i] + widget + html[i:]


def _upsert(db, kind: str, ref_id: int, stars: int, text: str,
            customer_id: int | None) -> None:
    visitor_id = getattr(g, "visitor_id", None)
    ts = now()
    row = get_one(db, kind, ref_id)
    if row is None:
        db.execute(
            "INSERT INTO feedback (kind, ref_id, stars, text, customer_id, visitor_id,"
            " created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (kind, ref_id, stars, text or None, customer_id, visitor_id, ts))
    else:
        db.execute(
            "UPDATE feedback SET stars = ?, text = ?, updated_at = ?,"
            " customer_id = COALESCE(customer_id, ?), visitor_id = COALESCE(visitor_id, ?)"
            " WHERE id = ?",
            (stars, text or None, ts, customer_id, visitor_id, row["id"]))
    db.commit()


def _parse_form() -> tuple[int, str]:
    try:
        stars = int(request.form.get("stars") or 0)
    except ValueError:
        stars = 0
    if not 1 <= stars <= 5:
        abort(400)
    text = (request.form.get("text") or "").strip()[:TEXT_LIMIT]
    return stars, text


@bp_feedback.post("/free/<token>")
def free_feedback(token: str):
    db = get_db()
    row = db.execute("SELECT id, customer_id FROM free_analyses WHERE token = ?",
                     (token,)).fetchone()
    if row is None:
        abort(404)
    stars, text = _parse_form()
    _upsert(db, "free", row["id"], stars, text, row["customer_id"])
    track_event("feedback_left", {"kind": "free", "stars": stars,
                                  "with_text": bool(text)},
                customer_id=row["customer_id"])
    return jsonify({"ok": True, "stars": stars})


@bp_feedback.post("/order/<token>")
def order_feedback(token: str):
    db = get_db()
    row = db.execute(
        "SELECT o.id, o.customer_id FROM reports r JOIN orders o ON o.id = r.order_id"
        " WHERE r.public_token = ?", (token,)).fetchone()
    if row is None:
        abort(404)
    stars, text = _parse_form()
    _upsert(db, "order", row["id"], stars, text, row["customer_id"])
    track_event("feedback_left", {"kind": "order", "stars": stars,
                                  "with_text": bool(text)},
                customer_id=row["customer_id"])
    return jsonify({"ok": True, "stars": stars})
