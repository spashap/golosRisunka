"""Блог-скелет (spec §4.3: архитектура с первого дня, §11.1: статьи = md-файлы).

Статья = content/blog/<slug>.md с frontmatter между '---':
  title: ...
  description: ...
  date: 2026-06-20
Добавить статью = положить файл. Без админки.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass
from pathlib import Path

import markdown as md

from config import settings

BLOG_DIR = settings.BASE_DIR / "content" / "blog"


@dataclass
class Post:
    slug: str
    title: str
    description: str
    date: datetime.date
    html: str


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
    try:
        date = datetime.date.fromisoformat(meta.get("date", ""))
    except ValueError:
        date = datetime.date.fromtimestamp(path.stat().st_mtime)
    return Post(
        slug=path.stem,
        title=meta.get("title", path.stem),
        description=meta.get("description", ""),
        date=date,
        html=md.markdown(body, extensions=["extra"]),
    )


def get_posts() -> list[Post]:
    posts = [p for f in sorted(BLOG_DIR.glob("*.md")) if (p := _parse(f))]
    return sorted(posts, key=lambda p: p.date, reverse=True)


def get_post(slug: str) -> Post | None:
    f = BLOG_DIR / f"{slug}.md"
    return _parse(f) if f.exists() else None
