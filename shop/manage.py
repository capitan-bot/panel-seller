from __future__ import annotations

import json
import logging
import re

from aiohttp import web

from bot import db
from bot.panel import PanelError, gen_password, get_pg
from bot.user import USER_RE, pw_problem

from .auth import same_origin
from .buy import balance, bg, tg_admins
from .buyui import ST
from .theme import esc, fa, fg, shell

log = logging.getLogger("shop.manage")
BUSY: set = set()
CH = re.compile(r"^[^<>]{2,32}$")
FAIL = "عملیات ناموفق بود؛ مدیر مطلع شد."


def nick(x):
    return x["nick"] or x["admin_username"]


async def own(req):
    x = await db.row("SELECT * FROM panels WHERE id=? AND user_id=?", int(req.match_info["id"]), req["uid"])
    if not x:
        raise web.HTTPFound("/panels")
    return x


async def base_url():
    try:
        return (await get_pg()).base
    except Exception:
        return ""


async def live(x):
    try:
        i = await (await get_pg(x["server_id"])).admin_info(x["admin_username"])
    except Exception as e:
        log.warning("admin_info failed: %s", e)
        return {"state": "❓ نامشخص", "ok": False, "limit": None, "used": None, "users": None}
    if i is None:
        return {"state": "❌ در پنل پیدا نشد", "ok": False, "limit": None, "used": None, "users": None}
    if i["disabled"]:
        i["state"], i["ok"] = "⛔ غیرفعال", False
    elif i["limit"] and i["used"] is not None and i["used"] >= i["limit"]:
        i["state"], i["ok"] = "⚠️ حجم تمام شده", False
    else:
        i["state"], i["ok"] = "✅ فعال", True
    return i


def gv(v):
    return "—" if v is None else "%s گیگ" % fg(v)


async def render(x, msg="", err="", status=200):
    v = await live(x)
    lim, used = v["limit"], v["used"]
    base = await base_url()
    pw = db.dec(x["pw"]) if x["pw"] else ""
    i = x["id"]
    bar = ""
    if lim and used is not None:
        pc = min(100, int(used * 100 / lim))
        bar = ('<div style="height:10px;border-radius:99px;background:#23232b;overflow:hidden;margin:10px 0">'
               '<div style="height:100%%;width:%d%%;background:linear-gradient(90deg,#a78bfa,#22d3ee)"></div></div>'
               '<div class="mu">%s درصد مصرف · باقی‌مانده %s</div>' % (pc, fa(pc), gv(max(lim - used, 0))))
    pwrow = ('<div class="cr"><div><small>رمز پنل</small><b id="pwv" dir="ltr">••••••••••</b></div>'
             '<button class="ib" id="ev" type="button">👁</button><button class="cp" data-c="%s">📋 کپی</button></div>'
             % esc(pw)) if pw else '<div class="mu">رمز ذخیره نشده؛ با «تغییر رمز» یک رمز جدید بساز.</div>'
    box = ('<div class="card" style="border-color:#34d399;margin-bottom:14px">%s</div>' % esc(msg)) if msg else ""
    eb = ('<div class="er">%s</div>' % esc(err)) if err else ""
    info = ('<div class="card"><h3>%s</h3><span class="st %s">%s</span>'
            '<div class="cr"><div><small>نام کاربری ورود</small><b dir="ltr">%s</b></div>'
            '<button class="cp" data-c="%s">📋 کپی</button></div>%s'
            '<div class="mu" style="margin-top:12px">سقف حجم: <b>%s</b> · مصرف‌شده: <b>%s</b> · کاربران ساخته‌شده: <b>%s</b></div>%s'
            '%s</div>') % (
        esc(nick(x)), "ok" if v["ok"] else "no", esc(v["state"]), esc(x["admin_username"]), esc(x["admin_username"]), pwrow,
        "نامحدود" if lim == 0 else gv(lim), gv(used), "—" if v["users"] is None else fa(v["users"]), bar,
        ('<a class="cta" style="margin-top:14px" href="%s/dashboard" target="_blank" rel="noopener">🖥 ورود به پنل وب</a>'
         % esc(base.rstrip("/"))) if base else "")

    def fm(path, title, inner, btn):
        return ('<form class="card fm" method="post" action="/panels/%d/%s" autocomplete="off" style="margin-top:14px">'
                '<h3>%s</h3>%s<button class="go">%s</button></form>' % (i, path, title, inner, btn))
    forms = (
        fm("pw", "🔑 تغییر رمز",
           '<label>رمز دلخواه (خالی بگذار تا رمز تصادفی ساخته شود)</label><input name="pw" type="text" placeholder="اختیاری">',
           "تغییر رمز")
        + fm("un", "👤 تغییر نام کاربری",
             '<label>نام کاربری جدید (انگلیسی، ۴ تا ۲۰ کاراکتر)</label><input name="user" required maxlength="20">'
             '<div class="mu">بعد از تغییر باید با نام کاربری جدید وارد پنل شوی.</div>', "تغییر نام کاربری")
        + fm("nn", "✏️ نام نمایشی سرویس",
             '<label>نام جدید</label><input name="nick" value="%s" required maxlength="32" style="direction:rtl">' % esc(nick(x)),
             "ذخیره نام")
        + '<a class="cta" style="margin-top:14px" href="/panels/%d/volume">💳 خرید حجم</a>' % i)
    js = ('<script>(function(){var v=document.getElementById("pwv"),b=document.getElementById("ev"),p=%s,s=0;'
          'if(b)b.onclick=function(){s=!s;v.textContent=s?p:"••••••••••"}})();</script>') % json.dumps(pw).replace("<", "\\u003c")
    return shell("مدیریت سرویس", ST + box + eb + info + forms + js, "panels", status=status)


