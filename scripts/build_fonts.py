"""Build self-hosted webfonts: download official variable TTFs from google/fonts,
pin the weights we need, subset to latin+cyrillic+₽, emit woff2 (web) + ttf (WeasyPrint).

Why not google-webfonts-helper: its cyrillic_latin subsets are missing U+20BD (₽),
which a Russian pricing site cannot live without (UseCases.md #2).

Run: venv/Scripts/python.exe scripts/build_fonts.py
"""
import io
import urllib.request
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont

FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "fonts"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) golosrisunka-setup"}

# family -> (github path to variable ttf, weights needed)
SOURCES = {
    "rubik": ("ofl/rubik/Rubik%5Bwght%5D.ttf", [800, 900]),
    "inter": ("ofl/inter/Inter%5Bopsz,wght%5D.ttf", [400, 500, 600]),
    "caveat": ("ofl/caveat/Caveat%5Bwght%5D.ttf", [600, 700]),
}
RAW = "https://raw.githubusercontent.com/google/fonts/main/{path}"

# latin-1 (incl. · « »), cyrillic, general punctuation (— … “”), currency (₽), №, ™,
# arrows ←↑→↓ (LLM-текст любит →), галочки ✓✔ (UseCases.md #6)
UNICODES = ("U+0000-00FF,U+0131,U+0400-04FF,U+2010-205F,U+20A0-20BF,"
            "U+2116,U+2122,U+2190-2193,U+2713-2714")


def fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req) as resp:
        return resp.read()


def build(family: str, raw: bytes, weight: int) -> None:
    font = TTFont(io.BytesIO(raw))
    axes = {"wght": weight}
    if "opsz" in {a.axisTag for a in font["fvar"].axes}:
        axes["opsz"] = 14  # Inter text optical size
    instantiateVariableFont(font, axes, inplace=True)
    # инстансер оставляет STAT при удалённом fvar — Chrome OTS такое ОТВЕРГАЕТ
    # (тихий fallback на системный serif в браузере; UseCases.md #10)
    for table in ("STAT", "avar", "fvar", "gvar", "cvar", "MVAR", "HVAR", "VVAR"):
        if table in font:
            del font[table]

    options = subset.Options()
    options.flavor = None
    options.layout_features = ["*"]  # keep kerning etc.
    subsetter = subset.Subsetter(options)
    subsetter.populate(unicodes=subset.parse_unicodes(UNICODES))
    subsetter.subset(font)

    for flavor, ext in ((None, "ttf"), ("woff2", "woff2")):
        font.flavor = flavor
        dest = FONTS_DIR / f"{family}-{weight}.{ext}"
        font.save(str(dest))
        print(f"{dest.name:22s} {dest.stat().st_size // 1024} KB")


def main() -> None:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    for family, (path, weights) in SOURCES.items():
        raw = fetch(RAW.format(path=path))
        print(f"-- {family}: source {len(raw) // 1024} KB")
        for w in weights:
            build(family, raw, w)
    # sanity: every built ttf must contain the ruble sign
    bad = [f.name for f in FONTS_DIR.glob("*.ttf")
           if 0x20BD not in TTFont(str(f)).getBestCmap()]
    # ASCII-only output: Windows console is cp1252 and cannot print the ruble char itself
    print("RUBLE CHECK:", "FAIL: " + ", ".join(bad) if bad else "all fonts contain U+20BD (RUB)")


if __name__ == "__main__":
    main()
