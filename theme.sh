# ---- Custom look ----
OWNER_TG="@Amiralihdtt"
SLOGAN1="Reseller panel bot for easier selling"
SLOGAN2="Simple, fast & fully manageable"

header() {
  clear
  echo; echo; echo
  cline "$PINK" '██████╗  ██████╗     ██████╗  ██████╗ ████████╗'
  cline "$PINK" '██╔══██╗██╔════╝     ██╔══██╗██╔═══██╗╚══██╔══╝'
  cline "$PINK" '██████╔╝██║  ███╗    ██████╔╝██║   ██║   ██║   '
  cline "$BLUE" '██╔═══╝ ██║   ██║    ██╔══██╗██║   ██║   ██║   '
  cline "$BLUE" '██║     ╚██████╔╝    ██████╔╝╚██████╔╝   ██║   '
  cline "$BLUE" '╚═╝      ╚═════╝     ╚═════╝  ╚═════╝    ╚═╝   '
  echo; echo; echo
  cline "$CYAN" "Telegram: $OWNER_TG"
  echo
  cline "$BOLD" "$SLOGAN1"
  cline "$BOLD" "$SLOGAN2"
  echo
  cline "$YEL" "~ Secure & Anonymous ~"
  echo; echo
  hr
  if systemctl is-active --quiet "$SERVICE"; then
    st="${GREEN}● Running${RST}"
  else
    st="${RED}● Stopped${RST}"
  fi
  echo -e " Bot status: $st   ${GRAY}| $(date '+%Y-%m-%d %H:%M')${RST}"
  hr
  echo
  sec "SETUP"
  item 1 "🚀" "Install"
  item 2 "🗑 " "Uninstall"
  item 3 "🔄" "Update"
  echo
  sec "BACKUP & LOGS"
  item 4 "📋" "Get logs"
  item 5 "📦" "Get backup"
  item 6 "♻️ " "Add backup (restore)"
  echo
  sec "SETTINGS"
  item 7 "🔑" "Change bot token"
  item 8 "🆔" "Change admin IDs"
  item 9 "🌐" "Web panel setup"
  echo
  hr
  item 0 "🚪" "Exit"
  hr
  echo
}

# ---- Message sent to admins after install ----
notify_installed() {
  local token ids id msg
  token=$(get_env BOT_TOKEN); ids=$(get_env ADMIN_TELEGRAM_IDS)
  if [ -z "$token" ] || [ -z "$ids" ]; then return; fi
  msg=$'✅ ربات شما ساخته شد\n\nبرای ورود به پنل ادمین بزنید:\n/admin\n\n🤖 ساخته شده از CAPITAN VPN'
  for id in ${ids//,/ }; do
    curl -s -m 15 "https://api.telegram.org/bot${token}/sendMessage" \
      --data-urlencode "chat_id=$id" \
      --data-urlencode "text=$msg" >/dev/null
  done
}
