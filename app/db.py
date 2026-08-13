"""SQLite-слой: stdlib sqlite3, без ORM (закон простоты). Схема — spec §5
+ решения 12.06: drawn_at / birth_ym / base_order_id (Development, upsell)
+ events / visitor / UTM (аналитика будущей админки).
"""
from __future__ import annotations

import datetime
import json
import secrets
import sqlite3

from flask import g

from config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    login_token TEXT,                     -- durable magic-login token (ссылки «войти» в письмах)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS children (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    name TEXT NOT NULL,
    gender TEXT,                          -- 'м' / 'ж' (авторитетный источник пола)
    birth_ym TEXT,                        -- 'YYYY-MM' (возраст вычисляется на дату рисунка)
    birth_info TEXT,                      -- как введено родителем (spec §5)
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,                  -- введён в форме; customer создаётся при оплате
    customer_id INTEGER REFERENCES customers(id),
    child_id INTEGER REFERENCES children(id),
    product_code TEXT NOT NULL,           -- 'snapshot' / 'development'
    price_kopecks INTEGER NOT NULL,
    coupon_code TEXT,
    status TEXT NOT NULL DEFAULT 'created',
        -- created / paid / generating / failed / delivered / insufficient
    yookassa_payment_id TEXT,
    base_order_id INTEGER REFERENCES orders(id),  -- Development: на каком заказе основан
    child_json TEXT,                      -- данные ребёнка из формы (до создания child)
    visitor_id TEXT,                      -- аналитика: кто купил
    utm_json TEXT,                        -- first-touch UTM на момент заказа
    free_token TEXT,                      -- из какого бесплатного разбора пришёл заказ (атрибуция)
    retry_count INTEGER DEFAULT 0,        -- сколько авто-перезапусков уже было (транзитные сбои)
    next_retry_at TEXT,                   -- когда воркеру забрать 'failed'-заказ снова (UTC ISO); NULL = не перезапускать
    created_at TEXT NOT NULL,
    paid_at TEXT
);
CREATE TABLE IF NOT EXISTS drawings (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    file_path TEXT NOT NULL,
    drawn_at TEXT,                        -- 'YYYY-MM' (обязателен в форме; upsell-триггер)
    context_json TEXT,                    -- все поля формы по этому рисунку
    uploaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id),
    html_path TEXT,
    pdf_path TEXT,
    report_json_path TEXT,                -- сырой JSON Gemini — хранить обязательно
    public_token TEXT UNIQUE,
    generated_at TEXT,
    attempts INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id),
    token TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS login_codes (
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    code TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 0,
    requested_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_attempts (
    -- попытки входа «по данным ребёнка» (резервный вход, когда код не доходит).
    -- IP НЕ храним (как и в events) — лимитируем по email: брутфорс месяца рождения
    -- бьёт по конкретной жертве, поэтому email-лимит и есть нужный контроль.
    id INTEGER PRIMARY KEY,
    email TEXT NOT NULL,
    success INTEGER DEFAULT 0,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recovery_email ON recovery_attempts(email, created_at);
CREATE TABLE IF NOT EXISTS coupons (
    code TEXT PRIMARY KEY,
    percent_off INTEGER NOT NULL,
    multi_use INTEGER DEFAULT 0,
    active INTEGER DEFAULT 1,
    uses_count INTEGER DEFAULT 0
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY,
    visitor_id TEXT,
    customer_id INTEGER,
    type TEXT NOT NULL,
    payload_json TEXT,
    utm_json TEXT,
    user_agent TEXT,                      -- сырой UA (для разбора устройства)
    device TEXT,                          -- mobile / tablet / desktop / bot
    referer TEXT,                         -- откуда пришёл (origin)
    geo_country TEXT,                     -- страна по IP (код или назв.); сам IP НЕ храним
    geo_region TEXT,                      -- регион (для РФ — область/край и т.п.)
    geo_city TEXT,                        -- город (если есть в базе)
    created_at TEXT NOT NULL
);
-- === Фремиум-бета (projectSpec/fremium) ==========================================
-- Строка создаётся УЖЕ на шаге вывода после вопросов, до всякой загрузки: так видны
-- и оборванные воронки, а не только дошедшие до разбора.
CREATE TABLE IF NOT EXISTS free_analyses (
    id INTEGER PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,           -- публичная ссылка /free/r/<token>, вход без логина
    visitor_id TEXT,
    limit_key TEXT,                       -- ключ мягкого лимита (cookie gr_f или customer)
    child_name TEXT,
    child_name_norm TEXT,                 -- нормализация в Python: SQLite lower() не сворачивает кириллицу
    child_age INTEGER,
    address_form TEXT,                    -- 'он' / 'она' (грамматика, не анкетный пол)
    concern_key TEXT,
    duration_key TEXT,
    parent_text TEXT,
    ask_variant TEXT,                     -- какой из трёх вариантов просьбы о рисунке показан
    status TEXT NOT NULL DEFAULT 'answers',
        -- answers / queued / running / done / rejected / failed
    stage TEXT,                           -- стадия для экрана ожидания
    reject_reason TEXT,                   -- photo_poor / not_a_drawing / blank / other
    flags_json TEXT,                      -- sparse / coloring / thin (НЕ mismatch, см. ниже)
    correlate INTEGER,                    -- 1/0/NULL — ЕДИНСТВЕННЫЙ источник правды про несовпадение
    correlate_note TEXT,
    file_path TEXT,                       -- относительный к BASE_DIR, as_posix()
    analysis_json_path TEXT,
    model TEXT,
    prompt_version TEXT,
    attempts INTEGER DEFAULT 0,
    repair_rounds INTEGER DEFAULT 0,
    hypothesis_dropped INTEGER DEFAULT 0,
    prompt_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    gen_seconds REAL,
    allow_replace INTEGER DEFAULT 0,      -- ставит АДМИН: разрешить повтор в спорном случае
    replaces_id INTEGER REFERENCES free_analyses(id),  -- автозамена после mismatch (одна)
    customer_id INTEGER REFERENCES customers(id),
    child_id INTEGER REFERENCES children(id),  -- только если ребёнок УЖЕ существует
    email TEXT,
    created_at TEXT NOT NULL,
    started_at TEXT,
    delivered_at TEXT,
    deleted_at TEXT                       -- срок хранения фото (FREE_IMAGE_TTL_DAYS)
);
CREATE INDEX IF NOT EXISTS idx_free_status ON free_analyses(status, created_at);
CREATE INDEX IF NOT EXISTS idx_free_limit ON free_analyses(limit_key, child_name_norm);
CREATE INDEX IF NOT EXISTS idx_free_customer ON free_analyses(customer_id);
-- Наблюдённая фраза этого разбора + оценка родителя «это про него / не про него».
-- Оценка привязана к КОНКРЕТНОЙ интерпретации, а не к разбору целиком: иначе непонятно,
-- что именно не понравилось.
CREATE TABLE IF NOT EXISTS free_interpretations (
    id INTEGER PRIMARY KEY,
    analysis_id INTEGER NOT NULL REFERENCES free_analyses(id),
    phrase TEXT NOT NULL,
    attribution TEXT,
    key TEXT NOT NULL,                    -- из закрытого словаря config/free_keys.py либо 'new'
    new_key_description TEXT,             -- только при key='new'
    age_scope TEXT,
    parent_vote TEXT,                     -- 'yes' / 'no' / NULL
    voted_at TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_free_interp_key ON free_interpretations(key);
CREATE INDEX IF NOT EXISTS idx_free_interp_analysis ON free_interpretations(analysis_id);
-- Разметка заказчика ПО КЛЮЧУ, а не по строке: иначе один вердикт означал бы UPDATE N строк.
CREATE TABLE IF NOT EXISTS free_interpretation_keys (
    key TEXT PRIMARY KEY,
    verdict TEXT,                         -- confirmed / narrow / folklore
    note TEXT,
    first_seen_at TEXT,
    verdict_at TEXT
);
-- Признак живости фоновых юнитов: deploy.sh новый юнит не поднимает, мониторинга нет,
-- и после перезагрузки бокса разборы молча перестали бы генерироваться.
CREATE TABLE IF NOT EXISTS service_heartbeat (
    name TEXT PRIMARY KEY,
    last_seen_at TEXT NOT NULL
);
-- =================================================================================
CREATE INDEX IF NOT EXISTS idx_events_type ON events(type, created_at);
CREATE INDEX IF NOT EXISTS idx_events_visitor ON events(visitor_id, created_at);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_drawings_order ON drawings(order_id);
"""


def now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 5000")  # воркер + веб пишут в одну БД
    return conn


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(SCHEMA)
        _migrate(conn)
        conn.commit()
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Лёгкие миграции для уже существующих БД (CREATE IF NOT EXISTS не добавляет
    колонки в готовую таблицу). Идемпотентно: только ADD COLUMN, если колонки нет."""
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(events)")}
    for col in ("user_agent", "device", "referer",
                "geo_country", "geo_region", "geo_city"):
        if col not in cols:
            conn.execute(f"ALTER TABLE events ADD COLUMN {col} TEXT")

    # durable magic-login токен покупателя (ссылка «войти» в каждом письме).
    # Колонку добавляем ДО индекса: на старой БД executescript(SCHEMA) пропускает
    # CREATE TABLE customers, поэтому уникальный индекс строим здесь, после ALTER.
    ccols = {r["name"] for r in conn.execute("PRAGMA table_info(customers)")}
    if "login_token" not in ccols:
        conn.execute("ALTER TABLE customers ADD COLUMN login_token TEXT")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_customers_login_token"
                 " ON customers(login_token)")

    # самовосстановление воркера: счётчик авто-перезапусков и время следующего.
    ocols = {r["name"] for r in conn.execute("PRAGMA table_info(orders)")}
    if "retry_count" not in ocols:
        conn.execute("ALTER TABLE orders ADD COLUMN retry_count INTEGER DEFAULT 0")
    if "next_retry_at" not in ocols:
        conn.execute("ALTER TABLE orders ADD COLUMN next_retry_at TEXT")
    # Атрибуция «фремиум -> покупка»: токен бесплатного разбора, из которого пришёл заказ.
    # Косвенная склейка (email/visitor_id) остаётся, но она гадательная; прямой переход
    # из разбора — единственный точный источник, и без колонки он терялся.
    if "free_token" not in ocols:
        conn.execute("ALTER TABLE orders ADD COLUMN free_token TEXT")


def get_db() -> sqlite3.Connection:
    """Per-request соединение (Flask g). Закрывается в teardown (app/__init__)."""
    if "db" not in g:
        g.db = connect()
    return g.db


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def track(event_type: str, visitor_id: str | None = None,
          customer_id: int | None = None, payload: dict | None = None,
          utm: dict | None = None, conn: sqlite3.Connection | None = None,
          user_agent: str | None = None, device: str | None = None,
          referer: str | None = None, geo_country: str | None = None,
          geo_region: str | None = None, geo_city: str | None = None) -> None:
    """Серверное событие аналитики. Никогда не роняет запрос.
    conn — явное соединение для процессов без Flask (воркер).
    user_agent/device/referer/geo_* заполняются из request (track.py); воркер их не шлёт.
    Сам IP НЕ сохраняется — только производная гео-метка (страна/регион/город)."""
    try:
        db = conn if conn is not None else get_db()
        db.execute(
            "INSERT INTO events (visitor_id, customer_id, type, payload_json, utm_json,"
            " user_agent, device, referer, geo_country, geo_region, geo_city, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (visitor_id, customer_id, event_type,
             json.dumps(payload, ensure_ascii=False) if payload else None,
             json.dumps(utm, ensure_ascii=False) if utm else None,
             user_agent, device, referer,
             geo_country, geo_region, geo_city, now()),
        )
        db.commit()
    except Exception:
        pass
