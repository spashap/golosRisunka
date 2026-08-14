"""Фремиум-поток `/free`: мастер, загрузка, ожидание, разбор, оценка, email.

Правила, зашитые здесь и объяснённые на месте:
  * страница НЕ индексируется и НЕ упоминается в robots/sitemap (robots.txt — публичный
    файл, строка Disallow там опубликовала бы URL);
  * email НЕ даёт сессию покупателя — только скоуп-доступ к своему разбору + magic-link
    письмом (иначе чужой адрес открывал бы чужие платные PDF);
  * фремиум НЕ создаёт строк children (у нас целый возраст, а не birth_ym, и платный
    путь получил бы ребёнка без даты рождения);
  * тяжёлое (декодирование картинки, вызов Gemini) делает free_worker, а не веб.
"""
from __future__ import annotations

import io
import json
import logging
import re
from pathlib import Path

from flask import (Blueprint, Response, abort, g, jsonify, redirect,
                   render_template, request, url_for)

from app.auth import SESSION_COOKIE, login_link_for
from app.db import get_db, new_token, now
from app.mailer import render_email, send_email
from app.track import track_event
from config import free_keys, free_names, settings
from config import free_texts as T

log = logging.getLogger("free")

bp_free = Blueprint("free", __name__, url_prefix="/free")

FREE_COOKIE = "gr_f"          # мягкий лимит: ключ ребёнка живёт в браузере
FREE_SCOPE_COOKIE = "gr_fs"   # скоуп-доступ к СВОИМ разборам (не сессия покупателя)
ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# magic-bytes: дешёвая проверка ДО вставки строки и до всякого декодирования.
_MAGIC = {
    b"\xff\xd8\xff": ".jpg", b"\x89PNG\r\n\x1a\n": ".png",
    b"RIFF": ".webp", b"\x00\x00\x00": ".heic",   # ftyp-боксы HEIC начинаются с размера
}


def _sniff(blob: bytes) -> bool:
    if blob[4:8] == b"ftyp":
        return True
    return any(blob.startswith(m) for m in _MAGIC)


def _scope_tokens() -> list[str]:
    try:
        return json.loads(request.cookies.get(FREE_SCOPE_COOKIE) or "[]")[:20]
    except ValueError:
        return []


def _owns(token: str) -> bool:
    return token in _scope_tokens()


def _limit_key() -> str:
    return request.cookies.get(FREE_COOKIE) or (getattr(g, "visitor_id", "") or "")


def _norm_name(name: str) -> str:
    return free_names.normalize_name(name)


def _link_customer(db, addr: str, name_norm: str) -> tuple[int, int | None]:
    """Находит/создаёт клиента по email и привязывает существующего ребёнка.

    Строку children фремиум НЕ создаёт: у нас полоса возраста, а не birth_ym, и
    ребёнок без даты рождения испортил бы будущий платный заказ (mark_paid берёт
    существующего по имени и ничего не обновляет).
    """
    cust = db.execute("SELECT id FROM customers WHERE email = ?", (addr,)).fetchone()
    if cust is None:
        db.execute("INSERT INTO customers (email, created_at) VALUES (?, ?)",
                   (addr, now()))
        cust = db.execute("SELECT id FROM customers WHERE email = ?", (addr,)).fetchone()
    child_id = None
    for c in db.execute("SELECT id, name FROM children WHERE customer_id = ?",
                        (cust["id"],)).fetchall():
        if _norm_name(c["name"]) == name_norm:
            child_id = c["id"]
            break
    return cust["id"], child_id


def _existing_free(db, limit_key: str, name_norm: str, age: int):
    """Предикат лимита §9. Расходует лимит ТОЛЬКО status='done'.

    `mismatch` лимит не расходует и даёт ровно ОДНУ автоматическую замену: текст разбора
    сам приглашает показать нужный рисунок, и отказать после этого значило бы позвать к
    действию, которое мы же и запрещаем. Вторая замена уже считается.
    """
    rows = db.execute(
        "SELECT id, token, flags_json, replaces_id FROM free_analyses"
        " WHERE status = 'done' AND allow_replace = 0 AND deleted_at IS NULL"
        "   AND limit_key = ? AND child_name_norm = ? AND abs(child_age - ?) <= 1"
        " ORDER BY id DESC", (limit_key, name_norm, age)).fetchall()
    for r in rows:
        flags = json.loads(r["flags_json"] or "[]")
        if "mismatch" in flags and not r["replaces_id"]:
            continue          # несовпадение — приглашаем принести нужный лист
        return r
    return None