async def detail(req):
    return await render(await own(req))


async def locked(req, work):
    """Run work(x) once per panel at a time; every failure is shown as an error, never as a crash."""
    same_origin(req)
    x = await own(req)
    f = await req.post()
    if x["id"] in BUSY:
        return await render(x, err="عملیات قبلی در حال انجام است؛ چند ثانیه صبر کن.", status=429)
    BUSY.add(x["id"])
    try:
        msg, err = await work(x, f)
    finally:
        BUSY.discard(x["id"])
    x = await own(req)
    return await render(x, msg=msg, err=err, status=400 if err else 200)


async def pw_post(req):
    async def work(x, f):
        pw = str(f.get("pw", "")).strip() or gen_password()
        bad = pw_problem(pw)
        if bad:
            return "", bad
        try:
            await (await get_pg(x["server_id"])).set_password(x["admin_username"], pw)
        except Exception as e:
            log.exception("web pw failed")
            bg(tg_admins, "⚠️ تغییر رمز %s از سایت ناموفق بود:\n%s" % (esc(x["admin_username"]), esc(e)))
            return "", FAIL
        await db.run("UPDATE panels SET pw=? WHERE id=?", db.enc(pw), x["id"])
        await db.ev("pw", x["user_id"], x["admin_username"])
        return "✅ رمز عوض شد. رمز جدید در همین صفحه (بخش رمز پنل) قابل مشاهده است.", ""
    return await locked(req, work)


async def un_post(req):
    async def work(x, f):
        new = str(f.get("user", "")).strip()
        if not USER_RE.match(new):
            return "", "نام کاربری معتبر نیست (انگلیسی، عدد و _، شروع با حرف، ۴ تا ۲۰ کاراکتر)."
        if new.lower() == x["admin_username"].lower():
            return "", "این همان نام کاربری فعلی است."
        if await db.row("SELECT 1 FROM panels WHERE lower(admin_username)=lower(?)", new):
            return "", "این نام کاربری قبلاً گرفته شده؛ نام دیگری بزن."
        pw = db.dec(x["pw"]) if x["pw"] else gen_password()
        try:
            await (await get_pg(x["server_id"])).set_username(x["admin_username"], new, pw)
        except PanelError as e:
            if "گرفته" in str(e):
                return "", "این نام کاربری در پنل وجود دارد؛ نام دیگری بزن."
            return "", "تغییر نام کاربری ممکن نشد: " + str(e)[:150]
        except Exception as e:
            log.exception("web rename failed")
            bg(tg_admins, "⚠️ تغییر نام کاربری %s از سایت ناموفق بود:\n%s" % (esc(x["admin_username"]), esc(e)))
            return "", FAIL
        await db.run("UPDATE panels SET admin_username=?, pw=? WHERE id=?", new, db.enc(pw), x["id"])
        await db.ev("uname", x["user_id"], "%s>%s" % (x["admin_username"], new))
        return "✅ نام کاربری عوض شد. از این به بعد با نام کاربری جدید وارد پنل شو.", ""
    return await locked(req, work)


