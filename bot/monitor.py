from __future__ import annotations

import asyncio
import logging
import time

from . import db
from .panel import get_pg
from .ui import h, notify_admins

log = logging.getLogger("monitor")
STATE: dict = {}


async def monitor_loop(bot) -> None:
    await asyncio.sleep(30)
    while True:
        try:
            for r in await db.rows("SELECT id, name FROM servers"):
                if await db.get_setting(f"mon_{r['id']}", "1") != "1":
                    continue
                st = STATE.setdefault(r["id"], {"fails": 0, "down": False, "since": 0})
                err = ""
                try:
                    await (await get_pg(r["id"])).test()
                except Exception as e:
                    err = str(e)[:150] or type(e).__name__
                if err:
                    st["fails"] += 1
                    if st["fails"] >= 2 and not st["down"]:
                        st["down"], st["since"] = True, int(time.time())
                        await notify_admins(bot, f"🔴 <b>پنل «{h(r['name'])}» در دسترس نیست</b>\n<code>{h(err)}</code>")
                else:
                    if st["down"]:
                        mins = max(1, (int(time.time()) - st["since"]) // 60)
                        await notify_admins(bot, f"🟢 پنل «{h(r['name'])}» دوباره در دسترس است (قطعی حدود {mins} دقیقه).")
                    st["fails"], st["down"] = 0, False
        except Exception:
            log.exception("monitor loop")
        await asyncio.sleep(300)
