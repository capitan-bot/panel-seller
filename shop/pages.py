from __future__ import annotations

import asyncio
import time

from aiohttp import web

from web import app as A

from .wallet import charge_box
from .theme import bot_user, esc, fa, fg, shell

LBL = {"active": "فعال", "expired": "منقضی", "disabled": "غیرفعال", "deleted": "حذف‌شده", "limited": "محدودشده"}
ICONS = ["🚀", "⚡", "🛰", "💎", "🔥", "🌐"]


def cta():
    return '<a class="cta" href="/buy">🛒 خرید</a>'


async def home(req):
    uid = req["uid"]

    def work():
        b = A.q("SELECT balance FROM users WHERE tg_id=?", (uid,))
        pn = A.q("SELECT COUNT(*) FROM panels WHERE user_id=? AND is_test=0 AND status='active'", (uid,))[0][0]
        sp = A.q("SELECT COUNT(*), COALESCE(SUM(price),0) FROM sales WHERE user_id=?", (uid,))[0]
        prs = A.q("SELECT id,name,descr,price_gb,min_gb,max_gb FROM products WHERE active=1 ORDER BY sort,id")
        pks = A.q("SELECT product_id,gb,price FROM packages WHERE active=1 ORDER BY gb")
        return (b[0][0] if b else 0), pn, sp, prs, pks
    bal, pn, sp, prs, pks = await asyncio.to_thread(work)
    hero = ('<div class="hero rv"><div class="mu" style="color:#cbd5e1">موجودی کیف پول</div>'
            '<div class="big"><span class="n" data-n="%d">۰</span> <small>تومان</small></div><div class="hs">'
            '<div><b class="n" data-n="%d">۰</b><span>پنل فعال</span></div><div><b class="n" data-n="%d">۰</b><span>خرید</span></div>'
            '<div><b class="n" data-n="%d">۰</b><span>جمع خرید (تومان)</span></div></div></div>'
            % (int(bal or 0), pn, sp[0], int(sp[1] or 0)))
    cards = ""
    for i, (pid, name, descr, pgb, mn, mx) in enumerate(prs):
        mine = [(g, p) for q, g, p in pks if q == pid]
        chips = "".join('<span class="pl">%s گیگ <b>%s</b> تومان</span>' % (fg(g), fa(p)) for g, p in mine)
        start = min([p for g, p in mine] or [(pgb or 0) * (mn or 0)])
        extra = ('<div class="mu">حجم دلخواه: هر گیگ %s تومان (از %s تا %s گیگ)</div>' % (fa(pgb), fg(mn), fg(mx))) if pgb else ""
        cards += ('<div class="pc rv"><div class="pi"><div class="ph"><div class="pe">%s</div><div><h3>%s</h3>'
                  '<div class="mu" style="margin:0">شروع از <b>%s</b> تومان</div></div></div><div class="mu">%s</div>%s%s%s</div></div>'
                  % (ICONS[i % len(ICONS)], esc(name), fa(start), esc(descr), chips, extra, cta()))
    body = hero + "<h2>محصولات</h2>" + ('<div class="grid">%s</div>' % cards if cards else '<div class="card">محصولی فعال نیست.</div>')
    body += '<div class="mu" style="margin-top:14px">خرید مستقیم از سایت به‌زودی فعال می‌شود؛ فعلاً خرید از ربات انجام می‌شود.</div>'
    return shell("فروشگاه", body, "home", sub="خوش آمدی 👋")


async def panels(req):
    rows = await asyncio.to_thread(
        A.q, "SELECT admin_username,expires,status,created FROM panels WHERE user_id=? AND is_test=0 ORDER BY id DESC", (req["uid"],))
    now, cards = int(time.time()), ""
    for name, exp, st, created in rows:
        ok = st == "active" and (not exp or exp > now)
        days = max(0, (exp - now) // 86400) if exp else 0
        if not exp:
            col, ln, mid = "#22d3ee", 113.1, "∞"
        else:
            col = "#34d399" if days > 7 else "#fbbf24" if days > 3 else "#f87171"
            if not ok:
                col = "#4b4b5c"
            ln, mid = round(113.1 * min(days, 30) / 30, 1), fa(days)
        tail = ('<div class="mu">انقضا: <span class="tm" data-t="%d"></span></div>' % exp) if exp else '<div class="mu">بدون محدودیت زمانی</div>'
        cards += ('<div class="card pn rv"><div class="rg"><svg viewBox="0 0 44 44"><circle class="t" cx="22" cy="22" r="18"/>'
                  '<circle class="p" cx="22" cy="22" r="18" stroke="%s" style="stroke-dasharray:%s 113.1"/></svg>'
                  '<div class="rc"><b>%s</b><small>روز</small></div></div><div class="pf"><div class="pu" dir="ltr">%s</div>'
                  '<span class="st %s">%s</span>%s<div class="mu">ساخت: <span class="tm" data-t="%d"></span></div>'
                  '<button class="cp" data-c="%s">📋 کپی نام کاربری</button></div></div>'
                  % (col, ln, mid, esc(name), "ok" if ok else "no", esc(LBL.get(st, st)), tail, created or 0, esc(name)))
    body = '<div class="grid">%s</div>' % cards if cards else '<div class="card">هنوز پنلی نداری.</div>'
    return shell("پنل‌های من", body, "panels", sub="%s پنل" % fa(len(rows)))


async def wallet(req):
    uid = req["uid"]

    def work():
        b = A.q("SELECT balance FROM users WHERE tg_id=?", (uid,))
        return (b[0][0] if b else 0), A.q(
            "SELECT created,kind,panel,gb,price FROM sales WHERE user_id=? ORDER BY id DESC LIMIT 30", (uid,))
    bal, rows = await asyncio.to_thread(work)
    card = ('<div class="wc rv"><div class="mu">موجودی</div><div class="big"><span class="n" data-n="%d">۰</span> <small>تومان</small></div>'
            '<div class="wid">ID %s</div></div>'
            % (int(bal or 0), uid))
    tx = "".join('<div class="tx"><div><div>%s</div><small>%s%s · <span class="tm" data-f="dt" data-t="%d"></span></small></div>'
                 '<b>%s تومان</b></div>' % (esc(k), esc(p or "—"), (" · %s گیگ" % fg(g)) if g else "", t or 0, fa(pr))
                 for t, k, p, g, pr in rows)
    body = card + charge_box() + "<h2>تاریخچه</h2>" + ('<div class="card">%s</div>' % tx if tx else '<div class="card">تراکنشی نیست.</div>')
    return shell("کیف پول", body, "wallet")


def install(app):
    app.router.add_get("/", home)
    app.router.add_get("/panels", panels)
    app.router.add_get("/wallet", wallet)
