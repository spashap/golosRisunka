"""Блог (spec §4.3, §11.1: статьи = md-файлы в content/blog/<slug>.md).

Frontmatter между '---':
  title, description, date          — как раньше
  updated: 2026-09-02               — дата обновления (dateModified + «Обновлено»)
  category: worry|age|reading|tests|activities|product  — рубрика для хаба
  related: slug1,slug2,slug3        — карточки «Читайте также» (иначе — та же рубрика)
  seo_title: ...                    — необязательный короткий title-тег

Из тела извлекаются: «Частые вопросы» (**Вопрос?** + абзац) -> FAQPage JSON-LD; после второго
H2 вставляется маркер призыва к бесплатному разбору (рендерит шаблон). Добавить статью =
положить файл. Без админки. Тексты генерирует/расширяет scripts/blog_gen.py.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path

import markdown as md

from config import settings

BLOG_DIR = settings.BASE_DIR / "content" / "blog"

CATEGORIES: dict[str, str] = {
    "worry": "Тревоги родителей",
    "age": "По возрастам",
    "reading": "Как читать рисунок",
    "tests": "Тесты и расшифровки",
    "activities": "Занятия и игры",
    "product": "О сервисе",
}
CATEGORY_ORDER = ["worry", "age", "reading", "tests", "activities", "product"]

MID_CTA_MARKER = "<!--MID-CTA-->"


@dataclass
class Post:
    slug: str
    title: str
    description: str
    date: datetime.date
    html: str
    updated: datetime.date | None = None
    category: str = "reading"
    related: list[str] = field(default_factory=list)
    seo_title: str = ""
    faq: list[tuple[str, str]] = field(default_factory=list)
    words: int = 0

    @property
    def category_label(self) -> str:
        return CATEGORIES.get(self.category, CATEGORIES["reading"])

    @property
    def modified(self) -> datetime.date:
        return self.updated or self.date


_FAQ_RE = re.compile(r"^\*\*(.+?\?)\*\*\s*\n+([^\n#*][^\n]*(?:\n(?![\n#*])[^\n]*)*)", re.M)


def _extract_faq(body: str) -> list[tuple[str, str]]:
    """Пары вопрос/ответ из раздела «Частые вопросы» (для FAQPage JSON-LD)."""
    m = re.search(r"^## Частые вопросы\s*$(.*?)(?=^## |\Z)", body, re.M | re.S)
    if not m:
        return []
    out = []
    # Модель пишет и «**Вопрос: …?**» / «**Ответ:** …», и просто «**…?**» + абзац — сводим к одному.
    section = re.sub(r"\*\*Вопрос:\s*", "**", m.group(1))
    section = re.sub(r"^\*\*Ответ:\*\*\s*", "", section, flags=re.M)
    for q, a in _FAQ_RE.findall(section):
        a = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", a)      # ссылки -> текст
        a = re.sub(r"[*_`]", "", a).strip()
        if q and a:
            out.append((q.strip(), a))
    return out[:6]


def _inject_mid_cta(body: str) -> str:
    """Маркер после второго H2-раздела: тёплый читатель уже втянулся, но не устал."""
    parts = re.split(r"(?m)^(?=## )", body)
    if len(parts) < 4:              # вступление + минимум 3 раздела
        return body
    parts[2] = parts[2].rstrip() + "\n\n" + MID_CTA_MARKER + "\n\n"
    return "".join(parts)


def _date(v: str | None) -> datetime.date | None:
    try:
        return datetime.date.fromisoformat((v or "").strip())
    except ValueError:
        return None


def _parse(path: Path) -> Post | None:
    text = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = text
    if text.startswith("---"):
        try:
            _, fm, body = text.split("---", 2)
            for line in fm.strip().splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip()] = v.strip()
        except ValueError:
            pass
    date = _date(meta.get("date")) or datetime.date.fromtimestamp(path.stat().st_mtime)
    related = [s.strip() for s in meta.get("related", "").split(",") if s.strip()]
    body_marked = _inject_mid_cta(body)
    return Post(
        slug=path.stem,
        title=meta.get("title", path.stem),
        description=meta.get("description", ""),
        date=date,
        updated=_date(meta.get("updated")),
        category=meta.get("category", "reading") if meta.get("category") in CATEGORIES else "reading",
        related=related,
        seo_title=meta.get("seo_title", ""),
        faq=_extract_faq(body),
        words=len(re.findall(r"\w+", body)),
        html=md.markdown(body_marked, extensions=["extra"]),
    )


def get_posts() -> list[Post]:
    posts = [p for f in sorted(BLOG_DIR.glob("*.md")) if (p := _parse(f))]
    return sorted(posts, key=lambda p: p.modified, reverse=True)


def get_post(slug: str) -> Post | None:
    f = BLOG_DIR / f"{slug}.md"
    return _parse(f) if f.exists() else None


def related_posts(post: Post, all_posts: list[Post] | None = None, n: int = 3) -> list[Post]:
    """Явные related из frontmatter, добор — свежие из той же рубрики."""
    posts = all_posts or get_posts()
    by = {p.slug: p for p in posts}
    out = [by[s] for s in post.related if s in by and s != post.slug]
    for p in posts:
        if len(out) >= n:
            break
        if p.slug != post.slug and p not in out and p.category == post.category:
            out.append(p)
    return out[:n]


def by_category(posts: list[Post]) -> list[tuple[str, str, list[Post]]]:
    groups: dict[str, list[Post]] = {}
    for p in posts:
        groups.setdefault(p.category, []).append(p)
    return [(k, CATEGORIES[k], groups[k]) for k in CATEGORY_ORDER if k in groups]
