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


# Маркеры ботов в User-Agent (всё в lower-case). Сетевые защиты:
#  1) "+http"/"+https" — самоидентифицирующийся краулер/монитор (PingAdmin, leakix, Claude-User…);
#  2) нет "mozilla" — это утилита/сканер (curl, wget, *-Audit-Scanner, greedyhand…), не браузер;
#  3) явный список имён — на случай ботов с браузерным UA без само-URL.
# Яндекс.Браузер (YaBrowser) НЕ ловится этими правилами — он шлёт нормальный Mozilla-UA без +http.
BOT_UA_MARKERS = (
    "bot", "crawler", "spider", "headless", "slurp", "monitor",
    "scan", "audit", "sniff", "uptime", "pingdom", "pingadmin", "leakix",
    "masscan", "zgrab", "nmap", "nuclei", "wpscan", "sqlmap", "nikto",
    "scrapy", "phantomjs", "selenium", "puppeteer", "playwright",
    "curl", "wget", "python-requests", "urllib", "aiohttp", "httpx",
    "go-http", "okhttp", "java/", "libwww", "httpclient", "node-fetch",
    "gptbot", "chatgpt", "claude", "anthropic", "perplexity", "bytespider",
    "ccbot", "google-extended", "amazonbot", "applebot", "ai2bot",
    "ahrefs", "semrush", "mj12", "dotbot", "dataforseo", "petalbot", "blexbot",
    "facebookexternalhit", "telegrambot", "whatsapp", "twitterbot",
    "linkedinbot", "discordbot", "slackbot", "vkshare", "embedly",
)


def parse_device(ua: str | None) -> str:
    """Определение устройства по User-Agent; ботов/сканеры/утилиты помечаем 'bot'.
    Боты складываются в device='bot' и отсекаются в админ-аналитике (только люди).
    Яндекс.Браузер популярен в RU — он шлёт обычный Mozilla-UA и НЕ помечается ботом."""
    s = (ua or "").lower().strip()
    if not s:
        return "unknown"
    if "+http" in s:                       # самоидентифицирующийся краулер/монитор
        return "bot"
    if "mozilla" not in s:                 # curl/wget/сканеры — не браузеры
        return "bot"
    if any(b in s for b in BOT_UA_MARKERS):
        return "bot"
    if "ipad" in s or "tablet" in s or ("android" in s and "mobile" not in s):
        return "tablet"
    if any(m in s for m in ("mobi", "iphone", "ipod", "android", "phone")):
        return "mobile"
    return "desktop"


def client_ip() -> str | None:
    """Реальный IP клиента за nginx (он шлёт X-Real-IP и X-Forwarded-For).
    DNS-only/grey-cloud -> это настоящий IP посетителя, не Cloudflare. Сам IP
    нигде не сохраняется — только используется для гео-резолва в track_event()."""
    if not request:
        return None
    real = request.headers.get("X-Real-IP")
    if real:
        return real.strip()
    fwd = request.headers.get("X-Forwarded-For")
    if fwd:
        return fwd.split(",")[0].strip()      # первый хоп = клиент
    return request.remote_addr


def track_event(event_type: str, payload: dict | None = None,
                customer_id: int | None = None) -> None:
    from app import geoip
    from app.db import track
    ua = request.user_agent.string if request else None
    geo = geoip.lookup(client_ip()) or {}
    track(event_type,
          visitor_id=getattr(g, "visitor_id", None),
          customer_id=customer_id,
          payload=payload,
          utm=getattr(g, "utm", None),
          user_agent=(ua or None),
          device=parse_device(ua),
          referer=(request.referrer if request else None),
          geo_country=geo.get("country"),
          geo_region=geo.get("region"))
