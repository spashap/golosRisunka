"""Раздел «Задачи»: то, что нужно сделать РУКАМИ и чего нет в коде.

Зачем таблица, а не файл в репозитории: часть работы делается в чужих интерфейсах
(завести цели в Метрике, попросить подрядчика связать Директ со счётчиком, выдать
доступ) — такую задачу некуда положить в код, и из переписки она пропадает.

Засеянные задачи (`key` не пустой) НЕ удаляются, только закрываются: иначе после
удаления они возвращались бы при следующем открытии страницы, и кнопка «удалить»
выглядела бы сломанной. Задачи, добавленные руками, удаляются полностью.
"""
from __future__ import annotations

from app.db import now
from config import goals as G

# Первый блок из scripts/metrika_goals_sync.py --manual: без него не измеряется
# воронка и автостратегии Директа не на чем учить.
_CORE_GOALS = ["free_summary", "free_upload_submit", "free_to_order",
               "order_submit_form", "purchase", "landing_hero_order",
               "landing_hero_free", "checkout_pay", "sec_prices", "scroll_50",
               "scroll_75", "order_blocked_email_typo", "free_file_too_big",
               "free_wait_gave_up"]


def _metrika_goals_details() -> str:
    """Текст задачи собирается ИЗ РЕЕСТРА целей, а не пишется руками: реестр меняется,
    и разъехавшийся список в задаче отправил бы заводить несуществующие цели."""
    wanted = dict(G.metrika_actions())
    direct = {i for i, _l in G.direct_targets()}
    lines = [
        "ЗАЧЕМ. Метрика считает конверсию только по цели, ЗАВЕДЁННОЙ в счётчике.",
        "На сайте полсотни целей отправляют события, но пока цель не создана —",
        "вызов уходит в пустоту: в отчётах Метрики ноль, и автостратегиям Директа",
        "не на чем обучаться. Наша собственная аналитика от этого не зависит:",
        "в разделах «Аналитика» и «Действия» всё это уже видно.",
        "",
        "КАК. Метрика → Цели → Добавить цель → тип «JavaScript-событие».",
        "Идентификатор — левый столбец, вводить ТОЧНО как написано, без пробелов.",
        "Название — правый столбец (его можно менять как угодно, оно только для вас).",
        "",
        "14 ЦЕЛЕЙ. Этого достаточно: остальные 40 полезны, но не обязательны —",
        "они и так пишутся в нашу базу.",
        "",
    ]
    for n, ident in enumerate(_CORE_GOALS, start=1):
        label = wanted.get(ident, ident)
        mark = "   ← кандидат для автостратегии Директа" if ident in direct else ""
        lines.append(f"{n:>3}. {ident:<24} {label}{mark}")
    lines += [
        "",
        "ПЛЮС 4 ЦЕЛИ ТИПА «Просмотр URL» (условие «url содержит»):",
    ]
    for _ident, name, contains, _d in G.URL_GOALS:
        lines.append(f"     {contains:<18} {name}")
    lines += [
        "",
        "ПРО ДИРЕКТ. Реклама у подрядчика. «Покупка» при нашем объёме не наберёт",
        "~10 конверсий в неделю, а голодная цель делает автостратегию хуже, а не лучше.",
        "Поэтому подрядчику стоит отдать цель ПОВЫШЕ по воронке — из помеченных",
        "стрелкой берите самую нижнюю, у которой набирается объём.",
        "",
        "ЕСЛИ НЕ ХВАТАЕТ ПРАВ. Цели заводит владелец счётчика. Если счётчик",
        "109824945 создавал подрядчик, попросите доступ уровня «Полный доступ» —",
        "«Только просмотр» позволяет читать отчёты, но не создавать цели.",
        "",
        "Полный список всех 54 целей: data/metrika_goals_manual.txt на сервере",
        "(создаётся командой scripts/metrika_goals_sync.py --manual).",
    ]
    return "\n".join(lines)


def _seed(db) -> None:
    """Идемпотентно: задача с таким key создаётся один раз за всю жизнь базы."""
    seeds = [
        ("metrika_goals",
         "Завести 14 целей в Яндекс.Метрике (~10 минут, руками)",
         _metrika_goals_details()),
    ]
    for key, title, details in seeds:
        row = db.execute("SELECT id FROM admin_tasks WHERE key = ?", (key,)).fetchone()
        if row is None:
            db.execute(
                "INSERT INTO admin_tasks (key, title, details, status, created_at)"
                " VALUES (?, ?, ?, 'open', ?)", (key, title, details, now()))
    db.commit()


def load(db) -> dict:
    """Открытые сверху, закрытые снизу — закрытые не удаляем: по ним видно,
    что уже сделано, а «Метрика» и «доступы» всплывают повторно."""
    _seed(db)
    rows = db.execute(
        "SELECT * FROM admin_tasks ORDER BY status = 'done', id DESC").fetchall()
    items = [{
        "id": r["id"], "key": r["key"], "title": r["title"],
        "details": r["details"] or "",
        "done": r["status"] == "done",
        "created": (r["created_at"] or "")[:10],
        "done_at": (r["done_at"] or "")[:10],
        "seeded": bool(r["key"]),
    } for r in rows]
    return {"tasks": items,
            "open_n": sum(1 for i in items if not i["done"]),
            "done_n": sum(1 for i in items if i["done"])}


def add(db, title: str, details: str) -> None:
    db.execute("INSERT INTO admin_tasks (title, details, status, created_at)"
               " VALUES (?, ?, 'open', ?)", (title[:200], details[:8000], now()))
    db.commit()


def toggle(db, task_id: int) -> None:
    row = db.execute("SELECT status FROM admin_tasks WHERE id = ?",
                     (task_id,)).fetchone()
    if row is None:
        return
    if row["status"] == "done":
        db.execute("UPDATE admin_tasks SET status = 'open', done_at = NULL"
                   " WHERE id = ?", (task_id,))
    else:
        db.execute("UPDATE admin_tasks SET status = 'done', done_at = ?"
                   " WHERE id = ?", (now(), task_id))
    db.commit()


def delete(db, task_id: int) -> bool:
    """Засеянную задачу удалить нельзя — она вернулась бы при следующем открытии
    страницы, и кнопка выглядела бы сломанной. Такие только закрываются."""
    row = db.execute("SELECT key FROM admin_tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None or row["key"]:
        return False
    db.execute("DELETE FROM admin_tasks WHERE id = ?", (task_id,))
    db.commit()
    return True
