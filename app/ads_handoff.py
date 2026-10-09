"""Инструкция рекламному агенту (handoff) — версионированная, раздаётся через API.

Зачем: раньше каждое обновление инструкции владелец пересылал партнёру руками.
Теперь агент сам спрашивает GET /api/ads/v1/handoff/version и, если версия новее его
копии, забирает GET /api/ads/v1/handoff.

Как попадает на сервер: через git (push -> deploy pull), как весь код. Но репозиторий
ПУБЛИЧНЫЙ, а инструкция — рекламная стратегия, поэтому в git лежит ЗАШИФРОВАННЫЙ файл
config/ads_handoff.json (версия и дата открыты, текст — нет). Ключ выводится из
ADS_API_TOKEN: он и так есть у сервера (.env) и у партнёра (файл доступа), новый секрет
не нужен. Ротация токена (--rotate) требует переопубликовать инструкцию
(scripts/ads_handoff_publish.py) — до этого /handoff отвечает 503 с объяснением.

Исходник в открытом виде — projectSpec/ads/ADS-PARTNER-HANDOFF.md (в .gitignore).
"""
from __future__ import annotations

import base64
import hashlib
import json

from config import settings

HANDOFF_FILE = settings.BASE_DIR / "config" / "ads_handoff.json"
_KEY_SALT = b"golos-ads-handoff-v1:"
_cache: tuple[float, dict] | None = None


class HandoffError(Exception):
    pass


def fernet_key(token: str) -> bytes:
    return base64.urlsafe_b64encode(hashlib.sha256(_KEY_SALT + token.encode()).digest())


def encrypt(markdown: str, token: str) -> str:
    from cryptography.fernet import Fernet
    return Fernet(fernet_key(token)).encrypt(markdown.encode("utf-8")).decode("ascii")


def decrypt(ciphertext: str, token: str) -> str:
    from cryptography.fernet import Fernet, InvalidToken
    try:
        return Fernet(fernet_key(token)).decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise HandoffError("handoff was encrypted with another token: the owner must "
                           "re-publish it (scripts/ads_handoff_publish.py)") from e


def load() -> dict | None:
    """Опубликованный файл (с кэшем по mtime) или None, если ещё не публиковали."""
    global _cache
    try:
        mtime = HANDOFF_FILE.stat().st_mtime
    except OSError:
        return None
    if _cache is None or _cache[0] != mtime:
        _cache = (mtime, json.loads(HANDOFF_FILE.read_text(encoding="utf-8")))
    return _cache[1]


def meta() -> dict | None:
    d = load()
    if not d:
        return None
    return {"version": d["version"], "updated": d["updated"], "sha256": d["sha256"]}


def content() -> str:
    d = load()
    if not d:
        raise HandoffError("no handoff published yet")
    md = decrypt(d["ciphertext"], settings.ADS_API_TOKEN)
    if hashlib.sha256(md.encode("utf-8")).hexdigest() != d["sha256"]:
        raise HandoffError("handoff checksum mismatch: re-publish it")
    return md
