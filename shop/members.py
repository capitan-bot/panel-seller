"""Admin users manager for the shop (site users, balance, orders, ban/kick, limits, site admins, delete, log, csv).

Install: in main.py, right after `from . import shahin` add `from . import members`.
Own tables live in bot.db: shop_users, shop_audit, shop_admins (the bot ignores them).
"""
from __future__ import annotations

import asyncio
import csv
import io
import logging
import re
import secrets
import time
from urllib.parse import quote

from aiohttp import web

from bot import db
from bot.panel import PanelError, PanelTaken, gen_password
from bot.user import USER_RE, new_panel, pw_problem
from web import app as A

from . import admin, auth, buy, pages, theme
from .theme import esc, fa, fg

log = logging.getLogger("shop.members")

_orig_ids = A.admin_ids
_ADM = {"s": set()}
META, SEEN, KEEP = {}, {}, set()
EXEMPT = ("/login", "/api/login", "/logout", "/static/", "/health")
BUYPOST = re.compile(r"^/buy/[pc]/\d+$")
VOLPOST = re.compile(r"^/panels/\d+/volume$")
PER = 15
DEF = {"joined": 0, "seen_at": 0, "hits": 0, "ip": "", "ua": "", "note": "", "vip": 0, "banned": 0, "kicked": 0,
       "can_buy": 1, "can_charge": 1, "max_day": 0, "max_panels": 0}
SCHEMA = (
    "CREATE TABLE IF NOT EXISTS shop_users(uid INTEGER PRIMARY KEY, joined INTEGER NOT NULL DEFAULT 0, "
    "seen_at INTEGER NOT NULL DEFAULT 0, hits INTEGER NOT NULL DEFAULT 0, ip TEXT NOT NULL DEFAULT '', "
    "ua TEXT NOT NULL DEFAULT '', note TEXT NOT NULL DEFAULT '', vip INTEGER NOT NULL DEFAULT 0, "
    "banned INTEGER NOT NULL DEFAULT 0, kicked INTEGER NOT NULL DEFAULT 0, can_buy INTEGER NOT NULL DEFAULT 1, "
    "can_charge INTEGER NOT NULL DEFAULT 1, max_day INTEGER NOT NULL DEFAULT 0, max_panels INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS shop_audit(id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, "
    "adm INTEGER NOT NULL, uid INTEGER NOT NULL DEFAULT 0, act TEXT NOT NULL, info TEXT NOT NULL DEFAULT '')",
    "CREATE TABLE IF NOT EXISTS shop_admins(uid INTEGER PRIMARY KEY, added INTEGER NOT NULL, by_uid INTEGER NOT NULL DEFAULT 0)",
)


def now():
    return int(time.time())


# ---------------------------------------------------------------- site admins (extra admins stored in bot.db)
def root():
    return set(_orig_ids())


def admin_ids():
    return root() | _ADM["s"]


A.admin_ids = admin_ids


async def startup(app):
    for sql in SCHEMA:
        await db.run(sql)
    _ADM["s"] = {r["uid"] for r in await db.rows("SELECT uid FROM shop_admins")}


# ---------------------------------------------------------------- per-user meta
async def mrow(uid):
    r = await db.row("SELECT * FROM shop_users WHERE uid=?", uid)
    return dict(DEF, **dict(r)) if r else dict(DEF)


async def meta(uid):
    c = META.get(uid)
    if c and time.time() - c[0] < 30:
        return c[1]
    m = await mrow(uid)
    META[uid] = (time.time(), m)
    return m


async def mset(uid, **kw):
    await db.run("INSERT OR IGNORE INTO shop_users(uid) VALUES(?)", uid)
    await db.run("UPDATE shop_users SET %s WHERE uid=?" % ",".join("%s=?" % k for k in kw), *kw.values(), uid)
    META.pop(uid, None)


async def audit(adm, uid, act, info=""):
    await db.run("INSERT INTO shop_audit(ts,adm,uid,act,info) VALUES(?,?,?,?,?)", now(), adm, uid, act, str(info)[:300])


async def track(req, uid, login=False):
    t = now()
    if not login and t - SEEN.get(uid, 0) < 60:
        return
    SEEN[uid] = t
    await db.run(
        "INSERT INTO shop_users(uid,joined,seen_at,hits,ip,ua) VALUES(?,?,?,?,?,?) ON CONFLICT(uid) DO UPDATE SET "
        "seen_at=excluded.seen_at, ip=excluded.ip, ua=excluded.ua, hits=shop_users.hits+excluded.hits, "
        "joined=CASE WHEN shop_users.joined=0 THEN excluded.joined ELSE shop_users.joined END",
        uid, t, t, 1 if login else 0, auth.client_ip(req), req.headers.get("User-Agent", "")[:160])


# ---------------------------------------------------------------- enforcement middleware
def deny(msg):
    body = '<div class="card">%s</div><a class="cta off" style="margin-top:14px" href="/">بازگشت</a>' % esc(msg)
    return theme.shell("محدودیت حساب", body, "home", status=403)


