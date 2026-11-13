from __future__ import annotations

import logging

from . import config, db
from .manage import bar, g, gl, live, nick
from .panel import PanelError, gen_password, get_pg
from .tg import Callback, Message, Router
from .ui import WAIT, btn, fgb, fnum, h, kb, num, show, waiting, xbtn
from .usersadm import jdate

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)
log = logging.getLogger(__name__)


async def card(ev, pid: int) -> None:
    x = await db.row("SELECT * FROM panels WHERE id=?", pid)
    if not x:
        return await show(ev, "پنل پیدا نشد.", kb([[btn("🔙 بازگشت", "a:sold")]]))
    try:
        pg = await get_pg()
        base, cnt = pg.base, await pg.user_counts(x["admin_username"])
    except Exception:
        base, cnt = "", {}
    v = await live(x)
    o = await db.row("SELECT * FROM users WHERE tg_id=?", x["user_id"])
    pr = await db.row("SELECT name FROM products WHERE id=?", x["product_id"]) if x["product_id"] else None
    pw = db.dec(x["pw"]) if x["pw"] else None
    lim, used = v["limit"], v["used"]
    c = lambda k: "—" if cnt.get(k) is None else cnt[k]
    t = (f"📦 <b>{h(nick(x))}</b>{' (تست)' if x['is_test'] else ''}\n"
         f"وضعیت: {v['state']}{' | ⛔ تعلیق‌شده توسط ادمین' if x['status'] == 'suspended' else ''}\n\n"
         f"🆔 کد سرویس: {x['id']}   🛍 محصول: {h(pr['name']) if pr else '—'}\n"
         f"👤 یوزر پنل: <code>{h(x['admin_username'])}</code>\n"
         f"🔐 رمز پنل: {'<code>' + h(pw) + '</code>' if pw else 'ذخیره نشده'}\n📅 تاریخ ساخت: {jdate(x['created'])}\n\n"
         f"🧑 <b>مالک</b>\nنام: {h(o['name']) if o else '—'}   "
         f"{('@' + h(o['username'])) if o and o['username'] else ''}\nآیدی عددی: <code>{x['user_id']}</code>\n\n"
         f"📊 <b>حجم</b>\n📦 سقف: {gl(lim)}\n📥 مصرف: {g(used)}\n")
    if lim and used is not None:
        t += f"📤 باقی‌مانده: {g(max(lim - used, 0))}\n📈 {bar(used, lim)}\n"
    t += (f"\n👥 <b>کاربران داخل پنل</b>\nکل: {c('total')}   🟢 فعال: {c('active')}\n"
          f"🔴 حجم تمام‌شده: {c('limited')}   ⏳ منقضی: {c('expired')}   ⛔ غیرفعال: {c('disabled')}")
    if x["expires"]:
        t += f"\n\n⌛ پایان اعتبار: {jdate(x['expires'])[:10]}"
    if x["note"]:
        t += f"\n\n📝 یادداشت: {h(x['note'])}"
    i = pid
    rows = [*([[xbtn("🖥 ورود به پنل وب", url=f"{base}/dashboard")]] if base else []),
            [btn("➕ افزایش حجم", f"z:ag:{i}", style="success"), btn("➖ کاهش حجم", f"z:rg:{i}", style="danger")],
            [btn("✅ فعال‌سازی" if x["status"] == "suspended" else "⛔ غیرفعال‌سازی", f"a:spt:{i}"),
             btn("🔑 رمز جدید", f"z:pw:{i}")],
            [btn("🔁 انتقال به کاربر دیگر", f"z:tr:{i}"), btn("✉️ پیام به مالک", f"z:sm:{i}")],
            [btn("🧑 کارت مالک", f"x:u:{x['user_id']}"), btn("📝 یادداشت", f"z:nt:{i}")]]
    if x["expires"]:
        rows.append([btn("⏳ تمدید", f"a:spe:{i}")])
    rows += [[btn("🔄 بروزرسانی", f"z:r:{i}", style="primary"), btn("🗑 حذف", f"a:spd:{i}", style="danger")],
             [btn("🔙 بازگشت", "a:sold")]]
    await show(ev, t, kb(rows))


