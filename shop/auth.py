from __future__ import annotations

import asyncio
import hmac
import html
import json
import os
import secrets
import time
import urllib.request
from urllib.parse import urlparse

from aiohttp import web

from web import app as A

CODE_TTL, MAX_TRIES, SESSION = 300, 5, 7 * 86400
CODES, SENDS, IPS, VER = {}, {}, {}, {}
DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
SECRET_FILE = A.DATA / "shop_secret.txt"
TITLE = A.env("SHOP_TITLE") or "CAPITAN PANEL"
SEC = {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin",
       "Cache-Control": "no-store",
       "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
                                  "img-src 'self' data:; form-action 'self'; frame-ancestors 'none'"}
CSS = """
@font-face{font-family:V;src:url(/static/Vazirmatn-Regular.ttf)}
@font-face{font-family:V;font-weight:700;src:url(/static/Vazirmatn-Bold.ttf)}
:root{--card:#131318;--bd:#23232b;--tx:#e8e8ee;--mu:#9a9aa8;--ac:#a78bfa;--up:#34d399;--dn:#f87171}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;color:var(--tx);font-family:V,Tahoma,sans-serif;background:radial-gradient(600px 420px at 90% -6%,#7c5cf02b,transparent 62%),radial-gradient(520px 400px at 4% 104%,#22d3ee1f,transparent 62%),#07070c}
.top{display:flex;align-items:center;gap:6px;flex-wrap:wrap;padding:12px 16px;border-bottom:1px solid var(--bd);background:#0b0b10}
.top b{margin-left:auto}.nl{background:none;border:0;color:var(--mu);padding:8px 12px;border-radius:10px;text-decoration:none;font-family:inherit;font-size:14px;cursor:pointer}
.nl.on{background:#241f45;color:#c4b5fd}.nl.x{color:var(--dn)}
.main{max-width:980px;margin:auto;padding:18px 16px 40px}h1{margin:6px 0 14px;font-size:26px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
.card{background:linear-gradient(165deg,#161621,#101016);border:1px solid var(--bd);border-radius:20px;padding:18px}
.card h3{margin:0 0 6px}.mu{color:var(--mu);font-size:13px;margin-top:4px}
.ch{display:inline-block;margin:6px 0 0 6px;padding:6px 12px;border-radius:99px;background:#241f45;color:#c4b5fd;font-size:13px}
.buy{width:100%;margin-top:14px;padding:11px;border:0;border-radius:12px;background:#2a2a3a;color:var(--mu);font-family:inherit;font-size:14px}
.bal{font-size:30px;font-weight:700;margin:4px 0}
.st{display:inline-block;padding:3px 10px;border-radius:99px;font-size:12px;background:#23232b;margin-bottom:6px}.st.ok{background:#0f2e24;color:var(--up)}.st.no{background:#331818;color:var(--dn)}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px;border-bottom:1px solid var(--bd);text-align:right;white-space:nowrap}th{color:var(--mu);font-weight:400}.tw{overflow-x:auto}
.bx{width:min(92vw,420px);margin:12vh auto 0;padding:30px 24px}.bx h1{text-align:center}.bx p{text-align:center;color:var(--mu);font-size:14px;margin:0 0 16px}
input{width:100%;padding:14px;border-radius:12px;border:1px solid #2c2c36;background:#0f0f14;color:#fff;font-size:18px;font-family:inherit;direction:ltr;text-align:center;letter-spacing:2px}
input:focus{outline:2px solid #7c5cf0;border-color:transparent}
.go{width:100%;margin-top:16px;padding:14px;border:0;border-radius:12px;background:linear-gradient(135deg,#a78bfa,#7c5cf0 55%,#22d3ee);color:#fff;font-weight:700;font-size:16px;font-family:inherit;cursor:pointer}
.err{min-height:18px;margin-top:12px;color:var(--dn);font-size:13px;text-align:center}.lk{display:block;text-align:center;margin-top:14px;color:var(--mu);font-size:13px}
"""
JS = ("document.querySelectorAll('.tm').forEach(function(e){var t=+e.dataset.t;if(!t)return;var d=new Date(t*1000),o={timeZone:'Asia/Tehran'};"
      "e.textContent=e.dataset.f==='dt'?d.toLocaleString('fa-IR',Object.assign({dateStyle:'short',timeStyle:'short'},o)):"
      "d.toLocaleDateString('fa-IR',Object.assign({year:'numeric',month:'long',day:'numeric'},o))});")