# --- Мастер -----------------------------------------------------------------------

@bp_free.get("/")
def page():
    track_event("free_view")
    return render_template("free.html", concerns=T.CONCERNS, durations=T.DURATIONS,
                           texts=T, ages=list(range(3, 13)))


@bp_free.post("/summary")
def summary():
    """Вывод после вопросов. Собирается НА СЕРВЕРЕ: единственное абсолютное требование
    блока — склейка только по границам абзацев, и баг в клиентском сборщике произвёл бы
    ровно тот артефакт, против которого написан весь продукт."""
    f = request.form
    name = (f.get("name") or "").strip()[:40]
    # Возраст приходит ПОЛОСОЙ. В БД пишем представительный возраст полосы: age_band()
    # от него возвращает ту же полосу, поэтому предикат лимита и тексты не разъезжаются.
    band_key = f.get("band") or ""
    if band_key not in T.BAND_BY_KEY:
        track_event("free_summary_invalid", {"field": "band"})
        return jsonify({"error": "bad_input"}), 400
    age = T.band_age(band_key)
    concern = f.get("concern") or ""
    if not name or concern not in T.CONCERN_KEYS:
        track_event("free_summary_invalid",
                    {"field": "name" if not name else "concern"})
        return jsonify({"error": "bad_input"}), 400
    address = f.get("address") if f.get("address") in ("он", "она") else \
        free_names.address_form_or_ask(name)[0]
    duration = f.get("duration") or ""
    parent_text = (f.get("parent_text") or "").strip()[:2000]

    s = T.assemble_summary(concern_key=concern,
                           duration_key=None if concern == "neutral" else duration,
                           age=age, address_form=address, name=name)

    db = get_db()
    token = new_token(12)
    db.execute(
        "INSERT INTO free_analyses (token, visitor_id, limit_key, child_name,"
        " child_name_norm, child_age, address_form, concern_key, duration_key,"
        " parent_text, ask_variant, status, created_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,'answers',?)",
        (token, getattr(g, "visitor_id", None), _limit_key(), name, _norm_name(name),
         age, address, concern, duration or None, parent_text or None,
         s["ask_variant"], now()))
    db.commit()
    track_event("free_summary", {"concern": concern, "age": age})

    limit_row = _existing_free(db, _limit_key(), _norm_name(name), age)
    html = render_template("_free_summary.html", paragraphs=s["paragraphs"],
                           ask=s["ask"], ask_note=s["ask_note"], kinds=s["kinds"],
                           lens_question=s["lens_question"],
                           offer=T.offer_block(name, address),
                           token=token, name=name, age=age,
                           wait_hint=T.wait_hint(concern, address),
                           band=T.BAND_LABELS[T.age_band(age)], texts=T,
                           limit_token=limit_row["token"] if limit_row else None)
    resp = Response(html)
    if not request.cookies.get(FREE_COOKIE):
        resp.set_cookie(FREE_COOKIE, new_token(9), max_age=365 * 24 * 3600,
                        httponly=True, samesite="Lax")
    return resp


# --- Загрузка -----------------------------------------------------------------------

def _upload_failed(reason: str, payload: dict, code: int):
    """Отказ загрузки — СОБЫТИЕ, а не только сообщение в интерфейсе.

    Это была самая большая дыра в воронке: человек дошёл до конца анкеты, нажал
    «разобрать» и упёрся в лимит/формат/размер — а в аналитике не оставалось ничего,
    и шаг «загрузили рисунок» просто не наступал без объяснения причины.
    """
    track_event("free_upload_failed", {"reason": reason})
    return jsonify(payload), code


