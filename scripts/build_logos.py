"""Build web-optimized navigation logos from data/Images/.

Run once after pulling / when a logo source changes:
    venv\\Scripts\\python.exe scripts\\build_logos.py

Sources (not web-served, gitignored data/):
    data/Images/StripLogo.png   wide wordmark+icon  -> header on desktop
    data/Images/logo.png        square icon         -> header on mobile / tight spaces

Produces (in static/img/, served at /static/img/):
    logo-strip.webp / logo-strip.png   ~84px tall (2x of 42px display)
    logo-icon.webp  / logo-icon.png    96x96 (2x of ~42-48px display)

Header (_header.html) uses <picture>: webp with png fallback, icon below 560px.
ASCII-only console output (Windows cp1252 — UseCase #3).
"""
from pathlib import Path
import sys

try:
    from PIL import Image
except ImportError:
    sys.stderr.write("Pillow not installed in this venv. Run: pip install pillow\n")
    sys.exit(1)

BASE = Path(__file__).resolve().parent.parent
SRC = BASE / "data" / "Images"
OUT = BASE / "static" / "img"

# (source, out_basename, target_height_px, target_width_px_or_None)
JOBS = [
    ("stripLogo.png", "logo-strip", 84, None),   # keep aspect by height
    ("logo.png",      "logo-icon",  96, 96),      # square
]


def kb(p: Path) -> float:
    return p.stat().st_size / 1024


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    missing = [s for s, *_ in JOBS if not (SRC / s).exists()]
    if missing:
        sys.stderr.write("Source(s) not found in %s: %s\n" % (SRC, ", ".join(missing)))
        return 1
    for src, name, h, w in JOBS:
        im = Image.open(SRC / src).convert("RGB")
        if w is None:
            w = round(im.width * h / im.height)
        im = im.resize((w, h), Image.LANCZOS)
        png = OUT / (name + ".png")
        webp = OUT / (name + ".webp")
        im.save(png, "PNG", optimize=True)
        im.save(webp, "WEBP", quality=90, method=6)
        print("  %-11s %3dx%-3d  png %5.1f KB   webp %5.1f KB" % (name, w, h, kb(png), kb(webp)))
    print("done -> %s" % OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
