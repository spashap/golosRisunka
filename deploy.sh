#!/usr/bin/env bash
# deploy.sh — pull latest code from GitHub, refresh deps, restart services.
# Run as root from the app folder:
#   cd /var/www/golosrisunka && ./deploy.sh
#
# DB note: schema is created idempotently on every startup (CREATE TABLE IF NOT
# EXISTS), so a restart applies any *new* tables. Altering existing tables still
# needs a one-off migration. Secrets/API keys live in .env and are not touched.
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

APP_DIR=/var/www/golosrisunka
SVC_USER=www-data
cd "$APP_DIR"

echo "== pull =="
git pull --ff-only
echo "now at $(git rev-parse --short HEAD)  (V$(cat VERSION 2>/dev/null || echo '?'))"

echo "== python deps =="
venv/bin/pip install -q -r requirements.txt
venv/bin/pip install -q 'gunicorn>=21'

echo "== data dirs / ownership =="
mkdir -p data/drawings data/reports data/outbox
chown -R "$SVC_USER:$SVC_USER" data
# keep runtime-generated sample thumbnails writable by the web user
[ -d static/img ] && chown -R "$SVC_USER:$SVC_USER" static/img || true

echo "== restart services =="
systemctl restart golosrisunka-web.service golosrisunka-worker.service
sleep 1
echo "web:    $(systemctl is-active golosrisunka-web.service)"
echo "worker: $(systemctl is-active golosrisunka-worker.service)"
echo "deployed."