@bp_free.post("/upload/<token>")
def upload(token: str):
    db = get_db()
    row = db.execute("SELECT * FROM free_analyses WHERE token = ?", (token,)).fetchone()
    if row is None:
        return _upload_failed("not_found", {"error": "not_found"}, 404)
    if row["status"] not in ("answers", "rejected", "failed"):
        return _upload_failed("already", {"error": "already", "token": token}, 409)

    limit_row = _existing_free(db, row["limit_key"], row["child_name_norm"],
                               row["child_age"])
    if limit_row is not None:
        return _upload_failed("limit",
                              {"error": "limit", "token": limit_row["token"]}, 409)

    if settings.FREE_DAILY_CAP:
        today = now()[:10]
        n = db.execute("SELECT COUNT(*) c FROM free_analyses"
                       " WHERE status IN ('queued','running','done')"
                       "   AND created_at >= ?", (today,)).fetchone()["c"]
        if n >= settings.FREE_DAILY_CAP:
            track_event("free_cap_hit")
            return jsonify({"error": "cap"}), 429

    # Почта собирается ВМЕСТЕ с фотографией — как «куда прислать», а не стеной после
    # сорока секунд ожидания. Заодно закрывает старую дыру: резервный выход обещал
    # письмо, которого у нас не было.
    addr = (request.form.get("email") or "").strip().lower()
    if not EMAIL_RE.match(addr):
        return _upload_failed("email", {"error": "email"}, 400)

    fs = request.files.get("file")
    if fs is None or not fs.filename:
        return _upload_failed("no_file", {"error": "no_file"}, 400)
    ext = Path(fs.filename.lower()).suffix
    if ext not in ALLOWED_EXT:
        return _upload_failed("format", {"error": "format"}, 400)
    blob = fs.read()
    # Дешёвые проверки СИНХРОННО и до вставки: так «неудачная загрузка не расходует
    # лимит» выполняется по построению, а не сверкой статусов.
    if len(blob) > settings.UPLOAD_MAX_BYTES:
        return _upload_failed("too_big", {"error": "too_big"}, 400)
    if len(blob) < 1024 or not _sniff(blob):
        return _upload_failed("broken", {"error": "broken"}, 400)

    d = settings.FREE_DIR / str(row["id"])
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"drawing{ext}"
    path.write_bytes(blob)
    cust_id, child_id = _link_customer(db, addr, row["child_name_norm"])
    db.execute(
        "UPDATE free_analyses SET file_path = ?, status = 'queued', stage = 'prepare',"
        " reject_reason = NULL, started_at = NULL, email = ?, customer_id = ?,"
        " child_id = ? WHERE id = ?",
        (path.relative_to(settings.BASE_DIR).as_posix(), addr, cust_id, child_id,
         row["id"]))
    db.commit()
    track_event("free_upload", {"concern": row["concern_key"]})

    resp = jsonify({"ok": True, "token": token})
    scope = _scope_tokens()
    if token not in scope:
        scope.append(token)
    resp.set_cookie(FREE_SCOPE_COOKIE, json.dumps(scope[-20:]),
                    max_age=365 * 24 * 3600, httponly=True, samesite="Lax")
    return resp


# Стадии для честного индикатора ожидания. Поле stage пишет free_worker, поэтому
# честный индикатор стоит ровно столько же, сколько поддельный, и не врёт на 90-й секунде.
STAGE_LABELS = {
    "prepare": "Готовим фотографию…",
    "looking": "Смотрим на рисунок…",
    "detail": "Ищем деталь, за которую стоит зацепиться…",
    "lint": "Перечитываем формулировки…",
    "almost": "Почти готово…",
}
STAGE_ORDER = ["prepare", "looking", "detail", "lint", "almost"]


@bp_free.get("/status/<token>")
def status(token: str):
    row = get_db().execute(
        "SELECT status, stage, reject_reason FROM free_analyses WHERE token = ?",
        (token,)).fetchone()
    if row is None:
        return jsonify({"error": "not_found"}), 404
    stage = row["stage"] or "prepare"
    return jsonify({
        "status": row["status"], "stage": stage,
        "label": STAGE_LABELS.get(stage, STAGE_LABELS["prepare"]),
        "step": STAGE_ORDER.index(stage) + 1 if stage in STAGE_ORDER else 1,
        "steps": len(STAGE_ORDER),
        "reject": row["reject_reason"],
    })


# --- Разбор -------------------------------------------------------------------------

