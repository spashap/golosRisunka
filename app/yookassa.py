"""Клиент ЮKassa (YooKassa API v3) — встроенный платёж (confirmation=embedded).

Порт проверенной реализации из соседнего проекта shepotZvezd, но на stdlib `urllib`
(в проекте нет зависимости requests — mailer.py уже ходит по HTTP через urllib).

create_payment(...) -> confirmation_token для виджета на странице оплаты.
get_payment(id)     -> текущее состояние платежа (для проверки в webhook/поллинге).

Подлинность webhook ЮKassa НЕ подписывает → проверяем перезапросом платежа через API
плюс сверкой суммы. Только статус 'succeeded' приводит к mark_paid (см. routes.py).
"""
from __future__ import annotations

import base64
import json
import logging
import time
import urllib.error
import urllib.request
import uuid

from config import settings

log = logging.getLogger("yookassa")

# Короткий ретрай на транзиентные ошибки — пользователь ждёт на чекауте.
# Idempotence-Key переиспользуется между попытками, дубль-платежа ЮKassa не создаст.
_MAX_ATTEMPTS = 2
_RETRY_SLEEP = 3
_TIMEOUT = 30


class YuKassaError(Exception):
    """Платёж не удалось создать (после ретраев) — показываем пользователю ретрай."""


def _auth_header() -> str:
    raw = f"{settings.YUKASSA_SHOP_ID}:{settings.YUKASSA_SECRET_KEY}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _request(method: str, path: str, body: dict | None = None,
             idempotence_key: str | None = None) -> tuple[int, dict]:
    """Один HTTP-вызов к API ЮKassa. Возвращает (status_code, json|{})."""
    url = f"{settings.YUKASSA_API_URL}{path}"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json", "Authorization": _auth_header()}
    if idempotence_key:
        headers["Idempotence-Key"] = idempotence_key
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8", "replace") or "{}")
    except urllib.error.HTTPError as he:
        raw = he.read().decode("utf-8", "replace")
        try:
            payload = json.loads(raw)
        except ValueError:
            payload = {"description": raw[:300]}
        return he.code, payload


def _amount_value(kopecks: int) -> str:
    """Копейки -> строка суммы ЮKassa '2399.20' (точно, без потери копеек скидки)."""
    rub, kop = divmod(kopecks, 100)
    return f"{rub}.{kop:02d}"


def _build_receipt(email: str, amount_kopecks: int, product_title: str) -> dict:
    """Чек 54-ФЗ для live (значения как в shepotZvezd: vat_code=1 «без НДС», услуга)."""
    return {
        "customer": {"email": email},
        "items": [{
            "description": product_title[:128],
            "quantity": "1.00",
            "amount": {"value": _amount_value(amount_kopecks), "currency": "RUB"},
            "vat_code": 1,
            "payment_subject": "service",
            "payment_mode": "full_payment",
        }],
    }


def create_payment(order_id: int, amount_kopecks: int, email: str,
                   description: str, product_title: str,
                   return_url: str | None = None) -> dict:
    """Создаёт платёж. Возвращает {payment_id, confirmation_token, confirmation_url, status}.
    `return_url` задан -> redirect-флоу (платёжная страница ЮKassa): на мобильном СБП
    показывает выбор банка / переход в банк-приложение, чего НЕ умеет embedded-виджет
    (только QR — бесполезен, когда сканировать нечем со своего же экрана). Без `return_url`
    -> встроенный виджет (confirmation=embedded), как было — десктоп остаётся на странице.
    Сумма берётся точно из копеек заказа (скидка купона может давать копейки)."""
    confirmation = ({"type": "redirect", "return_url": return_url}
                    if return_url else {"type": "embedded"})
    payload = {
        "amount": {"value": _amount_value(amount_kopecks), "currency": "RUB"},
        "capture": True,
        "confirmation": confirmation,
        "description": description[:128],
        "metadata": {"order_id": str(order_id)},
    }
    if settings.YUKASSA_MODE == "live" and email:
        payload["receipt"] = _build_receipt(email, amount_kopecks, product_title)

    idem = str(uuid.uuid4())  # один ключ на все ретраи этого вызова
    last = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            status, data = _request("POST", "/payments", payload, idempotence_key=idem)
        except (urllib.error.URLError, TimeoutError) as e:
            last = type(e).__name__
            log.warning("create_payment order %s attempt %s/%s transport: %s",
                        order_id, attempt, _MAX_ATTEMPTS, last)
        else:
            if status in (200, 201):
                conf = data.get("confirmation") or {}
                return {"payment_id": data.get("id"),
                        "confirmation_token": conf.get("confirmation_token"),
                        "confirmation_url": conf.get("confirmation_url"),
                        "status": data.get("status")}
            if status == 429 or 500 <= status < 600:
                last = f"HTTP {status}"
                log.warning("create_payment order %s attempt %s/%s transient %s",
                            order_id, attempt, _MAX_ATTEMPTS, last)
            else:                                   # 4xx — не самоисцелится
                msg = data.get("description", f"HTTP {status}")
                log.error("create_payment order %s rejected: %s", order_id, msg)
                raise YuKassaError(msg)
        if attempt < _MAX_ATTEMPTS:
            time.sleep(_RETRY_SLEEP)
    raise YuKassaError(last or "transient_failure")


def get_payment(payment_id: str) -> dict | None:
    """Текущее состояние платежа из API ЮKassa (для проверки в webhook/поллинге).
    None при сбое — вызывающий не должен трактовать это как 'оплачено'."""
    last = ""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            status, data = _request("GET", f"/payments/{payment_id}")
        except (urllib.error.URLError, TimeoutError) as e:
            last = type(e).__name__
        else:
            if status == 200:
                return data
            if not (status == 429 or 500 <= status < 600):
                log.error("get_payment %s HTTP %s", payment_id, status)
                return None
            last = f"HTTP {status}"
        if attempt < _MAX_ATTEMPTS:
            time.sleep(_RETRY_SLEEP)
    log.error("get_payment %s failed: %s", payment_id, last)
    return None