def banned_page():
    body = ('<div class="card bx"><h1>دسترسی مسدود است</h1><p>دسترسی حساب شما به سایت مسدود شده است. '
            'برای پیگیری به پشتیبانی پیام بده.</p><form method="post" action="/logout"><button class="go">خروج</button></form></div>')
    return theme.shell("مسدود", body, nav=False, status=403)


async def gate(req, uid, ck):
    if uid in A.admin_ids():
        return None
    m = await meta(uid)
    try:
        issued = int(ck.split(".")[1]) - auth.SESSION
    except Exception:
        issued = 0
    if m["kicked"] and issued < m["kicked"]:
        r = web.HTTPFound("/login")
        r.del_cookie("pgshop", path="/")
        return r
    if m["banned"]:
        return banned_page()
    if req.method != "POST":
        return None
    p = req.path
    if p.startswith("/wallet/") and not m["can_charge"]:
        return deny("شارژ کیف پول برای حساب شما غیرفعال شده است.")
    new = bool(BUYPOST.match(p))
    if (new or VOLPOST.match(p)) and not m["can_buy"]:
        return deny("خرید برای حساب شما غیرفعال شده است.")
    if new and m["max_day"]:
        n = (await db.row("SELECT COUNT(*) c FROM sales WHERE user_id=? AND kind='panel' AND created>?", uid, now() - 86400))["c"]
        if n >= m["max_day"]:
            return deny("به سقف خرید ۲۴ ساعته (%s خرید) رسیده‌ای؛ بعداً امتحان کن." % fa(m["max_day"]))
    if new and m["max_panels"]:
        n = (await db.row("SELECT COUNT(*) c FROM panels WHERE user_id=? AND is_test=0 AND status!='deleted'", uid))["c"]
        if n >= m["max_panels"]:
            return deny("به سقف تعداد پنل (%s پنل) رسیده‌ای." % fa(m["max_panels"]))
    return None


async def login_hook(req, resp):
    try:
        if req.method == "POST" and req.path in ("/login/code", "/api/login/code"):
            c = resp.cookies.get("pgshop")
            uid = auth.read_cookie(c.value) if c and c.value else None
            if uid is not None:
                await track(req, uid, True)
    except Exception:
        log.exception("login hook")


@web.middleware
async def mw(req, handler):
    uid = None
    try:
        if not req.path.startswith(EXEMPT):
            ck = req.cookies.get("pgshop", "")
            uid = auth.read_cookie(ck)
            if uid is not None:
                blocked = await gate(req, uid, ck)
                if blocked is not None:
                    return blocked
    except web.HTTPException:
        raise
    except Exception:
        log.exception("members gate")
    try:
        resp = await handler(req)
    except web.HTTPException as e:
        await login_hook(req, e)
        raise
    await login_hook(req, resp)
    if uid is not None:
        try:
            await track(req, uid)
        except Exception:
            log.exception("track")
    return resp


# ---------------------------------------------------------------- ui helpers
STY = ("<style>.adm select{width:100%;padding:11px;border-radius:12px;border:1px solid var(--bd);background:var(--card);"
       "color:var(--tx);font-family:inherit;font-size:15px}.g2{display:grid;gap:10px;grid-template-columns:1fr 1fr}"
       ".sg{display:grid;gap:10px;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));margin-bottom:14px}"
       ".sg div{padding:14px;border-radius:16px;background:var(--card);border:1px solid var(--bd)}"
       ".sg b{display:block;font-size:19px}.sg span{color:var(--mu);font-size:12px}"
       ".adm .ck{display:flex;align-items:center;gap:8px;margin:10px 0;color:var(--tx)}.adm .ck input{width:auto}"
       ".acts{display:flex;flex-wrap:wrap;gap:8px}.acts form{display:inline}.acts .b{margin-top:0}"
       ".msg{padding:12px;border-radius:14px;margin-bottom:12px}.msg.ok{background:#34d3991f;color:#10b981}"
       ".msg.er{background:#f871711f;color:#ef4444}.kv{display:flex;justify-content:space-between;gap:10px;padding:8px 0;"
       "border-bottom:1px solid var(--bd)}.kv:last-child{border:0}.kv span{color:var(--mu)}.kv b{text-align:left;word-break:break-all}"
       "</style>")


def page(active, title, body, req=None):
    flash = ""
    if req is not None:
        if req.query.get("m"):
            flash += '<div class="msg ok">%s</div>' % esc(req.query["m"])
        if req.query.get("e"):
            flash += '<div class="msg er">%s</div>' % esc(req.query["e"])
    return admin.layout(active, title, STY + flash + body)


def tm(ts):
    return '<span class="tm" data-f="dt" data-t="%d"></span>' % ts if ts else "—"


def back(uid, m="", e=""):
    raise web.HTTPFound("/admin/users/%d?%s=%s" % (uid, "e" if e else "m", quote(e or m)))


