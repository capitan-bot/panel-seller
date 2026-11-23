"""More user management on top of members.py: new list + profile UI, temp ban, tags, per-user discount,
login history, shared-IP warning, panel tools (add volume / reset password), bulk actions, sales csv.

Install: in main.py, right after `from . import members` add `from . import members_plus`.
"""
from __future__ import annotations

import asyncio
import contextvars
import csv
import io
import logging
import time
from urllib.parse import quote

from aiohttp import web

from bot import db
from bot.panel import PanelError, gen_password, get_pg
from bot.user import pw_problem
from web import app as A

from . import admin, auth, buy, members as M, pages
from .members import audit, back, badges, form, hid, mrow, mset, now, num, root, tm
from .theme import esc, fa, fg

log = logging.getLogger("shop.plus")
CUID = contextvars.ContextVar("plus_uid", default=None)
PER = 12
M.DEF.update({"ban_until": 0, "tag": "", "discount": 0})


# ---------------------------------------------------------------- schema + hooks into members / buy
async def startup(app):
    have = {r["name"] for r in await db.rows("PRAGMA table_info(shop_users)")}
    for c, t in (("ban_until", "INTEGER NOT NULL DEFAULT 0"), ("tag", "TEXT NOT NULL DEFAULT ''"),
                 ("discount", "INTEGER NOT NULL DEFAULT 0")):
        if c not in have:
            await db.run("ALTER TABLE shop_users ADD COLUMN %s %s" % (c, t))
    await db.run("CREATE TABLE IF NOT EXISTS shop_logins(id INTEGER PRIMARY KEY AUTOINCREMENT, uid INTEGER NOT NULL, "
                 "ts INTEGER NOT NULL, ip TEXT NOT NULL DEFAULT '', ua TEXT NOT NULL DEFAULT '')")
    await db.run("CREATE INDEX IF NOT EXISTS ix_shop_logins ON shop_logins(uid, ts)")


_otrack = M.track


async def track(req, uid, login=False):
    await _otrack(req, uid, login)
    if login:
        await db.run("INSERT INTO shop_logins(uid,ts,ip,ua) VALUES(?,?,?,?)", uid, now(), auth.client_ip(req),
                     req.headers.get("User-Agent", "")[:160])
        await db.run("DELETE FROM shop_logins WHERE uid=? AND id NOT IN "
                     "(SELECT id FROM shop_logins WHERE uid=? ORDER BY id DESC LIMIT 30)", uid, uid)


_ogate = M.gate


async def gate(req, uid, ck):
    if uid not in A.admin_ids() and (await M.meta(uid)).get("ban_until", 0) > now():
        return M.banned_page()
    return await _ogate(req, uid, ck)


_ores = buy.resolve


async def resolve(kind, rid, gb_raw=""):
    x, gb, price, e = await _ores(kind, rid, gb_raw)
    u = CUID.get()
    if kind == "p" and u and price > 0 and not e:
        d = (await M.meta(u)).get("discount", 0)
        if d:
            price = max(1, int(round(price * (100 - d) / 100)))
    return x, gb, price, e


@web.middleware
async def cmw(req, handler):
    CUID.set(auth.read_cookie(req.cookies.get("pgshop", "")))
    return await handler(req)


M.track, M.gate, buy.resolve = track, gate, resolve

# ---------------------------------------------------------------- css
PCSS = ("<style>.ur{display:flex;align-items:center;gap:10px;padding:12px 0;border-bottom:1px solid var(--bd)}.ur:last-child{border:0}"
        ".ur .ub{width:20px;height:20px;flex:none}.ua{display:flex;align-items:center;gap:12px;flex:1;min-width:0;color:var(--tx)}"
        ".av{position:relative;flex:none;width:46px;height:46px;border-radius:16px;display:grid;place-items:center;font-weight:700;"
        "background:var(--tile);color:var(--pri,#a78bfa)}.av.on:after{content:\"\";position:absolute;bottom:-2px;left:-2px;width:12px;"
        "height:12px;border-radius:50%;background:#22c55e;border:2px solid var(--card)}"
        ".uin{min-width:0}.uin b{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
        ".uin small{display:block;color:var(--mu);font-size:12px}.ubal{flex:none;text-align:left;font-weight:700}"
        ".ubal small{display:block;color:var(--mu);font-weight:400;font-size:11px}"
        ".tgx{display:inline-block;padding:2px 9px;border-radius:99px;background:var(--tile);color:var(--pri,#a78bfa);font-size:11px}"
        ".chip{display:inline-block;margin:6px 0 0 6px;padding:6px 12px;border-radius:99px;border:1px solid var(--bd);"
        "background:var(--s2);color:var(--tx);font:inherit;font-size:13px;cursor:pointer}"
        ".dt{border:1px solid var(--bd);border-radius:18px;background:var(--card);margin-bottom:12px;overflow:hidden}"
        ".dt>summary{cursor:pointer;padding:15px 16px;font-weight:700;list-style:none;display:flex;justify-content:space-between}"
        ".dt>summary::-webkit-details-marker{display:none}.dt>summary:after{content:\"﹀\";color:var(--mu)}"
        ".dt[open]>summary:after{content:\"︿\"}.dt .in{padding:0 16px 16px}"
        ".hd{display:flex;align-items:center;gap:14px}.hd .av{width:64px;height:64px;font-size:26px;border-radius:20px}"
        ".hd h2{margin:0 0 4px;font-size:20px}.pgn{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}"
        ".pgn a,.pgn span{min-width:38px;text-align:center;padding:8px 10px;border-radius:12px;border:1px solid var(--bd);color:var(--tx)}"
        ".pgn span{background:var(--tile);color:var(--pri,#a78bfa)}.wn{padding:12px;border-radius:14px;background:#fbbf2420;"
        "color:#d97706;margin-bottom:12px;font-size:14px}.bk{margin-top:14px;padding-top:12px;border-top:1px solid var(--bd)}"
        "</style>")


