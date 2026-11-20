"""Unified theme + guest cart + in-page login for the shop. Loaded from main.py after `landing`."""
from __future__ import annotations

import asyncio
import contextvars
import hmac
import re
import secrets
import time

from aiohttp import web

from bot import db

from . import auth, buy, landing, pages, skin, theme, wallet
from .buyui import ST
from .theme import esc, fa, fg

CUR = contextvars.ContextVar("shop_cur", default=(None, 0))  # (uid from cookie, cart count)
CART = re.compile(r"^([pc]):(\d{1,9})$")
BUYP = re.compile(r"^/buy/([pc])/(\d+)$")
TABS = (("home", "/", "🏠", "خانه"), ("buy", "/buy", "🛍", "فروشگاه"), ("cart", "/cart", "🛒", "سبد"),
        ("panels", "/panels", "🖥", "پنل‌ها"), ("wallet", "/wallet", "💳", "کیف پول"))

UCSS = r"""
[hidden]{display:none!important}
body{padding-bottom:86px!important}
.utabs{position:fixed;bottom:0;left:0;right:0;z-index:30;display:flex;justify-content:center;gap:4px;padding:8px 8px calc(8px + env(safe-area-inset-bottom));background:#0b0b12;border-top:1px solid #232331}
.utb{position:relative;flex:1;max-width:130px;display:flex;flex-direction:column;align-items:center;gap:2px;padding:6px 0;border-radius:14px;color:#9a9db0;font-size:11px;text-decoration:none;font-family:V,Tahoma,sans-serif}
.utb i{font-style:normal;font-size:19px}.utb.on{color:#fff;background:#251f4a}
.utb em{position:absolute;top:2px;right:calc(50% - 26px);min-width:17px;height:17px;padding:0 4px;border-radius:9px;background:#a78bfa;color:#fff;font-size:10px;font-style:normal;display:grid;place-items:center}
.lo a{display:inline-block;background:#171722;border:1px solid #232331;color:#c4b5fd;border-radius:10px;padding:7px 12px;font-size:13px}
.fab{bottom:92px!important}.sc{bottom:96px!important}
.ulm{position:fixed;inset:0;z-index:100;display:grid;place-items:center;background:#000b;padding:16px}
.ulc{position:relative;width:min(100%,400px);padding:26px 22px;border-radius:24px;background:#12121a;border:1px solid #232331;color:#eceef5;text-align:center;font-family:V,Tahoma,sans-serif}
.ulc h3{margin:0 0 6px;font-size:20px}.ulc p{margin:0 0 16px;color:#9a9db0;font-size:14px;line-height:1.9}
.ulc input{width:100%;padding:14px;border-radius:14px;border:1px solid #2c2c36;background:#0d0d13;color:#fff;font-size:18px;font-family:inherit;direction:ltr;text-align:center;letter-spacing:2px}
.ugo{width:100%;margin-top:14px;padding:14px;border:0;border-radius:14px;background:linear-gradient(135deg,#a78bfa,#7c5cf0 55%,#22d3ee);color:#fff;font-weight:700;font-size:16px;font-family:inherit;cursor:pointer}
.ugo:disabled{opacity:.5}
.ulx{position:absolute;top:10px;left:10px;width:34px;height:34px;border-radius:50%;border:1px solid #2c2c41;background:#1b1b2a;color:#eceef5;cursor:pointer}
.uer{min-height:18px;margin-top:12px;color:#f87171;font-size:13px}
.ulc a{display:block;margin-top:12px;color:#9a9db0;font-size:13px}
button.cta{width:100%;border:0;font-family:inherit;font-size:16px;cursor:pointer}
.rmv{width:100%;margin-top:10px;padding:12px;border-radius:14px;border:1px solid #2c2c41;background:#1b1b2a;color:#f87171;font-family:inherit;font-size:14px;cursor:pointer}
"""

