from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
import urllib.request

from aiohttp import web

from bot import db
from bot.panel import PanelError, PanelTaken, gen_password
from bot.user import USER_RE, creds_text, new_panel, parse_gb, pw_problem
from web import app as A

from .auth import same_origin
from .buyui import DONE_JS, FORM_JS, ST
from .theme import esc, fa, fg, shell

log = logging.getLogger("shop.buy")
BUSY: set = set()
DONE: dict = {}
KEEP: set = set()
FAILED = "ساخت پنل ناموفق بود؛ مبلغ به کیف پولت برگشت."
ICONS = ["🚀", "⚡", "🛰", "💎", "🔥", "🌐"]


async def startup(app):
    await db.init()


def tg_call(body):
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % A.env("BOT_TOKEN"),
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            r.read()
    except Exception as e:
        log.warning("telegram send failed: %r", e)


def bg(fn, *a):
    t = asyncio.ensure_future(asyncio.to_thread(fn, *a))
    KEEP.add(t)
    t.add_done_callback(KEEP.discard)


def tg_card(uid, name, pw, gb, base):
    rows = [[{"text": "🖥 ورود به پنل", "url": base.rstrip("/") + "/dashboard"}],
            [{"text": "🔑 کپی رمز", "copy_text": {"text": pw}}, {"text": "👤 کپی نام کاربری", "copy_text": {"text": name}}]]
    tg_call({"chat_id": uid, "parse_mode": "HTML", "reply_markup": {"inline_keyboard": rows},
             "text": "🎉 <b>خرید از سایت انجام شد</b>\n\n" + creds_text(name, pw, gb, base)})


def tg_admins(text):
    for a in A.admin_ids():
        tg_call({"chat_id": a, "text": text, "parse_mode": "HTML"})


async def balance(uid):
    r = await db.row("SELECT balance FROM users WHERE tg_id=?", uid)
    return int(r["balance"]) if r and r["balance"] is not None else 0


async def resolve(kind, rid, gb_raw=""):
    """-> (product, gb, price, error). Price always comes from the DB."""
    if kind == "p":
        k = await db.row("SELECT * FROM packages WHERE id=? AND active=1", rid)
        x = await db.row("SELECT * FROM products WHERE id=? AND active=1", k["product_id"]) if k else None
        if not k or not x:
            return None, 0, 0, "این پکیج دیگر موجود نیست."
        return x, k["gb"], k["price"], ""
    x = await db.row("SELECT * FROM products WHERE id=? AND active=1", rid)
    if not x or x["price_gb"] <= 0:
        return None, 0, 0, "حجم دلخواه برای این محصول فعال نیست."
    gb = parse_gb(gb_raw) if gb_raw else None
    if gb is None or not x["min_gb"] <= gb <= x["max_gb"]:
        return x, 0, 0, "حجم باید بین %s تا %s گیگ باشد." % (x["min_gb"], x["max_gb"])
    return x, gb, int(round(gb * x["price_gb"])), ""


async def _purchase(uid, x, gb, price, user, pw):
    """Debit -> create panel -> refund on any failure. Returns (result, error)."""
    BUSY.add(uid)
    try:
        if not await db.debit(uid, price):
            return None, "موجودی کافی نیست؛ اول کیف پول را شارژ کن."
        try:
            res = await new_panel(uid, x["id"], gb, False, user, pw)
        except Exception as ex:
            await db.credit(uid, price)
            if isinstance(ex, PanelTaken):
                return None, "این نام کاربری روی پنل گرفته شده؛ نام دیگری بزن."
            log.exception("web buy failed")
            if isinstance(ex, PanelError):
                return None, "پنل درخواست را نپذیرفت: " + str(ex)[:200]
            return None, FAILED
        try:
            await db.sale(uid, res[0], "panel", gb, price)
        except Exception:
            log.exception("sale record failed")
        return res, ""
    finally:
        BUSY.discard(uid)


