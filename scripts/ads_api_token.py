"""Включить API рекламы на сервере и выдать партнёру файл доступа — одной командой.

Запуск НА СЕРВЕРЕ (под root, из корня репозитория):
    cd /var/www/golosrisunka && git pull -q && venv/bin/python scripts/ads_api_token.py

Что делает:
  1. Берёт ADS_API_TOKEN из .env, а если его нет (или --rotate) — генерирует новый
     и записывает в .env (остальные строки, владелец и права файла сохраняются).
  2. Перезапускает веб-юнит (golosrisunka-web), чтобы токен подхватился.
  3. Проверяет снаружи: без токена API отвечает 401, с токеном — 200.
  4. Пишет файл доступа для партнёра (по умолчанию ~/golosrisunka-ads-access.md, права 600)
     и печатает, как забрать его на свой компьютер.

Повторный запуск без --rotate безопасен: токен тот же, у партнёра ничего не ломается,
файл просто пересоздаётся. --rotate = старый токен перестаёт работать сразу.
Только stdlib: скрипт не импортирует приложение (config.settings читает .env при импорте).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import secrets
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
ENV = BASE / ".env"
KEY = "ADS_API_TOKEN"
MIN_LEN = 24
SERVICE = "golosrisunka-web"
HANDOFF = "ADS-PARTNER-HANDOFF.md"


def read_token() -> str:
    if not ENV.exists():
        return ""
    for line in ENV.read_text(encoding="utf-8").splitlines():
        m = re.match(rf"^\s*{KEY}\s*=\s*(.*?)\s*$", line)
        if m:
            return m.group(1).strip().strip('"').strip("'")
    return ""


def write_token(token: str) -> None:
    """Заменяет строку ADS_API_TOKEN или дописывает её; атомарно, с прежними правами."""
    lines = ENV.read_text(encoding="utf-8").splitlines() if ENV.exists() else []
    out, done = [], False
    for line in lines:
        if re.match(rf"^\s*{KEY}\s*=", line):
            if not done:
                out.append(f"{KEY}={token}")
                done = True
            continue
        out.append(line)
    if not done:
        out.append(f"{KEY}={token}")
    tmp = ENV.with_name(".env.tmp-ads")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    if ENV.exists():
        st = ENV.stat()
        os.chmod(tmp, st.st_mode & 0o777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)
        except (PermissionError, AttributeError):
            pass
    else:
        os.chmod(tmp, 0o600)
    os.replace(tmp, ENV)


def http(url: str, token: str | None) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode() or "{}")
        except ValueError:
            body = {}
        return e.code, body
    except (urllib.error.URLError, OSError, ValueError) as e:
        return 0, {"error": str(e)}


def access_file(base_url: str, token: str, site: dict) -> str:
    api = f"{base_url}/api/ads/v1"
    prices = ", ".join(f"{p.get('code')}: {p.get('price_rub')} RUB" for p in site.get("products", [])) \
        or "see GET /site"
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=3))).strftime("%Y-%m-%d %H:%M MSK")
    return f"""# golosrisunka.ru — ads API access (SECRET)

Issued {now} by the site owner. This file contains a **secret token**. It is your key
to the site's ads API, which is described in `{HANDOFF}` §10 (you get that file separately).

| | |
|---|---|
| Base URL | `{api}` |
| Header | `Authorization: Bearer <token>` |
| Token | `{token}` |

## For Claude Code: set this up once
1. Store the token **outside version control**: put the line
   `GR_ADS_TOKEN={token}`
   into your project's `.env`, and make sure `.env` is in `.gitignore`. Read it from the
   environment in every call. Never write the token into code, docs, commits, logs or ads.
2. **Do not keep this file inside your repository.** After step 1, delete it or move it
   outside the project.
3. Check access:
   ```bash
   curl -s {api}/ping -H "Authorization: Bearer $GR_ADS_TOKEN"
   ```
   Expect `{{"ok": true, ...}}`.
   - `401` means the token is wrong or the owner rotated it; ask the owner for a new file.
   - `404` on every path means the API is switched off on the server; tell the owner.
4. Read `GET /site` for live prices and landing rules (today: {prices}).
5. Register your campaigns (`PUT /campaigns`), then send stats daily (`POST /stats`) and read
   results (`GET /report`), exactly as `{HANDOFF}` §10 describes.

## Rules
- The token only opens `/api/ads/v1/*`. It gives no access to the admin or customer data, and
  the API never returns emails or names.
- Every call is logged and visible to the owner. Limit: 120 requests a minute.
- If the token leaks, tell the owner right away. They re-run the issuing script with
  `--rotate`, which makes the old token stop working immediately.
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Enable the ads API and issue the partner access file.")
    ap.add_argument("--rotate", action="store_true", help="issue a NEW token (the old one stops working)")
    ap.add_argument("--no-restart", action="store_true", help="do not restart the web service")
    ap.add_argument("--base-url", default="https://golosrisunka.ru")
    ap.add_argument("--out", default=str(Path.home() / "golosrisunka-ads-access.md"))
    a = ap.parse_args()

    token = read_token()
    if a.rotate or len(token) < MIN_LEN:
        token = secrets.token_urlsafe(32)
        write_token(token)
        print(f"[1/4] new token written to {ENV}")
        changed = True
    else:
        print(f"[1/4] existing token kept (use --rotate to replace it)")
        changed = False

    if a.no_restart:
        print("[2/4] restart skipped (--no-restart)")
    elif changed or http(f"{a.base_url}/api/ads/v1/ping", token)[0] != 200:
        r = subprocess.run(["systemctl", "restart", SERVICE], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"[2/4] FAILED: systemctl restart {SERVICE}: {r.stderr.strip()}")
            return 1
        print(f"[2/4] {SERVICE} restarted")
    else:
        print("[2/4] service already serves this token, no restart needed")

    ping = (0, {})
    for _ in range(30):
        ping = http(f"{a.base_url}/api/ads/v1/ping", token)
        if ping[0] == 200:
            break
        time.sleep(1)
    anon = http(f"{a.base_url}/api/ads/v1/ping", None)[0]
    if ping[0] != 200 or anon != 401:
        print(f"[3/4] FAILED: with token -> {ping[0]} {ping[1]}, without -> {anon} (want 200 / 401)")
        return 1
    print(f"[3/4] API live: with token 200, without 401 (site {ping[1].get('site_version')})")

    site = http(f"{a.base_url}/api/ads/v1/site", token)[1]
    out = Path(a.out)
    out.write_text(access_file(a.base_url, token, site), encoding="utf-8")
    os.chmod(out, 0o600)
    print(f"[4/4] access file: {out}")
    print("")
    print("Copy it to your computer (run THERE, not on the server):")
    host = a.base_url.split("//", 1)[-1].split("/", 1)[0]      # DNS-only: домен = сам сервер
    print(f"    scp root@{host}:{out} .")
    print(f"Send your partner TWO files, privately: {out.name} (secret) and projectSpec/ads/{HANDOFF}.")
    print("Then delete the copy on the server if you like:  rm " + str(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