MODAL = r"""<div class="ulm" id="ulm" hidden><div class="ulc"><button class="ulx" id="ulx" type="button">✕</button>
<div id="us1"><h3>ورود به حساب</h3><p>آیدی عددی تلگرامت را بزن تا کد ورود برایت ارسال شود.</p>
<input id="ui" inputmode="numeric" placeholder="آیدی عددی تلگرام" autocomplete="username">
<button class="ugo" id="ug1" type="button">دریافت کد ورود</button></div>
<div id="us2" hidden><h3>کد ورود</h3><p>کد ۶ رقمی ارسال‌شده به تلگرام را وارد کن.</p>
<input id="uc" inputmode="numeric" maxlength="6" autocomplete="one-time-code" placeholder="------">
<button class="ugo" id="ug2" type="button">ورود</button><a href="#" id="ubk">تغییر آیدی</a></div>
<div class="uer" id="uer"></div></div></div>
<script>(function(){
var m=document.getElementById('ulm');if(!m)return;
function $(i){return document.getElementById(i)}
var nx='/',uid='',busy=false;
function norm(s){return String(s).replace(/[\u06F0-\u06F9]/g,function(c){return c.charCodeAt(0)-1776}).replace(/[\u0660-\u0669]/g,function(c){return c.charCodeAt(0)-1632}).replace(/\D/g,'')}
function err(t){$('uer').textContent=t||''}
function step(n){$('us1').hidden=n!==1;$('us2').hidden=n!==2;err('');setTimeout(function(){$(n===1?'ui':'uc').focus()},50)}
function open(n){nx=n||'/';m.hidden=false;step(1)}
document.addEventListener('click',function(e){var a=e.target.closest&&e.target.closest('[data-login]');if(!a)return;e.preventDefault();open(a.getAttribute('data-login'))});
$('ulx').onclick=function(){m.hidden=true};
m.addEventListener('click',function(e){if(e.target===m)m.hidden=true});
function post(u,d){return fetch(u,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams(d).toString()}).then(function(r){return r.json()})}
function done(b){busy=false;$('ug1').disabled=$('ug2').disabled=false}
$('ug1').onclick=function(){if(busy)return;uid=norm($('ui').value);if(!uid){err('آیدی عددی را وارد کن.');return}
busy=true;$('ug1').disabled=true;err('');
post('/api/login',{uid:uid}).then(function(j){done();if(j.ok)step(2);else err(j.error)}).catch(function(){done();err('خطا در ارتباط، دوباره امتحان کن.')})};
$('ug2').onclick=function(){if(busy)return;var c=norm($('uc').value);if(c.length<6){err('کد ۶ رقمی را کامل وارد کن.');return}
busy=true;$('ug2').disabled=true;err('');
post('/api/login/code',{uid:uid,code:c}).then(function(j){if(j.ok){location.href=nx;return}done();err(j.error);if(j.back)step(1)}).catch(function(){done();err('خطا در ارتباط، دوباره امتحان کن.')})};
$('ui').addEventListener('keydown',function(e){if(e.key==='Enter')$('ug1').click()});
$('uc').addEventListener('input',function(){var v=norm(this.value);this.value=v;if(v.length===6)$('ug2').click()});
$('ubk').onclick=function(e){e.preventDefault();step(1)};
})();</script>"""


def parse_cart(val):
    m = CART.match(val or "")
    return (m.group(1), int(m.group(2))) if m else None


def tabs(active):
    uid, n = CUR.get()
    out = ""
    for k, u, ic, t in TABS:
        attr = ' data-login="%s"' % u if uid is None and k in ("panels", "wallet") else ""
        badge = "<em>%s</em>" % fa(n) if k == "cart" and n else ""
        out += '<a class="utb%s" href="%s"%s><i>%s</i>%s%s</a>' % (" on" if k == active else "", u, attr, ic, t, badge)
    return '<nav class="utabs">' + out + "</nav>"


