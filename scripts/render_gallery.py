"""Milestone M1: render the dev component gallery to a static HTML file.

Run: venv/Scripts/python.exe scripts/render_gallery.py [palette]
  palette: "" (Синий, default) | pu | dk | cl
Output: component-gallery.html in project root — open in a browser.
"""
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent.parent


def main() -> None:
    palette = sys.argv[1] if len(sys.argv) > 1 else ""
    env = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))
    html = env.get_template("dev/components.html").render(
        static="static",  # relative: gallery sits in project root
        palette=palette,
    )
    out = BASE_DIR / "component-gallery.html"
    out.write_text(html, encoding="utf-8")
    print(f"OK: {out}  (palette: {palette or 'Sinij default'})")


if __name__ == "__main__":
    main()