def pg2(active, title, body, req=None):
    return M.page(active, title, PCSS + body, req)


# ---------------------------------------------------------------- list
SORTS = (("seen", "آخرین بازدید", "COALESCE(s.seen_at,0) DESC, u.created DESC"), ("bal", "بیشترین موجودی", "u.balance DESC"),
         ("new", "جدیدترین عضو", "u.created DESC"), ("spent", "بیشترین خرید", "spent DESC"))
FILT = M.FILT + (("tag", "دارای برچسب"), ("disc", "دارای تخفیف"), ("lim", "دارای محدودیت"))


def where2(f, q):
    w, a = M.where_for(f, q)
    extra = {"tag": "s.tag!=''", "disc": "s.discount>0", "lim": "(s.can_buy=0 OR s.can_charge=0 OR s.max_day>0 OR s.max_panels>0)"}.get(f)
    if extra:
        w = (w + " AND " + extra) if w else " WHERE " + extra
    return w, a


def urow(r):
    on = " on" if r["seen_at"] > now() - 300 else ""
    sub = ("@" + esc(r["username"]) + " · " if r["username"] else "") + str(r["tg_id"])
    seen = ("آخرین بازدید: " + tm(r["seen_at"])) if r["seen_at"] else "هنوز وارد سایت نشده"
    extra = ""
    if r["tag"]:
        extra += ' <span class="tgx">%s</span>' % esc(r["tag"])
    if r["disc"]:
        extra += ' <span class="tgx">٪%s تخفیف</span>' % fa(r["disc"])
    if r["bu"] > now():
        extra += ' <span class="st no">بن موقت</span>'
    return ('<div class="ur"><input type="checkbox" class="ub" name="ids" value="%d"><a class="ua" href="/admin/users/%d">'
            '<div class="av%s">%s</div><div class="uin"><b>%s%s%s</b><small>%s</small><small>%s</small></div></a>'
            '<div class="ubal">%s<small>تومان · %s خرید</small></div></div>' % (
                r["tg_id"], r["tg_id"], on, esc((r["name"] or "?").strip()[:1].upper() or "?"), esc(r["name"] or "?"),
                badges(r["tg_id"], r["blocked"], r["banned"], r["vip"]), extra, sub, seen, fa(r["balance"]), fa(r["spent"])))