def header():
    uid, _ = CUR.get()
    right = ('<form class="lo" method="post" action="/logout"><button>خروج</button></form>' if uid is not None
             else '<div class="lo"><a href="/login" data-login="/">ورود</a></div>')
    return ('<header class="top"><a class="logo" href="/about">' + theme.LOGO + '</a><a class="brand" href="/about">' +
            esc(theme.TITLE) + "</a>" + right + "</header>")


# ---- one shell for every inner page (buy.py, pages.py, wallet.py, skin.py, ... all get it) ----
_shell = theme.shell
HDR = re.compile(r'<header class="top">.*?</header>', re.S)
NAV = re.compile(r'<nav class="tabs">.*?</nav>', re.S)


def shell(title, body, active="", nav=True, status=200, sub=""):
    r = _shell(title, body, active, nav, status, sub)
    if not nav:
        return r
    t = HDR.sub(lambda m: header(), r.text, 1)
    t = NAV.sub(lambda m: tabs(active), t, 1)
    t = t.replace("</body>", MODAL + "</body>", 1)
    return web.Response(text=t, content_type="text/html", status=status)


theme.CSS += UCSS
for _m in (theme, auth, buy, pages, wallet, skin):
    if hasattr(_m, "shell"):
        _m.shell = shell

# ---- landing gets the same bottom bar + login modal ----
_render = landing.render


def render(uid, d):
    h = _render(uid, d)
    h = h.replace('class="nb" href="/login"', 'class="nb" href="/login" data-login="/"')
    h = re.sub(r'href="/login"(?! data-login)', 'href="/login" data-login="/buy"', h)
    h = h.replace("</head>", "<style>" + UCSS + "</style></head>", 1)
    return h.replace("</body>", tabs("home") + MODAL + "</body>", 1)


landing.render = render


# ---- shop page (guests allowed): packages go to the cart instead of straight to the form ----
async def shop_list(req):
    uid = req.get("uid")
    out = ""
    for i, x in enumerate(await db.rows("SELECT * FROM products WHERE active=1 ORDER BY sort, id")):
        ks = await db.rows("SELECT * FROM packages WHERE product_id=? AND active=1 ORDER BY gb", x["id"])
        ok = [k for k in ks if k["gb"] > 0]
        best = min(ok, key=lambda k: k["price"] / k["gb"])["id"] if len(ok) > 1 else None
        tiles = "".join('<a class="tl" href="/cart/add/p/%d">%s<b>%s</b><small>گیگ</small><div class="pr">%s تومان</div></a>' % (
            k["id"], '<span class="bdg">💎 به‌صرفه‌ترین</span>' if k["id"] == best else "", fg(k["gb"]), fa(k["price"])) for k in ks)
        if x["price_gb"] > 0:
            tiles += ('<a class="tl" href="/cart/add/c/%d"><b>✏️</b><small>حجم دلخواه</small><div class="pr">هر گیگ %s</div></a>'
                      % (x["id"], fa(x["price_gb"])))
        out += ('<div class="pc rv"><div class="pi"><div class="ph"><div class="pe">%s</div><div><h3>%s</h3></div></div>'
                '<div class="mu">%s</div><div class="tg">%s</div></div></div>') % (
            buy.ICONS[i % len(buy.ICONS)], esc(x["name"]), esc(x["descr"]), tiles or '<div class="mu">پکیجی ثبت نشده.</div>')
    steps = ('<div class="stp"><span class="on"><i>۱</i>انتخاب پکیج</span><u></u><span><i>۲</i>سبد خرید</span><u></u>'
             '<span><i>۳</i>پرداخت</span></div>')
    sub = ("موجودی تو: <b>%s</b> تومان" % fa(await buy.balance(uid))) if uid is not None else "پکیج را انتخاب کن و به سبد خرید اضافه کن"
    body = ST + steps + ('<div class="grid">%s</div>' % out if out else '<div class="card">محصولی فعال نیست.</div>')
    return shell("فروشگاه", body, "buy", sub=sub)


buy.buy_list = shop_list