def num(v, lo=0, hi=10 ** 11):
    try:
        n = int(str(v).translate(auth.DIG).replace(",", "").replace("٬", "").strip())
    except (TypeError, ValueError):
        return None
    return n if lo <= n <= hi else None


def form(action, inner, btn, cls="b", confirm=""):
    return ('<form method="post" action="%s"%s>%s<button class="%s">%s</button></form>'
            % (action, ' onsubmit="return confirm(\'%s\')"' % confirm if confirm else "", inner, cls, btn))


def hid(name, val):
    return '<input type="hidden" name="%s" value="%s">' % (name, esc(val))


def badges(tg, blocked, banned, vip):
    out = ""
    if blocked:
        out += ' <span class="st no">مسدود</span>'
    if banned:
        out += ' <span class="st no">بن سایت</span>'
    if vip:
        out += ' <span class="st ok">VIP</span>'
    if tg in A.admin_ids():
        out += ' <span class="st ok">ادمین</span>'
    return out


# ---------------------------------------------------------------- list
FILT = (("site", "ورودکرده‌ها به سایت"), ("act", "فعال ۲۴ ساعت اخیر"), ("ban", "مسدودها"), ("bal", "دارای موجودی"),
        ("vip", "VIP"), ("all", "همه‌ی کاربران ربات"))


def where_for(f, q):
    w, a = [], []
    if f == "site":
        w.append("s.seen_at>0")
    elif f == "act":
        w.append("s.seen_at>?")
        a.append(now() - 86400)
    elif f == "ban":
        w.append("(u.blocked=1 OR s.banned=1)")
    elif f == "bal":
        w.append("u.balance>0")
    elif f == "vip":
        w.append("s.vip=1")
    if q:
        w.append("(CAST(u.tg_id AS TEXT)=? OR u.name LIKE ? OR u.username LIKE ?)")
        a += [q, "%" + q + "%", "%" + q.lstrip("@") + "%"]
    return (" WHERE " + " AND ".join(w)) if w else "", a


async def users_page(req):
    admin.need(req)
    q = str(req.query.get("q", "")).strip()[:40]
    f = req.query.get("f", "site")
    f = f if f in dict(FILT) else "site"
    p = num(req.query.get("p", 1), 1, 100000) or 1
    w, a = where_for(f, q)
    base = "FROM users u LEFT JOIN shop_users s ON s.uid=u.tg_id" + w
    total = (await db.row("SELECT COUNT(*) c " + base, *a))["c"]
    rows = await db.rows("SELECT u.tg_id,u.name,u.username,u.balance,u.blocked,COALESCE(s.seen_at,0) seen_at,"
                         "COALESCE(s.banned,0) banned,COALESCE(s.vip,0) vip " + base +
                         " ORDER BY COALESCE(s.seen_at,0) DESC, u.created DESC LIMIT ? OFFSET ?", *a, PER, (p - 1) * PER)
    t = now() - 86400
    st = await db.row("SELECT (SELECT COUNT(*) FROM users) a,(SELECT COUNT(*) FROM shop_users WHERE seen_at>0) b,"
                      "(SELECT COUNT(*) FROM shop_users WHERE seen_at>?) c,(SELECT COUNT(*) FROM shop_users WHERE joined>?) d,"
                      "(SELECT COUNT(*) FROM sales WHERE created>?) e,(SELECT COALESCE(SUM(price),0) FROM sales WHERE created>?) g,"
                      "(SELECT COALESCE(SUM(balance),0) FROM users) h", t, t, t, t)
    cells = (("کل کاربران ربات", st["a"]), ("ورودکرده به سایت", st["b"]), ("فعال ۲۴ ساعت", st["c"]),
             ("جدید در سایت (۲۴س)", st["d"]), ("خرید ۲۴ ساعت", st["e"]), ("فروش ۲۴ ساعت (تومان)", st["g"]),
             ("جمع موجودی‌ها (تومان)", st["h"]))
    stats = '<div class="sg">%s</div>' % "".join("<div><b>%s</b><span>%s</span></div>" % (fa(v), k) for k, v in cells)
    opts = "".join('<option value="%s"%s>%s</option>' % (k, " selected" if k == f else "", n) for k, n in FILT)
    search = ('<form method="get" action="/admin/users"><div class="g2"><div><label>جستجو (آیدی، نام یا یوزرنیم)</label>'
              '<input name="q" value="%s"></div><div><label>فیلتر</label><select name="f">%s</select></div></div>'
              '<button class="b">🔍 جستجو</button> <a class="b" style="text-decoration:none" href="/admin/users.csv">⬇️ خروجی CSV</a></form>'
              % (esc(q), opts))
    items = "".join(
        '<a class="tx" href="/admin/users/%d"><div><b>%s</b>%s<br><small>%s%s · %d</small><br><small>%s</small></div><b>%s</b></a>' % (
            r["tg_id"], esc(r["name"] or "?"), badges(r["tg_id"], r["blocked"], r["banned"], r["vip"]),
            ("@" + esc(r["username"]) + " · ") if r["username"] else "", "", r["tg_id"],
            ("آخرین بازدید: " + tm(r["seen_at"])) if r["seen_at"] else "هنوز وارد سایت نشده", fa(r["balance"]))
        for r in rows)
    pq = "&q=%s&f=%s" % (quote(q), f)
    nav = ""
    if p > 1:
        nav += '<a class="b" style="text-decoration:none" href="/admin/users?p=%d%s">قبلی</a> ' % (p - 1, pq)
    if p * PER < total:
        nav += '<a class="b" style="text-decoration:none" href="/admin/users?p=%d%s">بعدی</a>' % (p + 1, pq)
    body = (stats + admin.card(search) + admin.card((items or '<div class="mu">کاربری پیدا نشد.</div>') +
                                                   '<div class="mu" style="margin-top:10px">%s مورد</div>%s' % (fa(total), nav)))
    return page("users", "کاربران", body, req)


