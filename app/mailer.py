"""Email за абстракцией: send_email() — ЕДИНАЯ точка отправки.

Backend выбирается settings.MAIL_BACKEND:
- 'outbox'    — письмо сохраняется HTML-файлом в data/outbox/ + ASCII-строка в лог (dev);
- 'unisender' — транзакционный API Unisender Go (Phase 8). Отправитель —
  settings.MAIL_FROM_EMAIL (sales@golosrisunka.ru). При сбое сети/API письмо
  НЕ теряется: падаем в outbox + ERROR в лог (воркер/авторизация не падают).

Вызывающий код (worker, auth) одинаков для обоих backend'ов.
"""
from __future__ import annotations

import base64
import datetime
import json
import logging
import re
import urllib.error
import urllib.request
from html import escape, unescape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import settings

log = logging.getLogger("mailer")
_env = Environment(loader=FileSystemLoader(settings.BASE_DIR / "templates" / "email"))

_MIME = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg",
         ".jpeg": "image/jpeg", ".html": "text/html", ".txt": "text/plain"}


class MailSendError(RuntimeError):
    """Транспортная ошибка отправки (Unisender вернул не-success / сеть упала)."""


def render_email(template: str, **ctx) -> str:
    """Jinja-шаблон письма из templates/email/ (+ стандартный контекст сайта)."""
    return _env.get_template(template).render(
        site_name=settings.SITE_NAME, base_url=settings.PUBLIC_BASE_URL, **ctx)


def send_email(to: str, subject: str, html_body: str,
               attachments: list[Path] | None = None, kind: str = "mail") -> Path | None:
    """Отправляет письмо через текущий backend. kind — slug для имени файла/лога.
    Возвращает путь к файлу в outbox (None при успешной отправке Unisender)."""
    attachments = attachments or []
    if settings.MAIL_BACKEND == "unisender":
        try:
            _unisender_send(to, subject, html_body, attachments, kind)
            return None
        except Exception as e:  # сеть/API/таймаут — письмо не теряем, пишем в outbox
            log.error("EMAIL [%s] -> %s | Unisender FAILED (%s) — fallback to outbox",
                      kind, to, e)
            return _outbox_write(to, subject, html_body, attachments, kind)
    return _outbox_write(to, subject, html_body, attachments, kind)


def _unisender_send(to: str, subject: str, html_body: str,
                    attachments: list[Path], kind: str) -> None:
    """Транзакционное письмо через Unisender Go (email/send.json). Бросает MailSendError
    при не-success ответе или сетевой ошибке (urlopen бросит сам)."""
    if not settings.UNISENDER_GO_API_KEY:
        raise MailSendError("UNISENDER_GO_API_KEY пуст")
    message: dict = {
        "recipients": [{"email": to}],
        "subject": subject,
        "from_email": settings.MAIL_FROM_EMAIL,
        "from_name": settings.MAIL_FROM_NAME,
        "body": {"html": html_body, "plaintext": _html_to_text(html_body)},
        "track_links": 0,
        "track_read": 0,
    }
    atts = []
    for p in attachments:
        p = Path(p)
        atts.append({"type": _MIME.get(p.suffix.lower(), "application/octet-stream"),
                     "name": p.name,
                     "content": base64.b64encode(p.read_bytes()).decode("ascii")})
    if atts:
        message["attachments"] = atts

    # Unisender Go: ключ — в HTTP-заголовке X-API-KEY (НЕ в теле, как у старого Unisender API).
    payload = json.dumps({"message": message}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        settings.UNISENDER_GO_API_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json",
                 "X-API-KEY": settings.UNISENDER_GO_API_KEY})
    try:
        with urllib.request.urlopen(req, timeout=settings.UNISENDER_GO_TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as he:           # 4xx/5xx: тело содержит причину
        body = he.read().decode("utf-8", "replace")
        raise MailSendError(f"HTTP {he.code}: {body[:300]}")
    try:
        data = json.loads(raw)
    except ValueError:
        raise MailSendError(f"non-JSON response: {raw[:200]}")
    failed = data.get("failed_emails") or {}
    if data.get("status") == "success" and not failed:
        log.info("EMAIL [%s] -> %s | unisender job=%s", kind, to, data.get("job_id", "?"))
        return
    raise MailSendError(f"unisender response: {raw[:300]}")


def _html_to_text(html: str) -> str:
    """Грубый plaintext-фолбэк из HTML письма (для доставляемости/текстовых клиентов)."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", html)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</(p|div|tr|h[1-6]|li|table)>", "\n", text)
    text = re.sub(r"(?s)<[^>]+>", "", text)
    text = unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n[ \t]*\n[ \t]*\n+", "\n\n", text)
    return text.strip()


def send_admin_alert(subject: str, body_text: str) -> Path | None:
    """Алерт администратору (ошибки воркера, insufficient). До Unisender — outbox."""
    html = (f"<pre style='font: 13px/1.5 Consolas, monospace; white-space: pre-wrap'>"
            f"{escape(body_text)}</pre>")
    return send_email(settings.ADMIN_ALERT_EMAIL, f"[{settings.SITE_DOMAIN}] {subject}",
                      html, kind="alert")


def _outbox_write(to: str, subject: str, html_body: str,
                  attachments: list[Path], kind: str) -> Path:
    settings.OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    safe_kind = re.sub(r"[^a-z0-9_-]", "", kind.lower()) or "mail"
    path = settings.OUTBOX_DIR / f"{ts}_{safe_kind}.html"
    head = (f"<!--\nTo: {to}\nSubject: {subject}\n"
            + "".join(f"Attach: {a}\n" for a in attachments)
            + "-->\n")
    path.write_text(head + html_body, encoding="utf-8")
    # консоль Windows cp1252 — в лог только ASCII (UseCase #3)
    log.info("EMAIL [%s] -> %s | %s", safe_kind, to, path.name)
    return path
