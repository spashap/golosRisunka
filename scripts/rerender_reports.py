"""Перерендер hosted-HTML (и PDF при --pdf) сэмплов из сохранённых report.json.

Без вызова Gemini — только шаблон. Использовать после правок report.html/css.
Run: venv/Scripts/python.exe scripts/rerender_reports.py [--pdf]
"""
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from pipeline.images import prepare_image
from pipeline.render import render_html, render_pdf
from pipeline.schema import validate_report

# каталог отчёта -> (файлы рисунков, подписи)
REPORTS = {
    "data/test_reports/Draw-3_5yr-v1-final": (
        ["projectSpec/testDrawings/Draw-3_5yr-v1.png"], None),
    "data/test_reports/Draw-6yr-v1-final": (
        ["projectSpec/testDrawings/Draw-6yr-v1.png"], None),
    "data/test_reports/Draw-8yr-v1-final": (
        ["projectSpec/testDrawings/Draw-8yr-v1.png"], None),
    "data/test_reports/set1-consolidated": (
        ["projectSpec/testDrawings/set1-img1.png", "projectSpec/testDrawings/set1-img2.png"],
        ["Рисунок 1 — «Стич»", "Рисунок 2 — «Лабубу»"]),
}
GENERATED = "17 июня 2026"


def data_uri(jpeg: bytes) -> str:
    import base64
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")


def main() -> None:
    make_pdf = "--pdf" in sys.argv
    for rdir_s, (imgs, captions) in REPORTS.items():
        rdir = BASE_DIR / rdir_s
        report = validate_report(json.loads((rdir / "report.json").read_text(encoding="utf-8")))
        jpegs = [prepare_image(BASE_DIR / p) for p in imgs]
        caps = captions or [report.child.name] * len(jpegs)
        drawings = [{"src": data_uri(j), "caption": c} for j, c in zip(jpegs, caps)]

        html = render_html(report, drawings, GENERATED,
                           static_prefix="/static", site_header=True)
        (rdir / "report.html").write_text(html, encoding="utf-8")
        if make_pdf:
            html_print = render_html(report, drawings, GENERATED, static_prefix="static")
            render_pdf(html_print, rdir / "report.pdf")
        print(f"{rdir.name}: html{' + pdf' if make_pdf else ''} OK")


if __name__ == "__main__":
    main()
