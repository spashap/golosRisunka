#!/usr/bin/env bash
# go_live.sh — STEP 2 of golosrisunka.ru deploy.
# Writes systemd units (web + worker) and the nginx vhost, obtains a Let's Encrypt
# certificate via the certbot nginx plugin, then starts everything.
# Idempotent. Aborts early if .env is not ready, so it can never half-deploy.
# Your existing sites are NOT touched.
#
# TLS model: DNS-only (Cloudflare grey cloud) + Let's Encrypt — golosrisunka.ru and
# www.golosrisunka.ru must already resolve DIRECTLY to this server's public IP (no
# orange-cloud proxy), exactly like shepotzvezd.ru. Auto-renewal: certbot.timer
# (installer=nginx → reloads nginx on renew). If you ever switch back to Cloudflare
# orange-cloud, use a CF Origin cert instead (see git history of this file).
#
# Run as root AFTER provision.sh + editing .env:
#   sed -i 's/\r$//' /tmp/go_live.sh && bash /tmp/go_live.sh
set -euo pipefail

APP_DIR=/var/www/golosrisunka
SVC_USER=www-data
DOMAIN=golosrisunka.ru
SOCK=/run/golosrisunka/web.sock
LE_EMAIL=spashap@gmail.com
CERT=/etc/letsencrypt/live/$DOMAIN/fullchain.pem
KEY=/etc/letsencrypt/live/$DOMAIN/privkey.pem

line() { printf '\n========== %s ==========\n' "$1"; }
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

line "0  PREFLIGHT"
[ -x "$APP_DIR/venv/bin/gunicorn" ] || { echo "ERROR: gunicorn missing — run provision.sh first"; exit 1; }
if grep -q 'PASTE_GEMINI_KEY\|CHOOSE_A_STRONG' "$APP_DIR/.env"; then
  echo "ERROR: $APP_DIR/.env still has placeholders. Edit it first (GEMINI_API_KEY, ADMIN_PASS)."; exit 1
fi
command -v certbot >/dev/null || { echo "ERROR: certbot not installed. Run: apt-get install -y certbot python3-certbot-nginx"; exit 1; }
# DNS sanity (soft): both names should resolve to THIS server, or the ACME HTTP-01 challenge fails.
SRV_IP=$(curl -s --max-time 10 ifconfig.me || true)
for h in "$DOMAIN" "www.$DOMAIN"; do
  RES=$(getent hosts "$h" | awk '{print $1}' | head -1)
  if [ -n "$SRV_IP" ] && [ "$RES" != "$SRV_IP" ]; then
    echo "WARNING: $h resolves to '${RES:-<none>}' but this server is '$SRV_IP'."
    echo "         Let's Encrypt issuance will FAIL unless DNS points here (grey cloud / DNS-only)."
  fi
done
echo "preflight OK (.env filled, certbot present)"

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

line "4a  BOOTSTRAP HTTP VHOST (so certbot can answer the ACME challenge on :80)"
# Plain HTTP vhost serving the app. Used only to obtain the cert the first time;
# step 4c overwrites it with the final HTTPS vhost. On re-runs (cert already
# present) this is a harmless no-op since 4c runs immediately after.
cat > /etc/nginx/sites-available/golosrisunka <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN www.$DOMAIN;

    client_max_body_size 50m;

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
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF
ln -sfn /etc/nginx/sites-available/golosrisunka /etc/nginx/sites-enabled/golosrisunka
nginx -t
systemctl reload nginx
echo "bootstrap HTTP vhost live"

line "4b  LET'S ENCRYPT CERTIFICATE (certbot, ECDSA — same as shepotzvezd)"
if [ -f "$CERT" ]; then
  echo "cert already exists at $CERT — skipping issuance (renewals handled by certbot.timer)"
else
  certbot certonly --nginx \
    -d "$DOMAIN" -d "www.$DOMAIN" \
    --key-type ecdsa \
    -m "$LE_EMAIL" --agree-tos --no-eff-email -n
  echo "certificate obtained"
fi
[ -f "$CERT" ] || { echo "ERROR: $CERT still missing — certbot failed (check DNS / port 80)."; exit 1; }

line "4c  FINAL HTTPS VHOST"
cat > /etc/nginx/sites-available/golosrisunka <<EOF
# golosrisunka.ru — DNS-only (Cloudflare grey cloud) + Let's Encrypt cert.
# Auto-renew: certbot.timer (installer=nginx reloads nginx on renew).
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

echo "vhost written. testing full nginx config (all sites)..."
nginx -t
systemctl reload nginx
echo "nginx reloaded"

line "DONE — STEP 2 complete"
cat <<NEXT
golosrisunka.ru should now be live over HTTPS (Let's Encrypt, direct / DNS-only).

Verify:
  - From server (origin TLS directly):
      curl -sI https://$DOMAIN/ | head -5
  - Public trust + chain:
      echo | openssl s_client -connect $DOMAIN:443 -servername $DOMAIN 2>/dev/null | grep "Verify return code"
  - In a browser:  https://$DOMAIN/
  - Admin panel:   https://$DOMAIN/admin   (password = ADMIN_PASS from .env)

Renewal (already scheduled by certbot.timer):
  certbot renew --cert-name $DOMAIN --dry-run

Logs:
  journalctl -u golosrisunka-web    -f      # web
  journalctl -u golosrisunka-worker -f      # report worker
  tail -f $APP_DIR/data/worker.log
NEXT