@bp_free.get("/r/<token>")
def result(token: str):
    """Доступ по прямой ссылке БЕЗ входа — как у /r/<token> платных отчётов.
    Шестизначный код между родителем и его разбором убивает людей на пике."""
    db = get_db()
    row = db.execute("SELECT * FROM free_analyses WHERE token = ?", (token,)).fetchone()
    if row is None:
        abort(404)
    if row["status"] != "done":
        # Ожидание — тоже состояние воронки: сюда попадают те, кто вернулся по ссылке
        # раньше, чем разбор готов, и не увидел результата.
        track_event("free_wait_view", {"status": row["status"]})
        return render_template("free_wait.html", token=token,
                               wait_hint=T.wait_hint(row["concern_key"],
                                                     row["address_form"] or "он"))
    data = json.loads(
        (settings.BASE_DIR / row["analysis_json_path"]).read_text(encoding="utf-8"))
    interps = db.execute(
        "SELECT * FROM free_interpretations WHERE analysis_id = ? ORDER BY id",
        (row["id"],)).fetchall()
    flags = json.loads(row["flags_json"] or "[]")
    name, address = row["child_name"], row["address_form"] or "он"
    track_event("free_result_view", {"concern": row["concern_key"]})
    return render_template(
        "free_result.html", r=row, a=data, token=token, name=name,
        name_gen=T.genitive(name, address), name_acc=T.accusative(name, address),
        band_label=T.BAND_LABELS[T.age_band(row["child_age"] or 6)],
        flags=flags, interps=interps,
        source=(free_keys.source_for((data.get("hypothesis") or {}).get("key", ""))
                if data.get("hypothesis") else None),
        coloring_par=T.g(T.COLORING_PARAGRAPH, address) if "coloring" in flags else None,
        mismatch_par=(T.MISMATCH_PARAGRAPH if row["correlate"] == 0
                      and "coloring" not in flags else None),
        sparse_pars=([p.replace("{name}", name) for p in T.SPARSE_PARAGRAPHS]
                     if "sparse" in flags else []),
        cta=(T.coloring_cta(name, address) if "coloring" in flags
             else T.selling_block(name, address)),
        is_coloring="coloring" in flags,
        image_deleted=bool(row["deleted_at"]),
        has_email=bool(row["email"]))


@bp_free.get("/img/<token>")
def image(token: str):
    """Превью рисунка. Отдаём только владельцу скоупа или по прямой ссылке-токену —
    сам токен и есть контроль доступа, как у /r/."""
    row = get_db().execute(
        "SELECT file_path, deleted_at FROM free_analyses WHERE token = ?",
        (token,)).fetchone()
    if row is None or row["deleted_at"] or not row["file_path"]:
        abort(404)
    src = settings.BASE_DIR / row["file_path"]
    if not src.exists():
        abort(404)
    thumb = src.with_name(f"thumb_{src.stem}.jpg")
    if not thumb.exists() or thumb.stat().st_mtime < src.stat().st_mtime:
        from pipeline.images import prepare_image
        thumb.write_bytes(prepare_image(src, max_side=900))
    return Response(thumb.read_bytes(), mimetype="image/jpeg",
                    headers={"Cache-Control": "private, max-age=86400"})


@bp_free.post("/vote/<int:interp_id>")
def vote(interp_id: int):
    """Оценка привязана к КОНКРЕТНОЙ интерпретации, а не к разбору целиком: иначе
    непонятно, что именно не понравилось."""
    v = request.form.get("vote")
    if v not in ("yes", "no"):
        return jsonify({"error": "bad"}), 400
    db = get_db()
    db.execute("UPDATE free_interpretations SET parent_vote = ?, voted_at = ?"
               " WHERE id = ?", (v, now(), interp_id))
    db.commit()
    track_event("free_vote", {"vote": v})
    return jsonify({"ok": True})


# --- Email ПОСЛЕ разбора ------------------------------------------------------------

