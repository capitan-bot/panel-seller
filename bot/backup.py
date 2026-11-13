"""Database backup: consistent SQLite snapshot (gzip) -> report topic "backup" (or the owners' DM)."""
from __future__ import annotations

import asyncio
import gzip
import logging
import os
import sqlite3
import tempfile
import time

from . import config, db, report
from .ui import h, notify_admins

log = logging.getLogger("backup")


def _snapshot(src: str, dst: str) -> bytes:
    a, b = sqlite3.connect(src), sqlite3.connect(dst)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
    with open(dst, "rb") as f:
        return gzip.compress(f.read(), 6)


async def make_backup():
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        data = await asyncio.to_thread(_snapshot, config.DB_PATH, tmp)
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass
    return time.strftime("pgbot-%Y%m%d-%H%M.db.gz"), data


async def run_backup(bot, reason: str = "auto") -> str:
    """Makes a backup and sends it. Returns '' on success, otherwise an error text."""
    try:
        report.init(bot)
        name, data = await make_backup()
        users = (await db.row("SELECT COUNT(*) c FROM users"))["c"]
        pans = (await db.row("SELECT COUNT(*) c FROM panels"))["c"]
        cap = (f"💾 <b>بکاپ {'دستی' if reason == 'manual' else 'خودکار'}</b>\n🕒 {time.strftime('%Y-%m-%d %H:%M')}\n"
               f"📦 حجم: {len(data) / 1024:.0f} KB\n👥 کاربران: {users} | 🖥 سرویس‌ها: {pans}")
        ok = await report.send_file("backup", name, data, cap)
        if not ok:
            for a in sorted(config.OWNER_IDS):
                try:
                    await bot.send_document(a, name, data, cap)
                    ok = True
                except Exception as e:
                    log.warning("backup to owner %s failed: %s", a, e)
        if not ok:
            return "ارسال بکاپ ناموفق بود (ربات در گروه گزارش ادمین با دسترسی Manage Topics باشد)."
        await db.set_setting("backup_last", str(int(time.time())))
        return ""
    except Exception as e:
        log.exception("backup")
        return str(e)[:150] or type(e).__name__


async def backup_loop(bot) -> None:
    await asyncio.sleep(60)
    while True:
        try:
            if await db.get_setting("backup_on", "1") == "1":
                hrs = int(await db.get_setting("backup_hours", "2") or 2)
                last = int(await db.get_setting("backup_last", "0") or 0)
                if time.time() - last >= hrs * 3600 - 60:
                    err = await run_backup(bot)
                    if err:
                        await db.set_setting("backup_last", str(int(time.time()) - hrs * 3600 + 1800))   # retry in 30 min
                        await notify_admins(bot, f"⚠️ بکاپ خودکار ناموفق بود:\n<code>{h(err)}</code>")
        except Exception:
            log.exception("backup loop")
        await asyncio.sleep(300)
