from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _load_env() -> None:
    p = ROOT / ".env"
    if not p.exists():
        return
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


_load_env()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = {
    int(x) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").replace(" ", "").split(",")
    if x.strip().lstrip("-").isdigit()
}
ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")
DB_PATH = os.getenv("DB_PATH", str(ROOT / "data" / "bot.db"))
VERIFY_SSL = os.getenv("PANEL_VERIFY_SSL", "1") != "0"

# owners come from .env; extra admins / operators are loaded from the staff table
OWNER_IDS = set(ADMIN_IDS)
OPERATOR_IDS: set = set()