@bp_free.post("/email/<token>")
def email(token: str):
    """Ветка «нет рисунка под рукой»: сохранить место и прислать ссылку.

    Основной путь почту больше здесь не собирает — она берётся на экране загрузки
    вместе с фотографией. Сессию покупателя это по-прежнему НЕ выдаёт: введя чужой
    адрес, человек получил бы доступ к чужим платным отчётам. Скоуп-cookie на свой
    разбор + magic-link письмом.
    """
    addr = (request.form.get("email") or "").strip().lower()
    if not EMAIL_RE.match(addr):
        return jsonify({"error": "email"}), 400
    db = get_db()
    row = db.execute("SELECT * FROM free_analyses WHERE token = ?", (token,)).fetchone()
    if row is None:
        return jsonify({"error": "not_found"}), 404

    cust_id, child_id = _link_customer(db, addr, row["child_name_norm"])
    db.execute("UPDATE free_analyses SET email = ?, customer_id = ?, child_id = ?"
               " WHERE id = ?", (addr, cust_id, child_id, row["id"]))
    db.commit()
    try:
        send_free_email(db, row["id"])
    except Exception as e:                       # письмо не должно ломать поток
        log.warning("free: email send failed: %s", e)
    track_event("free_email")

    resp = jsonify({"ok": True})
    scope = _scope_tokens()
    if token not in scope:
        scope.append(token)
        resp.set_cookie(FREE_SCOPE_COOKIE, json.dumps(scope[-20:]),
                        max_age=365 * 24 * 3600, httponly=True, samesite="Lax")
    return resp


def send_free_email(db, analysis_id: int) -> bool:
    """Письмо родителю. Вызывается и из веба (ветка «нет рисунка»), и из free_worker
    (когда разбор готов), поэтому живёт здесь и берёт всё из строки БД."""
    row = db.execute("SELECT * FROM free_analyses WHERE id = ?",
                     (analysis_id,)).fetchone()
    if row is None or not row["email"]:
        return False
    link = f"{settings.PUBLIC_BASE_URL}/free/r/{row['token']}"
    cabinet = login_link_for(db, email=row["email"])
    if row["status"] == "done":
        html = render_email("free_ready.html", child_name=row["child_name"],
                            result_url=link, cabinet_link=cabinet)
        subject = f"Разбор рисунка — {settings.SITE_NAME}"
    else:
        # Разбора ещё нет — письмо «ваш разбор готов» здесь было бы враньём.
        # Памятку про возрастную полосу берём из уже написанного возрастного якоря:
        # так обещание «расскажем, что меняется» выполняется, а не остаётся обещанием.
        band = T.age_band(row["child_age"] or 6)
        html = render_email("free_saved.html", child_name=row["child_name"],
                            result_url=link, cabinet_link=cabinet,
                            band_label=T.BAND_LABELS[band],
                            band_note=T.g(T.AGE_ANCHORS[band],
                                          row["address_form"] or "он"))
        subject = f"Сохранили ваше место — {settings.SITE_NAME}"
    send_email(row["email"], subject, html, kind="free_mail")
    return True


def send_free_reject_email(db, analysis_id: int, reason: str) -> bool:
    """Отказ по непригодному фото. Почта у нас уже есть, значит родитель ЖДЁТ письма —
    промолчать здесь хуже, чем прислать честное «нужно другое фото»."""
    row = db.execute("SELECT * FROM free_analyses WHERE id = ?",
                     (analysis_id,)).fetchone()
    if row is None or not row["email"]:
        return False
    html = render_email("free_reject.html", child_name=row["child_name"],
                        reason=reason,
                        retry_url=f"{settings.PUBLIC_BASE_URL}/free")
    send_email(row["email"], f"Нужно другое фото — {settings.SITE_NAME}", html,
               kind="free_reject")
    return True


# --- Переиспользование рисунка в платном заказе -------------------------------------

def materialize_free_drawing(token: str):
    """Собирает FileStorage из сохранённого бесплатного рисунка.

    Проверено по коду orders.py: validate_and_create_order использует fs.filename,
    fs.read(), fs.seek(0) и fs.save() — всё это FileStorage поверх BytesIO поддерживает,
    поэтому app/orders.py НЕ меняется вообще.
    """
    from werkzeug.datastructures import FileStorage
    row = get_db().execute(
        "SELECT file_path, deleted_at FROM free_analyses WHERE token = ?",
        (token,)).fetchone()
    if row is None or row["deleted_at"] or not row["file_path"]:
        return None
    src = settings.BASE_DIR / row["file_path"]
    if not src.exists():
        return None
    return FileStorage(stream=io.BytesIO(src.read_bytes()), name="d1_file",
                       filename=f"drawing{src.suffix}")


def free_row_for_order(token: str):
    return get_db().execute(
        "SELECT * FROM free_analyses WHERE token = ? AND deleted_at IS NULL",
        (token,)).fetchone()
