"""Единая настройка логирования для веб- и воркер-процессов.

Один формат на оба процесса; INFO пишется в файл (UTF-8, греппится локально и на
сервере) И в stdout/stderr (под gunicorn это уходит в journald, см.
`journalctl -u golosrisunka-web`). Идемпотентно: повторный вызов в том же процессе
(несколько gunicorn-воркеров вызывают create_app каждый у себя) не плодит хендлеры.
"""
from __future__ import annotations

import logging
from pathlib import Path

from config import settings

# Болтливые библиотеки — только предупреждения (наши auth/jobs/mailer/worker — INFO).
_NOISY = ("fontTools", "weasyprint", "httpx", "google_genai", "PIL", "urllib3")
_FMT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(logfile: Path, *, level: int = logging.INFO) -> None:
    """Вешает file+console хендлеры на root один раз за процесс."""
    root = logging.getLogger()
    if getattr(root, "_gr_configured", False):
        return
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fmt = logging.Formatter(_FMT)
    file_h = logging.FileHandler(logfile, encoding="utf-8")  # 'a' mode: append на Linux атомарен построчно
    file_h.setFormatter(fmt)
    console_h = logging.StreamHandler()                      # stderr → gunicorn → journald
    console_h.setFormatter(fmt)
    root.setLevel(level)
    root.addHandler(file_h)
    root.addHandler(console_h)
    for noisy in _NOISY:
        logging.getLogger(noisy).setLevel(logging.WARNING)
    root._gr_configured = True  # type: ignore[attr-defined]
