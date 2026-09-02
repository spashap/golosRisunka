"""Проверка блога после генерации: длины, ссылки, рубрики, «сироты», противоречия продукту.

  venv\\Scripts\\python.exe scripts\\blog_check.py        # отчёт в data/tmp/blog_check.txt (+ASCII в консоль)
Ненулевой код выхода при критичных проблемах (битые ссылки, отсутствие обязательных полей).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from app.blog import BLOG_DIR, CATEGORIES, get_posts  # noqa: E402

LINK_RE = re.compile(r"\]\(([^)]+)\)")
BAD = ("нельзя понять характер", "не читаются эмоции", "не показывает характер",
       "креативность и воображение, цвет и свет")


def main() -> int:
    posts = get_posts()
    slugs = {p.slug for p in posts}
    out, crit = [], 0
    inbound: dict[str, int] = {s: 0 for s in slugs}
    for p in posts:
        text = (BLOG_DIR / f"{p.slug}.md").read_text(encoding="utf-8")
        body = text.split("---", 2)[-1]
        links = LINK_RE.findall(body)
        broken = [l for l in links if l.startswith("/blog/") and l[6:].split("#")[0] not in slugs]
        ext = [l for l in links if l.startswith("http")]
        for l in links:
            if l.startswith("/blog/") and l[6:] in inbound and l[6:] != p.slug:
                inbound[l[6:]] += 1
        for r in p.related:
            if r in inbound and r != p.slug:
                inbound[r] += 1
        problems = []
        if broken:
            problems.append(f"битые ссылки: {broken}"); crit += 1
        if ext:
            problems.append(f"внешние ссылки: {ext}")
        if not 25 <= len(p.title) <= 62:
            problems.append(f"title {len(p.title)} символов")
        if not 100 <= len(p.description) <= 160:
            problems.append(f"description {len(p.description)} символов")
        if p.words < 900:
            problems.append(f"коротко: {p.words} слов")
        if "/free/#name" not in links:
            problems.append("нет ссылки на бесплатный разбор")
        if not p.faq:
            problems.append("FAQ не распознан")
        if not p.updated:
            problems.append("нет updated")
        low = body.lower()
        for b in BAD:
            if b in low:
                problems.append(f"противоречие продукту: «{b}»"); crit += 1
        missing = [r for r in p.related if r not in slugs]
        if missing:
            problems.append(f"related не существует: {missing}"); crit += 1
        out.append(f"{p.slug:55s} {p.category:10s} {p.words:5d}w  t={len(p.title):2d} d={len(p.description):3d}"
                   f" links={len(links):2d} faq={len(p.faq)}  " + ("; ".join(problems) if problems else "OK"))
    out.append("")
    orphans = [s for s, n in inbound.items() if n == 0]
    out.append(f"posts: {len(posts)}; categories: " + ", ".join(f"{CATEGORIES[k]} {sum(1 for p in posts if p.category == k)}" for k in CATEGORIES))
    out.append(f"orphans (no inbound from other posts): {orphans or 'none'}")
    out.append(f"critical: {crit}")
    rep = BASE / "data" / "tmp" / "blog_check.txt"
    rep.parent.mkdir(parents=True, exist_ok=True)
    rep.write_text("\n".join(out), encoding="utf-8")
    for line in out:
        print(line.encode("ascii", "replace").decode())
    return 1 if crit else 0


if __name__ == "__main__":
    sys.exit(main())
