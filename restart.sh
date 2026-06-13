#!/usr/bin/env bash
# restart.sh — restart the golosrisunka services. Run as root from the app folder:
#   cd /var/www/golosrisunka && ./restart.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

systemctl restart golosrisunka-web.service golosrisunka-worker.service
sleep 1
echo "web:    $(systemctl is-active golosrisunka-web.service)"
echo "worker: $(systemctl is-active golosrisunka-worker.service)"