def esc(s):
    return html.escape(str(s))


def shell(title, body, active="", nav=True, status=200):
    head = ""
    if nav:
        links = "".join('<a class="nl%s" href="%s">%s</a>' % (" on" if k == active else "", u, t) for k, u, t in (
            ("home", "/", "فروشگاه"), ("panels", "/panels", "پنل‌های من"), ("wallet", "/wallet", "کیف پول")))
        head = ('<header class="top">%s<form method="post" action="/logout"><button class="nl x">خروج</button></form>'
                "<b>%s</b></header>") % (links, esc(TITLE))
    t = ('<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         "<title>%s</title><style>%s</style></head><body>%s%s<script>%s</script></body></html>") % (
        esc(title), CSS, head, body if not nav else '<main class="main"><h1>%s</h1>%s</main>' % (esc(title), body), JS)
    return web.Response(text=t, content_type="text/html", status=status)


def page_login(err="", status=200):
    body = ('<form class="card bx" method="post" action="/login"><h1>%s</h1>'
            "<p>آیدی عددی تلگرامت را وارد کن؛ یک کد ورود برایت در تلگرام می‌فرستیم.</p>"
            '<input name="uid" inputmode="numeric" autocomplete="username" placeholder="آیدی عددی" required>'
            '<button class="go">دریافت کد</button><div class="err">%s</div>'
            '<span class="lk">آیدی عددی را از «👤 حساب کاربری» در ربات می‌بینی. قبلاً باید ربات را /start کرده باشی.</span></form>'
            % (esc(TITLE), esc(err)))
    return shell("ورود", body, nav=False, status=status)


def page_code(uid, err="", status=200):
    body = ('<form class="card bx" method="post" action="/login/code"><h1>کد ورود</h1>'
            "<p>اگر این آیدی در ربات ثبت باشد، یک کد ۶ رقمی به تلگرامش رفته است. اعتبار کد ۵ دقیقه است.</p>"
            '<input type="hidden" name="uid" value="%s"><input name="code" inputmode="numeric" maxlength="6" '
            'autocomplete="one-time-code" placeholder="------" required><button class="go">ورود</button>'
            '<div class="err">%s</div><a class="lk" href="/login">آیدی دیگر یا ارسال دوباره</a></form>' % (int(uid), esc(err)))
    return shell("کد ورود", body, nav=False, status=status)


def secret() -> bytes:
    try:
        s = SECRET_FILE.read_text().strip()
    except OSError:
        s = ""
    if not s:
        s = secrets.token_hex(32)
        A.DATA.mkdir(exist_ok=True)
        SECRET_FILE.write_text(s)
        os.chmod(SECRET_FILE, 0o600)
    return bytes.fromhex(s)


def sig(msg: str) -> str:
    return hmac.new(secret(), msg.encode(), "sha256").hexdigest()


def read_cookie(val: str):
    try:
        uid, exp, s = val.split(".")
        if hmac.compare_digest(s, sig("%s.%s" % (uid, exp))) and int(exp) > time.time():
            return int(uid)
    except Exception:
        pass
    return None


def client_ip(req) -> str:
    if req.remote in ("127.0.0.1", "::1"):
        xf = req.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
        if xf:
            return xf
    return req.remote or "?"


def hit(d, key, limit, window) -> bool:
    now = time.time()
    lst = [t for t in d.get(key, []) if now - t < window]
    d[key] = lst
    if len(lst) >= limit:
        return False
    lst.append(now)
    return True


def same_origin(req):
    o = req.headers.get("Origin") or req.headers.get("Referer")
    if o and urlparse(o).netloc != req.host:
        raise web.HTTPForbidden()


