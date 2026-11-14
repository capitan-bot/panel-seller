from __future__ import annotations

import asyncio

import httpx

from . import config, db
from . import manage as M
from .cardimg import render
from .tg import Callback, Router
from .ui import btn, h, kb, show

router = Router(guard=lambda ev: True)


async def collect(x) -> dict:
    v = await M.live(x)
    lim, used = v["limit"], v["used"]
    has = bool(lim) and used is not None
    return {
        "nick": x["admin_username"],
        "state": v["state"] or "—",
        "limit": M.gl(lim),
        "used": M.g(used),
        "remain": M.g(max(lim - used, 0)) if has else "—",
        "users": "—" if v["users"] is None else str(v["users"]),
        "created": M.fdate(x["created"]),
        "pct": max(0.0, min(100.0, used * 100.0 / lim)) if has else None,
    }


@router.callback("cd:")
async def cd(c: Callback):
    uid = c.from_user.id
    pid = c.data.split(":")[1]
    try:
        cid = getattr(c, "id", None)
        if cid:
            try:
                await c.bot.api("answerCallbackQuery", callback_query_id=cid, text="در حال ساخت کارت...")
            except Exception:
                pass
        x = await db.row("SELECT * FROM panels WHERE id=?", int(pid))
        if not x or (x["user_id"] != uid and uid not in config.ADMIN_IDS):
            return await show(c, "سرویس پیدا نشد.", kb([[btn("📦 پنل‌های من", "u:panels")]]))
        png = await asyncio.to_thread(render, await collect(x))
        r = await c.bot.http.post("sendPhoto", data={"chat_id": str(uid), "caption": "🪪 کارت مصرف سرویس"},
                                  files={"photo": ("usage-card.png", png, "image/png")},
                                  timeout=httpx.Timeout(60.0, connect=10.0))
        j = r.json()
        if not j.get("ok"):
            raise RuntimeError(j.get("description", "sendPhoto failed"))
    except Exception as e:
        import traceback
        traceback.print_exc()
        await show(c, "❌ ساخت کارت ناموفق بود: <code>" + h(repr(e)) + "</code>",
                   kb([[btn("🔙 بازگشت", f"m:m:{pid}")]]))
