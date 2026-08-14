"""Самопроверка аналитики: визиты, маяки, события-сбои, вложенность воронок.

Работает на КОПИИ боевой базы во временном файле — ничего не портит.
Запуск:  venv\\Scripts\\python.exe scripts\\analytics_selftest.py

Зачем скрипт, а не «посмотреть глазами»: воронка ломается тихо. Шаг, который
считается не по тем событиям, выглядит как «люди не доходят», и это невозможно
отличить от правды без проверки на заведомо известных данных.

Вывод — ASCII (правило проекта: cp1252-консоль Windows не печатает кириллицу).
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings  # noqa: E402

_tmp = Path(tempfile.gettempdir()) / "golos_analytics_selftest.sqlite3"
if _tmp.exists():
    _tmp.unlink()
if settings.DB_PATH.exists():
    shutil.copy(settings.DB_PATH, _tmp)
settings.DB_PATH = _tmp

from app import create_app  # noqa: E402
from app.admin_funnels import build  # noqa: E402
from app.db import connect, now  # noqa: E402
from app.track import classify_channel  # noqa: E402
from config import goals as G  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{'ok ' if ok else 'FAIL'}] {name}{(' — ' + detail) if detail and not ok else ''}")
    if not ok:
        FAILED.append(name)


def main() -> int:
    app = create_app()
    conn = connect()
    base_id = conn.execute("SELECT COALESCE(MAX(id), 0) m FROM events").fetchone()["m"]
    ts = now()

    print("1. channel classification")
    cases = [({}, "ycl", None, "ads"), ({"utm_medium": "cpc"}, None, None, "ads"),
             (None, None, None, "direct"),
             (None, None, "https://yandex.ru/search/?text=x", "organic"),
             (None, None, "https://vk.com/w", "social"),
             (None, None, "https://blog.example/x", "referral")]
    for utm, ycl, ref, want in cases:
        got = classify_channel(utm, ycl, ref)
        check(f"channel {want}", got == want, f"got {got}")

    print("2. visit, path and beacon fields")
    c = app.test_client()
    c.get("/?utm_source=yandex&utm_medium=cpc&utm_campaign=t&yclid=1234")
    c.get("/blog")
    c.post("/t/e", data={"engaged": "1", "p": "/", "sw": "390", "t": "1"})
    c.post("/t/e", data={"g": "scroll_75", "p": "/"})
    c.post("/t/e", data={"g": "scroll_25", "p": "/"})
    c.post("/t/e", data={"g": "sec_prices", "p": "/"})
    c.post("/t/e", data={"g": "bad goal!", "p": "/"})
    v = conn.execute("SELECT * FROM web_visits ORDER BY rowid DESC LIMIT 1").fetchone()
    check("visit created", v is not None)
    check("channel = ads (yclid)", v["channel"] == "ads", str(v["channel"]))
    check("pages counted, beacons not", v["pages"] == 2, str(v["pages"]))
    check("engaged", v["engaged"] == 1)
    check("max_scroll keeps the deepest", v["max_scroll"] == 75, str(v["max_scroll"]))
    check("screen width from client", v["screen_w"] == 390, str(v["screen_w"]))
    rows = conn.execute("SELECT type, path, visit_id FROM events WHERE id > ?",
                        (base_id,)).fetchall()
    check("every event has a visit", all(r["visit_id"] for r in rows))
    check("every event has a path", all(r["path"] for r in rows))
    check("garbage goal rejected",
          not any(r["type"] == "click:bad goal!" for r in rows))

    print("3. failure events")
    c.get("/no-such-page-here")
    c.post("/free/summary", data={"name": "", "band": "5-6", "concern": "black"})
    r = c.post("/free/summary", data={"name": "Test", "band": "5-6",
                                      "concern": "black", "duration": "weeks"})
    tok = conn.execute("SELECT token FROM free_analyses ORDER BY id DESC"
                       " LIMIT 1").fetchone()["token"]
    c.post(f"/free/upload/{tok}", data={"email": "bad"})
    c.post(f"/free/upload/{tok}", data={"email": "a@b.ru"})
    types: dict[str, list] = {}
    for e in conn.execute("SELECT type, payload_json FROM events WHERE id > ?", (base_id,)):
        types.setdefault(e["type"], []).append(e["payload_json"])
    for t in ("error_404", "blog_index_view", "free_summary_invalid",
              "free_upload_failed"):
        check(f"event {t}", t in types)
    reasons = {json.loads(p)["reason"] for p in types.get("free_upload_failed", []) if p}
    check("upload failures carry a reason", {"email", "no_file"} <= reasons, str(reasons))

    print("4. goal registry covers the templates")
    names = {n for n, *_ in G.ACTIONS}
    used: set[str] = set()
    for f in (BASE_DIR / "templates").rglob("*.html"):
        used |= set(re.findall(r'data-ym-goal(?:-submit)?="([^"{]+)"',
                               f.read_text(encoding="utf-8")))
    check("no template goal missing from the registry", used <= names,
          str(sorted(used - names)))
    js: set[str] = set()
    for f in (BASE_DIR / "static" / "js").glob("*.js"):
        js |= set(re.findall(r'ymGoal\("([a-z0-9_]+)"', f.read_text(encoding="utf-8")))
    check("no JS goal missing from the registry", js - {"scroll_", "sec_"} <= names,
          str(sorted(js - {"scroll_", "sec_"} - names)))
    tagged = set(re.findall(r'data-track-section="([a-z_]+)"',
                            (BASE_DIR / "templates" / "landing.html").read_text(encoding="utf-8")))
    check("landing sections are registered", tagged <= {k for k, _ in G.SECTIONS},
          str(sorted(tagged - {k for k, _ in G.SECTIONS})))
    for page in ("landing.html", "order.html", "free.html", "blog_post.html"):
        html = (BASE_DIR / "templates" / page).read_text(encoding="utf-8")
        if page == "landing.html":
            check("landing loads track.js", "js/track.js" in html)

    # Шапка общая: подмена кнопки на /free-check не должна протечь на остальные страницы.
    fc = c.get("/free-check").get_data(as_text=True)
    check("/free-check renders", "Бесплатная проверка детского рисунка" in fc)
    check("/free-check swaps the header CTA", 'data-ym-goal="header_cta_freecheck"' in fc
          and 'data-ym-goal="header_order"' not in fc)
    for url in ("/", "/order"):
        h = c.get(url).get_data(as_text=True)
        check(f"header CTA unchanged on {url}", 'data-ym-goal="header_order"' in h)
        check(f"nav item present on {url}", 'data-ym-goal="header_nav_check"' in h)

    print("5. funnels are nested where they must be")
    for vid, evs, dev, ch, sw in [
            ("st_p1", ["landing_view"], "desktop", "ads", None),
            ("st_p2", ["landing_view", "engaged", "order_form_view", "checkout_view"],
             "desktop", "ads", None),
            ("st_p3", ["landing_view", "engaged", "click:scroll_50",
                       "click:sec_prices", "order_form_view", "form_started",
                       "order_created", "checkout_view"], "mobile", "ads", 390),
            ("st_bot", ["landing_view", "order_created"], "bot", "ads", None)]:
        conn.execute(
            "INSERT INTO web_visits (visit_id, visitor_id, started_at, last_at,"
            " entry_path, exit_path, pages, device, channel, screen_w)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (vid, "vv-" + vid, ts, ts, "/", "/", 1, dev, ch, sw))
        for t in evs:
            conn.execute("INSERT INTO events (visitor_id, visit_id, type, created_at)"
                         " VALUES (?,?,?,?)", ("vv-" + vid, vid, t, ts))
    conn.execute(
        "INSERT INTO orders (email, product_code, price_kopecks, status, child_json,"
        " visit_id, created_at, paid_at) VALUES (?,?,?,?,?,?,?,?)",
        ("st@e.ru", "snapshot", 299900, "delivered", "{}", "st_p3", ts, ts))
    conn.commit()

    f = build(conn, "0000")
    prev = None
    nested = True
    for s in f["paid"]["steps"]:
        if s["kind"] == "gate":
            if prev is not None and s["n"] > prev:
                nested = False
            prev = s["n"]
    check("paid gates nested", nested)
    labels = [s["label"] for s in f["paid"]["steps"]]
    check("no duplicated step", len(labels) == len(set(labels)))
    by = {s["label"]: s for s in f["paid"]["steps"]}
    check("bot excluded", not any(d == "bot" for d, _ in f["devices"]))
    check("observation not back-filled",
          by["Досмотрел до цен"]["n"] < by["Открыл форму заказа"]["n"]
          or by["Досмотрел до цен"]["n"] == 1, str(by["Досмотрел до цен"]["n"]))
    check("paid comes from the order", by["Оплатил"]["n"] >= 1)
    check("mobile split by screen width", by["Оплатил"]["mobile"] >= 1)

    conn.close()
    print("")
    if FAILED:
        print(f"FAILED: {len(FAILED)}")
        for n in FAILED:
            print("  - " + n)
        return 1
    print("ALL OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