async def users_csv(req):
    admin.need(req)
    rs = await db.rows("SELECT u.tg_id,u.name,u.username,u.balance,u.blocked,u.created,COALESCE(s.seen_at,0) seen_at,"
                       "COALESCE(s.hits,0) hits,COALESCE(s.banned,0) banned FROM users u LEFT JOIN shop_users s ON s.uid=u.tg_id "
                       "WHERE s.seen_at>0 ORDER BY s.seen_at DESC")
    b = io.StringIO()
    w = csv.writer(b)
    w.writerow(["id", "name", "username", "balance", "blocked", "site_banned", "created", "last_site_visit", "logins"])
    for r in rs:
        w.writerow([r["tg_id"], r["name"], r["username"], r["balance"], r["blocked"], r["banned"], r["created"], r["seen_at"], r["hits"]])
    return web.Response(body=("\ufeff" + b.getvalue()).encode("utf-8"), headers={
        "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": 'attachment; filename="site-users-%s.csv"' % time.strftime("%Y%m%d")})


# ---------------------------------------------------------------- profile
async def user_page(req):
    me = admin.need(req)
    uid = int(req.match_info["id"])
    u = await db.row("SELECT * FROM users WHERE tg_id=?", uid)
    if not u:
        raise web.HTTPNotFound()
    s = await mrow(uid)
    isroot, isadm = uid in root(), uid in A.admin_ids()
    kv = lambda k, v: '<div class="kv"><span>%s</span><b>%s</b></div>' % (k, v)
    info = (kv("نام", esc(u["name"] or "—")) + kv("یوزرنیم", ("@" + esc(u["username"])) if u["username"] else "—") +
            kv("آیدی", '<span dir="ltr">%d</span>' % uid) + kv("عضویت در ربات", tm(u["created"])) +
            kv("اولین ورود به سایت", tm(s["joined"])) + kv("آخرین بازدید سایت", tm(s["seen_at"])) +
            kv("تعداد ورود", fa(s["hits"])) + kv("IP آخر", '<span dir="ltr">%s</span>' % esc(s["ip"] or "—")) +
            kv("دستگاه", '<span dir="ltr">%s</span>' % esc(s["ua"][:70] or "—")) +
            kv("وضعیت", badges(uid, u["blocked"], s["banned"], s["vip"]) or "عادی") +
            kv("نقش", "ادمین اصلی" if isroot else ("ادمین سایت" if isadm else "کاربر")))
    bal = (kv("موجودی فعلی", "<b>%s</b> تومان" % fa(u["balance"])) +
           form("/admin/users/%d/bal" % uid,
                '<div class="g2"><div><label>عملیات</label><select name="op"><option value="add">افزایش</option>'
                '<option value="sub">کاهش</option><option value="set">تنظیم دقیق</option></select></div>'
                '<div><label>مبلغ (تومان)</label><input name="amt" inputmode="numeric" required></div></div>'
                '<label>دلیل (ثبت در لاگ)</label><input name="why" maxlength="100">'
                '<label class="ck"><input type="checkbox" name="notify" value="1" checked> اطلاع به کاربر در تلگرام</label>',
                "💰 اعمال", "b", "اعمال تغییر موجودی؟"))
    acts = '<div class="acts">'
    acts += form("/admin/users/%d/act" % uid, hid("a", "ban"), "✅ رفع بن سایت" if s["banned"] else "🚫 بن از سایت",
                 "b r" if not s["banned"] else "b", "انجام شود؟")
    acts += form("/admin/users/%d/act" % uid, hid("a", "kick"), "👢 اخراج فوری", "b r", "جلسه‌ی ورود کاربر باطل شود؟")
    acts += form("/admin/users/%d/act" % uid, hid("a", "block"), "🔓 رفع مسدودی ربات" if u["blocked"] else "⛔ مسدود (سایت و ربات)",
                 "b" if u["blocked"] else "b r", "انجام شود؟")
    acts += form("/admin/users/%d/act" % uid, hid("a", "vip"), "⭐ برداشتن VIP" if s["vip"] else "⭐ VIP کردن")
    if me in root() and not isroot:
        acts += form("/admin/users/%d/act" % uid, hid("a", "adm"), "👑 برداشتن ادمین سایت" if uid in _ADM["s"] else "👑 ادمین سایت کن",
                     "b", "تغییر نقش ادمین؟")
    acts += '<a class="b" style="text-decoration:none" href="/admin/users/%d/order">🛒 ثبت سفارش برای کاربر</a></div>' % uid
    lim = form("/admin/users/%d/limits" % uid,
               '<label class="ck"><input type="checkbox" name="can_buy" value="1"%s> اجازه‌ی خرید</label>'
               '<label class="ck"><input type="checkbox" name="can_charge" value="1"%s> اجازه‌ی شارژ کیف پول</label>'
               '<div class="g2"><div><label>سقف خرید در ۲۴ ساعت (۰ = بدون سقف)</label><input name="max_day" inputmode="numeric" value="%d"></div>'
               '<div><label>حداکثر تعداد پنل (۰ = بدون سقف)</label><input name="max_panels" inputmode="numeric" value="%d"></div></div>'
               % (" checked" if s["can_buy"] else "", " checked" if s["can_charge"] else "", s["max_day"], s["max_panels"]),
               "💾 ذخیره‌ی محدودیت‌ها")
    msg = form("/admin/users/%d/msg" % uid, '<label>پیام تلگرام به این کاربر</label><textarea name="t" rows="3" maxlength="1000" required></textarea>', "📨 ارسال")
    note = form("/admin/users/%d/note" % uid, '<label>یادداشت مدیر (فقط خودت می‌بینی)</label><textarea name="n" rows="2" maxlength="300">%s</textarea>' % esc(s["note"]), "💾 ذخیره‌ی یادداشت")
    ps = await db.rows("SELECT admin_username,status,expires,gb,is_test FROM panels WHERE user_id=? ORDER BY id DESC LIMIT 20", uid)
    pl = "".join('<div class="tx"><div><b dir="ltr">%s</b><br><small>%s · %s گیگ · انقضا: %s</small></div></div>' % (
        esc(p["admin_username"]), esc(p["status"]) + (" · تست" if p["is_test"] else ""), fg(p["gb"]), tm(p["expires"])) for p in ps)
    ss = await db.rows("SELECT created,kind,panel,gb,price FROM sales WHERE user_id=? ORDER BY id DESC LIMIT 10", uid)
    sl = "".join('<div class="tx"><div>%s<br><small>%s · %s</small></div><b>%s تومان</b></div>' % (
        esc(x["kind"]), esc(x["panel"] or "—"), tm(x["created"]), fa(x["price"])) for x in ss)
    rc = await db.rows("SELECT created,amount,status FROM receipts WHERE user_id=? ORDER BY id DESC LIMIT 5", uid)
    rl = "".join('<div class="tx"><div>%s<br><small>%s</small></div><b>%s تومان</b></div>' % (esc(x["status"]), tm(x["created"]), fa(x["amount"])) for x in rc)
    dele = ""
    if me in root() and not isadm:
        dele = admin.card('<h3>🗑 حذف کامل کاربر</h3><div class="mu">اگر پنل فعال یا رسید در انتظار داشته باشد حذف نمی‌شود. '
                          'تاریخچه‌ی فروش و رویدادها می‌ماند.</div>' +
                          form("/admin/users/%d/del" % uid, '<label>برای تأیید آیدی کاربر را بنویس: <b>%d</b></label><input name="confirm" inputmode="numeric" required>' % uid,
                               "🗑 حذف کامل", "b r", "کاربر برای همیشه حذف شود؟"))
    body = (admin.card("<h3>اطلاعات</h3>" + info) + admin.card("<h3>موجودی</h3>" + bal) + admin.card("<h3>عملیات</h3>" + acts) +
            admin.card("<h3>محدودیت‌ها</h3>" + lim) + admin.card("<h3>پیام و یادداشت</h3>" + msg + note) +
            admin.card("<h3>پنل‌ها</h3>" + (pl or '<div class="mu">پنلی ندارد.</div>')) +
            admin.card("<h3>آخرین خریدها</h3>" + (sl or '<div class="mu">خریدی ندارد.</div>')) +
            admin.card("<h3>آخرین رسیدها</h3>" + (rl or '<div class="mu">رسیدی ندارد.</div>')) + dele)
    return page("users", "کاربر %s" % (u["name"] or uid), body, req)


