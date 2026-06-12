"""Создание заказа: валидация формы по конфигу, сохранение файлов, запись в БД."""
from __future__ import annotations

import json
import re
from pathlib import Path

from werkzeug.datastructures import FileStorage

from app.db import get_db, now
from config import settings
from config.form_fields import CHILD_FIELDS, DRAWING_FIELDS

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class FormError(Exception):
    """Ошибки валидации: словарь {поле: сообщение} для рендера формы."""

    def __init__(self, errors: dict[str, str]):
        super().__init__("form validation failed")
        self.errors = errors


def _validate_block(fields: list[dict], data: dict, prefix: str,
                    errors: dict[str, str]) -> dict:
    out = {}
    for f in fields:
        name = f"{prefix}{f['key']}"
        if f["type"] == "ym":
            # два селекта <name>_m + <name>_y -> 'YYYY-MM'
            m = (data.get(f"{name}_m") or "").strip()
            y = (data.get(f"{name}_y") or "").strip()
            val = f"{y}-{m}" if (m and y) else ""
            if f["required"] and not val:
                errors[name] = "Выберите месяц и год"
            elif val and not MONTH_RE.match(val):
                errors[name] = "Выберите месяц и год из списка"
        else:
            val = (data.get(name) or "").strip()
            if f["required"] and not val:
                errors[name] = "Обязательное поле"
        out[f["key"]] = val
    return out


def validate_and_create_order(form: dict, files: list[FileStorage],
                              visitor_id: str | None, utm: dict | None) -> int:
    """Полная валидация (сервер не доверяет клиенту) → заказ в БД + файлы на диске.
    Возвращает order_id. Бросает FormError."""
    errors: dict[str, str] = {}

    email = (form.get("email") or "").strip().lower()
    if not EMAIL_RE.match(email):
        errors["email"] = "Укажите корректный email"

    child = _validate_block(CHILD_FIELDS, form, "child_", errors)

    products = settings.get_products()
    product_code = form.get("product", "snapshot")
    if product_code not in products or not products[product_code]["enabled"]:
        product_code = "snapshot"
    product = products[product_code]

    # рисунки: 1..max, у каждого свой блок полей d{i}_
    drawings: list[dict] = []
    if not files:
        errors["drawings"] = "Загрузите хотя бы один рисунок"
    if len(files) > product["drawings_max"]:
        errors["drawings"] = f"Не больше {product['drawings_max']} рисунков"
    for i, fs in enumerate(files, start=1):
        name = (fs.filename or "").lower()
        ext = Path(name).suffix
        if ext not in ALLOWED_EXT:
            errors[f"d{i}_file"] = "Формат: JPG, PNG, HEIC или WebP"
            continue
        blob = fs.read()
        fs.seek(0)
        if len(blob) > settings.UPLOAD_MAX_BYTES:
            errors[f"d{i}_file"] = "Файл больше 15 МБ"
        if len(blob) < 100:
            errors[f"d{i}_file"] = "Файл повреждён или пуст"
        ctx = _validate_block(DRAWING_FIELDS, form, f"d{i}_", errors)
        drawings.append({"ext": ext, "file": fs, "context": ctx})

    # здравый смысл дат: рисунок не раньше рождения и не из будущего
    import datetime
    this_month = datetime.date.today().strftime("%Y-%m")
    birth = child.get("birth_ym", "")
    if birth and birth > this_month:
        errors["child_birth_ym"] = "Дата рождения в будущем?"
    for i, d in enumerate(drawings, start=1):
        da = d["context"].get("drawn_at", "")
        if da:
            if da > this_month:
                errors[f"d{i}_drawn_at"] = "Дата рисунка в будущем"
            elif birth and da < birth:
                errors[f"d{i}_drawn_at"] = "Рисунок раньше рождения ребёнка — проверьте даты"

    # промокод: пустой ок; непустой должен существовать, быть активным и не исчерпанным
    db = get_db()
    price_kopecks = product["price_rub"] * 100
    coupon_code = (form.get("coupon") or "").strip().upper() or None
    if coupon_code:
        c = db.execute("SELECT * FROM coupons WHERE upper(code) = ?", (coupon_code,)).fetchone()
        if c is None or not c["active"] or (not c["multi_use"] and c["uses_count"] > 0):
            errors["coupon"] = "Промокод не найден или уже использован"
        else:
            price_kopecks = price_kopecks * (100 - c["percent_off"]) // 100

    if errors:
        raise FormError(errors)

    cur = db.execute(
        "INSERT INTO orders (email, product_code, price_kopecks, coupon_code, status,"
        " child_json, visitor_id, utm_json, created_at)"
        " VALUES (?, ?, ?, ?, 'created', ?, ?, ?, ?)",
        (email, product_code, price_kopecks, coupon_code,
         json.dumps(child, ensure_ascii=False),
         visitor_id, json.dumps(utm, ensure_ascii=False) if utm else None, now()),
    )
    order_id = cur.lastrowid

    order_dir = settings.DRAWINGS_DIR / str(order_id)
    order_dir.mkdir(parents=True, exist_ok=True)
    for i, d in enumerate(drawings, start=1):
        path = order_dir / f"drawing_{i}{d['ext']}"
        d["file"].save(path)
        db.execute(
            "INSERT INTO drawings (order_id, file_path, drawn_at, context_json, uploaded_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (order_id, path.relative_to(settings.BASE_DIR).as_posix(),
             d["context"].get("drawn_at"),
             json.dumps(d["context"], ensure_ascii=False), now()),
        )
    db.commit()
    return order_id
