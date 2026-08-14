"""Заводит в счётчике Метрики цели из реестра config/goals.py.

ЗАЧЕМ. Метрика считает конверсию только по цели, СОЗДАННОЙ в счётчике. Полсотни
`data-ym-goal` в шаблонах шлют reachGoal, но если цели нет — вызов уходит в пустоту:
в отчётах ноль, и Директу не на чем обучать автостратегию. Руками это не заводят.

Запуск (с хоста, токен в .env):
    venv\\Scripts\\python.exe scripts\\metrika_goals_sync.py --dry-run   # только показать
    venv\\Scripts\\python.exe scripts\\metrika_goals_sync.py             # создать недостающие

Идемпотентно: существующие цели не трогает и не переименовывает — сверка идёт по
ИДЕНТИФИКАТОРУ (conditions.url), а не по названию, поэтому переименование цели
в интерфейсе Метрики не приведёт к созданию дубля.

Ничего не удаляет: цель с накопленной статистикой удалять из скрипта нельзя.
Вывод — ASCII (правило проекта: cp1252-консоль Windows не печатает кириллицу).
"""
from __future__ import annotations

import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import metrika  # noqa: E402
from config import goals as G  # noqa: E402
from config import settings  # noqa: E402


def _existing_identifiers(existing: list[dict]) -> set[str]:
    """Идентификаторы уже заведённых целей: для action — conditions.url."""
    out: set[str] = set()
    for g in existing:
        for c in g.get("conditions") or []:
            if c.get("url"):
                out.add(c["url"])
    return out


def _print_manual() -> int:
    """Список целей для РУЧНОГО заведения в интерфейсе Метрики.

    Нужен, когда права на запись в счётчик недоступны (счётчик чужой либо в форме
    OAuth не нашлось права «Управление счётчиками»). Руками полсотни целей никто не
    заведёт, поэтому печатаем по приоритету: сначала то, без чего не измеряется
    воронка и не на чем учить автостратегию, потом остальное.
    Тип цели в интерфейсе — «JavaScript-событие», идентификатор — второй столбец.
    """
    direct = {i for i, _l in G.direct_targets()}
    core = ["free_summary", "free_upload_submit", "free_to_order", "order_submit_form",
            "purchase", "landing_hero_order", "landing_hero_free", "checkout_pay",
            "sec_prices", "scroll_50", "scroll_75",
            "order_blocked_email_typo", "free_file_too_big", "free_wait_gave_up"]
    wanted = dict(G.metrika_actions())
    out = ["СПИСОК ЦЕЛЕЙ ДЛЯ РУЧНОГО ЗАВЕДЕНИЯ В МЕТРИКЕ",
           "Метрика -> Цели -> Добавить цель -> тип «JavaScript-событие».",
           "Идентификатор — второй столбец, ВВОДИТЬ ТОЧНО как написано.",
           "",
           "--- ОБЯЗАТЕЛЬНЫЕ (воронка + кандидаты для автостратегии Директа) ---"]
    n = 0
    for ident in core:
        if ident in wanted:
            n += 1
            star = "   <-- кандидат для Директа" if ident in direct else ""
            out.append(f"{n:>3}. {ident:<28} {wanted[ident]}{star}")
    out += ["", "--- ОСТАЛЬНЫЕ (полезно, но всё это и так пишется в нашу базу) ---"]
    for ident, label in wanted.items():
        if ident not in core:
            n += 1
            out.append(f"{n:>3}. {ident:<28} {label}")
    out += ["", f"Всего: {n}.", "",
            "Плюс 4 цели типа «Просмотр URL» (условие «url содержит»):"]
    for _ident, name, contains, _d in G.URL_GOALS:
        out.append(f"     {contains:<20} {name}")
    out += ["",
            "Если заводить всё некогда — хватит первого блока: он закрывает воронку",
            "и даёт Директу цель, на которой автостратегия наберёт статистику."]

    # В файл, а не в консоль: список по-русски, а cp1252-консоль Windows его не печатает.
    path = settings.DATA_DIR / "metrika_goals_manual.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"written: {path}")
    print(f"goals listed: {n} action + {len(G.URL_GOALS)} url")
    print("Open the file, create the FIRST block by hand in the Metrika UI.")
    return 0


def main() -> int:
    dry = "--dry-run" in sys.argv
    if "--manual" in sys.argv:
        return _print_manual()
    if not metrika.enabled():
        print("SKIP: YANDEX_OAUTH_TOKEN or YANDEX_METRIKA_ID is empty (.env)")
        return 1
    print(f"counter: {settings.YANDEX_METRIKA_ID}  dry-run: {dry}")

    try:
        existing = metrika.list_goals()
    except metrika.MetrikaError as e:
        print(f"ERROR: cannot list goals: {e}")
        return 1
    have = _existing_identifiers(existing)
    print(f"goals already in counter: {len(existing)}")

    wanted = G.metrika_actions()
    todo = [(ident, name) for ident, name in wanted if ident not in have]
    print(f"action goals wanted: {len(wanted)}, missing: {len(todo)}")

    url_todo = [(ident, name, contains)
                for ident, name, contains, _d in G.URL_GOALS if contains not in have]
    print(f"url goals wanted: {len(G.URL_GOALS)}, missing: {len(url_todo)}")

    created = 0
    for ident, name in todo:
        if dry:
            print(f"  would create action goal: {ident}")
            continue
        try:
            metrika.create_action_goal(ident, name)
            created += 1
            print(f"  created action goal: {ident}")
        except metrika.MetrikaError as e:
            print(f"  FAILED {ident}: {e}")
    for ident, name, contains in url_todo:
        if dry:
            print(f"  would create url goal: {contains}")
            continue
        try:
            metrika.create_url_goal(name, contains)
            created += 1
            print(f"  created url goal: {contains}")
        except metrika.MetrikaError as e:
            print(f"  FAILED {contains}: {e}")

    print(f"done. created: {created}")
    print("")
    print("Direct auto-strategy candidates (volume first, money last):")
    for ident, _label in G.direct_targets():
        print(f"  - {ident}")
    print("Pick the LOWEST one that gets ~10 conversions/week; 'purchase' will not")
    print("have enough volume yet, and a starving goal makes the strategy worse.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