# ---------------------------------------------------------------- actions
async def target(req):
    me = admin.need(req, True)
    uid = int(req.match_info["id"])
    u = await db.row("SELECT * FROM users WHERE tg_id=?", uid)
    if not u:
        raise web.HTTPNotFound()
    return me, uid, u, await req.post()


async def user_act(req):
    me, uid, u, f = await target(req)
    a = str(f.get("a", ""))
    s = await mrow(uid)
    if a in ("ban", "kick", "block") and (uid in root() or (uid in A.admin_ids() and me not in root())):
        back(uid, e="روی ادمین‌ها این کار ممکن نیست.")
    if a == "ban":
        await mset(uid, banned=0 if s["banned"] else 1)
        msg = "بن سایت برداشته شد." if s["banned"] else "کاربر از سایت بن شد."
    elif a == "kick":
        await mset(uid, kicked=now())
        msg = "جلسه‌ی ورود کاربر باطل شد."
    elif a == "block":
        await db.run("UPDATE users SET blocked=1-blocked WHERE tg_id=?", uid)
        msg = "وضعیت مسدودی ربات تغییر کرد."
    elif a == "vip":
        await mset(uid, vip=0 if s["vip"] else 1)
        msg = "وضعیت VIP تغییر کرد."
    elif a == "adm":
        if me not in root() or uid in root():
            back(uid, e="فقط ادمین اصلی می‌تواند ادمین سایت تعیین کند.")
        if uid in _ADM["s"]:
            await db.run("DELETE FROM shop_admins WHERE uid=?", uid)
            _ADM["s"].discard(uid)
            msg = "ادمین سایت برداشته شد."
        else:
            await db.run("INSERT OR REPLACE INTO shop_admins(uid,added,by_uid) VALUES(?,?,?)", uid, now(), me)
            _ADM["s"].add(uid)
            msg = "کاربر ادمین سایت شد."
    else:
        back(uid, e="عملیات نامعتبر است.")
    await audit(me, uid, a, msg)
    back(uid, m=msg)


