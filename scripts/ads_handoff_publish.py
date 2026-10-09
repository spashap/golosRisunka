"""Опубликовать инструкцию рекламному агенту: открытый .md -> зашифрованный config/ads_handoff.json.

Запуск ЛОКАЛЬНО (после правки projectSpec/ads/ADS-PARTNER-HANDOFF.md):
    venv\\Scripts\\python.exe scripts\\ads_handoff_publish.py
затем обычный релиз (commit + push) и деплой — сервер отдаст новую версию через
GET /api/ads/v1/handoff, агент партнёра заберёт её сам (сверяет handoff_version).

Версия поднимается САМА, если текст изменился (front matter исходника переписывается),
так что «забыл поднять версию» невозможно. Неизменённый текст — ничего не делает.
Ключ шифрования выводится из ADS_API_TOKEN (app/ads_handoff.py); токен берётся из
переменной окружения GR_ADS_TOKEN или из файла доступа партнёра
projectSpec/ads/golosrisunka-ads-access.md (он в .gitignore). Токен не печатается.
Вывод — ASCII (cp1252-консоль Windows).
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import os
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

SRC = BASE / "projectSpec" / "ads" / "ADS-PARTNER-HANDOFF.md"
ACCESS = BASE / "projectSpec" / "ads" / "golosrisunka-ads-access.md"
OUT = BASE / "config" / "ads_handoff.json"
_FM = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def split_front_matter(text: str) -> tuple[dict, str]:
    m = _FM.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(":")
        if k.strip():
            meta[k.strip()] = v.strip()
    return meta, text[m.end():]


def with_front_matter(version: int, updated: str, body: str) -> str:
    return f"---\nhandoff_version: {version}\nupdated: {updated}\n---\n{body}"


def find_token() -> str:
    tok = os.getenv("GR_ADS_TOKEN") or os.getenv("ADS_API_TOKEN") or ""
    if not tok and ACCESS.exists():
        m = re.search(r"GR_ADS_TOKEN=([A-Za-z0-9_\-]{24,})", ACCESS.read_text(encoding="utf-8"))
        tok = m.group(1) if m else ""
    return tok


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=str(SRC))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--force", action="store_true", help="re-encrypt even if unchanged (after token rotation)")
    a = ap.parse_args()
    src, out = Path(a.src), Path(a.out)

    from app import ads_handoff
    token = find_token()
    if len(token) < 24:
        print("ERROR: no token. Set GR_ADS_TOKEN or put the access file at " + str(ACCESS))
        return 1
    if not src.exists():
        print("ERROR: source not found: " + str(src))
        return 1

    meta, body = split_front_matter(src.read_text(encoding="utf-8").replace("\r\n", "\n"))
    body_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
    prev = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {}
    if prev.get("body_sha256") == body_sha and not a.force:
        print(f"unchanged: handoff v{prev.get('version')} already published")
        return 0

    try:
        src_v = int(meta.get("handoff_version") or 0)
    except ValueError:
        src_v = 0
    prev_v = int(prev.get("version") or 0)
    version = prev_v if (a.force and prev.get("body_sha256") == body_sha) else max(src_v, prev_v + 1)
    updated = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d")
    full = with_front_matter(version, updated, body)
    src.write_text(full, encoding="utf-8")                 # исходник = то, что получит агент

    data = {"format": 1, "version": version, "updated": updated,
            "sha256": hashlib.sha256(full.encode("utf-8")).hexdigest(),
            "body_sha256": body_sha, "ciphertext": ads_handoff.encrypt(full, token)}
    if ads_handoff.decrypt(data["ciphertext"], token) != full:
        print("ERROR: round-trip check failed")
        return 1
    out.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shown = out.relative_to(BASE) if out.is_relative_to(BASE) else out
    print(f"published handoff v{version} ({updated}) -> {shown}")
    print("next: commit + push + deploy; the partner's agent picks it up via /handoff/version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
