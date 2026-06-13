#!/usr/bin/env bash
# server_recon.sh — READ-ONLY server inventory for golosrisunka.ru deploy planning.
# Changes nothing. Run:  bash /tmp/server_recon.sh   (or wherever you uploaded it)
# Paste the entire output back to Claude.

set +e
line() { printf '\n========== %s ==========\n' "$1"; }

line "WHO / WHERE"
echo "whoami: $(whoami)"
echo "hostname: $(hostname)"
echo "pwd: $(pwd)"
echo "date: $(date)"
echo "uptime: $(uptime 2>/dev/null)"

line "OS / DISTRO"
cat /etc/os-release 2>/dev/null | grep -E '^(PRETTY_NAME|VERSION|ID)='
echo "kernel: $(uname -a)"
echo "arch: $(uname -m)"

line "RESOURCES"
echo "--- memory ---"; free -h 2>/dev/null
echo "--- disk ---"; df -h / /var /home 2>/dev/null | sort -u
echo "--- cpu count ---"; nproc 2>/dev/null

line "LOCALE (expect UTF-8)"
locale 2>/dev/null | grep -E 'LANG|LC_ALL|LC_CTYPE'

line "PYTHON"
for p in python3 python3.10 python3.11 python3.12 python3.13 python; do
  command -v "$p" >/dev/null 2>&1 && echo "$p -> $($p --version 2>&1) @ $(command -v $p)"
done
echo "--- venv module (python3) ---"
python3 -c "import venv; print('venv: OK')" 2>&1
echo "--- pip ---"
command -v pip3 >/dev/null 2>&1 && pip3 --version 2>&1
echo "--- python3-dev / headers ---"
ls /usr/include/python3*/Python.h 2>/dev/null || echo "Python.h: NOT found (python3-dev may be missing)"

line "WEASYPRINT SYSTEM LIBS (shared objects)"
for lib in libpango-1.0 libpangocairo-1.0 libcairo libgdk_pixbuf-2.0 libffi libgobject-2.0 libglib-2.0 libharfbuzz; do
  found=$(ldconfig -p 2>/dev/null | grep -m1 "$lib")
  if [ -n "$found" ]; then echo "OK   $found"; else echo "MISS $lib (not in ldconfig cache)"; fi
done
echo "--- libpango package (dpkg) ---"
dpkg -l 2>/dev/null | grep -iE 'libpango|libcairo|libgdk-pixbuf|libffi-dev|libharfbuzz' | awk '{print $1, $2, $3}'

line "WEB SERVERS"
echo "--- nginx ---"
command -v nginx >/dev/null 2>&1 && nginx -v 2>&1 || echo "nginx: NOT installed"
echo "--- apache ---"
command -v apache2 >/dev/null 2>&1 && apache2 -v 2>&1 | head -1 || echo "apache2: NOT installed"
command -v httpd >/dev/null 2>&1 && httpd -v 2>&1 | head -1 || true

line "NGINX CONFIG (if present)"
if command -v nginx >/dev/null 2>&1; then
  echo "--- nginx -T config test (errors only) ---"
  nginx -t 2>&1
  echo "--- sites-enabled ---"
  ls -la /etc/nginx/sites-enabled/ 2>/dev/null
  echo "--- conf.d ---"
  ls -la /etc/nginx/conf.d/ 2>/dev/null
  echo "--- server_name / listen directives across all vhosts ---"
  grep -rohE '^\s*(server_name|listen)\s+[^;]+;' /etc/nginx/sites-enabled/ /etc/nginx/conf.d/ /etc/nginx/sites-available/ 2>/dev/null | sed 's/^\s*//' | sort | uniq -c
  echo "--- does golosrisunka already appear anywhere in nginx? ---"
  grep -rl 'golosrisunka' /etc/nginx/ 2>/dev/null || echo "no existing golosrisunka nginx config"
fi

line "LISTENING PORTS (who owns 80/443/5000/8000 etc.)"
ss -tlnp 2>/dev/null || netstat -tlnp 2>/dev/null

line "SSL / CERTBOT / CLOUDFLARE"
command -v certbot >/dev/null 2>&1 && certbot --version 2>&1 || echo "certbot: NOT installed"
echo "--- existing letsencrypt certs ---"
ls /etc/letsencrypt/live/ 2>/dev/null || echo "no letsencrypt certs"
echo "--- cloudflare origin cert dir (if you made one) ---"
ls /etc/ssl/cloudflare* /etc/ssl/certs/cloudflare* 2>/dev/null || echo "no obvious cloudflare origin cert"

line "SYSTEMD"
command -v systemctl >/dev/null 2>&1 && echo "systemd: OK ($(systemctl --version | head -1))" || echo "systemd: NOT present"

line "TOOLS"
for t in git curl wget unzip rsync sqlite3 ufw; do
  command -v "$t" >/dev/null 2>&1 && echo "$t: $(command -v $t)" || echo "$t: MISSING"
done

line "FIREWALL"
ufw status 2>/dev/null || echo "ufw: not active / not installed"
iptables -L INPUT -n 2>/dev/null | head -20

line "EXISTING WEB ROOT / www"
echo "--- /var/www ---"; ls -la /var/www 2>/dev/null
echo "--- /root www-ish ---"; ls -la /root/www /root/public_html ~/www 2>/dev/null
echo "--- common app dirs ---"; ls -la /opt /srv 2>/dev/null

line "DONE"
echo "Recon complete. Copy ALL output above back to Claude."