async def buy_list(req):
    bal = await balance(req["uid"])
    out = ""
    for i, x in enumerate(await db.rows("SELECT * FROM products WHERE active=1 ORDER BY sort, id")):
        ks = await db.rows("SELECT * FROM packages WHERE product_id=? AND active=1 ORDER BY gb", x["id"])
        ok = [k for k in ks if k["gb"] > 0]
        best = min(ok, key=lambda k: k["price"] / k["gb"])["id"] if len(ok) > 1 else None
        tiles = "".join('<a class="tl" href="/buy/p/%d">%s<b>%s</b><small>گیگ</small><div class="pr">%s تومان</div></a>' % (
            k["id"], '<span class="bdg">💎 به‌صرفه‌ترین</span>' if k["id"] == best else "", fg(k["gb"]), fa(k["price"])) for k in ks)
        if x["price_gb"] > 0:
            tiles += ('<a class="tl" href="/buy/c/%d"><b>✏️</b><small>حجم دلخواه</small><div class="pr">هر گیگ %s</div></a>'
                      % (x["id"], fa(x["price_gb"])))
        out += ('<div class="pc rv"><div class="pi"><div class="ph"><div class="pe">%s</div><div><h3>%s</h3></div></div>'
                '<div class="mu">%s</div><div class="tg">%s</div></div></div>') % (
            ICONS[i % len(ICONS)], esc(x["name"]), esc(x["descr"]), tiles or '<div class="mu">پکیجی ثبت نشده.</div>')
    steps = ('<div class="stp"><span class="on"><i>۱</i>انتخاب پکیج</span><u></u><span><i>۲</i>مشخصات</span><u></u>'
             '<span><i>۳</i>تحویل</span></div>')
    body = ST + steps + ('<div class="grid">%s</div>' % out if out else '<div class="card">محصولی فعال نیست.</div>')
    return shell("خرید پنل", body, "buy", sub="موجودی تو: <b>%s</b> تومان" % fa(bal))


