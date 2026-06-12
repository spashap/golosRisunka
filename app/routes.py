"""Все роуты MVP. ЧПУ-урлы, серверный HTML (spec §4.3)."""
from __future__ import annotations

import datetime
import json
from functools import lru_cache

from flask import (Blueprint, Response, abort, g, redirect, render_template,
                   request, url_for)

from app.blog import get_post, get_posts
from app.db import get_db
from app.orders import FormError, validate_and_create_order
from app.payments import create_payment, mark_paid
from app.samples import get_sample_by_token, get_samples
from app.track import track_event
from config import settings
from config.form_fields import CHILD_FIELDS, DRAWING_FIELDS, EMAIL_FIELD

bp = Blueprint("main", __name__)


@lru_cache(maxsize=1)
def _inline_css() -> str:
    """Критический CSS лендинга: токены + компоненты одним инлайном (spec §4.2)."""
    css_dir = settings.BASE_DIR / "static" / "css"
    return (css_dir / "tokens.css").read_text(encoding="utf-8") + \
           (css_dir / "components.css").read_text(encoding="utf-8")


def _schema_jsonld() -> str:
    base = f"https://{settings.SITE_DOMAIN}"
    product = {
        "@context": "https://schema.org",
        "@type": "Product",
        "name": "Отчёт о развитии ребёнка по детскому рисунку",
        "description": "PDF-отчёт: 8 направлений развития, оценки с объяснениями, "
                       "занятия для родителей. Образовательное наблюдение.",
        "brand": {"@type": "Brand", "name": settings.SITE_NAME},
        "offers": [
            {"@type": "Offer", "name": p["title"],
             "price": p["price_rub"], "priceCurrency": "RUB",
             "url": f"{base}/order?product={code}", "availability": "https://schema.org/InStock"}
            for code, p in settings.get_products().items() if p["enabled"]
        ],
    }
    faq = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q,
             "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in FAQ_ITEMS
        ],
    }
    return json.dumps([product, faq], ensure_ascii=False)


@bp.get("/")
def landing():
    products = settings.get_products()
    track_event("landing_view")
    return render_template(
        "landing.html",
        products=products,
        samples=get_samples(),
        faq=FAQ_ITEMS,
        min_price=min(p["price_rub"] for p in products.values() if p["enabled"]),
        inline_css=_inline_css(),
        schema_jsonld=_schema_jsonld(),
    )


@bp.get("/r/<token>")
def hosted_report(token: str):
    # Образцы лендинга; отчёты заказов (Phase 6) подключатся сюда же по public_token.
    sample = get_sample_by_token(token)
    if sample and sample.html_path.exists():
        track_event("sample_view", {"token": token})
        return Response(sample.html_path.read_text(encoding="utf-8"), mimetype="text/html")
    row = get_db().execute(
        "SELECT html_path FROM reports WHERE public_token = ?", (token,)).fetchone()
    if row and row["html_path"]:
        path = settings.BASE_DIR / row["html_path"]
        if path.exists():
            return Response(path.read_text(encoding="utf-8"), mimetype="text/html")
    abort(404)


@bp.get("/login")
def login_stub():
    # Phase 7: вход по email-коду. Пока — заглушка для пункта «Войти» в шапке.
    return render_template("login_stub.html")


@bp.get("/cabinet")
def cabinet_stub():
    # Phase 7: настоящий кабинет. Пока — заглушка (success-страница ссылается сюда).
    return render_template("login_stub.html")


# --- Заказ (Phase 5) ---

def _render_order_form(values: dict, errors: dict, status: int = 200):
    products = settings.get_products()
    code = request.args.get("product", values.get("product", "snapshot"))
    if code not in products or not products[code]["enabled"]:
        code = "snapshot"
    return render_template(
        "order.html",
        product_code=code,
        product=products[code],
        child_fields=CHILD_FIELDS,
        drawing_fields=DRAWING_FIELDS,
        email_field=EMAIL_FIELD,
        values=values,
        errors=errors,
        current_year=datetime.date.today().year,
    ), status


@bp.get("/order")
def order_form():
    track_event("order_form_view", {"product": request.args.get("product", "snapshot")})
    return _render_order_form(values={}, errors={})


@bp.post("/order")
def order_submit():
    files = [request.files[f"d{i}_file"] for i in (1, 2, 3)
             if request.files.get(f"d{i}_file") and request.files[f"d{i}_file"].filename]
    try:
        order_id = validate_and_create_order(
            request.form, files,
            visitor_id=getattr(g, "visitor_id", None),
            utm=getattr(g, "utm", None),
        )
    except FormError as e:
        track_event("order_form_errors", {"fields": list(e.errors)})
        # to_dict(), не dict(): werkzeug MultiDict при dict() даёт списки значений
        return _render_order_form(values=request.form.to_dict(), errors=e.errors, status=400)
    track_event("order_created", {"order_id": order_id, "drawings": len(files)})
    db = get_db()
    order = db.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    return redirect(create_payment(order_id, order["price_kopecks"]))


