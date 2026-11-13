from __future__ import annotations

import logging
from datetime import datetime, timezone

from . import config, db
from .panel import PanelError
from .tg import Callback, Message, Router
from .ui import WAIT, xbtn, btn, fgb, fmt, fnum, h, kb, num, show, waiting

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)
log = logging.getLogger(__name__)
PAGE = 8
NOBUY = "NOT EXISTS(SELECT 1 FROM panels p WHERE p.user_id=u.tg_id AND p.is_test=0)"
LISTS = {  # kind: (title, where, order)
    "all": ("👥 تمام کاربران", "1", "u.created DESC"),
    "bal": ("💰 کاربران دارای موجودی", "u.balance>0", "u.balance DESC"),
    "blk": ("🚫 کاربران مسدود", "u.blocked=1", "u.created DESC"),
    "nob": ("🛒 کاربرانی که خرید ندارند", NOBUY, "u.created DESC"),
    "act": ("✅ کاربران فعال (پنل فعال دارند)", "EXISTS(SELECT 1 FROM panels p WHERE p.user_id=u.tg_id AND p.status='active')",
            "u.created DESC"),
    "top": ("🏆 بیشترین خرید", "NOT " + NOBUY, "(SELECT COUNT(*) FROM panels p WHERE p.user_id=u.tg_id AND p.is_test=0) DESC"),
}


