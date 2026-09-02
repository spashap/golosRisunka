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
# SKIP_PULL=1 — код уже доставлен в этот клон напрямую (git push в ветку claude-deploy +
# ff-merge), а GitHub недоступен: аккаунт spashap скрыт с 28.08.2026, анонимный
# HTTPS-pull отвечает 404, deploy-ключи тоже не читают. Как только аккаунт вернут,
# обычный запуск без переменной снова делает git pull.
if [ "${SKIP_PULL:-0}" = "1" ]; then
  echo "SKIP_PULL=1: git pull пропущен (код доставлен напрямую)"
else
  git pull --ff-only
fi
echo "now at $(git rev-parse --short HEAD)  (V$(cat VERSION 2>/dev/null || echo '?'))"

echo "== python deps =="
venv/bin/pip install -q -r requirements.txt
venv/bin/pip install -q 'gunicorn>=21'

echo "== data dirs / ownership =="
mkdir -p data/drawings data/reports data/outbox data/free
chown -R "$SVC_USER:$SVC_USER" data
# keep runtime-generated sample thumbnails writable by the web user
[ -d static/img ] && chown -R "$SVC_USER:$SVC_USER" static/img || true

echo "== restart services =="
systemctl restart golosrisunka-web.service golosrisunka-worker.service
# Фремиум-воркер: перезапускаем, только если юнит уже установлен. Первый раз его
# ставят руками (systemctl enable --now golosrisunka-free) — deploy.sh сам юниты
# не создаёт, и молча пропустить это нельзя: без воркера разборы не генерируются.
# Проверка через `systemctl cat`, а НЕ через `list-unit-files | grep`: полный листинг
# после рестарта web/worker один раз вернулся пустым (systemd был занят), юнит сочли
# неустановленным и молча не перезапустили — воркер остался на старом коде.
if systemctl cat golosrisunka-free.service >/dev/null 2>&1; then
  systemctl restart golosrisunka-free.service
else
  echo "WARNING: golosrisunka-free.service НЕ УСТАНОВЛЕН — бесплатные разборы"
  echo "         не будут генерироваться. Установка описана в scripts/deploy/go_live.sh"
fi
sleep 1
echo "web:    $(systemctl is-active golosrisunka-web.service)"
echo "worker: $(systemctl is-active golosrisunka-worker.service)"
echo "free:   $(systemctl is-active golosrisunka-free.service 2>/dev/null || echo 'not installed')"
echo "deployed."
