from __future__ import annotations

import time

from . import config, db
from .panel import get_pg
from .tg import Callback, Router
from .ui import btn, fgb, fmt, h, kb, show

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)
PERIODS = {1: "۲۴ ساعت اخیر", 7: "۷ روز اخیر", 30: "۳۰ روز اخیر", 0: "کل"}
EVENTS = [("pw", "🔑 تغییر رمز"), ("uname", "👤 تغییر نام کاربری"), ("nick", "✏️ تغییر نام سرویس"), ("transfer", "📥 انتقال مالکیت"),
          ("delete", "🗑 حذف پنل"), ("admin_gb", "📊 تغییر حجم توسط ادمین"), ("balance", "💰 تغییر موجودی توسط ادمین"),
          ("block", "🚫 مسدود / آزادسازی")]


async def q(sql: str, *a) -> dict:
    return await db.row(sql, *a)


async def menu(ev) -> None:
    u = (await q("SELECT COUNT(*) c FROM users"))["c"]
    p = (await q("SELECT COUNT(*) c FROM panels WHERE is_test=0"))["c"]
    rows = [[btn(f"📅 آمار {PERIODS[1]}", "s:v:1", style="primary"), btn(f"📅 آمار {PERIODS[7]}", "s:v:7", style="primary")],
            [btn(f"📅 آمار {PERIODS[30]}", "s:v:30", style="primary"), btn("📈 آمار کل", "s:v:0", style="success")]]
    await show(ev, f"📊 <b>آمار ربات</b>\n\n👥 کاربران: {u}\n📦 پنل‌های فروخته‌شده: {p}\n\nبازهٔ آمار را انتخاب کن:",
               kb(rows + [[btn("🔙 مدیریت", "a:home")]]))


async def report(ev, days: int) -> None:
    now = int(time.time())
    s = now - days * 86400 if days else 0
    users = await q("SELECT COUNT(*) t, COALESCE(SUM(created>=?),0) new, COALESCE(SUM(seen>=? AND seen>0),0) act, "
                    "COALESCE(SUM(blocked),0) blk, COALESCE(SUM(balance>0),0) wb, COALESCE(SUM(balance),0) bal FROM users", s, s)
    pan = await q("SELECT COUNT(*) n, COALESCE(SUM(gb),0) gb FROM panels WHERE is_test=0 AND created>=?", s)
    tst = (await q("SELECT COUNT(*) n FROM panels WHERE is_test=1 AND created>=?", s))["n"]
    st = {r["status"]: r["n"] for r in await db.rows("SELECT status, COUNT(*) n FROM panels GROUP BY status")}
    sal = {r["kind"]: r for r in await db.rows(
        "SELECT kind, COUNT(*) n, COALESCE(SUM(price),0) p, COALESCE(SUM(gb),0) gb FROM sales WHERE created>=? GROUP BY kind", s)}
    rc = {r["status"]: r for r in await db.rows(
        "SELECT status, COUNT(*) n, COALESCE(SUM(amount),0) a FROM receipts WHERE created>=? GROUP BY status", s)}
    g = lambda d, k, f="n": d[k][f] if k in d else 0
    t = (f"📊 <b>آمار ربات — {PERIODS[days]}</b>\n\n"
         f"👥 <b>کاربران</b>\nکل: {users['t']}   جدید: {users['new']}   فعال در بازه: {users['act']}\n"
         f"مسدود: {users['blk']}   دارای موجودی: {users['wb']}   جمع موجودی‌ها: {fmt(users['bal'])} تومان\n\n"
         f"📦 <b>پنل‌ها</b>\nساخته‌شده (خرید + سفارش ادمین): {pan['n']}   تست: {tst}\nحجم فروخته‌شده: {fgb(pan['gb'])}\n"
         f"وضعیت کل → فعال: {st.get('active', 0)}   تعلیق: {st.get('suspended', 0)}   منقضی: {st.get('expired', 0)}\n\n"
         f"🛒 <b>فروش</b>\nخرید پنل: {g(sal, 'panel')} عدد — {fmt(g(sal, 'panel', 'p'))} تومان\n"
         f"خرید حجم اضافه: {g(sal, 'volume')} عدد ({fgb(g(sal, 'volume', 'gb'))}) — {fmt(g(sal, 'volume', 'p'))} تومان\n"
         f"سفارش رایگان توسط ادمین: {g(sal, 'gift')}\n"
         f"جمع فروش: <b>{fmt(g(sal, 'panel', 'p') + g(sal, 'volume', 'p'))}</b> تومان\n\n"
         f"💳 <b>شارژ کیف پول</b>\nتأییدشده: {g(rc, 'ok')} — {fmt(g(rc, 'ok', 'a'))} تومان\n"
         f"در انتظار: {g(rc, 'pending')}   ردشده: {g(rc, 'no')}\n")
    top = await db.rows("SELECT s.user_id, COUNT(*) n, SUM(s.price) p, u.name FROM sales s LEFT JOIN users u ON u.tg_id=s.user_id "
                        "WHERE s.created>=? AND s.kind IN ('panel','volume') GROUP BY s.user_id ORDER BY p DESC, n DESC LIMIT 3", s)
    if top:
        t += "\n🏆 <b>بیشترین خرید</b>\n" + "\n".join(
            f"{i}. {h(r['name'] or '?')} (<code>{r['user_id']}</code>) — {r['n']} خرید، {fmt(r['p'])} تومان" for i, r in enumerate(top, 1))
    best = await db.rows("SELECT gb, COUNT(*) n FROM sales WHERE created>=? AND kind='panel' GROUP BY gb ORDER BY n DESC LIMIT 3", s)
    if best:
        t += "\n\n💎 <b>پرفروش‌ترین حجم‌ها</b>\n" + "\n".join(f"{fgb(r['gb'])}: {r['n']} بار" for r in best)
    ev_rows = {r["kind"]: r["n"] for r in await db.rows(
        "SELECT kind, COUNT(*) n FROM events WHERE ts>=? GROUP BY kind", s)}
    lines = [f"{label}: {ev_rows[k]}" for k, label in EVENTS if k in ev_rows]
    if lines:
        t += "\n\n🛠 <b>فعالیت‌ها</b>\n" + "\n".join(lines)
    if days == 0:
        try:
            use = await (await get_pg()).admins_usage()
            names = [r["admin_username"] for r in await db.rows("SELECT admin_username FROM panels WHERE is_test=0 AND gb>0")]
            lim = sum(use[n][0] for n in names if n in use)
            used = sum(use[n][1] for n in names if n in use)
            if lim:
                t += f"\n\n📡 <b>مصرف زنده روی پاسارگارد</b>\nسقف کل: {fgb(lim)}   مصرف‌شده: {fgb(used)} ({used * 100 / lim:.0f}٪)"
        except Exception:
            pass
    t += "\n\n<i>مبلغ فروش و فعالیت‌ها از زمان نصب این بخش ثبت می‌شوند؛ خریدهای قدیمی‌تر فقط در شمار پنل‌ها دیده می‌شوند.</i>"
    await show(ev, t, kb([[btn("🔄 بروزرسانی", f"s:v:{days}", style="primary")], [btn("🔙 آمار", "s:m")]]))


@router.callback("s:")
async def scb(c: Callback):
    p = c.data.split(":")
    if p[1] == "m":
        return await menu(c)
    await report(c, int(p[2]))
