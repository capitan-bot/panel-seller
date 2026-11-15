#!/usr/bin/env bash
APP="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
GW_DOMAIN="${GW_DOMAIN:-web.aligater.ir}"
BRAND="${GW_BRAND:-capitan}"
cd "$APP" || exit 1
[ "$(id -u)" -eq 0 ] || { echo "Run as root."; exit 1; }
get_env() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"' \r"; }
set_env() { if grep -q "^$1=" .env; then sed -i "s|^$1=.*|$1=$2|" .env; else echo "$1=$2" >> .env; fi; }
BT=$(get_env BOT_TOKEN); [ -n "$BT" ] || { echo "BOT_TOKEN is missing in .env"; exit 1; }
echo "Installing libraries..."
"$APP/venv/bin/pip" install -q aiohttp pillow arabic-reshaper python-bidi || { echo "pip failed"; exit 1; }
UN=$(curl -s -m 15 "https://api.telegram.org/bot$BT/getMe" | "$APP/venv/bin/python" -c 'import sys,json;print(json.load(sys.stdin)["result"]["username"].lower())' 2>/dev/null)
[ -n "$UN" ] || { echo "Could not read the bot username from Telegram (check BOT_TOKEN)."; exit 1; }
PORT=$(get_env WEB_PORT)
if [ -z "$PORT" ]; then
  for i in $(seq 1 60); do PORT=$((20000 + RANDOM % 20000)); ss -ltn | grep -q ":$PORT " || break; done
fi
TOK=$(get_env WEB_GW_TOKEN); [ -n "$TOK" ] || TOK=$("$APP/venv/bin/python" -c 'import secrets;print(secrets.token_urlsafe(32))')
mkdir -p data
if [ ! -f data/web_cert.pem ]; then
  openssl req -x509 -newkey rsa:2048 -nodes -days 3650 -subj "/CN=pgweb" -keyout data/web_key.pem -out data/web_cert.pem 2>/dev/null
  chmod 600 data/web_key.pem
fi
FP=$(openssl x509 -in data/web_cert.pem -noout -fingerprint -sha256 | cut -d= -f2 | tr -d ':' | tr 'A-F' 'a-f')
set_env WEB_DOMAIN "$GW_DOMAIN"; set_env WEB_PREFIX "$BRAND/$UN/panel"; set_env WEB_PORT "$PORT"
set_env WEB_GW_TOKEN "$TOK"; set_env WEB_TLS_CERT "$APP/data/web_cert.pem"; set_env WEB_TLS_KEY "$APP/data/web_key.pem"
PW=""
[ -f data/web_auth.json ] || PW=$("$APP/venv/bin/python" -m web.app setpass | sed 's/^password: //')
cat > /etc/systemd/system/pgbot-web.service <<UNIT
[Unit]
Description=PG Bot web panel
After=network-online.target

[Service]
WorkingDirectory=$APP
Environment=WEB_HOST=0.0.0.0
Environment=WEB_PORT=$PORT
ExecStart=$APP/venv/bin/python -m web.app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  GWIP=$(getent ahostsv4 "$GW_DOMAIN" | awk 'NR==1{print $1}')
  [ -n "$GWIP" ] && ufw allow from "$GWIP" to any port "$PORT" proto tcp >/dev/null && echo "Firewall: allowed $GWIP -> port $PORT"
fi
systemctl daemon-reload; systemctl enable pgbot-web >/dev/null 2>&1; systemctl restart pgbot-web
for i in $(seq 1 25); do curl -ks -m 2 -H "X-GW-Token: $TOK" "https://127.0.0.1:$PORT/__gw/ping" | grep -q '"ok"' && break; sleep 1; done
curl -ks -m 3 -H "X-GW-Token: $TOK" "https://127.0.0.1:$PORT/__gw/ping" | grep -q '"ok"' || { echo "The web panel did not start. Check: journalctl -u pgbot-web -n 20 --no-pager"; exit 1; }
BODY=$("$APP/venv/bin/python" - "$UN" "$PORT" "$TOK" "$FP" "${GW_INVITE:-}" <<'PY'
import json, sys
u, p, t, f, i = sys.argv[1:6]
d = {"username": u, "port": int(p), "token": t, "fp": f}
if i:
    d["invite"] = i
print(json.dumps(d))
PY
)
RES=$(curl -sS -m 40 -X POST "https://$GW_DOMAIN/gw/register" -H 'Content-Type: application/json' -d "$BODY")
if echo "$RES" | grep -q '"ok": true'; then
  URL=$(echo "$RES" | "$APP/venv/bin/python" -c 'import sys,json;print(json.load(sys.stdin)["url"])')
  echo; echo "Web panel is ready:"; echo "  Address : $URL"; echo "  Username: your numeric admin ID"
  if [ -n "$PW" ]; then echo "  Password: $PW   (save it now)"; else echo "  Password: the one you already have (new one: $APP/venv/bin/python -m web.app setpass)"; fi
else
  echo "Registration failed: $RES"
  echo "If it says 'could not reach', open TCP port $PORT in your server provider's firewall for $GW_DOMAIN and run this option again."
fi
