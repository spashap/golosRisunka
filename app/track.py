"""Аналитика для будущей админки: анонимный visitor-cookie + first-touch UTM.

Только серверные события (без JS-аналитики — закон спеки + приватность).
Воронка: landing_view → sample_view → order_form_view → order_created
        → checkout_view → order_paid → report_delivered.
"""
from __future__ import annotations

import json
import secrets

from flask import g, request

VISITOR_COOKIE = "gr_v"
UTM_COOKIE = "gr_utm"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")
COOKIE_MAX_AGE = 365 * 24 * 3600


def before_request() -> None:
    """Назначает visitor_id и ловит UTM первого касания (сохранится в after_request)."""
    g.visitor_id = request.cookies.get(VISITOR_COOKIE) or secrets.token_urlsafe(12)
    g.new_visitor = VISITOR_COOKIE not in request.cookies

    utm_in_url = {k: request.args.get(k) for k in UTM_KEYS if request.args.get(k)}
    stored = request.cookies.get(UTM_COOKIE)
    if stored:
        try:
            g.utm = json.loads(stored)
        except ValueError:
            g.utm = None
    else:
        g.utm = utm_in_url or None
    g.utm_is_new = bool(utm_in_url) and not stored


def after_request(response):
    if getattr(g, "new_visitor", False):
        response.set_cookie(VISITOR_COOKIE, g.visitor_id, max_age=COOKIE_MAX_AGE,
                            httponly=True, samesite="Lax")
    if getattr(g, "utm_is_new", False) and g.utm:
        response.set_cookie(UTM_COOKIE, json.dumps(g.utm, ensure_ascii=False),
                            max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax")
    return response


def track_event(event_type: str, payload: dict | None = None,
                customer_id: int | None = None) -> None:
    from app.db import track
    track(event_type,
          visitor_id=getattr(g, "visitor_id", None),
          customer_id=customer_id,
          payload=payload,
          utm=getattr(g, "utm", None))