@bp.get("/pay/stub/<int:order_id>")
def stub_checkout(order_id: int):
    order = get_db().execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        abort(404)
    track_event("checkout_view", {"order_id": order_id})
    product = settings.get_products()[order["product_code"]]
    return render_template("checkout_stub.html", order=order, product=product)


@bp.post("/pay/stub/<int:order_id>/confirm")
def stub_confirm(order_id: int):
    """Stub-аналог webhook ЮKassa: единая точка mark_paid (идемпотентно)."""
    result = mark_paid(order_id)
    if result is None:
        abort(404)
    if not result["already_paid"]:   # дубль webhook не шумит в аналитике
        track_event("order_paid", {"order_id": order_id}, customer_id=result["customer_id"])
    resp = redirect(url_for("main.order_success", order_id=order_id))
    if result["session_token"]:
        resp.set_cookie("gr_s", result["session_token"],
                        max_age=settings.SESSION_DAYS * 24 * 3600,
                        httponly=True, samesite="Lax")
    return resp


@bp.get("/order/success/<int:order_id>")
def order_success(order_id: int):
    order = get_db().execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
    if order is None:
        abort(404)
    return render_template("order_success.html", email=order["email"])


# --- Блог (скелет, spec §4.3) ---

@bp.get("/blog")
def blog_index():
    return render_template("blog_index.html", posts=get_posts())


@bp.get("/blog/<slug>")
def blog_post(slug: str):
    post = get_post(slug)
    if post is None:
        abort(404)
    return render_template("blog_post.html", post=post)


# --- Юридические страницы (тексты-плейсхолдеры до Phase 9) ---

LEGAL_PAGES = {
    "privacy": ("Политика конфиденциальности",
                "Текст политики конфиденциальности будет размещён до запуска. "
                "Мы храним рисунки и данные только для подготовки отчёта; "
                "рисунки вашего ребёнка не публикуются и не передаются третьим лицам."),
    "terms": ("Пользовательское соглашение",
              "Текст оферты будет размещён до запуска."),
    "contacts": ("Контакты",
                 "Поддержка: почта будет указана до запуска. Мы отвечаем в течение рабочего дня."),
}


@bp.get("/privacy")
@bp.get("/terms")
@bp.get("/contacts")
def legal():
    from flask import request
    key = request.path.strip("/")
    title, text = LEGAL_PAGES[key]
    return render_template("legal.html", title=title, text=text)


# --- SEO-служебное ---

@bp.get("/robots.txt")
def robots():
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /r/",        # отчёты непубличные
        "Disallow: /order",
        f"Sitemap: https://{settings.SITE_DOMAIN}/sitemap.xml",
    ]
    return Response("\n".join(lines), mimetype="text/plain")


@bp.get("/sitemap.xml")
def sitemap():
    base = f"https://{settings.SITE_DOMAIN}"
    today = datetime.date.today().isoformat()
    urls = [("/", "1.0"), ("/blog", "0.6"), ("/privacy", "0.2"),
            ("/terms", "0.2"), ("/contacts", "0.3")]
    urls += [(f"/blog/{p.slug}", "0.7") for p in get_posts()]
    items = "\n".join(
        f"<url><loc>{base}{path}</loc><lastmod>{today}</lastmod>"
        f"<priority>{prio}</priority></url>"
        for path, prio in urls
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"{items}\n</urlset>")
    return Response(xml, mimetype="application/xml")


# --- FAQ (spec §4.1.7) — текст конфигурируем здесь, рендер в шаблоне ---

FAQ_ITEMS = [
    ("Какой возраст ребёнка подходит?",
     "От 3 до 12 лет. Отчёт учитывает возрастной этап развития рисунка: "
     "то, что типично для трёх лет, оценивается иначе, чем для девяти."),
    ("Как быстро придёт отчёт?",
     "Обычно в течение часа после оплаты. PDF придёт на почту, "
     "и он же будет доступен в личном кабинете."),
    ("Что нужно прислать?",
     "Фото 1–3 рисунков, которые ребёнок уже нарисовал, и короткие ответы о "
     "контексте: возраст, чем рисовал, что было задано. Ничего специально "
     "рисовать не нужно."),
    ("Это психологическая диагностика?",
     "Нет. Это образовательное наблюдение за навыками, которые видны в рисунке: "
     "композиция, контроль линий, вариативность решений. Мы принципиально не "
     "делаем выводов об эмоциях или психологическом состоянии ребёнка."),
    ("А если отчёт мне не понравится?",
     "Напишите нам в течение 7 дней — вернём деньги без лишних вопросов."),
    ("Кто увидит рисунки моего ребёнка?",
     "Только вы. Рисунки не публикуются, не используются для рекламы и "
     "не передаются третьим лицам."),
]
