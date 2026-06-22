#!/usr/bin/env bash
# provision.sh — STEP 1 of golosrisunka.ru deploy.
# Idempotent & SAFE: touches ONLY /var/www/golosrisunka. Does NOT change nginx,
# does NOT touch your other sites, does NOT start anything public.
#
# Run as root:
#   sed -i 's/\r$//' /tmp/provision.sh && bash /tmp/provision.sh
set -euo pipefail

APP_DIR=/var/www/golosrisunka
REPO=https://github.com/spashap/golosRisunka.git
SVC_USER=www-data
PYTHON=/usr/bin/python3

line() { printf '\n========== %s ==========\n' "$1"; }
[ "$(id -u)" -eq 0 ] || { echo "ERROR: run as root"; exit 1; }

line "1/6  CODE  ($APP_DIR)"
if [ -d "$APP_DIR/.git" ]; then
  echo "repo exists -> git pull"
  git -C "$APP_DIR" pull --ff-only
else
  echo "cloning $REPO"
  git clone "$REPO" "$APP_DIR"
fi
echo "at commit: $(git -C "$APP_DIR" rev-parse --short HEAD)"

line "2/6  VENV"
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  "$PYTHON" -m venv "$APP_DIR/venv"
  echo "venv created"
else
  echo "venv exists"
fi
"$APP_DIR/venv/bin/python" -m pip install --upgrade pip -q

line "3/6  PYTHON DEPS  (+ gunicorn)"
"$APP_DIR/venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
"$APP_DIR/venv/bin/pip" install -q 'gunicorn>=21'
echo "installed. weasyprint smoke check:"
"$APP_DIR/venv/bin/python" -c "import weasyprint, PIL, pillow_heif, google.genai, pydantic; print('  imports OK, weasyprint', weasyprint.__version__)"

line "4/6  DATA DIRS  (owned by $SVC_USER)"
mkdir -p "$APP_DIR/data/drawings" "$APP_DIR/data/reports" "$APP_DIR/data/outbox"
chown -R "$SVC_USER:$SVC_USER" "$APP_DIR/data"
echo "data/ owned by $SVC_USER; code stays root-owned (web user reads, cannot modify code)"

line "5/6  .env"
ENV="$APP_DIR/.env"
if [ -f "$ENV" ]; then
  echo ".env already exists -> left untouched"
else
  cat > "$ENV" <<'ENVEOF'
# golosrisunka PRODUCTION .env  (chmod 600). Fill the CAPS placeholders.
GEMINI_API_KEY=PASTE_GEMINI_KEY_FROM_LOCAL_.env
GEMINI_MODEL=gemini-2.5-pro
ADMIN_PASS=CHOOSE_A_STRONG_ADMIN_PASSWORD
PUBLIC_BASE_URL=https://golosrisunka.ru
MAIL_BACKEND=outbox
ADMIN_ALERT_EMAIL=spashap@gmail.com
YANDEX_METRIKA_ID=
# ЮKassa: YUKASSA_MODE=live / YUKASSA_SHOP_ID_LIVE= / YUKASSA_SECRET_KEY_LIVE= (+_TEST для теста)
# Прочее (later): UNISENDER_API_KEY=
ENVEOF
  echo ".env TEMPLATE written -> you must edit it (see next steps)"
fi
chmod 600 "$ENV"
chown "$SVC_USER:$SVC_USER" "$ENV"

line "6/6  DONE — STEP 1 complete"
cat <<'NEXT'
Nothing public has changed yet. Before running go_live.sh do these TWO things:

(A) EDIT  /var/www/golosrisunka/.env  (WinSCP editor):
      - GEMINI_API_KEY = the value from your LOCAL project's .env
      - ADMIN_PASS     = a strong password for /admin

(B) DNS (Cloudflare DNS-only / grey cloud — same as shepotzvezd.ru):
      1. Cloudflare dashboard -> DNS: A records for  golosrisunka.ru  and  www
         must point to THIS server's public IP, proxy status = DNS only (grey cloud).
      2. certbot must be installed:  apt-get install -y certbot python3-certbot-nginx
      go_live.sh then obtains a Let's Encrypt cert automatically (no Origin cert needed).
      (If you ever switch to Cloudflare orange-cloud, use a CF Origin cert instead.)

Then upload & run go_live.sh.
NEXT
