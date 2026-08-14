"""Аналитика: анонимный visitor-cookie, ВИЗИТ (30 мин), first/last-touch UTM, канал.

Три уровня опознания, и путать их нельзя:
  * `visitor_id` (cookie gr_v, год) — человек. Отвечает на «сколько разных людей».
  * `visit_id`   (cookie gr_s, 30 мин скользящих) — сеанс. Отвечает на «что человек
    сделал за один заход»; только по нему воронка получается ВЛОЖЕННОЙ, а шаги —
    упорядоченными. Без визита «воронка» = деление одного множества уникальных
    посетителей на другое, где шаг может быть больше предыдущего.
  * `utm` первого касания (cookie gr_utm, год) — откуда человек УЗНАЛ о нас;
    UTM/yclid текущего визита — что привело его ИМЕННО СЕЙЧАС. Для платного трафика
    решает второе: покупку приносит последний клик, а первое касание могло быть
    органикой полгода назад.
"""
from __future__ import annotations

import json
import secrets

from flask import g, request

VISITOR_COOKIE = "gr_v"
VISIT_COOKIE = "gr_s"
UTM_COOKIE = "gr_utm"
UTM_KEYS = ("utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content")
COOKIE_MAX_AGE = 365 * 24 * 3600
VISIT_MAX_AGE = 30 * 60          # окно визита; продлевается на каждом запросе

# Пути, которые НЕ являются просмотром страницы: маяки, поллинг, статика, служебное.
# Считать их «страницами визита» — значит объявить ожидание разбора активным чтением.
NON_PAGE_PREFIXES = ("/static/", "/t/e", "/track/", "/free/status/", "/free/img/",
                     "/pay/yookassa/", "/cabinet/drawing/", "/admin",
                     "/favicon.ico", "/robots.txt", "/sitemap.xml")

# Поисковики и соцсети для классификации канала по referer.
_SEARCH_HOSTS = ("yandex.", "google.", "bing.com", "duckduckgo.com", "mail.ru",
                 "rambler.ru", "go.mail.ru", "search.")
_SOCIAL_HOSTS = ("vk.com", "vk.ru", "t.me", "telegram", "ok.ru", "instagram.",
                 "facebook.", "youtube.", "pinterest.", "dzen.ru", "zen.yandex")
# Рекламные метки. yclid ставит сам Директ, поэтому он и есть точный признак «реклама».
_AD_MEDIUMS = ("cpc", "ppc", "paid", "cpm", "banner", "ads", "direct")


def _clean(v: str | None, limit: int = 120) -> str | None:
    return v.strip()[:limit] if v and v.strip() else None


def classify_channel(utm: dict | None, yclid: str | None,
                     referer: str | None) -> str:
    """Канал визита. Порядок проверок = порядок надёжности признака."""
    if yclid:
        return "ads"
    if utm:
        medium = (utm.get("utm_medium") or "").lower()
        source = (utm.get("utm_source") or "").lower()
        if medium in _AD_MEDIUMS or "direct" in source:
            return "ads"
        if any(s in source for s in ("vk", "telegram", "tg", "instagram", "ok")):
            return "social"
        return "utm"
    if not referer:
        return "direct"
    host = referer.split("//", 1)[-1].split("/", 1)[0].lower()
    from config import settings
    if settings.SITE_DOMAIN and settings.SITE_DOMAIN in host:
        return "internal"
    if any(s in host for s in _SEARCH_HOSTS):
        return "organic"
    if any(s in host for s in _SOCIAL_HOSTS):
        return "social"
    return "referral"


def before_request() -> None:
    """Назначает visitor_id/visit_id, ловит UTM первого касания и метки этого визита."""
    g.visitor_id = request.cookies.get(VISITOR_COOKIE) or secrets.token_urlsafe(12)
    g.new_visitor = VISITOR_COOKIE not in request.cookies

    # Визит: кука короткая, поэтому её отсутствие И ЕСТЬ признак нового сеанса —
    # ни таймстемпов, ни сравнения времени на сервере не нужно.
    g.visit_id = request.cookies.get(VISIT_COOKIE) or secrets.token_urlsafe(9)
    g.new_visit = VISIT_COOKIE not in request.cookies

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
    # Метки ЭТОГО визита (последнее касание) — отдельно от первого касания.
    g.utm_now = utm_in_url or None
    g.yclid = _clean(request.args.get("yclid") or request.args.get("gclid"), 64)


def _is_page_view(response) -> bool:
    """HTML-страница, отданная успешно. Маяки, картинки и поллинг — не страницы."""
    if response.status_code >= 400 or response.status_code in (301, 302, 303, 307, 308):
        return False
    if request.path.startswith(NON_PAGE_PREFIXES):
        return False
    return (response.mimetype or "").startswith("text/html")


