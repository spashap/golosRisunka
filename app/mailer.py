"""Email за абстракцией: send_email() — ЕДИНАЯ точка отправки.

Сейчас backend 'outbox': письмо сохраняется HTML-файлом в data/outbox/
(открывается в браузере) + ASCII-строка в лог. В Phase 8 сюда тем же
интерфейсом воткнётся Unisender (MAIL_BACKEND='unisender') — вызывающий
код (worker, auth) не изменится.
"""
from __future__ import annotations

import datetime
import logging
import re
from html import escape
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import settings

log = logging.getLogger("mailer")
_env = Environment(loader=FileSystemLoader(settings.BASE_DIR / "templates" / "email"))


def render_email(template: str, **ctx) -> str:
    """Jinja-шаблон письма из templates/email/ (+ стандартный контекст сайта)."""
    return _env.get_template(template).render(
        site_name=settings.SITE_NAME, base_url=settings.PUBLIC_BASE_URL, **ctx)


def send_email(to: str, subject: str, html_body: str,
               attachments: list[Path] | None = None, kind: str = "mail") -> Path | None:
    """Отправляет письмо через текущий backend. kind — slug для имени файла/лога.
    Возвращает путь к файлу в outbox (None у реальных провайдеров)."""
    if settings.MAIL_BACKEND == "unisender":
        raise NotImplementedError("Unisender подключается в Phase 8 этой же функцией")
    return _outbox_write(to, subject, html_body, attachments or [], kind)


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
