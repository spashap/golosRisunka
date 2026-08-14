"""Клиент API Яндекс.Метрики (Management + Reporting) на stdlib `urllib`.

Тот же приём, что в app/yookassa.py: в проекте нет `requests`, и ради одного
интеграционного вызова зависимость не заводим.

Авторизация — OAuth-токен из СЕРВЕРНОГО .env (`YANDEX_OAUTH_TOKEN`), заголовок
`Authorization: OAuth <token>`. Без токена модуль просто выключен (`enabled()`),
как `yukassa_enabled()` — это не ошибка, а «интеграция не настроена».
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request

from config import settings

log = logging.getLogger("metrika")

MANAGEMENT_URL = "https://api-metrika.yandex.net/management/v1"
STAT_URL = "https://api-metrika.yandex.net/stat/v1/data"

_TIMEOUT = 30
_MAX_ATTEMPTS = 3
_RETRY_SLEEP = 3


class MetrikaError(Exception):
    pass


def enabled() -> bool:
    return bool(settings.YANDEX_OAUTH_TOKEN and settings.YANDEX_METRIKA_ID)


def _request(method: str, url: str, body: dict | None = None) -> tuple[int, dict]:
    """Возвращает (код, json). HTTP-ошибку НЕ поднимаем — решает вызывающий."""
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"OAuth {settings.YANDEX_OAUTH_TOKEN}",
        "Content-Type": "application/json; charset=utf-8",
    })
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace") or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as he:
        raw = he.read().decode("utf-8", "replace")
        try:
            return he.code, json.loads(raw)
        except ValueError:
            return he.code, {"message": raw[:300]}


def _call(method: str, url: str, body: dict | None = None) -> dict:
    """С ретраями транзитных сбоев. 4xx (кроме 429) не самоисцелится — сразу ошибка."""
    if not enabled():
        raise MetrikaError("YANDEX_OAUTH_TOKEN / YANDEX_METRIKA_ID не заданы")
    last = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            status, payload = _request(method, url, body)
        except (urllib.error.URLError, TimeoutError) as e:
            last = f"сеть: {e}"
            status, payload = 0, {}
        else:
            if 200 <= status < 300:
                return payload
            last = f"HTTP {status}: {payload.get('message') or str(payload)[:200]}"
            if status not in (429, 500, 502, 503, 504):
                raise MetrikaError(last)
        if attempt < _MAX_ATTEMPTS:
            time.sleep(_RETRY_SLEEP)
    raise MetrikaError(last or "неизвестная ошибка")


# --- Management: цели ---------------------------------------------------------------

def list_goals() -> list[dict]:
    counter = settings.YANDEX_METRIKA_ID
    return _call("GET", f"{MANAGEMENT_URL}/counter/{counter}/goals").get("goals", [])


def create_action_goal(identifier: str, name: str) -> dict:
    """Цель «JavaScript-событие»: conditions.url — это идентификатор из reachGoal."""
    counter = settings.YANDEX_METRIKA_ID
    body = {"goal": {"name": name[:255], "type": "action",
                     "conditions": [{"type": "exact", "url": identifier}]}}
    return _call("POST", f"{MANAGEMENT_URL}/counter/{counter}/goals", body).get("goal", {})


def create_url_goal(name: str, contains: str) -> dict:
    """Цель «просмотр страницы»: конверсия, которую reachGoal дать не может —
    на форме заказа человек может не нажать ничего."""
    counter = settings.YANDEX_METRIKA_ID
    body = {"goal": {"name": name[:255], "type": "url",
                     "conditions": [{"type": "contain", "url": contains}]}}
    return _call("POST", f"{MANAGEMENT_URL}/counter/{counter}/goals", body).get("goal", {})


# --- Reporting: то, чего наша база знать не может -----------------------------------

def report(metrics: str, dimensions: str, date1: str, date2: str,
           filters: str | None = None, limit: int = 200) -> dict:
    """Отчёт stat/v1/data. Нужен ради РАСХОДА Директа и поведения (отказы, глубина):
    рекламные деньги в нашей базе не появятся никогда."""
    params = {"ids": settings.YANDEX_METRIKA_ID, "metrics": metrics,
              "dimensions": dimensions, "date1": date1, "date2": date2,
              "limit": limit, "accuracy": "full"}
    if filters:
        params["filters"] = filters
    return _call("GET", f"{STAT_URL}?{urllib.parse.urlencode(params)}")
