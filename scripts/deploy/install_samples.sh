#!/usr/bin/env bash
# install_samples.sh — drop the landing-page sample artifacts into place,
# make the thumbnail output dir writable by the web user, restart web.
# Upload golos_samples.tar.gz to /tmp/ first, then run as root:
#   sed -i 's/\r$//' /tmp/install_samples.sh && bash /tmp/install_samples.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

APP_DIR=/var/www/golosrisunka
SVC_USER=www-data
TARBALL=/tmp/golos_samples.tar.gz

[ -f "$TARBALL" ] || { echo "ERROR: $TARBALL not found — upload golos_samples.tar.gz to /tmp first"; exit 1; }

echo "== extract artifacts into $APP_DIR =="
tar xzf "$TARBALL" -C "$APP_DIR"
tar tzf "$TARBALL" | sed 's/^/  + /'

echo "== ownership =="
# report json/html live under data/ (web reads them) -> owned by web user
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR/data/test_reports"
# thumbnails are generated at runtime into static/img/samples -> must be writable
mkdir -p "$APP_DIR/static/img/samples"
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR/static/img"
# source drawings are only READ by the app; root-owned + world-readable is fine
chmod -R a+r "$APP_DIR/projectSpec/testDrawings"

echo "== restart web (clears cached empty sample list) =="
systemctl restart golosrisunka-web.service
sleep 2

echo "== warm the landing so thumbnails get generated =="
curl -sS --unix-socket /run/golosrisunka/web.sock -o /dev/null -w 'landing HTTP %{http_code}\n' http://localhost/ || true

echo "== generated thumbnails =="
ls -la "$APP_DIR/static/img/samples/" 2>/dev/null || echo "  (none yet)"

echo
echo "Done. Reload https://golosrisunka.ru/ — the sample strip should now show 4 cards."
echo "If a thumbnail is missing, check: journalctl -u golosrisunka-web -n 40"
