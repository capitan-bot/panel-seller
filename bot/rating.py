from __future__ import annotations

import logging
import time

from . import db
from .tg import Callback, Message, Router
from .ui import WAIT, btn, h, kb, notify_admins, show, waiting

log = logging.getLogger("rating")
router = Router(guard=lambda ev: True)
DDL = ("CREATE TABLE IF NOT EXISTS ratings(id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER NOT NULL UNIQUE, "
       "user_id INTEGER NOT NULL, stars INTEGER NOT NULL DEFAULT 0, comment TEXT NOT NULL DEFAULT '', "
       "rated INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, rated_at INTEGER NOT NULL DEFAULT 0)")


def home():
    return kb([[btn("🏠 منوی اصلی", "u:home")]])


async def mine(uid: int, sid: int):
    await db.run(DDL)
    r = await db.row("SELECT * FROM ratings WHERE sale_id=?", sid)
    return r if r and r["user_id"] == uid else None


async def alert(bot, uid: int, sid: int, stars: int, comment: str = "") -> None:
    info = await db.row("SELECT panel, kind FROM sales WHERE id=?", sid) if sid > 0 else None
    t = ("💬 <b>نظر مشتری</b> " if comment else "⚠️ <b>امتیاز پایین</b> ") + "⭐" * stars + f"\n\n👤 کاربر: <code>{uid}</code>\n"
    if info:
        t += f"🖥 {h(info['panel'] or '—')} · {h(info['kind'])}\n"
    if comment:
        t += f"\n{h(comment)}"
    await notify_admins(bot, t)


async def _cb(c: Callback) -> None:
    uid = c.from_user.id
    p = c.data.split(":")
    WAIT.pop(uid, None)
    bad = "این نظرسنجی معتبر نیست."
    if len(p) < 3:
        return await show(c, bad, home())
    if p[1] in ("c", "s"):
        act, sid, stars = p[1], int(p[2]), 0
    else:
        act, sid, stars = "r", int(p[1]), int(p[2])
    r = await mine(uid, sid)
    if not r:
        return await show(c, bad, home())
    if act == "s":
        return await show(c, "🙏 ممنون از وقتی که گذاشتی.", home())
    if act == "c":
        if not r["rated"]:
            return await show(c, bad, home())
        WAIT[uid] = ("rt_c", sid)
        return await show(c, "✍️ نظرت را در یک پیام بنویس (حداکثر ۳۰۰ حرف). برای انصراف /start بزن.",
                          kb([[btn("⏭ بیخیال", f"rt:s:{sid}")]]))
    if not 1 <= stars <= 5:
        return await show(c, bad, home())
    if r["rated"]:
        return await show(c, "✅ قبلاً امتیاز دادی: " + "⭐" * r["stars"] + "\nممنون!", home())
    await db.run("UPDATE ratings SET stars=?, rated=1, rated_at=? WHERE sale_id=? AND rated=0", stars, int(time.time()), sid)
    if stars <= 2:
        await alert(c.bot, uid, sid, stars)
    if stars >= 4:
        return await show(c, "🎉 ممنون! امتیاز " + "⭐" * stars + " ثبت شد.\nخوشحالیم که راضی بودی.", home())
    return await show(c, "🙏 ممنون از صراحتت. امتیاز " + "⭐" * stars + " ثبت شد.\nبگو چه چیزی باید بهتر شود؟ (اختیاری)",
                      kb([[btn("✍️ نوشتن نظر", f"rt:c:{sid}")], [btn("🏠 منوی اصلی", "u:home")]]))


@router.callback("rt:")
async def rtcb(c: Callback):
    try:
        await _cb(c)
    except Exception:
        log.exception("rating callback")
        try:
            await c.answer("خطایی رخ داد؛ دوباره امتحان کن.")
        except Exception:
            pass


@router.message(waiting("rt_"))
async def rtmsg(m: Message):
    uid = m.from_user.id
    try:
        _k, sid = WAIT[uid]
        text = (m.text or "").strip()
        if not text:
            return await m.answer("یک متن بفرست (یا /start برای انصراف).")
        text = text[:300]
        r = await mine(uid, sid)
        WAIT.pop(uid, None)
        if not r:
            return
        await db.run("UPDATE ratings SET comment=? WHERE sale_id=?", text, sid)
        if r["stars"] <= 3:
            await alert(m.bot, uid, sid, r["stars"], text)
        await m.answer("✅ ممنون، نظرت ثبت شد.", home())
    except Exception:
        log.exception("rating message")
        WAIT.pop(uid, None)
