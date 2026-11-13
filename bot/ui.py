from __future__ import annotations

import html
import logging
import re
import time
from datetime import datetime, timezone

from . import config, db
from .tg import Bot, Callback, Message, TgError

log = logging.getLogger(__name__)

# admin/user "waiting for the next message" state: {user_id: (kind, arg)}
WAIT: dict[int, tuple] = {}

STYLES = ["", "primary", "success", "danger"]
STYLE_NAME = {"": "بدون رنگ", "primary": "آبی", "success": "سبز", "danger": "قرمز"}
STATUS = {"active": "🟢 فعال", "expired": "🔴 منقضی", "suspended": "⛔ تعلیق"}
_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def h(s) -> str:
    return html.escape(str(s))


def fmt(n) -> str:
    return f"{int(n):,}"


def num(s: str) -> int | None:
    s = (s or "").translate(_DIG).replace(",", "").replace("،", "").strip()
    try:
        return int(s)
    except ValueError:
        return None


def fnum(s: str) -> float | None:
    """'1', '0.5', '۱٫۵' -> float; anything else -> None."""
    s = (s or "").translate(_DIG).replace("٫", ".").strip()
    return float(s) if re.fullmatch(r"\d+(\.\d+)?", s) else None


def fgb(x) -> str:
    x = float(x)
    return f"{x / 1024:g} TB" if x >= 1024 and x % 1024 == 0 else f"{x:g} GB"


def fdate(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d")


def days_left(ts: int) -> int:
    return max(0, -(-(ts - int(time.time())) // 86400))


OV: dict = {}   # admin overrides per button label: {default_text: (title, emoji_id, style)}


async def load_ov() -> None:
    OV.clear()
    for r in await db.rows("SELECT * FROM ubtn"):
        OV[r["key"]] = (r["title"], r["emoji_id"], r["style"])


def _build(text: str, emoji: str, style: str, ov: bool, extra: dict) -> dict:
    o = OV.get(text) if ov else None
    if o:
        text, emoji = o[0] or text, o[1] or emoji
        style = "" if o[2] == "none" else (o[2] or style)
    b = {"text": text, **extra}
    if emoji:
        b["icon_custom_emoji_id"] = emoji
    if style in ("primary", "success", "danger"):
        b["style"] = style
    return b


def btn(text: str, data: str, emoji: str = "", style: str = "", ov: bool = True) -> dict:
    """Inline ("glass") button. `emoji` = premium custom emoji id, `style` = primary/success/danger.
    User-facing buttons take the admin's overrides (ubtn table) by their default label."""
    return _build(text, emoji, style, ov and not data.startswith(("a:", "x:", "b:")), {"callback_data": data})


def pbtn(text: str, data: str) -> dict:
    """Preview of an overridable button (used by the admin editor)."""
    return _build(text, "", "", True, {"callback_data": data})


def xbtn(text: str, style: str = "", **extra) -> dict:
    """Button with a non-callback action (url / copy_text); same overrides as btn()."""
    return _build(text, "", style, True, extra)


def kb(rows) -> dict:
    return {"inline_keyboard": rows}


def chunk(items: list, n: int = 2) -> list[list]:
    return [items[i:i + n] for i in range(0, len(items), n)]


async def main_menu(is_admin: bool = False) -> dict:
    rows = await db.rows("SELECT * FROM buttons WHERE enabled=1 ORDER BY sort")
    layout = chunk([btn(r["title"], "u:" + r["key"], r["emoji_id"], r["style"], ov=False) for r in rows], 2)
    if is_admin:
        layout.append([btn("🛠 پنل مدیریت", "a:home")])
    return kb(layout)


def panel_text(p) -> str:
    extra = " (تست)" if p["is_test"] else ""
    exp = f"{fdate(p['expires'])} ({days_left(p['expires'])} روز مانده)" if p["expires"] else "♾ نامحدود"
    vol = f"\n💎 حجم: {fgb(p['gb'])}" if p["gb"] else ""
    return f"📦 <b>{h(p['admin_username'])}</b>{extra}\n{STATUS.get(p['status'], p['status'])}{vol}\n⏳ اعتبار: {exp}"


def panel_label(p) -> str:
    return f"{p['admin_username']} • " + (fgb(p["gb"]) if p["gb"] else f"{days_left(p['expires'])} روز")


async def show(ev: Message | Callback, text: str, markup: dict | None = None) -> None:
    if isinstance(ev, Callback):
        try:
            await ev.message.edit_text(text, markup)
        except TgError as e:
            if "not modified" not in str(e):
                await ev.message.answer(text, markup)
        try:
            await ev.answer()
        except TgError:
            pass
    else:
        await ev.answer(text, markup)


def waiting(prefix: str):
    def check(m: Message) -> bool:
        return m.from_user is not None and WAIT.get(m.from_user.id, ("",))[0].startswith(prefix)
    return check


async def notify_admins(bot: Bot, text: str) -> None:
    for a in config.ADMIN_IDS:
        try:
            await bot.send_message(a, text)
        except Exception:
            log.warning("cannot notify admin %s", a)
