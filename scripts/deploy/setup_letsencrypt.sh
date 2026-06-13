#!/usr/bin/env bash
# setup_letsencrypt.sh — obtain/replace the golosrisunka.ru TLS cert with Let's Encrypt.
# Replaces the old Cloudflare Origin-cert flow (install_cert.sh) now that the domain is
# DNS-only (grey cloud), served like shepotzvezd.ru. Safe to re-run (idempotent).
#
# Prereqs: nginx already serving golosrisunka.ru on :80 (go_live.sh does this), and
# golosrisunka.ru + www.golosrisunka.ru resolving DIRECTLY to this server (DNS-only).
#
# Run as root:
#   sed -i 's/\r$//' /tmp/setup_letsencrypt.sh && bash /tmp/setup_letsencrypt.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

DOMAIN=golosrisunka.ru
LE_EMAIL=spashap@gmail.com

command -v certbot >/dev/null || { echo "installing certbot..."; apt-get update -qq && apt-get install -y certbot python3-certbot-nginx; }

# --nginx authenticator + installer: obtains the cert AND rewrites the vhost's
# ssl_certificate directives, then sets up auto-renewal (certbot.timer, reload on renew).
# ECDSA key + --redirect to force HTTP->HTTPS, matching shepotzvezd.ru.
certbot --nginx \
  -d "$DOMAIN" -d "www.$DOMAIN" \
  --key-type ecdsa \
  -m "$LE_EMAIL" --agree-tos --no-eff-email --redirect -n

echo "== verify =="
nginx -t && systemctl reload nginx
echo | openssl s_client -connect "$DOMAIN":443 -servername "$DOMAIN" 2>/dev/null \
  | grep -E "Verify return code|issuer=" || true
echo "auto-renewal: certbot.timer is $(systemctl is-active certbot.timer 2>/dev/null) / $(systemctl is-enabled certbot.timer 2>/dev/null)"
certbot certificates --cert-name "$DOMAIN" 2>/dev/null | grep -E "Expiry Date" || true
echo "done."
echo
echo "(Optional) simulate a renewal — can be SLOW/flaky against LE staging, so it's not"
echo "run automatically. To check manually:  certbot renew --cert-name $DOMAIN --dry-run"
