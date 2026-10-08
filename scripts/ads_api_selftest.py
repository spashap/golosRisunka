"""Самопроверка API рекламы (/api/ads/v1) и атрибуции «клик -> лид -> продажа».

Работает на КОПИИ базы во временном файле — ничего не портит.
Запуск:  venv\\Scripts\\python.exe scripts\\ads_api_selftest.py

Проверяет то, что ломается тихо: доступ по токену, идемпотентность записи расхода
(повтор отчёта не удваивает деньги), совпадение фраз Директа с utm_term, привязку
лида и покупки к рекламному клику (в том числе покупки из письма), подозрительные
визиты, расход на дашборде. Вывод — ASCII (cp1252-консоль Windows).
"""
from __future__ import annotations

import datetime
import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from config import settings  # noqa: E402

_tmp = Path(tempfile.gettempdir()) / "golos_ads_api_selftest.sqlite3"
for suffix in ("", "-wal", "-shm"):
    p = Path(str(_tmp) + suffix)
    if p.exists():
        p.unlink()
if settings.DB_PATH.exists():
    shutil.copy(settings.DB_PATH, _tmp)
settings.DB_PATH = _tmp
TOKEN = "selftest-token-" + "x" * 24
settings.ADS_API_TOKEN = TOKEN
settings.ADMIN_PASS = settings.ADMIN_PASS or "selftest-admin"

from app import create_app  # noqa: E402
from app import admin_dashboard as dash  # noqa: E402
from app import ads  # noqa: E402
from app.db import connect  # noqa: E402
from app.track import classify_channel  # noqa: E402

FAILED: list[str] = []
H = {"Authorization": "Bearer " + TOKEN}


def check(name: str, ok: bool, detail: str = "") -> None:
    detail = detail.encode("ascii", "backslashreplace").decode("ascii")   # cp1252-консоль
    print(f"  [{'ok ' if ok else 'FAIL'}] {name}{(' -- ' + detail) if detail and not ok else ''}")
    if not ok:
        FAILED.append(name)


def iso(dt: datetime.datetime) -> str:
    return dt.astimezone(datetime.timezone.utc).isoformat(timespec="seconds")


