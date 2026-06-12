"""Milestone M0: prove WeasyPrint renders Cyrillic with our self-hosted fonts.

Run: venv/Scripts/python.exe scripts/hello_pdf.py
Output: data/hello.pdf — open it and check all three font families.
"""
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from weasyprint import HTML

HTML_DOC = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<link rel="stylesheet" href="static/css/fonts.css">
<style>
  @page { size: A4; margin: 2cm; }
  body { font-family: Inter, sans-serif; color: #1B2533; background: #F7F1E3; }
  h1 { font-family: Rubik, sans-serif; font-weight: 900; font-size: 32pt; letter-spacing: -1px; }
  h2 { font-family: Rubik, sans-serif; font-weight: 800; font-size: 18pt; color: #2456A6; }
  .hand { font-family: Caveat, cursive; font-weight: 700; font-size: 20pt; color: #C7762B; }
  .hand2 { font-family: Caveat, cursive; font-weight: 600; font-size: 16pt; }
  p { font-size: 12pt; line-height: 1.5; }
  .w500 { font-weight: 500; }
  .w600 { font-weight: 600; }
</style>
</head>
<body>
  <h1>У каждого рисунка есть голос. Услышьте его.</h1>
  <h2>Rubik 800 — Ёё Жж Щщ Ъъ Ыы Ээ Юю Яя</h2>
  <p>Inter 400: Съешь же ещё этих мягких французских булок, да выпей чаю. 1234567890 ₽</p>
  <p class="w500">Inter 500: Профессиональный отчёт о развитии ребёнка по его рисункам.</p>
  <p class="w600">Inter 600: Восемь направлений, оценки с объяснениями и занятия для родителей.</p>
  <div class="hand">Caveat 700: «Наш дом», Миша, 5 лет — креативность 8/10</div>
  <div class="hand2">Caveat 600: PDF за час · ничего специально рисовать не нужно</div>
</body>
</html>"""


def main() -> None:
    out = BASE_DIR / "data" / "hello.pdf"
    HTML(string=HTML_DOC, base_url=str(BASE_DIR)).write_pdf(out)
    print(f"OK: {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
