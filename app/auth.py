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


def ensure_login_token(db: sqlite3.Connection, customer_id: int) -> str:
    """Возвращает durable magic-login токен покупателя (создаёт при отсутствии).
    Токен живёт вечно — он попадает в письма, ссылка не должна «протухать».
    Свой commit (вызывается уже ПОСЛЕ основной транзакции письма/оплаты)."""
    row = db.execute("SELECT login_token FROM customers WHERE id = ?",
                     (customer_id,)).fetchone()
    if row and row["login_token"]:
        return row["login_token"]
    token = new_token(24)
    db.execute("UPDATE customers SET login_token = ? WHERE id = ?", (token, customer_id))
    db.commit()
    return token


def login_link_for(db: sqlite3.Connection, email: str | None = None,
                   customer_id: int | None = None) -> str | None:
    """Персональная ссылка «войти в кабинет» для письма. None, если покупателя
    с таким email ещё нет (новый адрес на /login — кабинета у него всё равно нет).
    db — явное соединение (воркер передаёт своё, веб — get_db())."""
    if customer_id is None:
        if not email:
            return None
        row = db.execute("SELECT id FROM customers WHERE email = ?",
                         (email.strip().lower(),)).fetchone()
        if row is None:
            return None
        customer_id = row["id"]
    token = ensure_login_token(db, customer_id)
    return f"{settings.PUBLIC_BASE_URL}/enter/{token}"


def login_with_token(token: str) -> str | None:
    """Magic-link вход: по durable-токену покупателя выдаёт session token.
    None, если токен неизвестен (старая/битая ссылка)."""
    db = get_db()
    row = db.execute("SELECT id FROM customers WHERE login_token = ?",
                     (token,)).fetchone()
    if row is None:
        log.info("magic-link login: unknown token")
        return None
    session = create_session(db, row["id"])
    db.commit()
    log.info("magic-link login OK (customer %s)", row["id"])
    return session


def _norm_name(s: str | None) -> str:
    """Нормализация имени для сравнения: без краёв, схлопнутые пробелы, lower
    (Python lower корректен для кириллицы — в отличие от SQLite lower())."""
    return " ".join((s or "").split()).lower()


def _record_recovery(db: sqlite3.Connection, email: str, success: int) -> None:
    db.execute("INSERT INTO recovery_attempts (email, success, created_at)"
               " VALUES (?, ?, ?)", (email, success, now()))
    db.commit()


def recover_login(email: str, child_name: str, child_birth: str) -> str:
    """Резервный вход «по данным ребёнка»: email + имя ребёнка + месяц рождения
    ('YYYY-MM'). Возвращает session token при совпадении. AuthError иначе.
    Лимит неудач на email (settings.RECOVERY_MAX_FAILS) гасит подбор."""
    db = get_db()
    email = email.strip().lower()
    since = _iso(_utcnow() - datetime.timedelta(minutes=settings.RECOVERY_WINDOW_MINUTES))
    fails = db.execute(
        "SELECT COUNT(*) AS n FROM recovery_attempts"
        " WHERE email = ? AND success = 0 AND created_at > ?",
        (email, since)).fetchone()["n"]
    if fails >= settings.RECOVERY_MAX_FAILS:
        log.warning("recovery login rate-limited for %s (%d fails in window)", email, fails)
        raise AuthError("Слишком много попыток. Попробуйте позже "
                        "или войдите по коду из письма.")

    want_name = _norm_name(child_name)
    want_birth = (child_birth or "").strip()
    if not want_name or not want_birth:
        _record_recovery(db, email, 0)
        raise AuthError("Укажите имя ребёнка и месяц его рождения.")

    # Сравнение в Python: SQLite lower() не сворачивает кириллицу.
    rows = db.execute(
        "SELECT ch.name AS name, ch.birth_ym AS birth_ym, ch.customer_id AS cid"
        " FROM children ch JOIN customers cu ON cu.id = ch.customer_id"
        " WHERE cu.email = ?", (email,)).fetchall()
    match = next((r for r in rows
                  if _norm_name(r["name"]) == want_name
                  and (r["birth_ym"] or "") == want_birth), None)
    if match is None:
        # Сообщение одинаково для «email не покупал» и «данные не сходятся» —
        # не раскрываем, есть ли заказы у этого адреса.
        _record_recovery(db, email, 0)
        log.info("recovery login mismatch for %s", email)
        raise AuthError("Не нашли совпадения по данным ребёнка. "
                        "Проверьте имя и месяц рождения — или войдите по коду из письма.")

    _record_recovery(db, email, 1)
    token = create_session(db, match["cid"])
    db.commit()
    log.info("recovery login OK for %s (customer %s)", email, match["cid"])
    return token


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
                        ttl_minutes=settings.LOGIN_CODE_TTL_MINUTES,
                        cabinet_link=login_link_for(db, email=email))
    send_email(email, f"Код входа — {settings.SITE_NAME}", html, kind="login_code")
    if settings.MAIL_BACKEND == "unisender":
        # боевой режим: код реально уходит письмом — НЕ пишем его значение в лог/файл
        log.info("login code issued for %s (delivered by email)", email)
    else:
        # dev/outbox: письма «никуда» не уходят — печатаем код для удобства (ASCII-строка)
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