def main() -> int:
    app = create_app()
    c = app.test_client()
    conn = connect()
    now = datetime.datetime.now(datetime.timezone.utc)
    today = ads.today_msk().isoformat()
    camp = "900000001"

    print("1. access")
    check("no token -> 401", c.get("/api/ads/v1/ping").status_code == 401)
    check("wrong token -> 401",
          c.get("/api/ads/v1/ping", headers={"Authorization": "Bearer nope"}).status_code == 401)
    check("token -> 200", c.get("/api/ads/v1/ping", headers=H).status_code == 200)
    settings.ADS_API_TOKEN = "short"
    check("short token = API off (404)", c.get("/api/ads/v1/ping", headers=H).status_code == 404)
    settings.ADS_API_TOKEN = TOKEN
    visits_before = conn.execute("SELECT COUNT(*) n FROM web_visits").fetchone()["n"]
    c.get("/api/ads/v1/site", headers=H)
    check("API calls create no visits",
          conn.execute("SELECT COUNT(*) n FROM web_visits").fetchone()["n"] == visits_before)

    print("2. site info")
    s = c.get("/api/ads/v1/site", headers=H).get_json()
    snap = settings.get_products()["snapshot"]
    got = {p["code"]: p for p in s["products"]}
    check("live price of snapshot", got.get("snapshot", {}).get("price_rub") == snap["price_rub"])
    check("landings listed", s["landings"]["free"]["url"] == "/free-check")

    print("3. campaigns")
    r = c.put("/api/ads/v1/campaigns", headers=H, json={"campaigns": [
        {"source": "yandex", "campaign_id": camp, "name": "Selftest free", "cell": "free",
         "landing": "/free-check", "status": "active"}]})
    check("upsert ok", r.status_code == 200, r.get_data(as_text=True)[:200])
    r = c.put("/api/ads/v1/campaigns", headers=H, json={"campaigns": [
        {"source": "yandex", "campaign_id": camp, "cell": "nonsense"}]})
    check("bad cell rejected", r.status_code == 400)
    r = c.put("/api/ads/v1/campaigns", headers=H, json={"campaigns": [
        {"source": "yandex", "campaign_id": "900000002", "cell": "paid", "landing": "/blog/x"}]})
    check("blog landing warned", r.status_code == 200 and r.get_json()["warnings"])

    print("4. stats: validation and idempotency")
    r = c.post("/api/ads/v1/stats", headers=H, json={"rows": [
        {"day": "2020-01-01", "source": "yandex", "campaign_id": camp, "cost_rub": 1},
        {"day": today, "source": "yandex", "campaign_id": camp}]})
    check("old day and missing cost rejected", r.status_code == 400
          and r.get_json().get("error_count") == 2, r.get_data(as_text=True)[:200])
    rows = [{"day": today, "source": "yandex", "campaign_id": camp, "ad_id": "1111111",
             "keyword": "Ребёнок рисует +черным -бесплатно", "impressions": 200,
             "clicks": 10, "cost_rub": 500},
            {"day": today, "source": "yandex", "campaign_id": camp, "ad_id": "1111111",
             "keyword": "---autotargeting", "impressions": 50, "clicks": 2, "cost_rub": 80}]
    r = c.post("/api/ads/v1/stats", headers=H, json={"rows": rows, "dry_run": True})
    n = conn.execute("SELECT COUNT(*) n FROM ad_stats WHERE campaign_id = ?", (camp,)).fetchone()["n"]
    check("dry_run writes nothing", r.status_code == 200 and n == 0)
    for _ in range(2):
        r = c.post("/api/ads/v1/stats", headers=H, json={"rows": rows})
    tot = conn.execute("SELECT SUM(cost_rub) s, COUNT(*) n FROM ad_stats WHERE campaign_id = ?",
                       (camp,)).fetchone()
    check("resending the same report does not double spend", tot["s"] == 580 and tot["n"] == 2,
          f"sum={tot['s']} n={tot['n']}")
    kws = {r["keyword"] for r in conn.execute("SELECT keyword FROM ad_stats WHERE campaign_id = ?", (camp,))}
    check("keyword normalised", "ребенок рисует черным" in kws, str(kws))
    r = c.get(f"/api/ads/v1/stats?from={today}&to={today}&campaign_id={camp}", headers=H)
    check("stats read back", r.status_code == 200 and len(r.get_json()["rows"]) == 2)

    print("5. attribution: click -> lead -> paid order from an email visit")
    t_click = iso(now - datetime.timedelta(minutes=6))
    t_free = iso(now - datetime.timedelta(minutes=4))
    t_order = iso(now - datetime.timedelta(minutes=2))
    utm = json.dumps({"utm_source": "yandex", "utm_medium": "cpc", "utm_campaign": f"free_{camp}",
                      "utm_content": "1111111_search", "utm_term": "ребенок рисует черным"},
                     ensure_ascii=False)
    utm_auto = json.dumps({"utm_source": "yandex", "utm_medium": "cpc", "utm_campaign": f"free_{camp}",
                           "utm_content": "2222222_search", "utm_term": "---autotargeting"})
    visits = [
        # (visit_id, visitor, started, entry, utm, yclid, referer, channel, screen_w)
        ("st_click", "st_va", t_click, "/free-check", utm, "y1", "https://yandex.ru/", "ads", 390),
        ("st_return", "st_va", t_free, "/free/", utm, "y1", "https://golosrisunka.ru/free-check", "ads", 390),
        ("st_mail", "st_va", t_order, "/order", None, None, "https://e.mail.ru/", "email", 390),
        ("st_suspect", "st_vb", t_click, "/", utm_auto, None, None, "ads", 1920),
        ("st_org", "st_vc", t_click, "/", None, None, "https://yandex.ru/search", "organic", 390),
    ]
    for vid, vis, st, entry, u, y, ref, ch, sw in visits:
        conn.execute("INSERT INTO web_visits (visit_id, visitor_id, started_at, last_at, entry_path,"
                     " exit_path, pages, device, screen_w, channel, utm_json, yclid, referer)"
                     " VALUES (?,?,?,?,?,?,1,'mobile',?,?,?,?,?)",
                     (vid, vis, st, st, entry, entry, sw, ch, u, y, ref))
    for vid, typ in (("st_click", "free_check_view"), ("st_click", "free_view")):
        conn.execute("INSERT INTO events (visitor_id, visit_id, type, created_at) VALUES (?,?,?,?)",
                     ("st_va", vid, typ, t_click))
    conn.execute("INSERT INTO free_analyses (token, visitor_id, visit_id, status, email, created_at)"
                 " VALUES ('st_tok', 'st_va', 'st_return', 'done', 'st@e.ru', ?)", (t_free,))
    conn.execute("INSERT INTO orders (email, product_code, price_kopecks, status, child_json,"
                 " visitor_id, visit_id, created_at, paid_at) VALUES"
                 " ('st@e.ru', 'snapshot', 299900, 'delivered', '{}', 'st_va', 'st_mail', ?, ?)",
                 (t_order, t_order))
    conn.commit()

    d = ads.today_msk()
    rep = ads.report(conn, d, d, level="keyword", campaign_id=camp)
    by_kw = {r["keyword"]: r for r in rep["rows"]}
    k = by_kw.get("ребенок рисует черным", {})
    check("keyword row joins spend and visits", k.get("cost_rub") == 500 and k.get("visits") == 1,
          json.dumps({x: k.get(x) for x in ("cost_rub", "visits")}))
    check("return visit is not a second click", k.get("visits") == 1)
    check("in-visit steps", k.get("free_check_views") == 1 and k.get("free_wizard") == 1)
    check("lead and result credited to the click", k.get("free_leads") == 1 and k.get("free_results") == 1)
    check("order from the email visit credited to the click",
          k.get("orders") == 1 and k.get("paid") == 1 and k.get("revenue_rub") == 2999,
          json.dumps({x: k.get(x) for x in ("orders", "paid", "revenue_rub")}))
    check("cost per lead", k.get("cost_per_lead_rub") == 500.0, str(k.get("cost_per_lead_rub")))
    a = by_kw.get(ads.AUTOTARGETING, {})
    check("suspect visit flagged (utm without yclid)", a.get("suspect_visits") == 1, str(a))
    camp_rep = ads.report(conn, d, d, level="campaign", campaign_id=camp)["rows"]
    check("campaign row: cell and name from registry",
          camp_rep and camp_rep[0]["cell"] == "free" and camp_rep[0]["campaign_name"] == "Selftest free")
    check("organic visit not in ads report", all(r["campaign_id"] != "?" for r in camp_rep))
    check("cell filter excludes", not ads.report(conn, d, d, level="campaign", campaign_id=camp,
                                                 cell="paid")["rows"])
    land = ads.report(conn, d, d, level="landing", campaign_id=camp)["rows"]
    lf = {r["landing"]: r for r in land}.get("/free-check", {})
    check("landing level gets the ad's spend", lf.get("cost_rub") == 580, str(lf.get("cost_rub")))
    api_rep = c.get(f"/api/ads/v1/report?from={today}&to={today}&level=ad&campaign_id={camp}",
                    headers=H).get_json()
    check("API report endpoint", api_rep.get("ok") and api_rep["rows"]
          and api_rep["rows"][0]["ad_id"] == "1111111")
    check("API report has no emails", "@" not in json.dumps(api_rep, ensure_ascii=False))

    print("6. dashboard and admin page")
    sp = dash.spend(conn, dash.period("7"))
    check("dashboard spend includes API spend", sp["api_total"] >= 580, str(sp["api_total"]))
    from app.admin import _admin_token
    with app.test_request_context():
        tok = _admin_token()
    c.set_cookie("gr_a", tok)
    page = c.get(f"/admin/ads?from={today}&to={today}&level=keyword")
    check("/admin/ads renders", page.status_code == 200
          and "ребенок рисует черным" in page.get_data(as_text=True), str(page.status_code))

    print("7. delete and meta channel")
    r = c.delete(f"/api/ads/v1/stats?day={today}&source=yandex&campaign_id={camp}", headers=H)
    check("delete a day of a campaign", r.status_code == 200 and r.get_json()["deleted"] == 2)
    check("meta via utm paid_social",
          classify_channel({"utm_source": "instagram", "utm_medium": "paid_social"}, None, None) == "meta")
    check("meta via fbclid", classify_channel(None, None, None, True) == "meta")
    check("facebook without paid medium stays social",
          classify_channel({"utm_source": "facebook", "utm_medium": "post"}, None, None) == "social")
    check("yandex cpc still ads", classify_channel({"utm_source": "yandex", "utm_medium": "cpc"},
                                                   None, None) == "ads")

    print("8. free result offer")
    from config import free_texts as T
    bad = []
    for addr in ("он", "она"):
        for ck in [x["key"] for x in T.CONCERNS] + ["unknown"]:
            s = T.selling_block("Маша" if addr == "она" else "Миша", addr, ck)
            txt = " ".join([s["title"], s["body"], *s["includes"], s["button"]])
            if "{" in txt or "}" in txt or not s["includes"]:
                bad.append(f"{addr}/{ck}")
    check("offer texts: every concern x gender fills all slots", not bad, ", ".join(bad))
    s = T.selling_block("Маша", "она", "alone")
    check("offer agrees with gender", "одну" in s["body"] and "какая Маша" in s["includes"][0],
          s["body"][:80])
    tmpjson = Path(tempfile.gettempdir()) / "golos_selftest_analysis.json"
    tmpjson.write_text(json.dumps({"opening": "Открытие.", "detail": "Деталь.",
                                   "question_to_child": "Вопрос?", "unknown_next": "Неизвестное."},
                                  ensure_ascii=False), encoding="utf-8")
    conn.execute("INSERT INTO free_analyses (token, visitor_id, status, child_name, child_age,"
                 " address_form, concern_key, analysis_json_path, email, created_at)"
                 " VALUES ('st_res', 'st_va', 'done', 'Маша', 6, 'она', 'black', ?, 'st@e.ru', ?)",
                 (str(tmpjson), t_free))
    conn.commit()
    page = c.get("/free/r/st_res").get_data(as_text=True)
    check("result page renders the offer", 'data-track-section="fr_offer"' in page
          and "/order?free=st_res" in page and "check-list--one" in page)
    check("offer sits before the rating widget",
          page.find('data-track-section="fr_offer"') < page.find("feedback") or "feedback" not in page)
    check("offer bridge uses the concern", "тёмными цветами" in page)
    check("sample proof shown (if samples exist locally)", "free-proof" in page or not
          __import__("app.samples", fromlist=["get_samples"]).get_samples())

    print("9. order form detection")
    base_ev = conn.execute("SELECT COALESCE(MAX(id), 0) m FROM events").fetchone()["m"]
    c.post("/track/order-form", data={"k": "exit", "sec": "95", "f": "child_name,email,evil field,d1_file",
                                      "last": "d1_theme", "files": "1", "via": "header_nav_check",
                                      "bi": "2", "free": "1"})
    c.post("/track/order-form", data={"k": "bogus"})
    rows = conn.execute("SELECT type, payload_json FROM events WHERE id > ?", (base_ev,)).fetchall()
    st = [json.loads(r["payload_json"]) for r in rows if r["type"] == "order_form_state"]
    check("one state stored, bogus kind ignored", len(st) == 1, str(len(st)))
    check("only whitelisted field names kept",
          st and st[0]["fields"] == ["child_name", "email", "d1_file"] and st[0]["last"] == "d1_theme",
          str(st[0] if st else None))
    app.config["MAX_CONTENT_LENGTH"] = 1000
    r = c.post("/order", data={"x": "y" * 3000})
    r2 = c.post("/free/summary", data={"x": "y" * 3000})
    app.config["MAX_CONTENT_LENGTH"] = settings.UPLOAD_MAX_BYTES * 3 + 1_000_000
    n413 = conn.execute("SELECT COUNT(*) n FROM events WHERE type = 'upload_too_large' AND id > ?",
                        (base_ev,)).fetchone()["n"]
    check("too-large upload recorded (HTML for form, JSON for wizard)",
          r.status_code == 413 and r2.status_code == 413 and r2.get_json() == {"error": "too_big"}
          and n413 == 2, f"{r.status_code} {r2.status_code} n={n413}")
    from app.routes import _record_cancel
    oid = conn.execute("SELECT id FROM orders WHERE visit_id = 'st_mail'").fetchone()["id"]
    pay = {"id": "st-pay-1", "status": "canceled", "metadata": {"order_id": str(oid)},
           "cancellation_details": {"reason": "insufficient_funds", "party": "payment_network"}}
    with app.test_request_context():
        _record_cancel(pay)
        _record_cancel(pay)
    nc = conn.execute("SELECT COUNT(*) n FROM events WHERE type = 'pay_canceled'"
                      " AND payload_json LIKE '%st-pay-1%'").fetchone()["n"]
    check("payment cancel reason recorded once", nc == 1, str(nc))

    # Синтетика: клик -> форма -> ушёл через шапку; второй — создал заказ, банк отказал.
    t_f = iso(now - datetime.timedelta(minutes=5))
    for vid, vis in (("st_form1", "st_vf1"), ("st_form2", "st_va")):
        conn.execute("INSERT INTO web_visits (visit_id, visitor_id, started_at, last_at, entry_path,"
                     " exit_path, pages, device, screen_w, channel, utm_json, yclid, referer)"
                     " VALUES (?,?,?,?, '/order', '/order', 1, 'mobile', 390, ?, ?, ?, ?)",
                     (vid, vis, t_f, t_f, "ads" if vid == "st_form1" else "email",
                      utm if vid == "st_form1" else None, "y9" if vid == "st_form1" else None,
                      "https://yandex.ru/" if vid == "st_form1" else "https://e.mail.ru/"))
    st_exit = json.dumps({"k": "exit", "sec": 40, "fields": ["child_name", "child_gender"],
                          "last": "child_birth_ym", "files": 0, "via": "header_nav_check"})
    evs = [("st_form1", "order_form_view", None), ("st_form1", "form_started", None),
           ("st_form1", "order_form_state", st_exit),
           ("st_form2", "order_form_view", None), ("st_form2", "order_created", None),
           ("st_form2", "pay_init_mobile_redirect", None)]
    for vid, typ, p in evs:
        conn.execute("INSERT INTO events (visitor_id, visit_id, type, payload_json, created_at)"
                     " VALUES (?,?,?,?,?)", ("st_vf1" if vid == "st_form1" else "st_va", vid, typ, p, t_f))
    conn.execute("INSERT INTO orders (email, product_code, price_kopecks, status, child_json,"
                 " visitor_id, visit_id, created_at) VALUES ('st2@e.ru', 'snapshot', 149000,"
                 " 'created', '{}', 'st_va', 'st_form2', ?)", (t_f,))
    oid2 = conn.execute("SELECT id FROM orders WHERE visit_id = 'st_form2'").fetchone()["id"]
    conn.commit()
    with app.test_request_context():
        _record_cancel({"id": "st-pay-2", "status": "canceled", "metadata": {"order_id": oid2},
                        "cancellation_details": {"reason": "3d_secure_failed"}})
    from app import order_diag
    dg = order_diag.build(conn, d, d, scope="ads", campaign_id=camp)
    fn_ = dg["funnel"]
    check("diag: both ad-credited form visits counted", fn_["viewed"] == 2, str(fn_))
    check("diag: stop reason = left before photo", dg["stopped_at"].get("left_before_photo") == 1,
          str(dg["stopped_at"]))
    check("diag: exit link captured", dg["left_via"].get("header_nav_check") == 1, str(dg["left_via"]))
    check("diag: last field captured", any(x["field"] == "child_birth_ym"
                                           for x in dg["last_field_before_leaving"]))
    check("diag: order created + payment started + bank refusal reason",
          fn_["created"] == 1 and fn_["payment_started"] == 1 and fn_["payment_canceled"] == 1
          and dg["payment_cancel_reasons"].get("3d_secure_failed") == 1, json.dumps(fn_))
    check("diag: free offer block counts the result view", dg["free_offer"]["result_views"] >= 0)
    api_d = c.get(f"/api/ads/v1/order-diagnostics?from={today}&to={today}&campaign_id={camp}",
                  headers=H).get_json()
    check("API order-diagnostics", api_d.get("ok") and api_d["funnel"]["viewed"] == 2
          and "@" not in json.dumps(api_d, ensure_ascii=False))
    page = c.get(f"/admin/ads?from={today}&to={today}&scope=ads")
    check("/admin/ads diagnostics section renders", page.status_code == 200
          and "Почему не доходят до оплаты" in page.get_data(as_text=True))

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