_done = buy.done_get


async def done_get2(req):
    r = await _done(req)
    r.del_cookie("pgcart", path="/")
    return r


buy.done_get = done_get2


# ---- cart (single item, stored in a cookie; price is always re-read from the DB) ----
async def cart_add(req):
    k, i = req.match_info["k"], int(req.match_info["id"])
    x, _gb, _p, _e = await buy.resolve(k, i)
    if not x:
        raise web.HTTPFound("/buy")
    resp = web.HTTPFound("/cart")
    resp.set_cookie("pgcart", "%s:%d" % (k, i), max_age=7 * 86400, httponly=True, samesite="Lax", path="/")
    raise resp


async def cart_clear(req):
    auth.same_origin(req)
    resp = web.HTTPFound("/cart")
    resp.del_cookie("pgcart", path="/")
    raise resp


async def cart_get(req):
    uid = req.get("uid")
    c = parse_cart(req.cookies.get("pgcart", ""))
    x = None
    if c:
        x, gb, price, _e = await buy.resolve(c[0], c[1])
    if not x:
        body = ('<div class="card" style="text-align:center"><div style="font-size:44px">🛒</div><h3>سبد خرید خالی است</h3>'
                '<div class="mu">یک پکیج از فروشگاه انتخاب کن.</div><a class="cta" href="/buy">🛍 رفتن به فروشگاه</a></div>')
        return shell("سبد خرید", body, "cart")
    k, i = c
    nxt = "/buy/%s/%d" % (k, i)
    if k == "p":
        lines = '<div class="tx"><span>حجم</span><b>%s گیگ</b></div><div class="tx"><span>قیمت</span><b>%s تومان</b></div>' % (fg(gb), fa(price))
    else:
        lines = ('<div class="tx"><span>حجم دلخواه</span><b>هر گیگ %s تومان</b></div>'
                 '<div class="mu">حجم را در مرحله بعد انتخاب می‌کنی.</div>') % fa(x["price_gb"])
    info = ""
    if uid is not None:
        bal = await buy.balance(uid)
        info = '<div class="mu" style="text-align:center;margin-top:12px">موجودی کیف پول: <b>%s</b> تومان</div>' % fa(bal)
        if k == "p" and bal < price:
            info += '<a class="cta off" href="/wallet">⚠ موجودی کم است؛ شارژ کیف پول</a>'
        go = '<a class="cta" href="%s">✅ ادامه و پرداخت</a>' % nxt
    else:
        go = '<button class="cta" type="button" data-login="%s">🔐 ورود و ادامه خرید</button>' % nxt
        info = '<div class="mu" style="text-align:center;margin-top:12px">برای پرداخت وارد حسابت شو؛ سبدت حفظ می‌شود.</div>'
    body = ('<div class="card rv"><div class="ph"><div class="pe">%s</div><div><h3>%s</h3><div class="mu" style="margin:0">%s</div></div></div>%s</div>'
            '%s%s<form method="post" action="/cart/clear"><button class="rmv">🗑 حذف از سبد</button></form>'
            '<a class="lk" href="/buy" style="display:block;text-align:center;margin-top:14px;color:#9a9db0;font-size:13px">+ افزودن پکیج دیگر (جایگزین می‌شود)</a>'
            % (buy.ICONS[0], esc(x["name"]), esc(x["descr"]), lines, go, info))
    return shell("سبد خرید", body, "cart")


# ---- in-page login (same logic/limits as auth.login_post / auth.code_post, JSON replies) ----
def J(ok, error="", status=200, back=False):
    return web.json_response({"ok": ok, "error": error, "back": back}, status=status)


