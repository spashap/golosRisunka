"""Срок хранения фотографий бесплатных загрузок (фремиум-бета).

Обещать удаление и не удалять хуже, чем не обещать, поэтому механизм выходит НЕ ПОЗЖЕ
самого обещания: текст «храним 90 дней» появляется на публичной странице (Фаза 3), а эти
функции — в Фазе 2, вместе с free_worker.

Что удаляется: только ФАЙЛ рисунка и его превью. Текст разбора, ключи трактовок и данные
беты живут дальше — в них нет изображения, и они и есть цель беты. Родитель по своей
ссылке продолжает видеть разбор, вместо картинки — пометка о сроке хранения.

Платный заказ этим не затрагивается никогда: при переиспользовании рисунка файл
КОПИРУЕТСЯ в data/drawings/<order_id>/, и заказ самодостаточен.
"""
from __future__ import annotations

import datetime
import logging
import sqlite3
from pathlib import Path

from app.db import now
from config import settings

log = logging.getLogger("free_retention")


def _remove_files(rel_path: str | None) -> int:
    """Удаляет файл и рядом лежащее превью. Отсутствие файла — не ошибка."""
    if not rel_path:
        return 0
    src = settings.BASE_DIR / rel_path
    removed = 0
    for p in (src, src.with_name(f"thumb_{src.stem}.jpg")):
        try:
            if p.exists():
                p.unlink()
                removed += 1
        except OSError as e:            # прод: файл может принадлежать другому UID
            log.warning("retention: cannot remove %s: %s", p, e)
    return removed


def delete_image(conn: sqlite3.Connection, analysis_id: int) -> bool:
    """Ручное удаление по просьбе родителя (кнопка в админке). Идемпотентно."""
    row = conn.execute(
        "SELECT file_path, deleted_at FROM free_analyses WHERE id = ?",
        (analysis_id,)).fetchone()
    if row is None:
        return False
    removed = _remove_files(row["file_path"])
    conn.execute("UPDATE free_analyses SET deleted_at = ? WHERE id = ?",
                 (now(), analysis_id))
    conn.commit()
    log.info("retention: manual delete id=%s files=%d", analysis_id, removed)
    return bool(removed) or not row["deleted_at"]


def sweep_expired(conn: sqlite3.Connection,
                  ttl_days: int = settings.FREE_IMAGE_TTL_DAYS) -> int:
    """Удаляет фотографии старше срока хранения. Возвращает число обработанных строк.

    Вызывается раз в сутки из free_worker: он и так долгоживущий процесс, это дешевле
    cron и не требует ещё одного юнита. Идемпотентно — повторный вызов ничего не ломает.
    """
    cutoff = (datetime.datetime.now(datetime.timezone.utc)
              - datetime.timedelta(days=ttl_days)).isoformat(timespec="seconds")
    rows = conn.execute(
        "SELECT id, file_path FROM free_analyses"
        " WHERE deleted_at IS NULL AND file_path IS NOT NULL AND created_at < ?",
        (cutoff,)).fetchall()
    for r in rows:
        _remove_files(r["file_path"])
        conn.execute("UPDATE free_analyses SET deleted_at = ? WHERE id = ?",
                     (now(), r["id"]))
    if rows:
        conn.commit()
        log.info("retention: swept %d image(s) older than %d days", len(rows), ttl_days)
    return len(rows)