async def change_gb(ev, x, sign: int, delta: float) -> None:
    pid = x["id"]
    v = await live(x)
    cur = v["limit"] if v["limit"] is not None else (x["gb"] or None)
    if not cur:
        return await show(ev, "حجم فعلی پنل نامعلوم یا نامحدود است؛ تغییر ممکن نیست.", kb([[btn("🔙 بازگشت", f"z:r:{pid}")]]))
    new = round(cur + sign * delta, 2)
    if new <= 0:
        return await show(ev, "حجم نهایی باید بیشتر از صفر باشد؛ مقدار کمتری بفرست.", None)
    try:
        await (await get_pg(x["server_id"])).set_limit(x["admin_username"], new)
    except Exception as e:
        log.warning("set_limit failed: %s", e)
        return await show(ev, f"❌ تغییر حجم ناموفق بود:\n<code>{h(e)}</code>", kb([[btn("🔙 بازگشت", f"z:r:{pid}")]]))
    WAIT.pop(ev.from_user.id, None)
    await db.run("UPDATE panels SET gb=? WHERE id=?", new, pid)
    await db.ev("admin_gb", x["user_id"], f"{x['admin_username']}:{new}")
    await card(ev, pid)


@router.callback("z:")
async def zcb(c: Callback):
    p = c.data.split(":")
    a, adm, pid = p[1], c.from_user.id, int(p[2])
    WAIT.pop(adm, None)
    x = await db.row("SELECT * FROM panels WHERE id=?", pid)
    if not x:
        return await c.answer("پیدا نشد.", show_alert=True)
    back = kb([[btn("🔙 بازگشت", f"z:r:{pid}")]])
    if a == "r":
        return await card(c, pid)
    if a in ("ag", "rg"):
        WAIT[adm] = ("z_gb", (pid, 1 if a == "ag" else -1))
        return await show(c, f"مقدار حجم برای {'اضافه' if a == 'ag' else 'کم'} کردن را (گیگ) بفرست. مثال: <code>50</code>", back)
    if a == "pw":
        pw = gen_password()
        try:
            await (await get_pg(x["server_id"])).set_password(x["admin_username"], pw)
        except Exception as e:
            return await show(c, f"❌ {h(e)}", back)
        await db.run("UPDATE panels SET pw=? WHERE id=?", db.enc(pw), pid)
        return await card(c, pid)
    if a == "tr":
        WAIT[adm] = ("z_tr", pid)
        return await show(c, "آیدی عددی مالک جدید را بفرست (باید ربات را استارت کرده باشد):", back)
    if a == "sm":
        WAIT[adm] = ("z_sm", pid)
        return await show(c, "متن پیام برای مالک این پنل را بفرست:", back)
    if a == "nt":
        WAIT[adm] = ("z_nt", pid)
        return await show(c, "یادداشت را بفرست (برای پاک کردن 0):", back)
    await c.answer()


@router.message(waiting("z_"))
async def zwait(m: Message):
    adm = m.from_user.id
    kind, arg = WAIT[adm]
    text = (m.text or "").strip()
    if kind == "z_gb":
        pid, sign = arg
        v = fnum(text)
        if not v or v <= 0:
            return await m.answer("یک عدد مثبت بفرست.")
        return await change_gb(m, await db.row("SELECT * FROM panels WHERE id=?", pid), sign, v)
    x = await db.row("SELECT * FROM panels WHERE id=?", arg)
    if not x:
        WAIT.pop(adm, None)
        return await m.answer("پنل پیدا نشد.")
    if kind == "z_tr":
        to = num(text)
        if not to or not await db.row("SELECT 1 FROM users WHERE tg_id=?", to):
            return await m.answer("این کاربر ربات را استارت نکرده؛ آیدی دیگری بفرست.")
        WAIT.pop(adm, None)
        await db.run("UPDATE panels SET user_id=? WHERE id=?", to, arg)
        await db.ev("transfer", x["user_id"], f"{x['admin_username']}>{to}")
        try:
            await m.bot.send_message(to, f"📥 سرویس <b>{h(nick(x))}</b> به تو منتقل شد.")
        except Exception:
            pass
    elif kind == "z_sm":
        WAIT.pop(adm, None)
        try:
            await m.bot.send_message(x["user_id"], text)
        except Exception as e:
            return await m.answer(f"❌ ارسال نشد: {h(e)}")
    elif kind == "z_nt":
        WAIT.pop(adm, None)
        await db.run("UPDATE panels SET note=? WHERE id=?", "" if text == "0" else text[:300], arg)
    await card(m, arg)
