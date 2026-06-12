"""Рендер отчёта: валидированный JSON → HTML (hosted) + PDF (WeasyPrint).

Чистые функции без Gemini — переиспользуются воркером, CLI и тестами (spec §7.1).
HTML рендерится дважды с разным префиксом static:
  - hosted-вариант («/static») — отдаётся браузеру по /r/{token};
  - print-вариант («static» относительно BASE_DIR) — скармливается WeasyPrint.
"""
from __future__ import annotations

import base64
import datetime
import mimetypes
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from config import settings
from pipeline.schema import Report

_env = Environment(loader=FileSystemLoader(settings.BASE_DIR / "templates"))

RU_MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
             "июля", "августа", "сентября", "октября", "ноября", "декабря"]


def ru_date(d: datetime.date) -> str:
    """«12 июня 2026» — дата генерации в шапке отчёта."""
    return f"{d.day} {RU_MONTHS[d.month - 1]} {d.year}"


def drawing_to_data_uri(path: Path) -> str:
    """Рисунок → data URI: одинаково работает в браузере и WeasyPrint,
    hosted-отчёту не нужен отдельный защищённый роут для картинок."""
    mime = mimetypes.guess_type(str(path))[0] or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def render_html(report: Report, drawings: list[dict], generated_date: str,
                static_prefix: str = "/static", site_header: bool = False) -> str:
    """drawings: [{"src": data-URI (см. drawing_to_data_uri), "caption": подпись}, ...]
    site_header=True — шапка сайта (только hosted-вариант, в PDF её нет)."""
    return _env.get_template("report.html").render(
        report=report,
        drawings=drawings,
        generated_date=generated_date,
        static=static_prefix,
        site_header=site_header,
    )


def render_pdf(html_for_print: str, out_path: Path) -> None:
    # импорт внутри: WeasyPrint тяжёлый, веб-процессу он не нужен
    from weasyprint import HTML

    out_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html_for_print, base_url=str(settings.BASE_DIR)).write_pdf(out_path)


def render_report_files(report: Report, drawings: list[dict], generated_date: str,
                        out_dir: Path, basename: str = "report") -> tuple[Path, Path]:
    """Сохраняет обе версии. Возвращает (html_path, pdf_path)."""
    out_dir.mkdir(parents=True, exist_ok=True)

    html_hosted = render_html(report, drawings, generated_date,
                              static_prefix="/static", site_header=True)
    html_path = out_dir / f"{basename}.html"
    html_path.write_text(html_hosted, encoding="utf-8")

    html_print = render_html(report, drawings, generated_date, static_prefix="static")
    pdf_path = out_dir / f"{basename}.pdf"
    render_pdf(html_print, pdf_path)

    return html_path, pdf_path