async def nn_post(req):
    async def work(x, f):
        t = str(f.get("nick", "")).strip()
        if not CH.match(t):
            return "", "نام معتبر نیست (۲ تا ۳۲ کاراکتر، بدون < یا >)."
        await db.run("UPDATE panels SET nick=? WHERE id=?", t, x["id"])
        await db.ev("nick", x["user_id"], t)
        return "✅ نام سرویس ذخیره شد.", ""
    return await locked(req, work)


async def pid_of(x):
    if x["product_id"]:
        return x["product_id"]
    r = await db.row("SELECT id FROM products WHERE active=1 ORDER BY sort, id")
    return r["id"] if r else 0


async def volume_get(req, err="", status=200):
    x = await own(req)
    ks = await db.rows("SELECT * FROM packages WHERE product_id=? AND active=1 ORDER BY gb", await pid_of(x))
    bal = await balance(req["uid"])
    tiles = "".join(
        '<form method="post" action="/panels/%d/volume" onsubmit="return confirm(\'افزودن حجم و پرداخت از کیف پول؟\')">'
        '<input type="hidden" name="k" value="%d"><button class="go" style="margin-top:10px">💎 %s گیگ — %s تومان</button></form>'
        % (x["id"], k["id"], fg(k["gb"]), fa(k["price"])) for k in ks)
    body = ST + ('<div class="er">%s</div>' % esc(err) if err else "") + (
        '<div class="card"><h3>%s</h3><div class="mu">حجمی که به همین سرویس اضافه شود را انتخاب کن.<br>موجودی تو: <b>%s</b> تومان</div>%s'
        '<a class="cta off" style="margin-top:14px" href="/wallet">⚡ شارژ کیف پول</a>'
        '<a class="cta off" style="margin-top:10px" href="/panels/%d">🔙 بازگشت</a></div>'
        % (esc(nick(x)), fa(bal), tiles or '<div class="mu">برای این سرویس پکیج حجم تعریف نشده؛ به پشتیبانی پیام بده.</div>', x["id"]))
    return shell("خرید حجم", body, "panels", status=status)


async def volume_post(req):
    async def work(x, f):
        uid = x["user_id"]
        try:
            kid = int(f.get("k", 0))
        except ValueError:
            kid = 0
        k = await db.row("SELECT * FROM packages WHERE id=? AND product_id=? AND active=1", kid, await pid_of(x))
        if not k:
            return "", "پکیج پیدا نشد."
        if not await db.debit(uid, k["price"]):
            return "", "موجودی کافی نیست؛ اول کیف پول را شارژ کن."
        try:
            v = await live(x)
            cur = v["limit"] if v["limit"] is not None else (x["gb"] or 0)
            if not cur:
                raise PanelError("حجم فعلی سرویس نامشخص است.")
            await (await get_pg(x["server_id"])).set_limit(x["admin_username"], cur + k["gb"])
        except Exception as e:
            await db.credit(uid, k["price"])
            log.exception("web volume failed")
            bg(tg_admins, "⚠️ خرید حجم %s از سایت ناموفق بود (پول برگشت):\n%s" % (esc(x["admin_username"]), esc(e)))
            return "", "افزودن حجم ناموفق بود و مبلغ به کیف پولت برگشت؛ دوباره امتحان کن."
        await db.run("UPDATE panels SET gb=?, warn=0 WHERE id=?", cur + k["gb"], x["id"])
        try:
            await db.sale(uid, x["admin_username"], "volume", k["gb"], k["price"])
        except Exception:
            log.exception("sale record failed")
        return "✅ %s گیگ به سرویس اضافه شد. حجم کل جدید: %s گیگ" % (fg(k["gb"]), fg(cur + k["gb"])), ""
    return await locked(req, work)


def install(app):
    r = app.router
    r.add_get(r"/panels/{id:\d+}", detail)
    r.add_post(r"/panels/{id:\d+}/pw", pw_post)
    r.add_post(r"/panels/{id:\d+}/un", un_post)
    r.add_post(r"/panels/{id:\d+}/nn", nn_post)
    r.add_get(r"/panels/{id:\d+}/volume", volume_get)
    r.add_post(r"/panels/{id:\d+}/volume", volume_post)
