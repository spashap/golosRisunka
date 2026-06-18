"""Build web-optimized hero images from data/Images/Hero.png.

Run once after pulling / when the source hero changes:
    venv\\Scripts\\python.exe scripts\\build_hero_image.py

Produces (in static/img/, served at /static/img/):
    hero.webp / hero.jpg          desktop (~1600px wide)
    hero-800.webp / hero-800.jpg  mobile  (~960px wide)

CSS (.hero in components.css) uses image-set(webp, jpg) by absolute /static path,
so modern browsers load the light .webp; .jpg is the fallback.

Tuned for light loading time. ASCII-only console output (Windows cp1252 — UseCase #3).
"""
from pathlib import Path
import sys

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("Pillow not installed in this venv. Run: pip install pillow\n")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "Images" / "Hero.png"
OUT = BASE / "static" / "img"

# (width, basename, jpg_quality, webp_quality)
VARIANTS = [
    (1600, "hero",     76, 70),
    (960,  "hero-800", 72, 66),
]


def kb(p: Path) -> int:
    return p.stat().st_size // 1024


def main() -> int:
    if not SRC.exists():
        sys.stderr.write("Source not found: %s\n" % SRC)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)
    src = Image.open(SRC).convert("RGB")
    print("source:", src.size[0], "x", src.size[1])
    for w, name, jq, wq in VARIANTS:
        h = round(src.height * w / src.width)
        im = src.resize((w, h), Image.LANCZOS)
        jp = OUT / (name + ".jpg")
        wp = OUT / (name + ".webp")
        im.save(jp, "JPEG", quality=jq, optimize=True, progressive=True)
        im.save(wp, "WEBP", quality=wq, method=6)
        print("  %-13s %4dx%-4d  jpg %3d KB   webp %3d KB" % (name, w, h, kb(jp), kb(wp)))
    print("done -> %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