def pager(p, total, qs):
    n = max(1, (total + PER - 1) // PER)
    if n == 1:
        return ""
    out = ""
    for i in range(max(1, p - 3), min(n, p + 3) + 1):
        out += '<span>%d</span>' % i if i == p else '<a href="/admin/users?p=%d%s">%s</a>' % (i, qs, fa(i))
    return '<div class="pgn">%s</div>' % out


async def users_page(req):
    admin.need(req)
    t = now()
    sc = (await db.row("SELECT COUNT(*) c FROM shop_users WHERE seen_at>0"))["c"]
    q = str(req.query.get("q", "")).strip()[:40]
    f = req.query.get("f") or ("site" if sc else "all")
    f = f if f in dict(FILT) else "all"
    so = req.query.get("o", "seen")
    order = dict((k, o) for k, _, o in SORTS).get(so) or SORTS[0][2]
    so = so if so in dict((k, 1) for k, _, _ in SORTS) else "seen"
    p = num(req.query.get("p", 1), 1, 100000) or 1
    w, a = where2(f, q)
    base = "FROM users u LEFT JOIN shop_users s ON s.uid=u.tg_id" + w
    total = (await db.row("SELECT COUNT(*) c " + base, *a))["c"]
    rows = await db.rows(
        "SELECT u.tg_id,u.name,u.username,u.balance,u.blocked,COALESCE(s.seen_at,0) seen_at,COALESCE(s.banned,0) banned,"
        "COALESCE(s.vip,0) vip,COALESCE(s.tag,'') tag,COALESCE(s.discount,0) disc,COALESCE(s.ban_until,0) bu,"
        "(SELECT COALESCE(SUM(price),0) FROM sales WHERE user_id=u.tg_id) spent " + base +
        " ORDER BY " + order + " LIMIT ? OFFSET ?", *a, PER, (p - 1) * PER)
    st = await db.row("SELECT (SELECT COUNT(*) FROM users) a,(SELECT COUNT(*) FROM shop_users WHERE seen_at>?) b,"
                      "(SELECT COUNT(*) FROM shop_users WHERE seen_at>?) c,(SELECT COUNT(*) FROM shop_users WHERE joined>?) d,"
                      "(SELECT COUNT(*) FROM sales WHERE created>?) e,(SELECT COALESCE(SUM(price),0) FROM sales WHERE created>?) g,"
                      "(SELECT COALESCE(SUM(balance),0) FROM users) h", t - 300, t - 86400, t - 86400, t - 86400, t - 86400)
    cells = (("🟢 آنلاین الان", st["b"]), ("فعال ۲۴ ساعت", st["c"]), ("ورودکرده‌ها", sc), ("جدید در سایت (۲۴س)", st["d"]),
             ("خرید ۲۴ ساعت", st["e"]), ("فروش ۲۴ ساعت", st["g"]), ("کل کاربران ربات", st["a"]), ("جمع موجودی‌ها", st["h"]))
    stats = '<div class="sg">%s</div>' % "".join("<div><b>%s</b><span>%s</span></div>" % (fa(v), k) for k, v in cells)
    sel = lambda opts, cur: "".join('<option value="%s"%s>%s</option>' % (k, " selected" if k == cur else "", n) for k, n in opts)
    search = ('<form method="get" action="/admin/users"><label>جستجو (آیدی، نام یا یوزرنیم)</label><input name="q" value="%s">'
              '<div class="g2"><div><label>فیلتر</label><select name="f">%s</select></div><div><label>مرتب‌سازی</label>'
              '<select name="o">%s</select></div></div><button class="b">🔍 اعمال</button> '
              '<a class="b" style="text-decoration:none" href="/admin/users.csv">⬇️ CSV</a></form>'
              % (esc(q), sel(FILT, f), sel([(k, n) for k, n, _ in SORTS], so)))
    bulk = ('<div class="bk"><label class="ck"><input type="checkbox" id="sa"> انتخاب همه‌ی این صفحه</label>'
            '<div class="g2"><div><select name="act"><option value="msg">پیام تلگرام</option><option value="bal">افزایش موجودی</option>'
            '<option value="ban">بن از سایت</option><option value="unban">رفع بن</option><option value="kick">اخراج</option>'
            '<option value="vip">VIP کردن</option><option value="unvip">برداشتن VIP</option><option value="tag">تنظیم برچسب</option>'
            '<option value="disc">تنظیم تخفیف ٪</option></select></div><div><input name="val" placeholder="متن / مبلغ / برچسب / درصد"></div></div>'
            '<button class="b" onclick="return confirm(\'روی کاربران انتخاب‌شده اعمال شود؟\')">▶️ اجرا روی انتخاب‌شده‌ها</button></div>')
    js = ('<script>(function(){var s=document.getElementById("sa");if(s)s.onchange=function(){var v=s.checked;'
          '[].forEach.call(document.querySelectorAll(".ub"),function(c){c.checked=v})}})();</script>')
    listing = ('<form method="post" action="/admin/users/bulk">' + ("".join(urow(r) for r in rows) or '<div class="mu">کاربری پیدا نشد.</div>') +
               ('<div class="mu" style="margin-top:10px">%s مورد</div>' % fa(total)) + bulk + "</form>" +
               pager(p, total, "&q=%s&f=%s&o=%s" % (quote(q), f, so)) + js)
    return pg2("users", "کاربران", stats + admin.card(search) + admin.card(listing), req)


async def bulk_post(req):
    me = admin.need(req, True)
    f = await req.post()
    ids = [int(x) for x in f.getall("ids", []) if str(x).isdigit()][:200]
    act, val = str(f.get("act", "")), str(f.get("val", "")).strip()
    if ids:
        ids = [r["tg_id"] for r in await db.rows("SELECT tg_id FROM users WHERE tg_id IN (%s)" % ",".join("?" * len(ids)), *ids)]
    if act in ("ban", "kick"):
        ids = [i for i in ids if i not in root()]
    err = ""
    if not ids:
        err = "کاربری انتخاب نشده."
    elif act == "msg":
        if not val:
            err = "متن پیام خالی است."
        else:
            task = asyncio.ensure_future(M._bc(me, ids, "📩 <b>پیام از مدیریت</b>\n\n" + esc(val[:1000])))
            M.KEEP.add(task)
            task.add_done_callback(M.KEEP.discard)
    elif act == "bal":
        amt = num(val, 1, 10 ** 10)
        if amt is None:
            err = "مبلغ معتبر نیست."
        else:
            for i in ids:
                await db.credit(i, amt)
                await audit(me, i, "bal_add", "%s تومان (گروهی)" % amt)
    elif act in ("ban", "unban", "kick", "vip", "unvip", "tag", "disc"):
        d = {"ban": {"banned": 1}, "unban": {"banned": 0, "ban_until": 0}, "kick": {"kicked": now()}, "vip": {"vip": 1},
             "unvip": {"vip": 0}, "tag": {"tag": val[:20]}, "disc": {"discount": num(val, 0, 90)}}[act]
        if None in d.values():
            err = "درصد باید بین ۰ تا ۹۰ باشد."
        else:
            for i in ids:
                await mset(i, **d)
                await audit(me, i, act + "_bulk", val[:40])
    else:
        err = "عملیات نامعتبر است."
    raise web.HTTPFound("/admin/users?%s=%s" % ("e" if err else "m", quote(err or "انجام شد برای %s کاربر." % fa(len(ids)))))


# ---------------------------------------------------------------- profile
def sec(title, inner, open_=False):
    return '<details class="dt"%s><summary>%s</summary><div class="in">%s</div></details>' % (" open" if open_ else "", title, inner)


def chips(items, js):
    return "".join('<button type="button" class="chip" onclick="%s">%s</button>' % (js % v, n) for n, v in items)


async def user_page(req):
    me = admin.need(req)
    uid = int(req.match_info["id"])
    u = await db.row("SELECT * FROM users WHERE tg_id=?", uid)
    if not u:
        raise web.HTTPNotFound()
    s, t = await mrow(uid), now()
    isroot, isadm = uid in root(), uid in A.admin_ids()
    ag = await db.row("SELECT (SELECT COALESCE(SUM(price),0) FROM sales WHERE user_id=?) spent,"
                      "(SELECT COUNT(*) FROM sales WHERE user_id=? AND kind='panel') nbuy,"
                      "(SELECT COUNT(*) FROM panels WHERE user_id=? AND status='active' AND is_test=0) np,"
                      "(SELECT COUNT(*) FROM receipts WHERE user_id=? AND status='pending') rp", uid, uid, uid, uid)
    ips = await db.rows("SELECT DISTINCT ip FROM shop_logins WHERE uid=? AND ts>?", uid, t - 7 * 86400)
    same = await db.rows("SELECT s.uid, u.name FROM shop_users s JOIN users u ON u.tg_id=s.uid WHERE s.ip=? AND s.uid!=? LIMIT 6",
                         s["ip"], uid) if s["ip"] else []
    logins = await db.rows("SELECT ts,ip,ua FROM shop_logins WHERE uid=? ORDER BY id DESC LIMIT 10", uid)
    hist = await db.rows("SELECT ts,adm,act,info FROM shop_audit WHERE uid=? ORDER BY id DESC LIMIT 15", uid)
    ps = await db.rows("SELECT id,admin_username,status,expires,gb,is_test FROM panels WHERE user_id=? ORDER BY id DESC LIMIT 20", uid)
    ss = await db.rows("SELECT created,kind,panel,gb,price FROM sales WHERE user_id=? ORDER BY id DESC LIMIT 15", uid)
    rc = await db.rows("SELECT created,amount,status FROM receipts WHERE user_id=? ORDER BY id DESC LIMIT 6", uid)
    kv = lambda k, v: '<div class="kv"><span>%s</span><b>%s</b></div>' % (k, v)
    A_ = "/admin/users/%d/" % uid
    on = " on" if s["seen_at"] > t - 300 else ""
    tag = ' <span class="tgx">%s</span>' % esc(s["tag"]) if s["tag"] else ""
    head = ('<div class="hd"><div class="av%s">%s</div><div><h2>%s</h2><div class="mu" dir="ltr" style="text-align:right">%s%d</div>'
            '<div>%s%s</div></div></div>' % (on, esc((u["name"] or "?").strip()[:1].upper() or "?"), esc(u["name"] or "?"),
                                            ("@" + esc(u["username"]) + " · ") if u["username"] else "", uid,
                                            badges(uid, u["blocked"], s["banned"], s["vip"]) + (' <span class="st no">بن موقت تا %s</span>' % tm(s["ban_until"]) if s["ban_until"] > t else ""), tag))
    tiles = '<div class="sg" style="margin-top:14px">%s</div>' % "".join("<div><b>%s</b><span>%s</span></div>" % (fa(v), k) for k, v in (
        ("موجودی (تومان)", u["balance"]), ("کل خرید (تومان)", ag["spent"]), ("تعداد خرید پنل", ag["nbuy"]),
        ("پنل فعال", ag["np"]), ("رسید در انتظار", ag["rp"]), ("تخفیف ٪", s["discount"])))
    warn = ""
    if len(ips) > 3:
        warn += '<div class="wn">⚠️ در ۷ روز اخیر با %s IP مختلف وارد شده (احتمال اشتراک حساب).</div>' % fa(len(ips))
    if same:
        warn += '<div class="wn">⚠️ هم‌IP با: %s</div>' % "، ".join('<a href="/admin/users/%d">%s</a>' % (x["uid"], esc(x["name"] or x["uid"])) for x in same)
    top = admin.card(head + tiles) + warn
    quick = ('<div class="acts" style="margin-bottom:12px"><a class="b" style="text-decoration:none" href="%sorder">🛒 ثبت سفارش</a>'
             '<a class="b" style="text-decoration:none" href="%ssales.csv">⬇️ خرید‌ها CSV</a></div>' % (A_, A_))
    bal = form(A_ + "bal", '<div class="g2"><div><label>عملیات</label><select name="op"><option value="add">افزایش</option>'
               '<option value="sub">کاهش</option><option value="set">تنظیم دقیق</option></select></div>'
               '<div><label>مبلغ (تومان)</label><input name="amt" inputmode="numeric" required></div></div>' +
               chips((("+۱۰ هزار", 10000), ("+۵۰ هزار", 50000), ("+۱۰۰ هزار", 100000), ("+۵۰۰ هزار", 500000)),
                     "var f=this.form;f.op.value='add';f.amt.value=%d") +
               chips((("−۱۰ هزار", 10000), ("−۵۰ هزار", 50000)), "var f=this.form;f.op.value='sub';f.amt.value=%d") +
               '<label>دلیل (ثبت در لاگ)</label><input name="why" maxlength="100">'
               '<label class="ck"><input type="checkbox" name="notify" value="1" checked> اطلاع به کاربر در تلگرام</label>',
               "💰 اعمال", "b", "اعمال تغییر موجودی؟")
    bh = "".join('<div class="kv"><span>%s<br><small>%s</small></span><b>%s</b></div>' % (tm(h["ts"]), esc(h["act"]), esc(h["info"])) for h in hist if h["act"].startswith("bal"))
    pl = "".join('<a class="tx" href="%spanel/%d"><div><b dir="ltr">%s</b><br><small>%s · %s گیگ · انقضا: %s</small></div><b>⚙️</b></a>' % (
        A_, p["id"], esc(p["admin_username"]), esc(p["status"]) + (" · تست" if p["is_test"] else ""), fg(p["gb"]), tm(p["expires"])) for p in ps)
    sl = "".join('<div class="tx"><div>%s<br><small>%s · %s</small></div><b>%s تومان</b></div>' % (
        esc(x["kind"]), esc(x["panel"] or "—"), tm(x["created"]), fa(x["price"])) for x in ss)
    rl = "".join('<div class="tx"><div>%s<br><small>%s</small></div><b>%s تومان</b></div>' % (esc(x["status"]), tm(x["created"]), fa(x["amount"])) for x in rc)
    ban = ""
    if not (isroot or (isadm and me not in root())):
        ban = ('<div class="acts">' +
               form(A_ + "act", hid("a", "ban"), "✅ رفع بن دائمی" if s["banned"] else "🚫 بن دائمی", "b" if s["banned"] else "b r", "انجام شود؟") +
               form(A_ + "act", hid("a", "kick"), "👢 اخراج فوری", "b r", "جلسه‌ی ورود کاربر باطل شود؟") +
               form(A_ + "act", hid("a", "block"), "🔓 رفع مسدودی ربات" if u["blocked"] else "⛔ مسدود (سایت و ربات)", "b" if u["blocked"] else "b r", "انجام شود؟") +
               "</div>" + form(A_ + "plus", hid("a", "tban") + '<label>بن موقت</label><select name="h"><option value="1">۱ ساعت</option>'
                               '<option value="6">۶ ساعت</option><option value="24">۱ روز</option><option value="168">۷ روز</option>'
                               '<option value="720">۳۰ روز</option></select>', "⏳ بن موقت", "b r", "کاربر موقتاً بن شود؟") +
               (form(A_ + "plus", hid("a", "unban"), "✅ رفع هر نوع بن") if s["ban_until"] > t or s["banned"] else ""))
    lim = form(A_ + "limits", '<label class="ck"><input type="checkbox" name="can_buy" value="1"%s> اجازه‌ی خرید</label>'
               '<label class="ck"><input type="checkbox" name="can_charge" value="1"%s> اجازه‌ی شارژ کیف پول</label>'
               '<div class="g2"><div><label>سقف خرید در ۲۴ ساعت (۰ = بدون سقف)</label><input name="max_day" inputmode="numeric" value="%d"></div>'
               '<div><label>حداکثر تعداد پنل (۰ = بدون سقف)</label><input name="max_panels" inputmode="numeric" value="%d"></div></div>' % (
                   " checked" if s["can_buy"] else "", " checked" if s["can_charge"] else "", s["max_day"], s["max_panels"]), "💾 ذخیره‌ی محدودیت‌ها")
    disc = form(A_ + "plus", hid("a", "disc") + '<label>تخفیف اختصاصی روی پکیج‌های آماده (۰ تا ۹۰ درصد)</label>'
                '<input name="v" inputmode="numeric" value="%d">' % s["discount"] + '<div class="mu">در مرحله‌ی پرداخت اعمال می‌شود. حجم دلخواه تخفیف ندارد.</div>', "🏷 ذخیره‌ی تخفیف")
    tagf = form(A_ + "plus", hid("a", "tag") + '<label>برچسب (حداکثر ۲۰ حرف)</label><input name="v" maxlength="20" value="%s">' % esc(s["tag"]) +
                chips((("نماینده", "نماینده"), ("مشکوک", "مشکوک"), ("همکار", "همکار"), ("مشتری ویژه", "مشتری ویژه")), "this.form.v.value='%s'"), "🏷 ذخیره‌ی برچسب")
    lg = "".join('<div class="kv"><span>%s</span><b dir="ltr">%s<br><small>%s</small></b></div>' % (tm(x["ts"]), esc(x["ip"]), esc(x["ua"][:50])) for x in logins)
    msgf = form(A_ + "msg", '<label>پیام تلگرام به این کاربر</label><textarea name="t" rows="3" maxlength="1000" required></textarea>' +
                chips((("پنل آماده شد", "پنل شما آماده شد."), ("ارسال رسید", "لطفاً تصویر رسید پرداخت را ارسال کنید."),
                       ("شارژ شد", "کیف پول شما شارژ شد."), ("تماس", "لطفاً با پشتیبانی تماس بگیرید.")), "this.form.t.value='%s'"), "📨 ارسال")
    notef = form(A_ + "note", '<label>یادداشت مدیر (فقط خودت می‌بینی)</label><textarea name="n" rows="2" maxlength="300">%s</textarea>' % esc(s["note"]), "💾 ذخیره‌ی یادداشت")
    oth = '<div class="acts">' + form(A_ + "act", hid("a", "vip"), "⭐ برداشتن VIP" if s["vip"] else "⭐ VIP کردن") + form(
        A_ + "plus", hid("a", "test"), "🧪 اجازه‌ی تست مجدد", "b", "تست رایگان دوباره فعال شود؟")
    if me in root() and not isroot:
        oth += form(A_ + "act", hid("a", "adm"), "👑 برداشتن ادمین سایت" if uid in M._ADM["s"] else "👑 ادمین سایت کن", "b", "تغییر نقش ادمین؟")
    oth += "</div>"
    ah = "".join('<div class="kv"><span>%s<br><small>توسط %d</small></span><b>%s<br><small>%s</small></b></div>' % (
        tm(h["ts"]), h["adm"], esc(h["act"]), esc(h["info"])) for h in hist)
    dele = ""
    if me in root() and not isadm:
        dele = sec("🗑 حذف کامل", '<div class="mu">اگر پنل فعال یا رسید در انتظار داشته باشد حذف نمی‌شود؛ تاریخچه‌ی فروش می‌ماند.</div>' + form(
            A_ + "del", '<label>برای تأیید آیدی را بنویس: <b>%d</b></label><input name="confirm" inputmode="numeric" required>' % uid,
            "🗑 حذف کامل", "b r", "کاربر برای همیشه حذف شود؟"))
    info = (kv("اولین ورود به سایت", tm(s["joined"])) + kv("آخرین بازدید", tm(s["seen_at"])) + kv("تعداد ورود", fa(s["hits"])) +
            kv("عضویت در ربات", tm(u["created"])) + kv("نقش", "ادمین اصلی" if isroot else ("ادمین سایت" if isadm else "کاربر")) +
            kv("یادداشت", esc(s["note"] or "—")))
    body = (top + quick + sec("💰 موجودی", bal + (("<h3 style='margin-top:14px'>تاریخچه‌ی تغییرات</h3>" + bh) if bh else ""), True) +
            sec("🖥 پنل‌ها (%s)" % fa(len(ps)), pl or '<div class="mu">پنلی ندارد.</div>') +
            sec("🧾 خریدها", sl or '<div class="mu">خریدی ندارد.</div>') + sec("📥 رسیدها", rl or '<div class="mu">رسیدی ندارد.</div>') +
            sec("🔐 بن و دسترسی", ban or '<div class="mu">روی ادمین‌ها ممکن نیست.</div>') + sec("🚦 محدودیت‌ها", lim) +
            sec("🏷 تخفیف و برچسب", disc + tagf) + sec("📨 پیام و یادداشت", msgf + notef) + sec("🕘 ورودها", lg or '<div class="mu">ثبتی نیست.</div>') +
            sec("ℹ️ اطلاعات", info) + sec("⭐ سایر عملیات", oth) + sec("📜 تاریخچه‌ی مدیریتی", ah or '<div class="mu">ثبتی نیست.</div>') + dele)
    return pg2("users", "کاربر %s" % (u["name"] or uid), body, req)


async def user_plus(req):
    me, uid, u, f = await M.target(req)
    a = str(f.get("a", ""))
    if a in ("tban", "unban") and (uid in root() or (uid in A.admin_ids() and me not in root())):
        back(uid, e="روی ادمین‌ها این کار ممکن نیست.")
    if a == "tban":
        h = num(f.get("h", 1), 1, 24 * 90) or 1
        await mset(uid, ban_until=now() + h * 3600)
        msg = "کاربر %s ساعت از سایت بن شد." % fa(h)
    elif a == "unban":
        await mset(uid, banned=0, ban_until=0)
        msg = "بن کاربر برداشته شد."
    elif a == "tag":
        await mset(uid, tag=str(f.get("v", "")).strip()[:20])
        msg = "برچسب ذخیره شد."
    elif a == "disc":
        d = num(f.get("v", 0), 0, 90)
        if d is None:
            back(uid, e="درصد باید بین ۰ تا ۹۰ باشد.")
        await mset(uid, discount=d)
        msg = "تخفیف %s درصد ذخیره شد." % fa(d)
    elif a == "test":
        await db.run("UPDATE users SET test_used=0 WHERE tg_id=?", uid)
        msg = "تست رایگان دوباره برای کاربر فعال شد."
    else:
        back(uid, e="عملیات نامعتبر است.")
    await audit(me, uid, a, msg)
    back(uid, m=msg)


async def sales_csv(req):
    admin.need(req)
    uid = int(req.match_info["id"])
    rs = await db.rows("SELECT id,panel,kind,gb,price,created FROM sales WHERE user_id=? ORDER BY id DESC", uid)
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(["id", "panel", "kind", "gb", "price", "created"])
    for r in rs:
        w.writerow([r["id"], r["panel"], r["kind"], r["gb"], r["price"], r["created"]])
    return web.Response(body=("\ufeff" + b.getvalue()).encode("utf-8"), headers={
        "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="sales-%d.csv"' % uid})


# ---------------------------------------------------------------- panel tools
async def panel_load(req, post=False):
    me = admin.need(req, post)
    uid, pid = int(req.match_info["id"]), int(req.match_info["pid"])
    x = await db.row("SELECT * FROM panels WHERE id=? AND user_id=?", pid, uid)
    if not x:
        raise web.HTTPNotFound()
    return me, uid, x


def pback(uid, pid, m="", e=""):
    raise web.HTTPFound("/admin/users/%d/panel/%d?%s=%s" % (uid, pid, "e" if e else "m", quote(e or m)))


async def user_plus(req):
    me, uid, u, f = await M.target(req)
    a = str(f.get("a", ""))
    if a in ("tban", "unban") and (uid in root() or (uid in A.admin_ids() and me not in root())):
        back(uid, e="روی ادمین‌ها این کار ممکن نیست.")
    if a == "tban":
        h = num(f.get("h", 1), 1, 24 * 90) or 1
        await mset(uid, ban_until=now() + h * 3600)
        msg = "کاربر %s ساعت از سایت بن شد." % fa(h)
    elif a == "unban":
        await mset(uid, banned=0, ban_until=0)
        msg = "بن کاربر برداشته شد."
    elif a == "tag":
        await mset(uid, tag=str(f.get("v", "")).strip()[:20])
        msg = "برچسب ذخیره شد."
    elif a == "disc":
        d = num(f.get("v", 0), 0, 90)
        if d is None:
            back(uid, e="درصد باید بین ۰ تا ۹۰ باشد.")
        await mset(uid, discount=d)
        msg = "تخفیف %s درصد ذخیره شد." % fa(d)
    elif a == "test":
        await db.run("UPDATE users SET test_used=0 WHERE tg_id=?", uid)
        msg = "تست رایگان دوباره برای کاربر فعال شد."
    else:
        back(uid, e="عملیات نامعتبر است.")
    await audit(me, uid, a, msg)
    back(uid, m=msg)


async def sales_csv(req):
    admin.need(req)
    uid = int(req.match_info["id"])
    rs = await db.rows("SELECT id,panel,kind,gb,price,created FROM sales WHERE user_id=? ORDER BY id DESC", uid)
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(["id", "panel", "kind", "gb", "price", "created"])
    for r in rs:
        w.writerow([r["id"], r["panel"], r["kind"], r["gb"], r["price"], r["created"]])
    return web.Response(body=("\ufeff" + b.getvalue()).encode("utf-8"), headers={
        "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="sales-%d.csv"' % uid})


# ---------------------------------------------------------------- panel tools
async def panel_load(req, post=False):
    me = admin.need(req, post)
    uid, pid = int(req.match_info["id"]), int(req.match_info["pid"])
    x = await db.row("SELECT * FROM panels WHERE id=? AND user_id=?", pid, uid)
    if not x:
        raise web.HTTPNotFound()
    return me, uid, x


def pback(uid, pid, m="", e=""):
    raise web.HTTPFound("/admin/users/%d/panel/%d?%s=%s" % (uid, pid, "e" if e else "m", quote(e or m)))


async def panel_page(req, extra=""):
    me, uid, x = await panel_load(req)
    live, err = None, ""
    try:
        live = await (await get_pg(x["server_id"])).admin_info(x["admin_username"])
    except Exception as e:
        err = str(e)[:120]
    base = "/admin/users/%d/panel/%d/" % (uid, x["id"])
    kv = lambda k, v: '<div class="kv"><span>%s</span><b>%s</b></div>' % (k, v)
    gv = lambda v: "—" if v is None else "%s گیگ" % fg(v)
    info = (kv("نام کاربری", '<span dir="ltr">%s</span>' % esc(x["admin_username"])) + kv("وضعیت در دیتابیس", esc(x["status"])) +
            kv("انقضا", tm(x["expires"]) if x["expires"] else "نامحدود") + kv("حجم ثبت‌شده", gv(x["gb"])))
    if live:
        info += (kv("سقف حجم (زنده)", "نامحدود" if live["limit"] == 0 else gv(live["limit"])) + kv("مصرف‌شده", gv(live["used"])) +
                 kv("کاربران ساخته‌شده", "—" if live["users"] is None else fa(live["users"])) + kv("غیرفعال در پنل", "بله" if live["disabled"] else "خیر"))
    elif err:
        info += '<div class="msg er">ارتباط با سرور پنل ناموفق بود: %s</div>' % esc(err)
    else:
        info += '<div class="msg er">این پنل روی سرور پیدا نشد.</div>'
    vol = form(base + "act", hid("a", "vol") + '<label>افزودن حجم (گیگابایت)</label><input name="gb" inputmode="numeric" required>' +
               chips((("+۵۰", 50), ("+۱۰۰", 100), ("+۲۵۰", 250), ("+۵۰۰", 500)), "this.form.gb.value=%d") +
               '<label class="ck"><input type="checkbox" name="notify" value="1" checked> اطلاع به کاربر در تلگرام</label>',
               "➕ افزودن حجم (رایگان)", "b", "حجم به پنل اضافه شود؟")
    pw = form(base + "act", hid("a", "pw") + '<label>رمز جدید (خالی = رمز تصادفی)</label><input name="pw" dir="ltr">'
              '<label class="ck"><input type="checkbox" name="notify" value="1"> ارسال رمز جدید به کاربر در تلگرام</label>',
              "🔑 ریست رمز", "b r", "رمز پنل تغییر کند؟")
    body = (extra + admin.card("<h3>%s</h3>%s" % (esc(x["nick"] or x["admin_username"]), info)) + admin.card("<h3>افزودن حجم</h3>" + vol) +
            admin.card("<h3>رمز پنل</h3>" + pw) + '<a class="b" style="text-decoration:none" href="/admin/users/%d">⬅️ بازگشت به کاربر</a>' % uid)
    return pg2("users", "مدیریت پنل", body, req)


async def panel_act(req):
    me, uid, x = await panel_load(req, True)
    f = await req.post()
    a, name = str(f.get("a", "")), x["admin_username"]
    pid = x["id"]
    try:
        pg = await get_pg(x["server_id"])
        if a == "vol":
            g = num(f.get("gb"), 1, 100000)
            if g is None:
                pback(uid, pid, e="مقدار حجم معتبر نیست.")
            info = await pg.admin_info(name)
            cur = info["limit"] if info and info["limit"] is not None else (x["gb"] or 0)
            if not cur:
                pback(uid, pid, e="حجم فعلی پنل نامشخص است؛ از ربات اقدام کن.")
            await pg.set_limit(name, cur + g)
            await db.run("UPDATE panels SET gb=?, warn=0 WHERE id=?", cur + g, pid)
            await audit(me, uid, "panel_vol", "%s +%s گیگ" % (name, g))
            if f.get("notify"):
                await asyncio.to_thread(auth.tg_send, uid, "🎁 %s گیگ به پنل <code>%s</code> شما اضافه شد.\nحجم کل: %s گیگ" % (fa(g), esc(name), fg(cur + g)))
            pback(uid, pid, m="%s گیگ اضافه شد. حجم کل: %s گیگ" % (fa(g), fg(cur + g)))
        if a == "pw":
            npw = str(f.get("pw", "")).strip() or gen_password()
            bad = pw_problem(npw)
            if bad:
                pback(uid, pid, e=bad)
            await pg.set_password(name, npw)
            await db.run("UPDATE panels SET pw=? WHERE id=?", db.enc(npw), pid)
            await audit(me, uid, "panel_pw", name)
            if f.get("notify"):
                await asyncio.to_thread(auth.tg_send, uid, "🔑 رمز پنل <code>%s</code> شما تغییر کرد.\nرمز جدید: <code>%s</code>" % (esc(name), esc(npw)))
            done = '<div class="card c"><h3>✅ رمز جدید</h3><div class="kv"><span>نام کاربری</span><b dir="ltr">%s</b></div><div class="kv"><span>رمز</span><b dir="ltr">%s</b></div></div>' % (esc(name), esc(npw))
            return await panel_page(req, done)
    except (web.HTTPException, asyncio.CancelledError):
        raise
    except PanelError as e:
        pback(uid, pid, e="پنل درخواست را نپذیرفت: " + str(e)[:150])
    except Exception:
        log.exception("panel action failed")
        pback(uid, pid, e="عملیات ناموفق بود (لاگ سرور را ببین).")
    pback(uid, pid, e="عملیات نامعتبر است.")


# ---------------------------------------------------------------- wiring
M.users_page, M.user_page = users_page, user_page
_pi = pages.install


def install(app):
    _pi(app)
    app.on_startup.append(startup)
    app.middlewares.append(cmw)
    r = app.router
    r.add_post("/admin/users/bulk", bulk_post)
    r.add_post(r"/admin/users/{id:\d+}/plus", user_plus)
    r.add_get(r"/admin/users/{id:\d+}/sales.csv", sales_csv)
    r.add_get(r"/admin/users/{id:\d+}/panel/{pid:\d+}", panel_page)
    r.add_post(r"/admin/users/{id:\d+}/panel/{pid:\d+}/act", panel_act)


pages.install = install
