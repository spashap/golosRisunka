"""Central config — spec law #2: everything the user sees is configurable here,
not hardcoded in logic. Secrets come from .env (never committed)."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# --- Secrets / external services (env) ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
ADMIN_ALERT_EMAIL = os.getenv("ADMIN_ALERT_EMAIL", "spashap@gmail.com")
# ЮKassa / Unisender keys land here later (Phase 8):
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID", "")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY", "")
UNISENDER_API_KEY = os.getenv("UNISENDER_API_KEY", "")

# --- Paths ---
DATA_DIR = BASE_DIR / "data"
DRAWINGS_DIR = DATA_DIR / "drawings"   # /data/drawings/{order_id}/...
REPORTS_DIR = DATA_DIR / "reports"     # /data/reports/{order_id}/...
DB_PATH = DATA_DIR / "golosrisunka.sqlite3"

# --- Products & prices ---
# Модель продукта (решение заказчика, override spec §1):
#   snapshot    — до 3 рисунков -> ОДИН сводный отчёт, цена не зависит от числа рисунков;
#   development — 2 набора рисунков с интервалом >= 6 мес. (может не войти в MVP).
# ВСЕ цифры управляются из будущей админки; до неё — config/products.json.
# Никогда не хардкодить цены в шаблонах/коде.
_PRODUCTS_FILE = BASE_DIR / "config" / "products.json"
_products_cache: tuple[float, dict] | None = None


def get_products() -> dict:
    """Читает products.json с кэшем по mtime — правки видны без рестарта."""
    global _products_cache
    import json
    mtime = _PRODUCTS_FILE.stat().st_mtime
    if _products_cache is None or _products_cache[0] != mtime:
        _products_cache = (mtime, json.loads(_PRODUCTS_FILE.read_text(encoding="utf-8")))
    return _products_cache[1]

# --- Site ---
SITE_NAME = "Голос рисунка"
SITE_DOMAIN = "golosrisunka.ru"
# Базовый URL для ссылок в письмах (на VPS станет https://golosrisunka.ru)
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "http://localhost:5000")
PALETTE = ""  # css class on <html>: "" = Синий (default), "pu" = Фиолет, "dk" = Тёмный, "cl" = Облака

# --- Report generation ---
GEMINI_MAX_ATTEMPTS = 5          # spec §7.2
IMAGE_MAX_LONG_SIDE = 2000       # px, resize before sending to Gemini
UPLOAD_MAX_BYTES = 15 * 1024 * 1024

# --- Worker / email (Phase 6) ---
WORKER_POLL_SECONDS = 5                # период опроса orders.status='paid'
WORKER_LOG = DATA_DIR / "worker.log"   # UTF-8 лог воркера (консоль — только ASCII!)
MAIL_BACKEND = os.getenv("MAIL_BACKEND", "outbox")  # 'outbox' сейчас | 'unisender' (Phase 8)
OUTBOX_DIR = DATA_DIR / "outbox"       # backend 'outbox': письма как HTML-файлы

# --- Auth (spec §9) ---
SESSION_DAYS = 30
LOGIN_CODE_TTL_MINUTES = 30
LOGIN_CODE_RESEND_MINUTES = 10
LOGIN_CODE_MAX_ATTEMPTS = 5