async def user_bal(req):
    me, uid, u, f = await target(req)
    op = str(f.get("op", ""))
    amt = num(f.get("amt", ""), 0, 10 ** 10)
    if amt is None or (amt == 0 and op != "set") or op not in ("add", "sub", "set"):
        back(uid, e="مبلغ یا عملیات معتبر نیست.")
    cur = int(u["balance"] or 0)
    if op == "set":
        diff = amt - cur
        op, amt = ("add", diff) if diff >= 0 else ("sub", -diff)
    if amt:
        if op == "add":
            await db.credit(uid, amt)
        elif not await db.debit(uid, amt):
            back(uid, e="موجودی کاربر برای این کاهش کافی نیست.")
    new = cur + amt if op == "add" else cur - amt
    why = str(f.get("why", "")).strip()[:100]
    await audit(me, uid, "bal_" + op, "%s تومان | قبل %s | بعد %s | %s" % (amt, cur, new, why))
    if f.get("notify") and amt:
        txt = "💰 موجودی کیف پول شما %s تومان %s شد.\nموجودی جدید: %s تومان" % (
            fa(amt), "افزایش یافت" if op == "add" else "کاهش یافت", fa(new))
        if why:
            txt += "\nتوضیح: " + esc(why)
        await asyncio.to_thread(auth.tg_send, uid, txt)
    back(uid, m="موجودی تغییر کرد. موجودی جدید: %s تومان" % fa(new))


async def user_limits(req):
    me, uid, u, f = await target(req)
    d = {"can_buy": 1 if f.get("can_buy") else 0, "can_charge": 1 if f.get("can_charge") else 0,
         "max_day": num(f.get("max_day", 0), 0, 1000) or 0, "max_panels": num(f.get("max_panels", 0), 0, 1000) or 0}
    await mset(uid, **d)
    await audit(me, uid, "limits", str(d))
    back(uid, m="محدودیت‌ها ذخیره شد.")


async def user_msg(req):
    me, uid, u, f = await target(req)
    t = str(f.get("t", "")).strip()[:1000]
    if not t:
        back(uid, e="متن پیام خالی است.")
    ok = await asyncio.to_thread(auth.tg_send, uid, "📩 <b>پیام از مدیریت</b>\n\n" + esc(t))
    await audit(me, uid, "msg", ("ارسال شد: " if ok else "ناموفق: ") + t[:100])
    back(uid, m="پیام ارسال شد." if ok else "", e="" if ok else "ارسال نشد (کاربر ربات را بلاک کرده یا /start نزده).")


async def user_note(req):
    me, uid, u, f = await target(req)
    await mset(uid, note=str(f.get("n", "")).strip()[:300])
    await audit(me, uid, "note", "")
    back(uid, m="یادداشت ذخیره شد.")


async def user_del(req):
    me, uid, u, f = await target(req)
    if me not in root():
        back(uid, e="فقط ادمین اصلی می‌تواند کاربر را حذف کند.")
    if str(f.get("confirm", "")).translate(auth.DIG).strip() != str(uid):
        back(uid, e="آیدی تأیید اشتباه است.")
    if uid in A.admin_ids():
        back(uid, e="ادمین را نمی‌شود حذف کرد.")
    n = (await db.row("SELECT COUNT(*) c FROM panels WHERE user_id=? AND status!='deleted'", uid))["c"]
    if n:
        back(uid, e="این کاربر %s پنل دارد؛ اول پنل‌هایش را از ربات حذف کن یا او را مسدود کن." % fa(n))
    if (await db.row("SELECT COUNT(*) c FROM receipts WHERE user_id=? AND status='pending'", uid))["c"]:
        back(uid, e="رسید در انتظار دارد؛ اول رسیدها را بررسی کن.")
    await audit(me, uid, "delete", "name=%s bal=%s" % (u["name"], u["balance"]))
    for sql in ("DELETE FROM code_uses WHERE user_id=?", "DELETE FROM shop_users WHERE uid=?", "DELETE FROM shop_admins WHERE uid=?",
                "DELETE FROM users WHERE tg_id=?"):
        await db.run(sql, uid)
    META.pop(uid, None)
    raise web.HTTPFound("/admin/users?m=" + quote("کاربر %d حذف شد." % uid))


