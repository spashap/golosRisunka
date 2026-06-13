"""Bump the site version in the VERSION file (single source of truth).

Usage (run from project root):
    venv\\Scripts\\python.exe scripts\\bump_version.py            # minor +1  (every git push)
    venv\\Scripts\\python.exe scripts\\bump_version.py --major     # major +1, minor -> 000 (manual only)

Format: "MAJOR.MINOR", minor zero-padded to 3 digits (e.g. 1.001 -> 1.002).
ASCII-only output (Windows cp1252 console — project rule #3).
"""
import sys
from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"


def main() -> int:
    major_bump = "--major" in sys.argv[1:]
    raw = VERSION_FILE.read_text(encoding="utf-8").strip()
    try:
        major_s, minor_s = raw.split(".", 1)
        major, minor = int(major_s), int(minor_s)
    except ValueError:
        print(f"ERROR: VERSION file malformed: {raw!r}")
        return 1

    if major_bump:
        major, minor = major + 1, 0
    else:
        minor += 1

    new = f"{major}.{minor:03d}"
    VERSION_FILE.write_text(new + "\n", encoding="utf-8")
    print(f"{raw} -> {new}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
