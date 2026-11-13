#!/usr/bin/env bash
# PG Reseller Bot installer (Ubuntu/Debian, root). Runs from the cloned folder.
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SERVICE=pgresellerbot
cd "$DIR"

[ "$(id -u)" -eq 0 ] || { echo "❌ با کاربر root اجرا کنید (sudo -i)"; exit 1; }
echo "====== PG Reseller Bot installer ======"

apt-get update -y >/dev/null
apt-get install -y python3 python3-venv python3-pip curl ca-certificates >/dev/null

[ -d venv ] || python3 -m venv venv
venv/bin/pip install -q --upgrade pip
venv/bin/pip install -q -r requirements.txt

ask() { local v; read -rp "$1" v </dev/tty; printf '%s' "$v" | tr -d '[:space:]'; }

if [ -f .env ]; then
  echo "ℹ️ فایل .env از قبل هست؛ همان استفاده می‌شود."
else
  while true; do
    TOKEN=$(ask "🤖 توکن ربات (از BotFather): ")
    [[ "$TOKEN" =~ ^[0-9]{6,12}:[A-Za-z0-9_-]{30,}$ ]] && break
    echo "❌ فرمت توکن درست نیست."
  done
  if ! curl -fsS --max-time 15 "https://api.telegram.org/bot${TOKEN}/getMe" >/dev/null 2>&1; then
    echo "❌ توکن معتبر نیست یا سرور به تلگرام دسترسی ندارد."; exit 1
  fi
  while true; do
    ADMINS=$(ask "🆔 آیدی عددی ادمین (چندتا با کاما): ")
    [[ "$ADMINS" =~ ^[0-9]+(,[0-9]+)*$ ]] && break
    echo "❌ فقط عدد."
  done
  KEY=$(venv/bin/python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())")
  umask 077
  cat > .env <<ENVEOF
BOT_TOKEN=$TOKEN
ADMIN_TELEGRAM_IDS=$ADMINS
ENCRYPTION_KEY=$KEY
ENVEOF
  echo "✅ فایل .env ساخته شد."
fi

cat > /etc/systemd/system/$SERVICE.service <<UNIT
[Unit]
Description=PG Reseller Bot
After=network-online.target
Wants=network-online.target

[Service]
WorkingDirectory=$DIR
ExecStart=$DIR/venv/bin/python -m bot.main
Restart=always
RestartSec=5
MemoryMax=150M

[Install]
WantedBy=multi-user.target
UNIT

systemctl daemon-reload
systemctl enable "$SERVICE" >/dev/null 2>&1
systemctl restart "$SERVICE"
sleep 6
if systemctl is-active --quiet "$SERVICE"; then
  echo "======================================"
  echo "🎉 نصب شد و ربات در حال اجراست."
  echo "توی ربات /admin را بزن و از «اتصال پنل» پاسارگارد را وصل کن."
  echo "لاگ: journalctl -u $SERVICE -f"
  echo "======================================"
else
  echo "❌ ربات بالا نیامد. لاگ:"
  journalctl -u "$SERVICE" -n 30 --no-pager
  exit 1
fi