def jdate(ts: int) -> str:
    """Unix time -> Jalali 'YYYY/MM/DD HH:MM' (Tehran, UTC+3:30)."""
    if not ts:
        return "—"
    d = datetime.fromtimestamp(ts + 12600, timezone.utc)
    gy, gm, gd = d.year, d.month, d.day
    g_d = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    jm, jd = (1 + days // 31, 1 + days % 31) if days < 186 else (7 + (days - 186) // 30, 1 + (days - 186) % 30)
    return f"{jy}/{jm:02d}/{jd:02d} {d.hour:02d}:{d.minute:02d}"


def ulabel(u, extra: str = "") -> str:
    return f"{(u['name'] or '?')[:18]} • {u['tg_id']}{' 🚫' if u['blocked'] else ''}{extra}"


async def user_menu(ev) -> None:
    rows = [[btn(t, f"x:l:{k}:0")] for k, (t, _, _) in LISTS.items()]
    rows.insert(0, [btn("🔎 جستجوی کاربر", "x:s", style="primary")])
    await show(ev, "👥 <b>مدیریت کاربران</b>", kb(rows + [[btn("🔙 مدیریت", "a:home")]]))


async def user_list(ev, kind: str, page: int) -> None:
    title, where, order = LISTS[kind]
    total = (await db.row(f"SELECT COUNT(*) c FROM users u WHERE {where}"))["c"]
    us = await db.rows(f"SELECT u.* FROM users u WHERE {where} ORDER BY {order} LIMIT {PAGE} OFFSET {page * PAGE}")
    rows = [[btn(ulabel(u, f" • {fmt(u['balance'])}" if kind == "bal" else ""), f"x:u:{u['tg_id']}")] for u in us]
    nav = []
    if page > 0:
        nav.append(btn("⬅️ قبلی", f"x:l:{kind}:{page - 1}"))
    if (page + 1) * PAGE < total:
        nav.append(btn("بعدی ➡️", f"x:l:{kind}:{page + 1}"))
    await show(ev, f"{title}\nتعداد: {total}" + ("" if us else "\n\nموردی نیست."),
               kb(rows + ([nav] if nav else []) + [[btn("🔙 کاربران", "x:m")]]))


async def card(ev, uid: int) -> None:
    u = await db.row("SELECT * FROM users WHERE tg_id=?", uid)
    if not u:
        return await show(ev, "کاربر پیدا نشد.", kb([[btn("🔙 کاربران", "x:m")]]))
    st = await db.row("SELECT COUNT(*) n, COALESCE(SUM(gb),0) gb, COALESCE(SUM(status='active'),0) a "
                      "FROM panels WHERE user_id=? AND is_test=0", uid)
    t = (f"👀 <b>اطلاعات کاربر</b>\n\n⭕️ وضعیت: {'🚫 مسدود' if u['blocked'] else '✅ فعال'}\n"
         f"⭕️ نام: {h(u['name'] or '—')}\n⭕️ نام کاربری: {'@' + h(u['username']) if u['username'] else '—'}\n"
         f"⭕️ آیدی عددی: <code>{uid}</code>\n⭕️ زمان عضویت: {jdate(u['created'])}\n"
         f"⭕️ آخرین استفاده از ربات: {jdate(u['seen'])}\n"
         f"⭕️ تست رایگان: {'استفاده کرده' if u['test_used'] else 'استفاده نکرده'}\n\n"
         f"💎 <b>گزارش مالی</b>\n\n🔰 موجودی: {fmt(u['balance'])} تومان\n🔰 تعداد خرید: {st['n']}\n"
         f"🔰 پنل فعال: {st['a']}\n🔰 جمع حجم خریداری‌شده: {fgb(st['gb'])}")
    i = uid
    await show(ev, t, kb([
        [btn("🔓 رفع مسدودی" if u["blocked"] else "🚫 مسدود کردن", f"x:b:{i}", style="success" if u["blocked"] else "danger")],
        [btn("➕ افزایش موجودی", f"x:ib:{i}", style="success"), btn("➖ کم کردن موجودی", f"x:db:{i}", style="danger")],
        [btn("✉️ ارسال پیام", f"x:sm:{i}", style="primary"), btn("📦 مشاهده سفارشات", f"x:o:{i}", style="primary")],
        [btn("🎁 افزودن سفارش", f"x:ao:{i}"), btn("🔄 ریست تست رایگان", f"x:rt:{i}")],
        [btn("🔙 کاربران", "x:m")]]))


@router.callback("x:")
async def xcb(c: Callback):
    p = c.data.split(":")
    a, adm = p[1], c.from_user.id
    WAIT.pop(adm, None)
    if a == "m":
        return await user_menu(c)
    if a == "l":
        return await user_list(c, p[2], int(p[3]))
    if a == "s":
        WAIT[adm] = ("x_find", None)
        return await show(c, "🔎 آیدی عددی، @نام‌کاربری یا بخشی از نام کاربر را بفرست:", kb([[btn("🔙 کاربران", "x:m")]]))
    uid = int(p[2])
    back = kb([[btn("🔙 بازگشت", f"x:u:{uid}")]])
    if a == "u":
        return await card(c, uid)
    if a == "b":
        if uid in config.ADMIN_IDS:
            return await c.answer("ادمین را نمی‌شود مسدود کرد.", show_alert=True)
        await db.run("UPDATE users SET blocked=1-blocked WHERE tg_id=?", uid)
        await db.ev("block", uid)
        return await card(c, uid)
    if a == "rt":
        await db.run("UPDATE users SET test_used=0 WHERE tg_id=?", uid)
        return await card(c, uid)
    if a in ("ib", "db"):
        WAIT[adm] = ("x_bal", (uid, 1 if a == "ib" else -1))
        return await show(c, "مبلغ را (تومان) بفرست:", back)
    if a == "sm":
        WAIT[adm] = ("x_msg", uid)
        return await show(c, "متن پیام برای این کاربر را بفرست:", back)
    if a == "ao":
        WAIT[adm] = ("x_ao", uid)
        return await show(c, "حجم پنلی که رایگان برای کاربر ساخته شود را بفرست (گیگ، مثلاً 250):", back)
    if a == "o":
        ps = await db.rows("SELECT * FROM panels WHERE user_id=? ORDER BY id DESC LIMIT 15", uid)
        lines = [f"• <code>{h(x['admin_username'])}</code> | {fgb(x['gb']) if x['gb'] else 'قدیمی'} | {x['status']}"
                 f"{' | تست' if x['is_test'] else ''} | {jdate(x['created'])[:10]}" for x in ps]
        return await show(c, "📦 <b>سفارشات کاربر</b>\n\n" + ("\n".join(lines) or "سفارشی ندارد."), back)
    await c.answer()


@router.message(waiting("x_"))
async def xwait(m: Message):
    adm = m.from_user.id
    kind, arg = WAIT[adm]
    text = (m.text or "").strip()
    if kind == "x_find":
        q = text.lstrip("@")
        if q.isdigit():
            us = await db.rows("SELECT * FROM users WHERE tg_id=?", int(q))
        else:
            us = await db.rows("SELECT * FROM users WHERE username LIKE ? OR name LIKE ? LIMIT 10", f"%{q}%", f"%{q}%")
        if not us:
            return await m.answer("کاربری پیدا نشد؛ دوباره بفرست یا /admin را بزن.")
        WAIT.pop(adm, None)
        if len(us) == 1:
            return await card(m, us[0]["tg_id"])
        return await m.answer("نتایج:", reply_markup=kb([[btn(ulabel(u), f"x:u:{u['tg_id']}")] for u in us]))
    if kind == "x_bal":
        uid, sign = arg
        v = num(text)
        if not v or v <= 0:
            return await m.answer("یک عدد مثبت بفرست.")
        if sign > 0:
            await db.credit(uid, v)
        elif not await db.debit(uid, v):
            return await m.answer("موجودی کاربر کمتر از این مبلغ است.")
        await db.ev("balance", uid, str(sign * v))
        WAIT.pop(adm, None)
        try:
            await m.bot.send_message(uid, f"💰 موجودی شما {fmt(v)} تومان {'افزایش' if sign > 0 else 'کاهش'} یافت.")
        except Exception:
            pass
        return await card(m, uid)
    if kind == "x_msg":
        WAIT.pop(adm, None)
        try:
            await m.bot.send_message(arg, text)
        except Exception as e:
            return await m.answer(f"❌ ارسال نشد: {h(e)}")
        return await m.answer("✅ پیام ارسال شد.", reply_markup=kb([[btn("🔙 کاربر", f"x:u:{arg}")]]))
    if kind == "x_ao":
        from .user import creds_text, new_panel
        gb = fnum(text)
        if not gb or gb <= 0:
            return await m.answer("یک عدد مثبت بفرست.")
        try:
            name, pw, base = await new_panel(arg, None, gb)
        except Exception as e:
            log.exception("admin add order failed")
            WAIT.pop(adm, None)
            return await m.answer(f"❌ ساخت پنل ناموفق بود: {h(e)}")
        WAIT.pop(adm, None)
        await db.sale(arg, name, "gift", gb, 0)
        rows = [[xbtn("🖥 ورود به پنل", url=f"{base}/dashboard")],
                [xbtn("🔑 کپی رمز", copy_text={"text": pw}), xbtn("👤 کپی نام کاربری", copy_text={"text": name})]]
        try:
            await m.bot.send_message(arg, "🎁 یک سرویس برای شما فعال شد.\n\n" + creds_text(name, pw, gb, base), kb(rows))
        except Exception:
            pass
        return await m.answer(f"✅ پنل <code>{h(name)}</code> ({fgb(gb)}) ساخته و برای کاربر ارسال شد.",
                              reply_markup=kb([[btn("🔙 کاربر", f"x:u:{arg}")]]))
