"""Дожим черновиков blog_gen (data/tmp/blog_draft_<slug>.md), не прошедших линтер 3 раза.

Правит только механику: «не обязательно» -> «необязательно», одиночное «обязательно» -> «стоит»,
битые пути ссылок (/blog/primer/…, пробелы, ссылка на саму себя), отсутствие ссылки на пример —
дописывается фраза в «Что сделать сегодня», длинный title — обрезка по последнему знаку.
Затем тот же линтер, что в blog_gen; прошедшие пишутся в content/blog/, остальные остаются
черновиками с перечнем ошибок в консоли (ASCII).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from scripts.blog_gen import BLOG, PLAN, SAMPLES, autofix, lint  # noqa: E402

DRAFTS = BASE / "data" / "tmp"


def fix(slug: str, text: str) -> str:
    text = autofix(text)
    text = re.sub(r"\]\(\s*/blog/(primer/[^)]+)\)", r"](/\1)", text)
    text = re.sub(r"\]\(\s+(/[^)]*)\)", r"](\1)", text)
    text = re.sub(rf"\[([^\]]+)\]\(/blog/{re.escape(slug)}\)", r"\1", text)      # ссылка на себя
    text = re.sub(r"\bне обязательно\b", "необязательно", text, flags=re.I)
    text = re.sub(r"\bНе обязательно\b", "Необязательно", text)
    text = re.sub(r"\bобязательно\b", "стоит", text)
    text = re.sub(r"\bОбязательно\b", "Стоит", text)
    if not re.search(r"\]\(/primer/", text):
        sample = SAMPLES["6"]
        text = re.sub(r"(^## Что сделать сегодня\s*\n)",
                      r"\1\n- Посмотрите, как выглядит бережный разбор чужого рисунка — "
                      f"[пример отчёта для ребёнка 6 лет]({sample}) — и сравните со своими наблюдениями.\n",
                      text, count=1, flags=re.M)
    m = re.search(r"^title:\s*(.+)$", text, re.M)
    if m and len(m.group(1)) > 60:
        t = m.group(1)[:60]
        cut = max(t.rfind(":"), t.rfind(" — "), t.rfind(","), t.rfind(" "))
        t = t[:cut].rstrip(" :,—-") if cut > 25 else t
        text = text[:m.start(1)] + t + text[m.end(1):]
    return text


def main() -> None:
    plan = {p["slug"]: p for p in PLAN}
    for f in sorted(DRAFTS.glob("blog_draft_*.md")):
        slug = f.stem[len("blog_draft_"):]
        p = plan.get(slug)
        if not p:
            continue
        text = fix(slug, f.read_text(encoding="utf-8"))
        errs = lint(p, text)
        if errs:
            print(f"STILL FAILING {slug}:")
            for e in errs:
                print("   - " + e.encode("ascii", "replace").decode())
            f.write_text(text, encoding="utf-8")       # сохраняем поправленный черновик
        else:
            (BLOG / f"{slug}.md").write_text(text.rstrip() + "\n", encoding="utf-8", newline="\n")
            f.unlink()
            print(f"FIXED -> content/blog/{slug}.md")


if __name__ == "__main__":
    main()
