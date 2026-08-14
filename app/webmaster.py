"""Клиент API Яндекс.Вебмастера (v4) на stdlib `urllib` — как app/metrika.py.

Зачем он вообще нужен, если есть Метрика: Метрика знает только тех, кто ДОШЁЛ.
Вебмастер знает спрос — по каким запросам нас показывают, сколько раз, на каком месте
и сколько кликают. Это единственный источник, который отвечает «нас ищут, но не
кликают» и «мы отвечаем не на тот вопрос»; из своей базы такое не выводится никак.

Авторизация — тот же OAuth-токен (`YANDEX_OAUTH_TOKEN`), права webmaster:hostinfo.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from config import settings

log = logging.getLogger("webmaster")

API_URL = "https://api.webmaster.yandex.net/v4"

_TIMEOUT = 30
_MAX_ATTEMPTS = 3
_RETRY_SLEEP = 3


class WebmasterError(Exception):
    pass


def enabled() -> bool:
    return bool(settings.YANDEX_OAUTH_TOKEN)


def _call(path: str, params: dict | None = None) -> dict:
    """GET с ретраями транзитных сбоев. 4xx (кроме 429) не самоисцелится."""
    if not enabled():
        raise WebmasterError("YANDEX_OAUTH_TOKEN не задан (.env)")
    url = f"{API_URL}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    req = urllib.request.Request(url, headers={
        "Authorization": f"OAuth {settings.YANDEX_OAUTH_TOKEN}"})
    last = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8", "replace") or "{}")
        except urllib.error.HTTPError as he:
            raw = he.read().decode("utf-8", "replace")
            last = f"HTTP {he.code}: {raw[:200]}"
            if he.code not in (429, 500, 502, 503, 504):
                raise WebmasterError(last)
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"сеть: {e}"
        if attempt < _MAX_ATTEMPTS:
            time.sleep(_RETRY_SLEEP)
    raise WebmasterError(last or "неизвестная ошибка")


def user_id() -> int:
    """ID пользователя — он нужен во ВСЕХ остальных путях API."""
    return _call("/user/")["user_id"]


def hosts(uid: int | None = None) -> list[dict]:
    uid = uid if uid is not None else user_id()
    return _call(f"/user/{uid}/hosts/").get("hosts", [])


def host_id_for(domain: str, uid: int | None = None) -> str | None:
    """host_id по домену: в API он выглядит как 'https:golosrisunka.ru:443'."""
    for h in hosts(uid):
        if domain in (h.get("unicode_host_url") or h.get("ascii_host_url") or ""):
            return h.get("host_id")
    return None


def popular_queries(host: str, uid: int | None = None,
                    order_by: str = "TOTAL_SHOWS", limit: int = 100) -> dict:
    """Топ запросов с показами/кликами/позицией. Индикаторы просим явно — без них
    ответ приходит без цифр, и таблица выглядит пустой «без ошибки»."""
    uid = uid if uid is not None else user_id()
    return _call(f"/user/{uid}/hosts/{host}/search-queries/popular/", {
        "order_by": order_by,
        "query_indicator": ["TOTAL_SHOWS", "TOTAL_CLICKS", "AVG_SHOW_POSITION",
                            "AVG_CLICK_POSITION"],
        "limit": limit,
    })


def summary(host: str, uid: int | None = None) -> dict:
    """Сводка по сайту: ИКС, число страниц в поиске, проблемы."""
    uid = uid if uid is not None else user_id()
    return _call(f"/user/{uid}/hosts/{host}/summary/")
