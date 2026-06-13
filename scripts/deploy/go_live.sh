#!/usr/bin/env bash
# go_live.sh — STEP 2 of golosrisunka.ru deploy.
# Writes systemd units (web + worker) and the nginx vhost, then starts everything.
# Idempotent. Aborts early if .env or the Cloudflare cert is not ready, so it can
# never half-deploy. Your existing sites are NOT touched.
#
# Run as root AFTER provision.sh + editing .env + placing the CF origin cert:
#   sed -i 's/\r$//' /tmp/go_live.sh && bash /tmp/go_live.sh
set -euo pipefail

APP_DIR=/var/www/golosrisunka
SVC_USER=www-data
DOMAIN=golosrisunka.ru
SOCK=/run/golosrisunka/web.sock
CERT=/etc/ssl/cloudflare/golosrisunka.pem
KEY=/etc/ssl/cloudflare/golosrisunka.key

line() { printf '\n========== %s ==========\n' "$1"; }
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

line "0  PREFLIGHT"
[ -x "$APP_DIR/venv/bin/gunicorn" ] || { echo "ERROR: gunicorn missing — run provision.sh first"; exit 1; }
if grep -q 'PASTE_GEMINI_KEY\|CHOOSE_A_STRONG' "$APP_DIR/.env"; then
  echo "ERROR: $APP_DIR/.env still has placeholders. Edit it first (GEMINI_API_KEY, ADMIN_PASS)."; exit 1
fi
[ -f "$CERT" ] || { echo "ERROR: $CERT not found — create the Cloudflare Origin cert first."; exit 1; }
[ -f "$KEY" ]  || { echo "ERROR: $KEY not found — save the Origin private key first."; exit 1; }
echo "preflight OK (.env filled, cert + key present)"

line "1  SYSTEMD: golosrisunka-web (gunicorn)"
cat > /etc/systemd/system/golosrisunka-web.service <<EOF
[Unit]
Description=golosrisunka web (gunicorn)
After=network.target

[Service]
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$APP_DIR
RuntimeDirectory=golosrisunka
RuntimeDirectoryMode=0750
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/venv/bin/gunicorn --workers 3 --timeout 120 --umask 007 \\
    --bind unix:$SOCK --access-logfile - --error-logfile - 'app:create_app()'
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

line "2  SYSTEMD: golosrisunka-worker (report pipeline)"
cat > /etc/systemd/system/golosrisunka-worker.service <<EOF
[Unit]
Description=golosrisunka report worker
After=network.target

[Service]
User=$SVC_USER
Group=$SVC_USER
WorkingDirectory=$APP_DIR
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/venv/bin/python worker.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now golosrisunka-web.service
systemctl enable --now golosrisunka-worker.service
sleep 2
systemctl --no-pager --lines=0 status golosrisunka-web.service  | head -4 || true
systemctl --no-pager --lines=0 status golosrisunka-worker.service | head -4 || true

line "3  LOCAL SMOKE TEST (via gunicorn socket, before nginx)"
if curl -sS --unix-socket "$SOCK" -o /dev/null -w 'app responded HTTP %{http_code}\n' http://localhost/ ; then
  echo "gunicorn is serving"
else
  echo "WARNING: app did not respond on socket — check: journalctl -u golosrisunka-web -n 50"
fi

line "4  NGINX VHOST"
cat > /etc/nginx/sites-available/golosrisunka <<EOF
# golosrisunka.ru — behind Cloudflare (orange) with Origin cert, SSL mode Full(strict)
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN www.$DOMAIN;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMAIN www.$DOMAIN;

    ssl_certificate     $CERT;
    ssl_certificate_key $KEY;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 50m;

    # restore real visitor IP from Cloudflare (so analytics/logs aren't all CF IPs)
    real_ip_header CF-Connecting-IP;
    set_real_ip_from 173.245.48.0/20;  set_real_ip_from 103.21.244.0/22;
    set_real_ip_from 103.22.200.0/22;  set_real_ip_from 103.31.4.0/22;
    set_real_ip_from 141.101.64.0/18;  set_real_ip_from 108.162.192.0/18;
    set_real_ip_from 190.93.240.0/20;  set_real_ip_from 188.114.96.0/20;
    set_real_ip_from 197.234.240.0/22; set_real_ip_from 198.41.128.0/17;
    set_real_ip_from 162.158.0.0/15;   set_real_ip_from 104.16.0.0/13;
    set_real_ip_from 104.24.0.0/14;    set_real_ip_from 172.64.0.0/13;
    set_real_ip_from 131.0.72.0/22;
    set_real_ip_from 2400:cb00::/32;   set_real_ip_from 2606:4700::/32;
    set_real_ip_from 2803:f800::/32;   set_real_ip_from 2405:b500::/32;
    set_real_ip_from 2405:8100::/32;   set_real_ip_from 2a06:98c0::/29;
    set_real_ip_from 2c0f:f248::/32;

    # static assets served directly by nginx (fonts, css, images)
    location /static/ {
        alias $APP_DIR/static/;
        access_log off;
        expires 30d;
    }

    location / {
        proxy_pass http://unix:$SOCK;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_read_timeout 120s;
    }
}
EOF

ln -sfn /etc/nginx/sites-available/golosrisunka /etc/nginx/sites-enabled/golosrisunka
echo "vhost linked. testing full nginx config (all sites)..."
nginx -t
systemctl reload nginx
echo "nginx reloaded"

line "DONE — STEP 2 complete"
cat <<NEXT
golosrisunka.ru should now be live behind Cloudflare.

Verify:
  - From server (bypasses Cloudflare, tests origin TLS directly):
      curl -sI --resolve $DOMAIN:443:127.0.0.1 https://$DOMAIN/ | head -5
  - In a browser:  https://$DOMAIN/
  - Admin panel:   https://$DOMAIN/admin   (password = ADMIN_PASS from .env)

Logs:
  journalctl -u golosrisunka-web    -f      # web
  journalctl -u golosrisunka-worker -f      # report worker
  tail -f $APP_DIR/data/worker.log
NEXT