def after_request(response):
    if getattr(g, "new_visitor", False):
        response.set_cookie(VISITOR_COOKIE, g.visitor_id, max_age=COOKIE_MAX_AGE,
                            httponly=True, samesite="Lax")
    if getattr(g, "utm_is_new", False) and g.utm:
        response.set_cookie(UTM_COOKIE, json.dumps(g.utm, ensure_ascii=False),
                            max_age=COOKIE_MAX_AGE, httponly=True, samesite="Lax")
    # Куку визита продлеваем на КАЖДОМ запросе: 30 минут неактивности = новый визит.
    # Статику пропускаем целиком: одна страница тянет с десяток файлов, и каждый из них
    # писал бы в базу отметку времени — визит от этого не становится живее.
    if (getattr(g, "visit_id", None) and not request.path.startswith("/admin")
            and not request.path.startswith(("/static/", "/favicon"))):
        response.set_cookie(VISIT_COOKIE, g.visit_id, max_age=VISIT_MAX_AGE,
                            httponly=True, samesite="Lax")
        try:
            _touch_visit(page=_is_page_view(response))
        except Exception:          # аналитика никогда не роняет ответ
            pass
    return response


def _touch_visit(page: bool) -> None:
    """Создаёт/обновляет строку визита. Гео и канал считаем ОДИН раз при создании."""
    from app import geoip
    from app.db import get_db, now
    db = get_db()
    if not getattr(g, "new_visit", False) and not page:
        # Существующий визит и не страница (маяк/поллинг) — только отметка времени.
        db.execute("UPDATE web_visits SET last_at = ? WHERE visit_id = ?",
                   (now(), g.visit_id))
        db.commit()
        return
    path = request.path[:200]
    if getattr(g, "new_visit", False):
        geo = geoip.lookup(client_ip()) or {}
        ref = _clean(request.referrer, 300)
        utm_now = getattr(g, "utm_now", None)
        yclid = getattr(g, "yclid", None)
        db.execute(
            "INSERT INTO web_visits (visit_id, visitor_id, started_at, last_at,"
            " entry_path, exit_path, pages, device, channel, utm_json, yclid, referer,"
            " geo_country, geo_region)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT(visit_id) DO NOTHING",
            (g.visit_id, g.visitor_id, now(), now(), path, path, 1 if page else 0,
             parse_device(request.user_agent.string if request else None),
             classify_channel(utm_now, yclid, ref),
             json.dumps(utm_now, ensure_ascii=False) if utm_now else None,
             yclid, ref, geo.get("country"), geo.get("region")))
        g.new_visit = False        # в пределах запроса второй INSERT не нужен
    else:
        db.execute(
            "UPDATE web_visits SET last_at = ?, exit_path = ?, pages = pages + ?"
            " WHERE visit_id = ?", (now(), path, 1 if page else 0, g.visit_id))
    db.commit()


def mark_visit(**fields) -> None:
    """Обновляет поля текущего визита (engaged / max_scroll / screen_w / customer_id).

    max_scroll идёт через MAX(): маяки приходят в произвольном порядке, и запись
    «25» после «75» не должна откатывать глубину назад.
    """
    if not getattr(g, "visit_id", None) or not fields:
        return
    allowed = {"engaged", "max_scroll", "screen_w", "is_touch", "customer_id"}
    sets, params = [], []
    for k, v in fields.items():
        if k not in allowed or v is None:
            continue
        sets.append(f"{k} = MAX(COALESCE({k}, 0), ?)" if k == "max_scroll" else f"{k} = ?")
        params.append(v)
    if not sets:
        return
    try:
        from app.db import get_db
        db = get_db()
        db.execute(f"UPDATE web_visits SET {', '.join(sets)} WHERE visit_id = ?",
                   (*params, g.visit_id))
        db.commit()
    except Exception:              # аналитика никогда не роняет запрос
        pass


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
                customer_id: int | None = None, path: str | None = None) -> None:
    """path переопределяют маяки: клик прилетает на /t/e, а произошёл на странице,
    которую браузер сообщает сам — иначе все цели сайта выглядят как события /t/e."""
    from app import geoip
    from app.db import track
    ua = request.user_agent.string if request else None
    geo = geoip.lookup(client_ip()) or {}
    track(event_type,
          visitor_id=getattr(g, "visitor_id", None),
          visit_id=getattr(g, "visit_id", None),
          customer_id=customer_id,
          payload=payload,
          path=(path or (request.path[:200] if request else None)),
          utm=getattr(g, "utm", None),
          user_agent=(ua or None),
          device=parse_device(ua),
          referer=(request.referrer if request else None),
          geo_country=geo.get("country"),
          geo_region=geo.get("region"))
    if customer_id:
        mark_visit(customer_id=customer_id)
