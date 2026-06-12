"""End-to-end CLI отчёта: изображения + контекст → Gemini → JSON → HTML → PDF.

Использование:
  один рисунок:   generate_report.py IMG --context FILE.txt [-o OUTDIR]
  2–3 рисунка:    generate_report.py IMG1 IMG2 [IMG3] --context F1.txt F2.txt [F3.txt]
                  (по одному файлу контекста на рисунок, в том же порядке;
                   один файл на всех — тоже допустимо)
  общие данные:   [--common COMMON.txt] — данные о ребёнке отдельно от историй рисунков

Контекст — свободный текст родителя (txt, UTF-8). Выход: report_raw.json,
report.json, report.html, report.pdf в OUTDIR (по умолчанию data/test_reports/<имя-картинки>/).
"""
import argparse
import base64
import datetime
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from pipeline.gemini import ReportGenerationError, generate_report
from pipeline.render import render_report_files, ru_date
from pipeline.schema import InsufficientReport


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("images", nargs="+", type=Path)
    ap.add_argument("--context", required=True, nargs="+", type=Path,
                    help="один файл на рисунок (в порядке изображений) или один на все")
    ap.add_argument("--common", type=Path, default=None,
                    help="общие данные о ребёнке (опционально)")
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    if len(args.context) not in (1, len(args.images)):
        ap.error(f"контекстов {len(args.context)}, изображений {len(args.images)} — "
                 f"нужен 1 файл или по одному на рисунок")

    out_dir = args.out or (BASE_DIR / "data" / "test_reports" / args.images[0].stem)
    out_dir.mkdir(parents=True, exist_ok=True)
    ctx_texts = [c.read_text(encoding="utf-8") for c in args.context]
    if len(ctx_texts) == 1 and len(args.images) > 1:
        contexts: list[str] | str = ctx_texts[0]          # один контекст на все
    else:
        contexts = ctx_texts
    common = args.common.read_text(encoding="utf-8") if args.common else ""

    print(f"-> Gemini ({len(args.images)} img), out: {out_dir}")
    try:
        result = generate_report(args.images, contexts, common_context=common,
                                 raw_dump_dir=out_dir / "raw")
    except ReportGenerationError as e:
        print("FAILED:", e)
        for line in e.attempts_log:
            print("  ", line.encode("ascii", "replace").decode())
        return 1

    (out_dir / "report_raw.json").write_text(result.raw_json_text, encoding="utf-8")
    print(f"attempts: {result.attempts_used} | prompt v{result.prompt_version} | {result.model}"
          f" | repairs: {result.repair_rounds} | lint hits left: {result.lint_hits_left}")

    if isinstance(result.report, InsufficientReport):
        (out_dir / "insufficient.json").write_text(
            result.report.model_dump_json(indent=2), encoding="utf-8")
        print("INSUFFICIENT INPUT:", result.report.insufficient_reason.encode("ascii", "replace").decode())
        return 2

    (out_dir / "report.json").write_text(
        json.dumps(result.report.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

    drawings = [
        {"src": "data:image/jpeg;base64," + base64.b64encode(j).decode("ascii"),
         "caption": f"Рисунок {i + 1}" if len(result.image_jpegs) > 1 else result.report.child.name}
        for i, j in enumerate(result.image_jpegs)
    ]
    html_path, pdf_path = render_report_files(
        result.report, drawings, generated_date=ru_date(datetime.date.today()),
        out_dir=out_dir,
    )
    print(f"OK html: {html_path}")
    print(f"OK pdf:  {pdf_path} ({pdf_path.stat().st_size // 1024} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
