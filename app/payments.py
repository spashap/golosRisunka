"""Оплата за абстракцией: stub сейчас, ЮKassa (Phase 8) — тем же интерфейсом.

create_payment(order_id, amount) -> URL чекаута (redirect).
mark_paid(order_id) — ЕДИНАЯ точка «оплата подтверждена» (stub-кнопка сейчас,
webhook ЮKassa потом): customer+child, сессия, статус paid. Идемпотентна.
"""
from __future__ import annotations

import datetime
import json

from flask import url_for

from app.db import get_db, new_token, now
from config import settings


def create_payment(order_id: int, price_kopecks: int) -> str:
    """Stub-провайдер: «чекаут» — своя страница с кнопкой. ЮKassa вернёт
    hosted-URL из своего API тем же контрактом."""
    return url_for("main.stub_checkout", order_id=order_id)


def mark_paid(order_id: int) -> dict | None:
    """Идемпотентно проводит оплату. Возвращает {'customer_id', 'session_token'}
    или None, если заказ не найден. Повторный вызов (дубль webhook) безопасен."""
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        return None
    if order["status"] != "created":            # уже оплачен/обработан — идемпотентность
        session = db.execute(
            "SELECT token FROM sessions WHERE customer_id = ? ORDER BY id DESC LIMIT 1",
            (order["customer_id"],)).fetchone()
        return {"customer_id": order["customer_id"],
                "session_token": session["token"] if session else None,
                "already_paid": True}

    # customer: найти или создать по email
    email = order["email"].strip().lower()
    cust = db.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
    if cust is None:
        cur = db.execute("INSERT INTO customers (email, created_at) VALUES (?, ?)",
                         (email, now()))
        customer_id = cur.lastrowid
    else:
        customer_id = cust["id"]

    # child: переиспользуем по имени у того же покупателя (spec §5)
    child = json.loads(order["child_json"] or "{}")
    child_id = None
    if child.get("name"):
        row = db.execute(
            "SELECT id FROM children WHERE customer_id = ? AND lower(name) = ?",
            (customer_id, child["name"].strip().lower())).fetchone()
        if row:
            child_id = row["id"]
        else:
            cur = db.execute(
                "INSERT INTO children (customer_id, name, gender, birth_ym, birth_info, created_at)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (customer_id, child["name"].strip(), child.get("gender"),
                 child.get("birth_ym"), json.dumps(child, ensure_ascii=False), now()))
            child_id = cur.lastrowid

    # сессия 30 дней — покупатель сразу «в кабинете» (spec §9.1)
    token = new_token()
    expires = (datetime.datetime.now(datetime.timezone.utc)
               + datetime.timedelta(days=settings.SESSION_DAYS)).isoformat(timespec="seconds")
    db.execute("INSERT INTO sessions (customer_id, token, expires_at, created_at)"
               " VALUES (?, ?, ?, ?)", (customer_id, token, expires, now()))

    db.execute("UPDATE orders SET status = 'paid', customer_id = ?, child_id = ?, paid_at = ?"
               " WHERE id = ?", (customer_id, child_id, now(), order_id))
    if order["coupon_code"]:
        db.execute("UPDATE coupons SET uses_count = uses_count + 1 WHERE upper(code) = ?",
                   (order["coupon_code"],))
    db.commit()
    return {"customer_id": customer_id, "session_token": token, "already_paid": False}
