from __future__ import annotations

import asyncio
import logging

from . import db
from .panel import get_pg
from .tg import Bot
from .ui import btn, days_left, fgb, h, kb

log = logging.getLogger(__name__)
TEXT = {80: "⚠️ حجم سرویس <b>{n}</b> به <b>۸۰٪</b> رسید.",
        95: "🚨 حجم سرویس <b>{n}</b> به <b>۹۵٪</b> رسید و رو به اتمام است!",
        100: "⛔ حجم سرویس <b>{n}</b> <b>تمام شد</b>."}


def level(used: float, limit: float) -> int:
    pc = used * 100 / limit
    return 100 if pc >= 100 else 95 if pc >= 95 else 80 if pc >= 80 else 0


async def check(bot: Bot) -> int:
    """Warns owners whose volume panel crossed 80/95/100 %. Returns how many messages were sent."""
    if await db.get_setting("warn_on") == "0":
        return 0
    ps = await db.rows("SELECT * FROM panels WHERE status='active' AND gb>0")
    if not ps:
        return 0
    pg = await get_pg()
    usage = await pg.admins_usage()
    sent = 0
    for x in ps:
        lim_used = usage.get(x["admin_username"])
        if lim_used is None:
            i = await pg.admin_info(x["admin_username"])
            lim_used = (i["limit"], i["used"]) if i else None
        if not lim_used or not lim_used[0] or lim_used[1] is None:
            continue
        lim, used = lim_used
        lv = level(used, lim)
        if lv == x["warn"]:
            continue
        await db.run("UPDATE panels SET warn=? WHERE id=?", lv, x["id"])
        if lv < x["warn"]:
            continue                       # volume was added: just re-arm the warnings
        nm = x["nick"] or x["admin_username"]
        try:
            await bot.send_message(
                x["user_id"], TEXT[lv].format(n=h(nm)) + f"\n📤 باقی‌مانده: {fgb(max(lim - used, 0))} از {fgb(lim)}",
                kb([[btn("💳 خرید حجم", f"m:bv:{x['id']}", style="success")],
                    [btn("⚙️ مدیریت سرویس", f"m:m:{x['id']}", style="primary")]]))
            sent += 1
        except Exception:
            log.info("warn: cannot message %s", x["user_id"])
        await asyncio.sleep(0.1)
    return sent


DAY_TEXT = {3: "⏳ اعتبار سرویس <b>{n}</b> تا <b>{d} روز</b> دیگر تمام می‌شود.",
            1: "🚨 اعتبار سرویس <b>{n}</b> <b>کمتر از ۱ روز</b> مانده است!"}


async def check_days(bot: Bot) -> int:
    """Warns owners of time-limited panels 3 days and 1 day before expiry (volume panels never expire)."""
    if await db.get_setting("warn_on") == "0":
        return 0
    try:
        await db.run("ALTER TABLE panels ADD COLUMN wd INTEGER NOT NULL DEFAULT 0")
    except Exception:
        pass                               # column already exists
    ps = await db.rows("SELECT * FROM panels WHERE status='active' AND expires>0")
    sent = 0
    for x in ps:
        d = days_left(x["expires"])
        lv = 1 if d <= 1 else 3 if d <= 3 else 0
        if lv == 0:
            if x["wd"]:
                await db.run("UPDATE panels SET wd=0 WHERE id=?", x["id"])   # extended: re-arm
            continue
        if x["wd"] and lv >= x["wd"]:
            continue                       # this level was already sent
        await db.run("UPDATE panels SET wd=? WHERE id=?", lv, x["id"])
        nm = x["nick"] or x["admin_username"]
        try:
            await bot.send_message(x["user_id"], DAY_TEXT[lv].format(n=h(nm), d=d),
                                   kb([[btn("⚙️ مدیریت سرویس", f"m:m:{x['id']}", style="primary")]]))
            sent += 1
        except Exception:
            log.info("warn-days: cannot message %s", x["user_id"])
        await asyncio.sleep(0.1)
    return sent


async def warn_loop(bot: Bot) -> None:
    await asyncio.sleep(60)
    while True:
        try:
            await check(bot)
            await check_days(bot)
        except Exception:
            log.exception("warn loop")
        await asyncio.sleep(1800)