# ---------------------------------------------------------------- order for user
async def order_page(req, err="", status=200):
    admin.need(req)
    uid = int(req.match_info["id"])
    u = await db.row("SELECT * FROM users WHERE tg_id=?", uid)
    if not u:
        raise web.HTTPNotFound()
    pks = await db.rows("SELECT k.id,k.gb,k.price,p.name FROM packages k JOIN products p ON p.id=k.product_id "
                        "WHERE k.active=1 AND p.active=1 ORDER BY p.sort,p.id,k.gb")
    cps = await db.rows("SELECT id,name,price_gb FROM products WHERE active=1 AND price_gb>0 ORDER BY sort,id")
    opts = "".join('<option value="p:%d">%s – %s گیگ – %s تومان</option>' % (k["id"], esc(k["name"]), fg(k["gb"]), fa(k["price"])) for k in pks)
    opts += "".join('<option value="c:%d">%s – حجم دلخواه (هر گیگ %s)</option>' % (c["id"], esc(c["name"]), fa(c["price_gb"])) for c in cps)
    body = ('<div class="mu" style="margin-bottom:10px">کاربر: <b>%s</b> · موجودی: <b>%s</b> تومان</div>' % (esc(u["name"] or uid), fa(u["balance"])) +
            ('<div class="msg er">%s</div>' % esc(err) if err else "") +
            admin.card(form("/admin/users/%d/order" % uid,
                            '<label>پکیج</label><select name="k">%s</select><label>حجم دلخواه (فقط برای «حجم دلخواه»، مثل 300 یا 2tb)</label>'
                            '<input name="gb"><label>نام کاربری پنل</label><input name="user" dir="ltr" value="p%s" maxlength="20" required>'
                            '<label>رمز پنل</label><input name="pw" dir="ltr" value="%s" required>'
                            '<label>پرداخت</label><select name="pay"><option value="free">رایگان (هدیه / ثبت دستی)</option>'
                            '<option value="charge">کسر از موجودی کاربر</option></select>'
                            '<div class="mu">اطلاعات پنل به تلگرام کاربر هم فرستاده می‌شود.</div>' % (opts, secrets.token_hex(4), esc(gen_password())),
                            "🛒 ساخت پنل", "b", "پنل برای این کاربر ساخته شود؟")) +
            '<a class="b" style="text-decoration:none" href="/admin/users/%d">⬅️ بازگشت</a>' % uid)
    r = page("users", "ثبت سفارش", body)
    if status != 200:
        return web.Response(text=r.text, content_type="text/html", status=status)
    return r


async def order_post(req):
    me = admin.need(req, True)
    uid = int(req.match_info["id"])
    u = await db.row("SELECT * FROM users WHERE tg_id=?", uid)
    if not u:
        raise web.HTTPNotFound()
    f = await req.post()
    kind, _, rid = str(f.get("k", "")).partition(":")
    user, pw, gb_raw, pay = (str(f.get(k, "")).strip() for k in ("user", "pw", "gb", "pay"))
    if kind not in ("p", "c") or not rid.isdigit():
        return await order_page(req, "پکیج نامعتبر است.", 400)
    x, gb, price, e = await buy.resolve(kind, int(rid), gb_raw)
    if not x or e or price <= 0:
        return await order_page(req, e or "سفارش معتبر نیست.", 400)
    if not USER_RE.match(user):
        return await order_page(req, "نام کاربری معتبر نیست (انگلیسی، عدد و _، شروع با حرف، ۴ تا ۲۰ کاراکتر).", 400)
    bad = pw_problem(pw)
    if bad:
        return await order_page(req, bad, 400)
    if uid in buy.BUSY:
        return await order_page(req, "سفارش دیگری برای این کاربر در حال انجام است.", 429)
    if pay == "charge":
        res, err = await buy._purchase(uid, x, gb, price, user, pw)
    else:
        res, err = None, ""
        buy.BUSY.add(uid)
        try:
            res = await new_panel(uid, x["id"], gb, False, user, pw)
            try:
                await db.sale(uid, res[0], "panel", gb, 0)
            except Exception:
                log.exception("sale record failed")
        except PanelTaken:
            err = "این نام کاربری روی پنل گرفته شده؛ نام دیگری بزن."
        except PanelError as ex:
            err = "پنل درخواست را نپذیرفت: " + str(ex)[:200]
        except Exception:
            log.exception("admin order failed")
            err = "ساخت پنل ناموفق بود."
        finally:
            buy.BUSY.discard(uid)
    if not res:
        return await order_page(req, err or "ساخت پنل ناموفق بود.", 400)
    buy.bg(buy.tg_card, uid, res[0], res[1], gb, res[2])
    await audit(me, uid, "order", "%s | %s گیگ | %s" % (res[0], gb, "کسر %s" % price if pay == "charge" else "رایگان"))
    kv = lambda k, v: '<div class="kv"><span>%s</span><b dir="ltr">%s</b></div>' % (k, esc(v))
    body = (admin.card("<h3>✅ پنل ساخته شد</h3>" + kv("آدرس", res[2].rstrip("/") + "/dashboard") + kv("نام کاربری", res[0]) +
                       kv("رمز", res[1]) + kv("حجم", "%s گیگ" % fg(gb))) +
            '<a class="b" style="text-decoration:none" href="/admin/users/%d">⬅️ بازگشت به کاربر</a>' % uid)
    return page("users", "سفارش ثبت شد", body)


