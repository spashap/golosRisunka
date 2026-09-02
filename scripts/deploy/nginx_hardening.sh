#!/usr/bin/env bash
# nginx_hardening.sh — заголовки безопасности, редирект www -> apex, gzip для css/js.
# Идемпотентно: правит /etc/nginx/sites-enabled/golosrisunka только если маркера ещё нет,
# проверяет конфиг (nginx -t) и перечитывает nginx. Запуск на сервере от root:
#   bash /var/www/golosrisunka/scripts/deploy/nginx_hardening.sh
# Аудит 02.09.2026 (C7): ни одного security-заголовка, www отдавал сайт с 200,
# components.css уходил без сжатия (65 КБ вместо ~12).
set -euo pipefail
CONF=/etc/nginx/sites-enabled/golosrisunka
MARK="# golosrisunka-hardening-v1"
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }
[ -f "$CONF" ] || { echo "ERROR: $CONF not found"; exit 1; }

if grep -q "$MARK" "$CONF"; then
  echo "already hardened: $CONF"
  exit 0
fi

cp "$CONF" "$CONF.bak-$(date +%Y%m%d%H%M%S)"

python3 - "$CONF" "$MARK" <<'PY'
import re, sys
conf, mark = sys.argv[1], sys.argv[2]
s = open(conf, encoding="utf-8").read()

headers = f"""
    {mark}
    add_header Strict-Transport-Security "max-age=31536000" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;
    add_header Permissions-Policy "camera=(), microphone=(), geolocation=(), payment=(self)" always;
    server_tokens off;
    # css/js со сжатием: html nginx жал и раньше, статику — нет
    gzip on;
    gzip_types text/css application/javascript application/json image/svg+xml font/woff2;
    gzip_min_length 1024;
    gzip_vary on;
"""

# 1) www -> apex на 443: отдельный server-блок перед основным
www_block = f"""server {{
    {mark} www -> apex
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name www.golosrisunka.ru;
    ssl_certificate /etc/letsencrypt/live/golosrisunka.ru/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/golosrisunka.ru/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    return 301 https://golosrisunka.ru$request_uri;
}}

"""
# 2) основной 443-блок: только apex + заголовки после ssl_protocols
m = re.search(r"server \{\s*\n\s*listen 443 ssl http2;.*?\n\}", s, re.S)
if not m:
    sys.exit("main 443 server block not found")
block = m.group(0)
block2 = block.replace("server_name golosrisunka.ru www.golosrisunka.ru;",
                       "server_name golosrisunka.ru;", 1)
block2 = re.sub(r"(ssl_protocols TLSv1\.2 TLSv1\.3;\n)", r"\1" + headers.replace("\\", "\\\\"), block2, count=1)
if block2 == block:
    sys.exit("could not patch main block")
s = s.replace(block, www_block + block2, 1)
# 3) http-блок: www тоже сразу на apex
s = s.replace("return 301 https://$host$request_uri;", "return 301 https://golosrisunka.ru$request_uri;")
open(conf, "w", encoding="utf-8").write(s)
print("patched", conf)
PY

nginx -t
systemctl reload nginx
echo "nginx reloaded"
