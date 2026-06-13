"""Generate the default OpenGraph/social image (1200x630) -> static/img/og-default.png.

Brand-consistent: warm paper bg, ink title in Rubik, blue accent, educational tagline.
Uses the project's self-hosted fonts. Re-run after brand/copy changes.
ASCII-only console output (Windows cp1252 rule #3).
"""
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "static" / "fonts"
OUT = ROOT / "static" / "img" / "og-default.png"

W, H = 1200, 630
BG = (247, 241, 227)        # --bg warm paper
INK = (27, 37, 51)          # --ink
ACCENT = (36, 86, 166)      # --accent blue
ACCENT2 = (199, 118, 43)    # --accent2 orange
MUTED = (90, 98, 115)       # --muted


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size)


def center(draw, y, text, fnt, fill):
    bbox = draw.textbbox((0, 0), text, font=fnt)
    w = bbox[2] - bbox[0]
    draw.text(((W - w) / 2, y), text, font=fnt, fill=fill)
    return bbox[3] - bbox[1]


def main():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # top accent bar
    d.rectangle([0, 0, W, 12], fill=ACCENT)
    # brand mark
    center(d, 92, "Голос рисунка", font("rubik-900.ttf", 64), ACCENT)
    # main title (two lines)
    center(d, 200, "Анализ детского рисунка", font("rubik-900.ttf", 78), INK)
    center(d, 292, "по фото", font("rubik-900.ttf", 78), INK)
    # accent underline
    d.rectangle([(W - 230) / 2, 392, (W + 230) / 2, 400], fill=ACCENT2)
    # tagline
    center(d, 430, "Образовательный PDF-отчёт о развитии ребёнка", font("inter-600.ttf", 38), INK)
    center(d, 492, "для родителей · без диагноза · golosrisunka.ru", font("inter-400.ttf", 30), MUTED)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, format="PNG", optimize=True)
    print("OK wrote %s (%dx%d, %d bytes)" % (OUT, W, H, OUT.stat().st_size))
    return 0


if __name__ == "__main__":
    sys.exit(main())
