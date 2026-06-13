#!/usr/bin/env bash
# update.sh — redeploy after you push new code to GitHub main.
# Pulls latest code, refreshes deps, restarts both services. Run as root:
#   sed -i 's/\r$//' /tmp/update.sh && bash /tmp/update.sh
set -euo pipefail

APP_DIR=/var/www/golosrisunka
SVC_USER=www-data
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

echo "== pull =="
git -C "$APP_DIR" pull --ff-only
echo "now at: $(git -C "$APP_DIR" rev-parse --short HEAD)"

echo "== deps =="
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/pip" install -q 'gunicorn>=21'

echo "== fix data ownership (in case new dirs appeared) =="
mkdir -p "$APP_DIR/data/drawings" "$APP_DIR/data/reports" "$APP_DIR/data/outbox"
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR/data"

echo "== restart services =="
systemctl restart golosrisunka-web.service
systemctl restart golosrisunka-worker.service
sleep 2
systemctl is-active golosrisunka-web.service golosrisunka-worker.service
echo "done. tail logs with: journalctl -u golosrisunka-web -n 30"
