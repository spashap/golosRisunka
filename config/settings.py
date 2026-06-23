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
# Доступ в админку /admin: отдельный вход по паролю (НЕ смешан с /login клиентов).
# Пустой ADMIN_PASS = админка полностью выключена (404).
ADMIN_PASS = os.getenv("ADMIN_PASS", "")
# Яндекс.Метрика: пока ID пуст — счётчик на страницы не вставляется
YANDEX_METRIKA_ID = os.getenv("YANDEX_METRIKA_ID", "")
# Dev-чит: этому email на localhost код входа показывается прямо на странице
DEV_LOGIN_CODE_EMAIL = "spashap@gmail.com"
# ЮKassa: режим test/live + раздельные ключи (как в shepotZvezd, проверено в бою).
# .env: YUKASSA_MODE=test|live, YUKASSA_SHOP_ID_{TEST,LIVE}, YUKASSA_SECRET_KEY_{TEST,LIVE}.
YUKASSA_MODE = os.getenv("YUKASSA_MODE", "test").strip().lower()
_YK = "LIVE" if YUKASSA_MODE == "live" else "TEST"
YUKASSA_SHOP_ID = os.getenv(f"YUKASSA_SHOP_ID_{_YK}", "").strip()
YUKASSA_SECRET_KEY = os.getenv(f"YUKASSA_SECRET_KEY_{_YK}", "").strip()
YUKASSA_API_URL = "https://api.yookassa.ru/v3"


def yukassa_enabled() -> bool:
    """True, если оба ключа заданы для текущего режима — иначе оплата недоступна."""
    return bool(YUKASSA_SHOP_ID and YUKASSA_SECRET_KEY)

UNISENDER_API_KEY = os.getenv("UNISENDER_API_KEY", "")          # legacy (маркетинговый API, не используется)
UNISENDER_GO_API_KEY = os.getenv("UNISENDER_GO_API_KEY", "")    # Unisender Go (транзакционные письма, Phase 8)

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


# Управляемые из админки тексты, которые пайплайн дописывает в КОНЕЦ отчёта при
# генерации (апсейл по числу рисунков + дисклеймеры + свободный блок). Pass-through,
# без логики; принцип «меняется в одном месте, без кода». Читается воркером при рендере.
_REPORT_TEXTS_FILE = BASE_DIR / "config" / "report_texts.json"
_report_texts_cache: tuple[float, dict] | None = None

# дефолты на случай отсутствия/повреждения файла — отчёт всё равно отрендерится
_REPORT_TEXTS_DEFAULT = {
    "upsell": {"1": "", "2": "", "3": ""},
    "disclaimer_main": "",
    "disclaimer_by_count": {"1": "", "2": "", "3": ""},
    "free_text": "",
}


def get_report_texts() -> dict:
    """Читает report_texts.json с кэшем по mtime — правки из админки видны без рестарта.
    При отсутствии/ошибке файла возвращает безопасные пустые дефолты."""
    global _report_texts_cache
    import json
    try:
        mtime = _REPORT_TEXTS_FILE.stat().st_mtime
    except OSError:
        return dict(_REPORT_TEXTS_DEFAULT)
    if _report_texts_cache is None or _report_texts_cache[0] != mtime:
        try:
            data = json.loads(_REPORT_TEXTS_FILE.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return dict(_REPORT_TEXTS_DEFAULT)
        _report_texts_cache = (mtime, data)
    return _report_texts_cache[1]

# --- Site ---
SITE_NAME = "Голос рисунка"
SITE_DOMAIN = "golosrisunka.ru"
# Версия сайта: единый источник — файл VERSION (major.minor, minor в 3 знака).
# Минор поднимается перед КАЖДЫМ git push (scripts/bump_version.py); мажор — вручную.
try:
    APP_VERSION = (BASE_DIR / "VERSION").read_text(encoding="utf-8").strip()
except OSError:
    APP_VERSION = "0.000"
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
MAIL_BACKEND = os.getenv("MAIL_BACKEND", "outbox")  # 'outbox' (файлы) | 'unisender' (Unisender Go)
OUTBOX_DIR = DATA_DIR / "outbox"       # backend 'outbox': письма как HTML-файлы
# Отправитель транзакционных писем (домен golosrisunka.ru, DKIM настраивается в Unisender).
MAIL_FROM_EMAIL = os.getenv("MAIL_FROM_EMAIL", "sales@golosrisunka.ru")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", SITE_NAME)
# Транзакционный API Unisender Go. Аккаунт golosrisunka — регион go2 (EU); go1 даёт
# 401 "User ... not found". Переопределяемо через env, если аккаунт сменит регион.
UNISENDER_GO_API_URL = os.getenv(
    "UNISENDER_GO_API_URL",
    "https://go2.unisender.ru/ru/transactional/api/v1/email/send.json")
UNISENDER_GO_TIMEOUT = 20              # сек на HTTP-запрос к Unisender Go
# Unisender Go добавляет блок «отписаться» (сигнал «рассылка» для Gmail → вкладка «Промоакции»).
# Для транзакционных писем его убирает skip_unsubscribe, НО аккаунту нужен флаг
# allow_skip_unsubscribe (включает поддержка Unisender Go). После включения — MAIL_SKIP_UNSUBSCRIBE=1.
MAIL_SKIP_UNSUBSCRIBE = os.getenv("MAIL_SKIP_UNSUBSCRIBE", "0").strip().lower() in ("1", "true", "yes")
# Бэкенд-домен отправки Unisender Go. Аккаунт ОБЩИЙ с shepotzvezd, дефолтный бэкенд —
# click.shepotzvezd.ru, из-за чего Return-Path/бэкенд НЕ выровнены с golosrisunka.ru → письма
# в спам. custom_backend_id привязывает отправку к click.golosrisunka.ru (Return-Path = наш домен,
# DKIM/DMARC-выравнивание). ID выдаёт поддержка Unisender (наш = 31525). Пусто = не передаём.
_cbid = os.getenv("UNISENDER_GO_CUSTOM_BACKEND_ID", "").strip()
UNISENDER_GO_CUSTOM_BACKEND_ID = int(_cbid) if _cbid.isdigit() else None

# --- Auth (spec §9) ---
SESSION_DAYS = 30
LOGIN_CODE_TTL_MINUTES = 30
LOGIN_CODE_RESEND_MINUTES = 10
LOGIN_CODE_MAX_ATTEMPTS = 5
