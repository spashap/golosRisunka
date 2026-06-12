"""Статический экспорт сайта для временного хостинга (Vercel) до русского VPS.

Рендерит все публичные страницы Flask-приложения в dist/ + копирует static/.
В каждый HTML вставляется <meta noindex> и robots.txt запрещает индексацию:
временный домен НЕ должен индексироваться — каноничный будет golosrisunka.ru.

Run: venv/Scripts/python.exe scripts/export_static.py
Deploy: запушить dist/ в git, на Vercel: Framework=Other, Output Directory=dist.
"""
import shutil
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from app import create_app
from app.samples import get_samples

DIST = BASE_DIR / "dist"
NOINDEX = '<meta name="robots" content="noindex, nofollow">'

# роуты → файлы (cleanUrls на Vercel уберёт .html из адресов)
PAGES = {
    "/": "index.html",
    "/order": "order.html",
    "/blog": "blog.html",
    "/privacy": "privacy.html",
    "/terms": "terms.html",
    "/contacts": "contacts.html",
}


def main() -> None:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir()

    app = create_app()
    client = app.test_client()

    pages = dict(PAGES)
    for s in get_samples():
        pages[f"/r/{s.token}"] = f"r/{s.token}.html"

    for route, fname in pages.items():
        resp = client.get(route)
        assert resp.status_code == 200, f"{route} -> {resp.status_code}"
        html = resp.get_data(as_text=True)
        if "<head>" in html and "noindex" not in html:
            html = html.replace("<head>", f"<head>\n{NOINDEX}", 1)
        out = DIST / fname
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        print(f"{fname:28s} {len(html) // 1024} KB")

    # статика (css/fonts/img)
    shutil.copytree(BASE_DIR / "static", DIST / "static")

    # robots: временный хост закрыт от индексации целиком
    (DIST / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    n_files = sum(1 for _ in DIST.rglob("*") if _.is_file())
    print(f"OK: dist/ ({n_files} files)")


if __name__ == "__main__":
    main()
