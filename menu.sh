#!/usr/bin/env bash
# PG Reseller Bot - management menu
# Run with:  pgbot   (or: bash /opt/pgbot/menu.sh)

APP_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SERVICE="pgresellerbot"
ENV_FILE="$APP_DIR/.env"
DATA_DIR="$APP_DIR/data"
BACKUP_DIR="$APP_DIR/backups"
OWNER_TG="@YourTelegramID"      # <-- change this to your Telegram ID

PINK='\033[1;38;5;205m'; BLUE='\033[1;38;5;39m'; GREEN='\033[1;32m'
RED='\033[1;31m'; YEL='\033[1;33m'; CYAN='\033[1;36m'; GRAY='\033[0;90m'
BOLD='\033[1m'; RST='\033[0m'

[ "$(id -u)" -ne 0 ] && { echo "Please run as root."; exit 1; }

# ---------- helpers ----------
cols() { tput cols 2>/dev/null || echo 60; }
cline() {
  local color="$1" text="$2" pad
  pad=$(( ($(cols) - ${#text}) / 2 )); [ "$pad" -lt 0 ] && pad=0
  printf "%*s%b%s%b\n" "$pad" "" "$color" "$text" "$RST"
}
hr() { printf "${BLUE}"; printf '─%.0s' $(seq 1 44); printf "${RST}\n"; }
pause() { echo; read -rp "Press Enter to go back... " _; }
sec() { echo -e " ${PINK}▌${RST}${YEL} $1${RST}"; }
item() { printf "  ${YEL}%s${RST}  %s  ${BOLD}%s${RST}\n" "$1" "$2" "$3"; }

get_env() { grep -E "^$1=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "\"' \r"; }
set_env() {
  python3 - "$ENV_FILE" "$1" "$2" <<'PY'
import sys
p, k, v = sys.argv[1:4]
try:
    lines = open(p).read().splitlines()
except FileNotFoundError:
    lines = []
out, done = [], False
for l in lines:
    if l.startswith(k + "="):
        out.append(f"{k}={v}"); done = True
    else:
        out.append(l)
if not done:
    out.append(f"{k}={v}")
open(p, "w").write("\n".join(out) + "\n")
PY
  chmod 600 "$ENV_FILE"
}

valid_token() { curl -s -m 15 "https://api.telegram.org/bot$1/getMe" | grep -q '"ok":true'; }
valid_ids() { [[ "$1" =~ ^[0-9]+(,[0-9]+)*$ ]]; }

tg_send() {   # $1=file  $2=caption
  local token ids id res ok=1
  token=$(get_env BOT_TOKEN); ids=$(get_env ADMIN_TELEGRAM_IDS)
  if [ -z "$token" ] || [ -z "$ids" ]; then
    echo -e "${RED}BOT_TOKEN or ADMIN_TELEGRAM_IDS is missing in .env${RST}"; return 1
  fi
  for id in ${ids//,/ }; do
    res=$(curl -s -m 90 -F "chat_id=$id" -F "caption=$2" -F "document=@$1" \
          "https://api.telegram.org/bot${token}/sendDocument")
    if echo "$res" | grep -q '"ok":true'; then
      echo -e "${GREEN}✔ Sent to $id${RST}"; ok=0
    else
      echo -e "${RED}✘ Failed for $id (did the admin press /start in the bot?)${RST}"
    fi
  done
  return $ok
}

find_db() { find "$DATA_DIR" -maxdepth 1 \( -name '*.db' -o -name '*.sqlite3' \) 2>/dev/null | head -1; }

make_backup() {   # $1 = file prefix ; sets BK_ZIP and BK_SQL
  local prefix="${1:-pgbot}" ts tmp db
  ts=$(date +%Y-%m-%d_%H-%M-%S)
  mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
  BK_ZIP="$BACKUP_DIR/${prefix}_$ts.zip"; BK_SQL=""
  tmp=$(mktemp -d); mkdir -p "$tmp/data"
  [ -d "$DATA_DIR" ] && cp -a "$DATA_DIR/." "$tmp/data/"
  [ -f "$ENV_FILE" ] && cp -a "$ENV_FILE" "$tmp/.env"
  python3 - "$DATA_DIR" "$tmp/data" <<'PY'
import sqlite3, sys, glob, os
src, dst = sys.argv[1], sys.argv[2]
for p in glob.glob(os.path.join(src, "*.db")) + glob.glob(os.path.join(src, "*.sqlite3")):
    a = sqlite3.connect(p); b = sqlite3.connect(os.path.join(dst, os.path.basename(p)))
    a.backup(b); b.close(); a.close()
PY
  rm -f "$tmp"/data/*-wal "$tmp"/data/*-shm
  ( cd "$tmp" && python3 -m zipfile -c "$BK_ZIP" data .env 2>/dev/null || python3 -m zipfile -c "$BK_ZIP" data )
  db=$(find_db)
  if [ -n "$db" ]; then
    BK_SQL="$BACKUP_DIR/${prefix}_$ts.sql"
    python3 - "$tmp/data/$(basename "$db")" "$BK_SQL" <<'PY'
import sqlite3, sys
con = sqlite3.connect(sys.argv[1])
with open(sys.argv[2], "w", encoding="utf-8") as f:
    for line in con.iterdump():
        f.write(line + "\n")
PY
  fi
  chmod 600 "$BK_ZIP" "$BK_SQL" 2>/dev/null
  rm -rf "$tmp"
  echo -e "${GREEN}✔ Saved:${RST} $BK_ZIP"
  [ -n "$BK_SQL" ] && echo -e "${GREEN}✔ Saved:${RST} $BK_SQL"
}

# ---------- screen ----------
banner() {
  local P1=' ____   ____ ' P2='|  _ \ / ___|' P3='| |_) | |  _ ' P4='|  __/| |_| |' P5='|_|    \____|'
  local B1=' ____   ___ _____ ' B2='| __ ) / _ \_   _|' B3='|  _ \| | | || |  ' B4='| |_) | |_| || |  ' B5='|____/ \___/ |_|  '
  local pad sp
  pad=$(( ($(cols) - 33) / 2 )); [ "$pad" -lt 0 ] && pad=0
  sp=$(printf '%*s' "$pad" '')
  printf "%s%b%s%b  %s%b\n" "$sp" "$PINK" "$P1" "$BLUE" "$B1" "$RST"
  printf "%s%b%s%b  %s%b\n" "$sp" "$PINK" "$P2" "$BLUE" "$B2" "$RST"
  printf "%s%b%s%b  %s%b\n" "$sp" "$PINK" "$P3" "$BLUE" "$B3" "$RST"
  printf "%s%b%s%b  %s%b\n" "$sp" "$PINK" "$P4" "$BLUE" "$B4" "$RST"
  printf "%s%b%s%b  %s%b\n" "$sp" "$PINK" "$P5" "$BLUE" "$B5" "$RST"
}

header() {
  clear
  echo; banner; echo
  cline "$CYAN" "Telegram: $OWNER_TG"
  cline "$BOLD" "This bot is made for the PasarGuard panel"
  cline "$BOLD" "Reseller panel sales & management bot"
  echo
  cline "$YEL" "~ Fast, Light & Secure ~"
  echo
  local st
  if systemctl is-active --quiet "$SERVICE"; then st="${GREEN}● Running${RST}"; else st="${RED}● Not running${RST}"; fi
  hr
  printf " ${BOLD}Bot status:${RST} %b   ${GRAY}| %s${RST}\n" "$st" "$(date '+%Y-%m-%d %H:%M')"
  hr
  echo
  sec "SETUP";            item 1 "🚀" "Install"; item 2 "🗑️ " "Uninstall"; item 3 "🔄" "Update"; echo
  sec "BACKUP & LOGS";    item 4 "📋" "Get logs"; item 5 "📦" "Get backup"; item 6 "♻️ " "Add backup (restore)"; echo
  sec "SETTINGS";         item 7 "🔑" "Change bot token"; item 8 "🆔" "Change admin IDs"; echo
  hr
  item 0 "🚪" "Exit"
  hr
  echo
}

# ---------- actions ----------
do_install() {
  echo -e "${CYAN}Installing PG Reseller Bot...${RST}"
  apt-get update -y >/dev/null 2>&1
  apt-get install -y python3 python3-venv python3-pip git curl >/dev/null 2>&1
  cd "$APP_DIR" || return
  mkdir -p "$DATA_DIR"
  [ -d venv ] || python3 -m venv venv
  ./venv/bin/pip install -q --upgrade pip
  ./venv/bin/pip install -q -r requirements.txt || { echo -e "${RED}pip install failed${RST}"; return; }

  [ -f "$ENV_FILE" ] || { cp .env.example "$ENV_FILE" 2>/dev/null || touch "$ENV_FILE"; chmod 600 "$ENV_FILE"; }

  if [ -z "$(get_env BOT_TOKEN)" ]; then
    while true; do
      read -rp "Bot token (from @BotFather): " t
      valid_token "$t" && break; echo -e "${RED}Invalid token, try again.${RST}"
    done
    set_env BOT_TOKEN "$t"
  fi
  if [ -z "$(get_env ADMIN_TELEGRAM_IDS)" ]; then
    while true; do
      read -rp "Admin numeric ID(s) (comma separated): " ids
      valid_ids "$ids" && break; echo -e "${RED}Use numbers only, e.g. 123,456${RST}"
    done
    set_env ADMIN_TELEGRAM_IDS "$ids"
  fi
  if [ -z "$(get_env ENCRYPTION_KEY)" ]; then
    set_env ENCRYPTION_KEY "$(./venv/bin/python -c 'from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())')"
    echo -e "${YEL}⚠ ENCRYPTION_KEY created. Keep a backup of .env!${RST}"
  fi

  if [ ! -f "/etc/systemd/system/$SERVICE.service" ]; then
    cat > "/etc/systemd/system/$SERVICE.service" <<UNIT
[Unit]
Description=PG Reseller Bot
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/venv/bin/python -m bot.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
UNIT
    systemctl daemon-reload
  fi
  chmod +x "$APP_DIR/menu.sh"
  ln -sf "$APP_DIR/menu.sh" /usr/local/bin/pgbot
  systemctl enable "$SERVICE" >/dev/null 2>&1
  systemctl restart "$SERVICE"
  sleep 2
  if systemctl is-active --quiet "$SERVICE"; then
    echo -e "${GREEN}✔ Installed and running. Use the command: pgbot${RST}"
    notify_installed
  else
    echo -e "${RED}✘ Service did not start. Check: Get logs (4)${RST}"
  fi
}

do_uninstall() {
  read -rp "Type YES to uninstall the bot service: " a
  [ "$a" = "YES" ] || { echo "Cancelled."; return; }
  make_backup pre-uninstall
  systemctl stop "$SERVICE" 2>/dev/null
  systemctl disable "$SERVICE" 2>/dev/null
  rm -f "/etc/systemd/system/$SERVICE.service" /usr/local/bin/pgbot
  systemctl daemon-reload
  read -rp "Also delete database (data/) and .env? [y/N]: " d
  if [[ "$d" =~ ^[Yy]$ ]]; then rm -rf "$DATA_DIR" "$ENV_FILE"; echo "Data and .env deleted (backup kept in $BACKUP_DIR)."; fi
  echo -e "${GREEN}✔ Uninstalled.${RST} Code folder kept at $APP_DIR"
}

do_update() {
  cd "$APP_DIR" || return
  make_backup pre-update
  echo -e "${CYAN}Pulling latest version...${RST}"
  git pull --ff-only || { echo -e "${RED}git pull failed (local changes?). Bot not restarted.${RST}"; return; }
  ./venv/bin/pip install -q -r requirements.txt
  systemctl restart "$SERVICE"; sleep 2
  systemctl is-active --quiet "$SERVICE" && echo -e "${GREEN}✔ Updated and running.${RST}" || echo -e "${RED}✘ Not running, check logs.${RST}"
}

do_logs() {
  local f="/tmp/pgbot_logs_$(date +%H%M%S).txt"
  journalctl -u "$SERVICE" -n 300 --no-pager > "$f" 2>&1
  tail -n 25 "$f"; echo
  read -rp "Send full log file to admins on Telegram? [y/N]: " a
  [[ "$a" =~ ^[Yy]$ ]] && tg_send "$f" "PG Bot logs $(date '+%F %H:%M')"
  rm -f "$f"
}

do_backup() {
  make_backup pgbot
  echo
  tg_send "$BK_ZIP" "PG Bot backup (zip) $(date '+%F %H:%M')"
  [ -n "$BK_SQL" ] && tg_send "$BK_SQL" "PG Bot backup (sql) $(date '+%F %H:%M')"
}

do_restore() {
  mkdir -p "$BACKUP_DIR"
  echo -e "${CYAN}Latest files in $BACKUP_DIR:${RST}"
  ls -1 "$BACKUP_DIR" 2>/dev/null | grep -E '\.(zip|sql)$' | tail -10
  echo
  read -rp "File name (.zip or .sql) or full path: " f
  [ -z "$f" ] && return
  if [ ! -f "$f" ]; then
    for d in "$BACKUP_DIR" "$APP_DIR" /root "$PWD"; do
      [ -f "$d/$f" ] && { f="$d/$f"; break; }
    done
  fi
  [ -f "$f" ] || { echo -e "${RED}File not found.${RST}"; return; }
  local kind
  case "${f,,}" in *.zip) kind=zip;; *.sql) kind=sql;; *) echo -e "${RED}Only .zip and .sql files are supported.${RST}"; return;; esac
  read -rp "Current data will be replaced. Continue? [y/N]: " a
  [[ "$a" =~ ^[Yy]$ ]] || { echo "Cancelled."; return; }

  make_backup pre-restore
  systemctl stop "$SERVICE" 2>/dev/null
  if [ "$kind" = "zip" ]; then
    local tmp; tmp=$(mktemp -d)
    if ! python3 -m zipfile -e "$f" "$tmp"; then echo -e "${RED}Bad zip file.${RST}"; rm -rf "$tmp"; systemctl start "$SERVICE"; return; fi
    if [ ! -d "$tmp/data" ] && [ ! -f "$tmp/.env" ]; then
      echo -e "${RED}Zip has no data/ or .env inside.${RST}"; rm -rf "$tmp"; systemctl start "$SERVICE"; return
    fi
    [ -d "$tmp/data" ] && { mkdir -p "$DATA_DIR"; cp -a "$tmp/data/." "$DATA_DIR/"; }
    [ -f "$tmp/.env" ] && { cp -a "$ENV_FILE" "$ENV_FILE.before_restore" 2>/dev/null; cp "$tmp/.env" "$ENV_FILE"; chmod 600 "$ENV_FILE"; echo -e "${YEL}.env restored from backup (old one: .env.before_restore)${RST}"; }
    rm -rf "$tmp"
  else
    local db; db=$(find_db); [ -z "$db" ] && db="$DATA_DIR/bot.db"
    mkdir -p "$DATA_DIR"
    python3 - "$db" "$f" <<'PY'
import sqlite3, sys, os
dbp, sql = sys.argv[1:3]
if os.path.exists(dbp):
    os.replace(dbp, dbp + ".old")
for ext in ("-wal", "-shm"):
    if os.path.exists(dbp + ext):
        os.remove(dbp + ext)
con = sqlite3.connect(dbp)
con.executescript(open(sql, encoding="utf-8").read())
con.commit(); con.close()
PY
    echo -e "${YEL}Database file: $db (old one kept as .old). The .env must have the same ENCRYPTION_KEY as the original.${RST}"
  fi
  systemctl start "$SERVICE"; sleep 2
  systemctl is-active --quiet "$SERVICE" && echo -e "${GREEN}✔ Restored and running.${RST}" || echo -e "${RED}✘ Not running, check logs.${RST}"
}

do_token() {
  local old; old=$(get_env BOT_TOKEN)
  echo -e "Current token: ${GRAY}${old:0:10}...${RST}"
  read -rp "New bot token (empty = cancel): " t
  [ -z "$t" ] && return
  valid_token "$t" || { echo -e "${RED}Telegram rejected this token.${RST}"; return; }
  set_env BOT_TOKEN "$t"
  systemctl restart "$SERVICE"; sleep 2
  echo -e "${GREEN}✔ Token changed and bot restarted.${RST}"
}

do_ids() {
  echo -e "Current admin IDs: ${CYAN}$(get_env ADMIN_TELEGRAM_IDS)${RST}"
  read -rp "New admin numeric ID(s), comma separated (empty = cancel): " ids
  [ -z "$ids" ] && return
  valid_ids "$ids" || { echo -e "${RED}Use numbers only, e.g. 123,456${RST}"; return; }
  set_env ADMIN_TELEGRAM_IDS "$ids"
  systemctl restart "$SERVICE"; sleep 2
  echo -e "${GREEN}✔ Admin IDs changed and bot restarted.${RST}"
}

source "$APP_DIR/theme.sh"
# ---------- main loop ----------
while true; do
  header
  printf "${BLUE}➜ ${CYAN}Select [0-8]: ${RST}"
  read -r c
  echo
  case "$c" in
    1) do_install; pause;;
    2) do_uninstall; pause;;
    3) do_update; pause;;
    4) do_logs; pause;;
    5) do_backup; pause;;
    6) do_restore; pause;;
    7) do_token; pause;;
    8) do_ids; pause;;
    0) clear; exit 0;;
    *) ;;
  esac
done