async def form_page(uid, kind, rid, gb_raw="", user="", pw="", err="", status=200):
    x, gb, price, e = await resolve(kind, rid, gb_raw)
    if not x:
        return shell("خرید پنل", '<div class="card">%s</div>' % esc(e), "buy", status=404)
    bal = await balance(uid)
    err = err or (e if gb_raw else "")
    tip = gbf = ""
    if kind == "p":
        fix = price
        nxt = await db.row("SELECT * FROM packages WHERE product_id=? AND active=1 AND gb>? ORDER BY gb LIMIT 1", x["id"], gb)
        if nxt and nxt["gb"] > 0 and gb > 0 and nxt["price"] / nxt["gb"] < price / gb:
            tip = ('<a class="card tp" href="/buy/p/%d" style="display:block">💡 با <b>%s</b> تومان بیشتر، <b>%s</b> گیگ بیشتر '
                   'بگیر؛ هر گیگ ارزان‌تر می‌شود.</a>' % (nxt["id"], fa(nxt["price"] - price), fg(nxt["gb"] - gb)))
        big = "%s <small>گیگ</small>" % fg(gb)
    else:
        fix, big = 0, "حجم دلخواه"
        try:
            sv = float(gb_raw)
        except ValueError:
            sv = x["min_gb"]
        sv = min(max(sv, x["min_gb"]), x["max_gb"])
        step = max(1, round((x["max_gb"] - x["min_gb"]) / 200))
        gbf = ('<label>حجم (گیگابایت؛ مثال: 300 یا 2tb)</label><input name="gb" value="%s" inputmode="decimal" required>'
               '<input type="range" id="sl" min="%g" max="%g" step="%d" value="%g">'
               '<div class="mu">هر گیگ %s تومان · از %s تا %s گیگ</div>') % (
            esc(gb_raw), x["min_gb"], x["max_gb"], step, sv, fa(x["price_gb"]), fg(x["min_gb"]), fg(x["max_gb"]))
    steps = ('<div class="stp"><span class="on"><i>✓</i>انتخاب</span><u></u><span class="on"><i>۲</i>مشخصات</span><u></u>'
             '<span><i>۳</i>تحویل</span></div>')
    hero = ('<div class="hero rv"><div class="mu" style="color:#cbd5e1;margin:0">%(n)s</div><div class="big">%(big)s</div>'
            '<div class="hs"><div><b id="pv">—</b><span>مبلغ سفارش</span></div><div><b>%(bal)s</b><span>موجودی تو (تومان)</span></div>'
            '<div><b id="af">—</b><span>بعد از خرید</span></div></div></div>') % {"n": esc(x["name"]), "big": big, "bal": fa(bal)}
    warn = ('<div id="lw" class="card wr" hidden>⚠️ موجودی کافی نیست؛ <b id="lwa"></b> تومان کم داری.'
            '<a class="cta" href="/wallet">⚡ شارژ سریع کیف پول</a></div>')
    errbox = '<div class="er">%s</div>' % esc(err) if err else ""
    form = ('<form id="bf" class="card fm" method="post" action="/buy/%(k)s/%(r)d" autocomplete="off" data-bal="%(bal)d" '
            'data-pg="%(pg)s" data-fix="%(fix)d" data-mn="%(mn)g" data-mx="%(mx)g">%(gbf)s'
            '<label>نام کاربری پنل (انگلیسی، ۴ تا ۲۰ کاراکتر)</label>'
            '<input name="user" value="%(u)s" placeholder="ali_panel" required maxlength="20"><div class="hint" id="uh"></div>'
            '<label>رمز پنل (حداقل ۸ کاراکتر و ۲ رقم)</label><div class="rw"><input name="pw" type="text" value="%(pw)s" required>'
            '<button type="button" class="ib" id="gp" title="رمز جدید">🎲</button>'
            '<button type="button" class="ib" id="tp" title="نمایش یا مخفی">👁</button></div>'
            '<button class="go" id="sb">🛒 پرداخت و ساخت پنل</button></form>') % {
        "k": kind, "r": rid, "bal": bal, "pg": x["price_gb"], "fix": fix, "mn": x["min_gb"], "mx": x["max_gb"],
        "gbf": gbf, "u": esc(user), "pw": esc(pw or gen_password())}
    sheet = ('<div class="ov" id="ov" hidden><div class="sh"><h3>تأیید سفارش</h3>'
             '<div class="ln"><span>نام کاربری پنل</span><b id="cu" dir="ltr"></b></div>'
             '<div class="ln"><span>مبلغ</span><b id="cs"></b></div>'
             '<div class="ln"><span>موجودی بعد از خرید</span><b id="ca"></b></div>'
             '<div class="ac"><button class="no" id="cn" type="button">انصراف</button>'
             '<button class="go" id="cy" type="button">تأیید و پرداخت</button></div></div></div>'
             '<div class="ov" id="ld" hidden><div class="sh" style="text-align:center"><div class="spn"></div>'
             '<b>در حال ساخت پنل...</b><div class="mu">چند ثانیه صبر کن؛ صفحه را نبند.</div></div></div>')
    return shell("خرید پنل", ST + steps + hero + warn + errbox + tip + form + sheet + FORM_JS, "buy", status=status)


