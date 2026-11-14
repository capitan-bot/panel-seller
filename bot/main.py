from __future__ import annotations

import asyncio
import logging
import time

from . import admin, btnadm, kbmenu, usagecard, uiadm, config, db, manage, paneladm, report, stats, user, usersadm, warn
from .panel import get_pg
from . import monitor
from . import backup
from .tg import Bot, Dispatcher, TgError
from .ui import h, load_ov

log = logging.getLogger("bot")


async def gate(ev) -> bool:
    """Registers every user and silently ignores blocked ones."""
    u = ev.from_user
    is_new = not await db.row("SELECT 1 FROM users WHERE tg_id=?", u.id)
    await db.touch_user(u.id, u.full_name, u.username)
    if is_new:
        report.on_new_user(u)
    if u.id not in config.ADMIN_IDS and await db.is_blocked(u.id):
        return False
    return True


async def expiry_loop(bot: Bot) -> None:
    """Every 10 minutes: disable reseller admins whose time is over."""
    while True:
        try:
            due = await db.rows("SELECT * FROM panels WHERE status='active' AND expires>0 AND expires<?", int(time.time()))
            if due:
                for p in due:
                    try:
                        await (await get_pg(p["server_id"])).set_disabled(p["admin_username"], True)
                    except Exception as e:
                        if "404" not in str(e):
                            log.exception("expire %s", p["admin_username"])
                            continue
                        log.warning("expire %s: admin already gone from panel, marking expired", p["admin_username"])
                    await db.run("UPDATE panels SET status='expired' WHERE id=?", p["id"])
                    try:
                        await bot.send_message(p["user_id"], f"⏳ پنل <code>{h(p['admin_username'])}</code> منقضی و غیرفعال شد. "
                                                             "از «پنل‌های من» تمدیدش کن.")
                    except TgError:
                        pass
        except Exception:
            log.exception("expiry loop")
        await asyncio.sleep(600)


async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)   # httpx logs full URLs, which contain the bot token
    if not config.BOT_TOKEN or not config.ENCRYPTION_KEY or not config.ADMIN_IDS:
        raise SystemExit("BOT_TOKEN, ADMIN_TELEGRAM_IDS and ENCRYPTION_KEY must be set in .env")
    await db.init()
    await load_ov()
    bot = Bot(config.BOT_TOKEN)
    report.init(bot)
    dp = Dispatcher(gate)
    dp.include(admin.router)
    dp.include(stats.router)
    dp.include(paneladm.router)
    dp.include(btnadm.router)
    dp.include(kbmenu.router)
    dp.include(usagecard.router)
    dp.include(uiadm.router)
    dp.include(usersadm.router)
    dp.include(manage.router)
    dp.include(user.router)
    await bot.api("deleteWebhook")   # a leftover webhook blocks polling
    log.info("started")
    task = asyncio.create_task(expiry_loop(bot))
    task2 = asyncio.create_task(warn.warn_loop(bot))
    task3 = asyncio.create_task(monitor.monitor_loop(bot))
    task4 = asyncio.create_task(backup.backup_loop(bot))
    try:
        await dp.poll(bot)
    finally:
        task.cancel()
        task2.cancel()
        task3.cancel()
        task4.cancel()
        await bot.close()
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