def get_user(uid):
    r = A.q("SELECT tg_id, blocked FROM users WHERE tg_id=?", (uid,))
    return r[0] if r else None


def tg_send(uid, text) -> bool:
    req = urllib.request.Request("https://api.telegram.org/bot%s/sendMessage" % A.env("BOT_TOKEN"),
                                 data=json.dumps({"chat_id": uid, "text": text, "parse_mode": "HTML"}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return bool(json.loads(r.read()).get("ok"))
    except Exception:
        return False


@web.middleware
async def guard(req, handler):
    if not req.path.startswith(("/login", "/static/", "/health")):
        uid = read_cookie(req.cookies.get("pgshop", ""))
        if uid is None:
            raise web.HTTPFound("/login")
        u = await asyncio.to_thread(get_user, uid)
        if not u or u[1]:
            raise web.HTTPFound("/login")
        req["uid"] = uid
    resp = await handler(req)
    resp.headers.update(SEC)
    return resp


async def login_get(req):
    return page_login()


async def login_post(req):
    same_origin(req)
    f = await req.post()
    raw = str(f.get("uid", "")).translate(DIG).strip()
    if not raw.isdigit() or not 5 <= len(raw) <= 15:
        return page_login("آیدی عددی معتبر نیست.")
    uid = int(raw)
    if not hit(IPS, client_ip(req), 10, 3600) or not hit(SENDS, uid, 3, 600):
        return page_login("درخواست‌های زیادی ثبت شد؛ چند دقیقه بعد دوباره امتحان کن.", 429)
    u = await asyncio.to_thread(get_user, uid)
    if u and not u[1]:
        code = "%06d" % secrets.randbelow(10 ** 6)
        CODES[uid] = [sig("%s:%s" % (uid, code)), time.time() + CODE_TTL, 0]
        await asyncio.to_thread(tg_send, uid, "🔐 <b>کد ورود به فروشگاه</b>\n\n<code>%s</code>\n\n"
                                "اعتبار: ۵ دقیقه. اگر خودت درخواست نداده‌ای نادیده بگیر و کد را به کسی نگو." % code)
    else:
        await asyncio.sleep(0.6)
    return page_code(uid)


async def code_post(req):
    same_origin(req)
    f = await req.post()
    raw = str(f.get("uid", "")).translate(DIG).strip()
    code = str(f.get("code", "")).translate(DIG).strip()
    if not raw.isdigit():
        raise web.HTTPFound("/login")
    uid = int(raw)
    if not hit(VER, client_ip(req), 30, 3600):
        return page_login("تلاش‌های زیادی ثبت شد؛ بعداً امتحان کن.", 429)
    ent = CODES.get(uid)
    if not ent or ent[1] < time.time() or ent[2] >= MAX_TRIES:
        CODES.pop(uid, None)
        return page_login("کد منقضی شده یا نامعتبر است؛ دوباره آیدی را وارد کن.", 400)
    ent[2] += 1
    if not hmac.compare_digest(ent[0], sig("%s:%s" % (uid, code))):
        left = MAX_TRIES - ent[2]
        if left <= 0:
            CODES.pop(uid, None)
            return page_login("تلاش‌های ناموفق زیاد بود؛ دوباره کد بگیر.", 400)
        return page_code(uid, "کد اشتباه است. %d تلاش دیگر مانده." % left, 401)
    CODES.pop(uid, None)
    exp = int(time.time()) + SESSION
    resp = web.HTTPFound("/")
    resp.set_cookie("pgshop", "%s.%s.%s" % (uid, exp, sig("%s.%s" % (uid, exp))), max_age=SESSION, httponly=True,
                    samesite="Lax", secure=req.headers.get("X-Forwarded-Proto") == "https" or req.secure, path="/")
    raise resp


async def logout(req):
    resp = web.HTTPFound("/login")
    resp.del_cookie("pgshop", path="/")
    raise resp


async def health(req):
    return web.json_response({"ok": True})


def install(app):
    r = app.router
    r.add_get("/login", login_get)
    r.add_post("/login", login_post)
    r.add_post("/login/code", code_post)
    r.add_post("/logout", logout)
    r.add_get("/health", health)
