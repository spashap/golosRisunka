"""Быстрая проверка связи с Gemini в обход воркера: маленький запрос, короткий
таймаут. Показывает, проблема в сети/прокси или в нашем коде.

Запуск (на сервере):  venv/bin/python scripts/gemini_ping.py
ASCII-вывод (безопасно для любой консоли)."""
import os
import sys
import time
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from google import genai
from google.genai import types
from config import settings


def main() -> int:
    base = os.getenv("GOOGLE_GEMINI_BASE_URL")
    timeout_ms = int(os.getenv("GEMINI_PING_TIMEOUT_MS", "30000"))
    print("model:    ", settings.GEMINI_MODEL)
    print("base_url: ", base or "default-google")
    print("timeout:  ", timeout_ms, "ms")
    print("api_key:  ", "set" if settings.GEMINI_API_KEY else "MISSING")

    kw = {"timeout": timeout_ms}
    if base:
        kw["base_url"] = base
    client = genai.Client(api_key=settings.GEMINI_API_KEY,
                          http_options=types.HttpOptions(**kw))

    t0 = time.time()
    try:
        resp = client.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents="Reply with exactly one word: pong",
        )
        dt = time.time() - t0
        txt = (resp.text or "").strip()[:60]
        print("RESULT OK in %.1fs: %s" % (dt, txt.encode("ascii", "replace").decode()))
        return 0
    except Exception as e:
        dt = time.time() - t0
        msg = str(e)[:300].encode("ascii", "replace").decode()
        print("RESULT FAILED in %.1fs: %s: %s" % (dt, type(e).__name__, msg))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