async def api_login(req):
    auth.same_origin(req)
    f = await req.post()
    raw = str(f.get("uid", "")).translate(auth.DIG).strip()
    if not raw.isdigit() or not 5 <= len(raw) <= 15:
        return J(False, "آیدی عددی معتبر نیست.", 400)
    uid = int(raw)
    if not auth.hit(auth.IPS, auth.client_ip(req), 10, 3600) or not auth.hit(auth.SENDS, uid, 3, 600):
        return J(False, "درخواست‌های زیادی ثبت شد؛ چند دقیقه بعد دوباره امتحان کن.", 429)
    u = await asyncio.to_thread(auth.get_user, uid)
    if u and not u[1]:
        code = "%06d" % secrets.randbelow(10 ** 6)
        auth.CODES[uid] = [auth.sig("%s:%s" % (uid, code)), time.time() + auth.CODE_TTL, 0]
        await asyncio.to_thread(auth.tg_send, uid, "🔐 <b>کد ورود به فروشگاه</b>\n\n<code>%s</code>\n\n"
                                "اعتبار: ۵ دقیقه. اگر خودت درخواست نداده‌ای نادیده بگیر و کد را به کسی نگو." % code)
    else:
        await asyncio.sleep(0.6)
    return J(True)


async def api_code(req):
    auth.same_origin(req)
    f = await req.post()
    raw = str(f.get("uid", "")).translate(auth.DIG).strip()
    code = str(f.get("code", "")).translate(auth.DIG).strip()
    if not raw.isdigit():
        return J(False, "آیدی معتبر نیست.", 400, True)
    uid = int(raw)
    if not auth.hit(auth.VER, auth.client_ip(req), 30, 3600):
        return J(False, "تلاش‌های زیادی ثبت شد؛ بعداً امتحان کن.", 429)
    ent = auth.CODES.get(uid)
    if not ent or ent[1] < time.time() or ent[2] >= auth.MAX_TRIES:
        auth.CODES.pop(uid, None)
        return J(False, "کد منقضی شده یا نامعتبر است؛ دوباره آیدی را وارد کن.", 400, True)
    ent[2] += 1
    if not hmac.compare_digest(ent[0], auth.sig("%s:%s" % (uid, code))):
        left = auth.MAX_TRIES - ent[2]
        if left <= 0:
            auth.CODES.pop(uid, None)
            return J(False, "تلاش‌های ناموفق زیاد بود؛ دوباره کد بگیر.", 400, True)
        return J(False, "کد اشتباه است. %d تلاش دیگر مانده." % left, 401)
    auth.CODES.pop(uid, None)
    exp = int(time.time()) + auth.SESSION
    resp = J(True)
    resp.set_cookie("pgshop", "%s.%s.%s" % (uid, exp, auth.sig("%s.%s" % (uid, exp))), max_age=auth.SESSION, httponly=True,
                    samesite="Lax", secure=req.headers.get("X-Forwarded-Proto") == "https" or req.secure, path="/")
    return resp


# ---- guard: guests may see /buy, /cart and use the login API; everything else as before ----
_prev = auth.guard


@web.middleware
async def guard3(req, handler):
    p = req.path
    ck = auth.read_cookie(req.cookies.get("pgshop", ""))
    CUR.set((ck, 1 if parse_cart(req.cookies.get("pgcart", "")) else 0))
    m = BUYP.match(p)
    if m and req.method == "GET" and ck is None:
        raise web.HTTPFound("/cart/add/%s/%s" % m.groups())
    if p in ("/buy", "/cart") or p.startswith(("/cart/", "/api/login")):
        if ck is not None:
            u = await asyncio.to_thread(auth.get_user, ck)
            if u and not u[1]:
                req["uid"] = ck
        resp = await handler(req)
        resp.headers.update(auth.SEC)
        return resp
    return await _prev(req, handler)


auth.guard = guard3

_pi = pages.install


def install(app):
    _pi(app)
    r = app.router
    r.add_get("/cart", cart_get)
    r.add_get(r"/cart/add/{k:[pc]}/{id:\d+}", cart_add)
    r.add_post("/cart/clear", cart_clear)
    r.add_post("/api/login", api_login)
    r.add_post("/api/login/code", api_code)


pages.install = install
