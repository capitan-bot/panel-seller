#!/usr/bin/env bash
# PG Reseller Bot - install / uninstall / update menu
DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
SERVICE=pgresellerbot
cd "$DIR" || exit 1

do_install() { bash "$DIR/install.sh"; }

do_update() {
  [ -d .git ] || { echo "Not a git repository."; return; }
  git pull --ff-only || { echo "git pull failed; nothing changed."; return; }
  venv/bin/pip install -q -r requirements.txt
  systemctl restart "$SERVICE"
  sleep 4
  systemctl is-active "$SERVICE" && echo "Update finished."
}

do_uninstall() {
  read -r -p "Stop and remove the service? [y/N]: " a
  [[ "$a" =~ ^[Yy]$ ]] || { echo "Cancelled."; return; }
  systemctl disable --now "$SERVICE" 2>/dev/null || true
  rm -f /etc/systemd/system/$SERVICE.service
  systemctl daemon-reload
  echo "Service removed. data/ and .env are kept."
  echo "(.env holds ENCRYPTION_KEY; without it the saved panel password cannot be read.)"
  read -r -p "Type DELETE to also remove data/ and .env, or Enter to keep: " b
  if [ "$b" = "DELETE" ]; then rm -rf data .env; echo "Data removed."; fi
}

while true; do
  echo
  echo "  1) Install"
  echo "  2) Uninstall"
  echo "  3) Update"
  echo "  0) Exit"
  echo
  read -r -p "Select [0-3]: " choice
  case "$choice" in
    1) do_install ;;
    2) do_uninstall ;;
    3) do_update ;;
    0) exit 0 ;;
    *) echo "Invalid choice." ;;
  esac
done
