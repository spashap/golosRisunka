"""Тест отправки письма через Unisender Go (Phase 8).

Запуск (venv\\Scripts\\python.exe):
  scripts\\send_test_email.py --dry-run             # собрать payload, НЕ отправлять
  scripts\\send_test_email.py you@example.com       # реальная отправка (после настройки DKIM)

--dry-run монкей-патчит HTTP: реального запроса нет; payload (api_key замаскирован)
пишется в data/outbox/_dryrun_payload.json. Печать в консоль — ТОЛЬКО ASCII (UseCase #3),
кириллица идёт в файл.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import mailer            # noqa: E402
from config import settings       # noqa: E402


def _sample_email() -> tuple[str, str]:
    html = mailer.render_email("login_code.html", code="123456",
                               ttl_minutes=settings.LOGIN_CODE_TTL_MINUTES)
    return "Test Unisender Go", html


def _dry_run(to: str, subject: str, html: str) -> None:
    import urllib.request
    captured: dict = {}

    class _Resp:
        def __init__(self, b: bytes):
            self._b = b

        def read(self) -> bytes:
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data.decode("utf-8")
        return _Resp(json.dumps({"status": "success", "job_id": "DRYRUN"}).encode())

    orig = urllib.request.urlopen
    urllib.request.urlopen = _fake_urlopen
    try:
        res = mailer.send_email(to, subject, html, kind="test")
    finally:
        urllib.request.urlopen = orig

    payload = json.loads(captured["data"])
    if payload.get("api_key"):
        payload["api_key"] = "***MASKED***"
    out = settings.OUTBOX_DIR
    out.mkdir(parents=True, exist_ok=True)
    pf = out / "_dryrun_payload.json"
    pf.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    msg = payload["message"]
    print("DRY-RUN ok (no network call made).")
    print("  endpoint   :", captured["url"])
    print("  from_email :", msg["from_email"])
    print("  to         :", msg["recipients"][0]["email"])
    print("  has_html   :", bool(msg["body"].get("html")))
    print("  has_text   :", bool(msg["body"].get("plaintext")))
    print("  attachments:", len(msg.get("attachments", [])))
    print("  would_send :", res is None, "(None = sent via API; Path = outbox fallback)")
    print("  payload    :", pf)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("to", nargs="?", default=settings.ADMIN_ALERT_EMAIL,
                    help="recipient email (default: ADMIN_ALERT_EMAIL)")
    ap.add_argument("--dry-run", action="store_true",
                    help="build payload without sending")
    args = ap.parse_args()

    subject, html = _sample_email()
    settings.MAIL_BACKEND = "unisender"   # форсируем backend независимо от .env

    if args.dry_run:
        _dry_run(args.to, subject, html)
        return

    if not settings.UNISENDER_GO_API_KEY:
        print("ERROR: UNISENDER_GO_API_KEY is empty in .env")
        sys.exit(1)
    res = mailer.send_email(args.to, subject, html, kind="test")
    if res is None:
        print("SENT via Unisender Go (status=success). Check inbox:", args.to)
    else:
        print("FAILED -> fell back to outbox file:", res)
        print("See the ERROR line in logs for the Unisender response (DKIM/domain?).")
        sys.exit(2)


if __name__ == "__main__":
    main()
