"""Проверка OAuth-токена Яндекса: что он реально умеет и что писать в .env.

Запуск (после того как токен добавлен в .env):
    venv\\Scripts\\python.exe scripts\\yandex_token_check.py

Скрипт НИЧЕГО не меняет — только читает и печатает. Он отвечает на четыре вопроса,
на которые иначе пришлось бы отвечать вручную через curl:
  1. токен вообще живой?
  2. видит ли он НАШ счётчик Метрики и хватает ли прав СОЗДАВАТЬ цели
     (счётчик мог завести подрядчик — тогда прав на запись у вас нет);
  3. какой user_id и host_id в Вебмастере (они нужны во всех путях API);
  4. приходит ли из Метрики расход Директа (он приходит ТОЛЬКО если рекламный
     аккаунт связан со счётчиком; связку делает тот, у кого доступ к Директу).

Вывод — ASCII (правило проекта: cp1252-консоль Windows не печатает кириллицу).
"""
from __future__ import annotations

import datetime
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import metrika, webmaster  # noqa: E402
from config import goals as G  # noqa: E402
from config import settings  # noqa: E402


def main() -> int:
    token = settings.YANDEX_OAUTH_TOKEN
    print("=" * 62)
    print("YANDEX OAUTH TOKEN CHECK")
    print("=" * 62)
    if not token:
        print("FAIL: YANDEX_OAUTH_TOKEN is empty in .env")
        print("      Add the line:  YANDEX_OAUTH_TOKEN=y0_Ab...your token...")
        return 1
    print(f"token: {token[:6]}...{token[-4:]} (len {len(token)})")
    print(f"metrika counter id: {settings.YANDEX_METRIKA_ID or '(empty!)'}")
    print("")

    ok = True

    # --- 1. Metrika: read + can we create goals? -----------------------------
    print("[1] METRIKA")
    if not settings.YANDEX_METRIKA_ID:
        print("  SKIP: YANDEX_METRIKA_ID is empty")
        ok = False
    else:
        try:
            existing = metrika.list_goals()
            print(f"  read OK: counter has {len(existing)} goal(s)")
            have = set()
            for g in existing:
                for c in g.get("conditions") or []:
                    if c.get("url"):
                        have.add(c["url"])
            wanted = [i for i, _n in G.metrika_actions()]
            missing = [i for i in wanted if i not in have]
            print(f"  goals from config/goals.py: {len(wanted)}, missing: {len(missing)}")
            if missing:
                print("  -> run: venv\\Scripts\\python.exe scripts\\metrika_goals_sync.py --dry-run")
        except metrika.MetrikaError as e:
            print(f"  FAIL: {e}")
            print("  (403/no access = the counter belongs to someone else, or the token")
            print("   lacks the 'metrika' permissions. Re-issue the token with them.)")
            ok = False

        # --- Direct spend: only present if the ad account is linked to the counter
        try:
            d2 = datetime.date.today() - datetime.timedelta(days=1)
            d1 = d2 - datetime.timedelta(days=29)
            rep = metrika.report(
                metrics="ym:s:visits,ym:s:adCost,ym:s:adClicks",
                dimensions="ym:s:lastDirectClickOrderName",
                date1=d1.isoformat(), date2=d2.isoformat(), limit=10)
            rows = rep.get("data") or []
            cost = sum((r.get("metrics") or [0, 0, 0])[1] or 0 for r in rows)
            print(f"  direct campaigns seen (30d): {len(rows)}, cost sum: {cost}")
            if not rows:
                print("  -> NO Direct data. Ads are run from an account that is NOT linked")
                print("     to this counter. Campaign cost/CPA cannot be read by us;")
                print("     ask the freelancer to link Direct to counter "
                      f"{settings.YANDEX_METRIKA_ID} (or to tag every link with UTM).")
        except metrika.MetrikaError as e:
            print(f"  direct spend check failed: {e}")

    # --- 2. Webmaster --------------------------------------------------------
    print("")
    print("[2] WEBMASTER")
    try:
        uid = webmaster.user_id()
        print(f"  user_id: {uid}")
        hs = webmaster.hosts(uid)
        print(f"  hosts: {len(hs)}")
        target = None
        for h in hs:
            mark = ""
            url = h.get("unicode_host_url") or h.get("ascii_host_url") or ""
            if settings.SITE_DOMAIN in url:
                target = h
                mark = "   <-- THIS ONE"
            print(f"    {h.get('host_id')}  {url}  "
                  f"verified={h.get('verified')}{mark}")
        if target:
            print("")
            print("  Put this in the SERVER .env:")
            print(f"    YANDEX_WEBMASTER_HOST_ID={target.get('host_id')}")
            if not target.get("verified"):
                print("  WARNING: host is not verified in Webmaster — query data will be empty.")
            try:
                q = webmaster.popular_queries(target["host_id"], uid, limit=5)
                qs = q.get("queries") or []
                print(f"  search queries available: {len(qs)} (showing up to 5)")
                for item in qs[:5]:
                    ind = item.get("indicators") or {}
                    print(f"    shows={ind.get('TOTAL_SHOWS')} clicks={ind.get('TOTAL_CLICKS')}"
                          f" pos={ind.get('AVG_SHOW_POSITION')}")
                if not qs:
                    print("  -> empty: normal for a young site with few impressions.")
            except webmaster.WebmasterError as e:
                print(f"  queries FAILED: {e}")
                ok = False
        else:
            print(f"  FAIL: {settings.SITE_DOMAIN} is not in this account's host list.")
            print("        Add and verify the site in Yandex Webmaster first.")
            ok = False
    except webmaster.WebmasterError as e:
        print(f"  FAIL: {e}")
        print("  (403 = token lacks webmaster:hostinfo. Re-issue it with that permission.)")
        ok = False

    print("")
    print("=" * 62)
    print("RESULT: " + ("everything the integration needs is available"
                        if ok else "something is missing — see FAIL lines above"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