# ---------------------------------------------------------------- log + broadcast
async def log_page(req):
    admin.need(req)
    rs = await db.rows("SELECT ts,adm,uid,act,info FROM shop_audit ORDER BY id DESC LIMIT 100")
    rows = "".join('<div class="tx"><div><b>%s</b> <small>توسط %d</small><br><small>%s</small></div><div style="text-align:left">'
                   '<a href="/admin/users/%d">%d</a><br><small>%s</small></div></div>' % (
                       esc(r["act"]), r["adm"], esc(r["info"]), r["uid"], r["uid"], tm(r["ts"])) for r in rs)
    return page("log", "لاگ عملیات", admin.card(rows or '<div class="mu">هنوز عملیاتی ثبت نشده.</div>'))


async def bc_page(req):
    admin.need(req)
    body = admin.card(form("/admin/broadcast",
                           '<label>مخاطب</label><select name="to"><option value="site">کاربران ورودکرده به سایت (بدون بن)</option>'
                           '<option value="all">همه‌ی کاربران ربات (بدون مسدود)</option></select>'
                           '<label>متن پیام</label><textarea name="t" rows="5" maxlength="1500" required></textarea>'
                           '<div class="mu">ارسال در پس‌زمینه انجام می‌شود و گزارش نهایی در تلگرام برایت می‌آید.</div>',
                           "📣 ارسال", "b", "پیام برای همه ارسال شود؟"))
    return page("bc", "پیام همگانی", body, req)


async def _bc(me, uids, text):
    ok = 0
    for i in uids:
        if await asyncio.to_thread(auth.tg_send, i, text):
            ok += 1
        await asyncio.sleep(0.06)
    await audit(me, 0, "broadcast", "%d از %d" % (ok, len(uids)))
    await asyncio.to_thread(auth.tg_send, me, "📣 ارسال همگانی تمام شد: %d از %d موفق." % (ok, len(uids)))


async def bc_post(req):
    me = admin.need(req, True)
    f = await req.post()
    t = str(f.get("t", "")).strip()[:1500]
    if not t:
        raise web.HTTPFound("/admin/broadcast?e=" + quote("متن خالی است."))
    sql = ("SELECT s.uid FROM shop_users s JOIN users u ON u.tg_id=s.uid WHERE s.seen_at>0 AND s.banned=0 AND u.blocked=0"
           if f.get("to") == "site" else "SELECT tg_id uid FROM users WHERE blocked=0")
    uids = [r["uid"] for r in await db.rows(sql)]
    task = asyncio.ensure_future(_bc(me, uids, "📣 <b>اطلاعیه</b>\n\n" + esc(t)))
    KEEP.add(task)
    task.add_done_callback(KEEP.discard)
    raise web.HTTPFound("/admin/broadcast?m=" + quote("ارسال برای %s نفر شروع شد." % fa(len(uids))))


# ---------------------------------------------------------------- wiring
admin.CORE[1:1] = [("users", "/admin/users", "👥", "کاربران"), ("log", "/admin/log", "🧾", "لاگ عملیات"),
                   ("bc", "/admin/broadcast", "📣", "پیام همگانی")]
_pi = pages.install


def install(app):
    _pi(app)
    app.on_startup.append(startup)
    app.middlewares.append(mw)
    r = app.router
    r.add_get("/admin/users", users_page)
    r.add_get("/admin/users.csv", users_csv)
    r.add_get(r"/admin/users/{id:\d+}", user_page)
    for name, fn in (("act", user_act), ("bal", user_bal), ("limits", user_limits), ("msg", user_msg),
                     ("note", user_note), ("del", user_del)):
        r.add_post(r"/admin/users/{id:\d+}/" + name, fn)
    r.add_get(r"/admin/users/{id:\d+}/order", order_page)
    r.add_post(r"/admin/users/{id:\d+}/order", order_post)
    r.add_get("/admin/log", log_page)
    r.add_get("/admin/broadcast", bc_page)
    r.add_post("/admin/broadcast", bc_post)


pages.install = install
