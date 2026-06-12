"""Вход по email-коду (spec §9): 6-значный код, TTL 30 мин, одноразовый;
сессия 30 дней (httpOnly cookie gr_s).

Доставка кода — через app.mailer (сейчас outbox + строка в лог с самим кодом;
Unisender в Phase 8 подключится в mailer, здесь ничего не изменится).
Rate limit: новый код не выдаётся, пока «живой» (неиспользованный,
неистёкший) запрошен меньше LOGIN_CODE_RESEND_MINUTES назад;
LOGIN_CODE_MAX_ATTEMPTS неверных вводов аннулируют код.
"""
from __future__ import annotations

import datetime
import logging
import secrets
import sqlite3

from flask import g, request

from app.db import get_db, new_token, now
from app.mailer import render_email, send_email
from config import settings

log = logging.getLogger("auth")

SESSION_COOKIE = "gr_s"


class AuthError(Exception):
    """Сообщение пригодно для показа пользователю."""


def _utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(dt: datetime.datetime) -> str:
    return dt.isoformat(timespec="seconds")


def request_code(email: str) -> None:
    """Создаёт и «отправляет» код входа. AuthError при rate limit."""
    db = get_db()
    live = db.execute(
        "SELECT requested_at FROM login_codes WHERE email = ? AND used = 0"
        " AND attempts < ? AND expires_at > ? ORDER BY id DESC LIMIT 1",
        (email, settings.LOGIN_CODE_MAX_ATTEMPTS, _iso(_utcnow()))).fetchone()
    if live:
        resend_after = (datetime.datetime.fromisoformat(live["requested_at"])
                        + datetime.timedelta(minutes=settings.LOGIN_CODE_RESEND_MINUTES))
        if _utcnow() < resend_after:
            raise AuthError("Код уже отправлен — проверьте почту (и папку «Спам»). "
                            f"Новый можно запросить через {settings.LOGIN_CODE_RESEND_MINUTES} минут.")

    code = f"{secrets.randbelow(1_000_000):06d}"
    expires = _iso(_utcnow() + datetime.timedelta(minutes=settings.LOGIN_CODE_TTL_MINUTES))
    db.execute("INSERT INTO login_codes (email, code, expires_at, requested_at)"
               " VALUES (?, ?, ?, ?)", (email, code, expires, now()))
    db.commit()

    html = render_email("login_code.html", code=code,
                        ttl_minutes=settings.LOGIN_CODE_TTL_MINUTES)
    send_email(email, f"Код входа — {settings.SITE_NAME}", html, kind="login_code")
    # до Unisender код читается из консоли/лога (план M7); ASCII-строка
    log.info("LOGIN CODE for %s: %s", email, code)


def verify_code(email: str, code: str) -> str:
    """Проверяет код. Возвращает session token. AuthError с причиной иначе."""
    db = get_db()
    row = db.execute(
        "SELECT * FROM login_codes WHERE email = ? AND used = 0"
        " ORDER BY id DESC LIMIT 1", (email,)).fetchone()
    if row is None:
        raise AuthError("Код не найден — запросите новый.")
    if row["attempts"] >= settings.LOGIN_CODE_MAX_ATTEMPTS:
        raise AuthError("Слишком много попыток — запросите новый код.")
    if _iso(_utcnow()) > row["expires_at"]:
        raise AuthError("Код истёк — запросите новый.")
    if code.strip() != row["code"]:
        db.execute("UPDATE login_codes SET attempts = attempts + 1 WHERE id = ?",
                   (row["id"],))
        db.commit()
        left = settings.LOGIN_CODE_MAX_ATTEMPTS - row["attempts"] - 1
        if left <= 0:
            raise AuthError("Слишком много попыток — запросите новый код.")
        raise AuthError(f"Неверный код. Осталось попыток: {left}.")

    db.execute("UPDATE login_codes SET used = 1 WHERE id = ?", (row["id"],))
    # customer find-or-create: вход без заказов даёт пустой кабинет
    # (и не раскрывает, покупал ли кто-то с этим email)
    cust = db.execute("SELECT id FROM customers WHERE email = ?", (email,)).fetchone()
    if cust is None:
        cur = db.execute("INSERT INTO customers (email, created_at) VALUES (?, ?)",
                         (email, now()))
        customer_id = cur.lastrowid
    else:
        customer_id = cust["id"]
    token = create_session(db, customer_id)
    db.commit()
    return token


def create_session(db: sqlite3.Connection, customer_id: int) -> str:
    """Сессия 30 дней. Используется здесь и в payments.mark_paid (auto-login
    при покупке). Без commit — вызывающий коммитит свою транзакцию."""
    token = new_token()
    expires = _iso(_utcnow() + datetime.timedelta(days=settings.SESSION_DAYS))
    db.execute("INSERT INTO sessions (customer_id, token, expires_at, created_at)"
               " VALUES (?, ?, ?, ?)", (customer_id, token, expires, now()))
    return token


def current_customer():
    """Покупатель текущего запроса (по cookie) или None. Кэш в g."""
    if "auth_customer" not in g:
        g.auth_customer = None
        token = request.cookies.get(SESSION_COOKIE)
        if token:
            g.auth_customer = get_db().execute(
                "SELECT c.* FROM sessions s JOIN customers c ON c.id = s.customer_id"
                " WHERE s.token = ? AND s.expires_at > ?",
                (token, _iso(_utcnow()))).fetchone()
    return g.auth_customer


def destroy_session() -> None:
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        db = get_db()
        db.execute("DELETE FROM sessions WHERE token = ?", (token,))
        db.commit()