def done_page(d):
    url = d["base"].rstrip("/") + "/dashboard"
    body = ST + (
        '<div class="okr"><svg viewBox="0 0 120 120"><circle class="c" cx="60" cy="60" r="52" transform="rotate(-90 60 60)"/>'
        '<path class="k" d="M38 62 L54 77 L84 45"/></svg></div>'
        '<div style="text-align:center"><h2 style="margin:0">پنلت آماده است 🎉</h2>'
        '<div class="mu">این اطلاعات را همین الان ذخیره کن؛ این صفحه تا ۱۰ دقیقه در دسترس است.</div></div>'
        '<div class="card" style="margin-top:16px">'
        '<div class="cr"><div><small>آدرس پنل</small><b>%(url)s</b></div><button class="cp" data-c="%(url)s">📋 کپی</button></div>'
        '<div class="cr"><div><small>نام کاربری</small><b>%(name)s</b></div><button class="cp" data-c="%(name)s">📋 کپی</button></div>'
        '<div class="cr"><div><small>رمز</small><b id="pwv">••••••••••</b></div>'
        '<button class="ib" id="ev" type="button">👁</button><button class="cp" data-c="%(pw)s">📋 کپی</button></div>'
        '<div class="cr"><div><small>حجم / اعتبار</small><b>%(gb)s گیگ · نامحدود</b></div></div></div>'
        '<a class="cta" href="%(url)s" target="_blank" rel="noopener">🖥 ورود به پنل</a>'
        '<a class="cta off" style="margin-top:10px" href="/panels">📦 پنل‌های من</a>'
        '<div class="mu" style="text-align:center;margin-top:14px">کسرشده: %(price)s تومان · موجودی فعلی: %(bal)s تومان<br>'
        'یک نسخه از اطلاعات به تلگرامت هم فرستاده می‌شود.</div>'
        '<script>(function(){var v=document.getElementById("pwv"),b=document.getElementById("ev"),p=%(pwj)s,s=0;'
        'b.onclick=function(){s=!s;v.textContent=s?p:"••••••••••"}})();</script>') % {
        "url": esc(url), "name": esc(d["name"]), "pw": esc(d["pw"]), "gb": fg(d["gb"]), "price": fa(d["price"]),
        "bal": fa(d["bal"]), "pwj": json.dumps(d["pw"]).replace("<", "\\u003c")}
    return shell("خرید موفق", body + DONE_JS, "buy")


async def buy_form(req):
    return await form_page(req["uid"], req.match_info["kind"], int(req.match_info["id"]))


async def buy_post(req):
    same_origin(req)
    uid, kind, rid = req["uid"], req.match_info["kind"], int(req.match_info["id"])
    f = await req.post()
    user, pw, gb_raw = (str(f.get(k, "")).strip() for k in ("user", "pw", "gb"))

    def again(err, status=400):
        return form_page(uid, kind, rid, gb_raw, user, pw, err, status)
    x, gb, price, e = await resolve(kind, rid, gb_raw)
    if not x or e or price <= 0:
        return await again(e or "سفارش معتبر نیست.")
    if not USER_RE.match(user):
        return await again("نام کاربری معتبر نیست (انگلیسی، عدد و _، شروع با حرف، ۴ تا ۲۰ کاراکتر).")
    bad = pw_problem(pw)
    if bad:
        return await again(bad)
    if uid in BUSY:
        return await again("سفارش قبلی در حال انجام است؛ چند ثانیه صبر کن.", 429)
    BUSY.add(uid)
    task = asyncio.ensure_future(_purchase(uid, x, gb, price, user, pw))
    res, err = await asyncio.shield(task)
    if not res:
        if err == FAILED:
            bg(tg_admins, "⚠️ ساخت پنل از سایت ناموفق بود؛ کاربر <code>%s</code> (پول برگشت داده شد)." % uid)
        return await again(err)
    now, tok = time.time(), secrets.token_urlsafe(16)
    for k in [k for k, v in DONE.items() if v[2] < now]:
        DONE.pop(k, None)
    DONE[tok] = (uid, {"name": res[0], "pw": res[1], "gb": gb, "base": res[2], "price": price,
                       "bal": await balance(uid)}, now + 600)
    bg(tg_card, uid, res[0], res[1], gb, res[2])
    raise web.HTTPFound("/buy/done/" + tok)


async def done_get(req):
    e = DONE.get(req.match_info["t"])
    if not e or e[0] != req["uid"] or e[2] < time.time():
        raise web.HTTPFound("/panels")
    return done_page(e[1])


def install(app):
    r = app.router
    r.add_get("/buy", buy_list)
    r.add_get(r"/buy/{kind:[pc]}/{id:\d+}", buy_form)
    r.add_post(r"/buy/{kind:[pc]}/{id:\d+}", buy_post)
    r.add_get(r"/buy/done/{t:[A-Za-z0-9_-]{10,40}}", done_get)
