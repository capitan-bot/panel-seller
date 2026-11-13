import asyncio, os, hmac, hashlib, json, time, logging
from datetime import datetime
from urllib.parse import parse_qsl
from aiohttp import web
from bot import db
from bot.panel import PanelError, PanelTaken, get_pg
from bot.user import new_panel, USER_RE, pw_problem

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("miniapp")
BOT_TOKEN = os.environ["BOT_TOKEN"]
LOCKS: dict = {}
DONE: dict = {}
LIVE: dict = {}


def j(data, status=200):
    return web.json_response(data, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


def verify(init_data, max_age=86400):
    pairs = dict(parse_qsl(init_data, keep_blank_values=True))
    got = pairs.pop("hash", None)
    if not got:
        return None
    check = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calc = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calc, got):
        return None
    if time.time() - int(pairs.get("auth_date", 0)) > max_age:
        return None
    return json.loads(pairs["user"])


async def auth(request):
    tg = verify(request.headers.get("X-Telegram-Init-Data", ""))
    if not tg:
        return None, j({"detail": "احراز هویت ناموفق بود؛ مینی‌اپ را از داخل ربات باز کنید."}, 401)
    name = ((tg.get("first_name") or "") + " " + (tg.get("last_name") or "")).strip()
    await db.touch_user(tg["id"], name, tg.get("username") or "")
    if await db.is_blocked(tg["id"]):
        return None, j({"detail": "حساب شما مسدود است."}, 403)
    return tg, None


async def live(pg, username):
    hit = LIVE.get(username)
    if hit and time.time() - hit[0] < 60:
        return hit[1]
    try:
        info = await asyncio.wait_for(pg.admin_info(username), 12)
    except Exception:
        info = None
    LIVE[username] = (time.time(), info)
    return info


def svc(r, info, base):
    pw = r["pw"] or ""
    try:
        pw = db.dec(pw) if pw else ""
    except Exception:
        pass
    total = round(info["limit"], 2) if info and info.get("limit") else (r["gb"] or 0)
    used = round(info["used"] or 0, 2) if info else 0
    users = (info.get("users") or 0) if info else 0
    off = r["status"] != "active" or bool(info and info.get("disabled"))
    return {
        "id": r["id"], "name": r["nick"] or r["admin_username"], "username": r["admin_username"],
        "password": pw, "total": total, "used": used, "users": users,
        "status": "inactive" if off else "active",
        "created": datetime.fromtimestamp(r["created"]).strftime("%Y-%m-%d"),
        "panel_url": (base + "/dashboard") if base else "",
    }


async def me(request):
    tg, err = await auth(request)
    if err:
        return err
    u = await db.row("SELECT balance FROM users WHERE tg_id=?", tg["id"])
    rows = await db.rows(
        "SELECT * FROM panels WHERE user_id=? AND is_test=0 AND status!='deleted' ORDER BY id DESC LIMIT 20", tg["id"])
    base = (await db.get_setting("panel_url")).strip().rstrip("/")
    try:
        pg = await get_pg()
        infos = await asyncio.gather(*[live(pg, r["admin_username"]) for r in rows])
    except Exception:
        infos = [None] * len(rows)
    return j({"balance": u["balance"] if u else 0, "services": [svc(r, i, base) for r, i in zip(rows, infos)]})


async def products(request):
    tg, err = await auth(request)
    if err:
        return err
    rows = await db.rows("SELECT * FROM products WHERE active=1 AND price_gb>0 ORDER BY sort, id")
    return j([{"id": r["id"], "name": r["name"], "desc": r["descr"], "perGb": r["price_gb"],
               "min": r["min_gb"], "max": r["max_gb"], "active": True} for r in rows])


async def orders(request):
    tg, err = await auth(request)
    if err:
        return err
    uid = tg["id"]
    try:
        b = await request.json()
        pid, gb = int(b["panel_id"]), int(b["gb"])
        username, pw, idem = str(b["username"]).strip(), str(b["password"]), str(b["idempotency_key"])[:64]
    except Exception:
        return j({"detail": "اطلاعات سفارش ناقص است."}, 422)
    key = f"{uid}:{idem}"
    for k in [k for k, v in DONE.items() if time.time() - v[0] > 3600]:
        DONE.pop(k, None)
    if key in DONE:
        return j(DONE[key][1])
    lock = LOCKS.setdefault(uid, asyncio.Lock())
    if lock.locked():
        return j({"detail": "سفارش قبلی شما در حال پردازش است؛ چند لحظه صبر کنید."}, 409)
    async with lock:
        if not USER_RE.match(username):
            return j({"detail": "نام کاربری باید با حرف شروع شود، ۴ تا ۲۰ کاراکتر باشد و فقط حروف انگلیسی، عدد و _ داشته باشد."}, 422)
        prob = pw_problem(pw)
        if prob:
            return j({"detail": prob}, 422)
        x = await db.row("SELECT * FROM products WHERE id=? AND active=1 AND price_gb>0", pid)
        if not x:
            return j({"detail": "این پنل دیگر برای خرید فعال نیست."}, 404)
        if not (x["min_gb"] <= gb <= x["max_gb"]):
            return j({"detail": f"حجم باید بین {x['min_gb']} و {x['max_gb']} گیگابایت باشد."}, 422)
        price = gb * int(x["price_gb"])
        if not await db.debit(uid, price):
            return j({"detail": "موجودی کیف پول کافی نیست؛ ابتدا کیف پول را شارژ کنید."}, 402)
        try:
            name, _pw, _base = await new_panel(uid, pid, gb, False, username, pw)
        except Exception as e:
            try:
                await db.credit(uid, price)
            except Exception:
                log.exception("REFUND FAILED uid=%s amount=%s", uid, price)
            log.warning("order failed uid=%s: %r", uid, e)
            if isinstance(e, PanelTaken):
                return j({"detail": "این نام کاربری روی پنل گرفته شده است؛ نام دیگری انتخاب کنید. وجه شما برگشت داده شد."}, 409)
            if isinstance(e, PanelError):
                return j({"detail": f"ساخت پنل ناموفق بود ({str(e)[:140]}). وجه شما برگشت داده شد."}, 502)
            return j({"detail": "خطای داخلی هنگام ساخت پنل. وجه شما برگشت داده شد."}, 500)
        await db.ev("miniapp_buy", uid, f"{name}:{gb}")
        u = await db.row("SELECT balance FROM users WHERE tg_id=?", uid)
        r = await db.row("SELECT * FROM panels WHERE admin_username=?", name)
        base = (await db.get_setting("panel_url")).strip().rstrip("/")
        resp = {"balance": u["balance"], "service": svc(r, None, base)}
        DONE[key] = (time.time(), resp)
        return j(resp)


import html as _html
import aiohttp
from bot import config

TICKET_LAST: dict = {}


async def support(request):
    tg, err = await auth(request)
    if err:
        return err
    try:
        b = await request.json()
        subject = str(b.get("subject", "")).strip()[:100]
        text = str(b.get("message", "")).strip()[:2000]
    except Exception:
        return j({"detail": "اطلاعات تیکت ناقص است."}, 422)
    if len(subject) < 3 or len(text) < 5:
        return j({"detail": "موضوع و توضیحات را کامل‌تر بنویسید."}, 422)
    uid = tg["id"]
    if time.time() - TICKET_LAST.get(uid, 0) < 60:
        return j({"detail": "تیکت قبلی شما به‌تازگی ثبت شده؛ یک دقیقه بعد دوباره تلاش کنید."}, 429)
    if not config.ADMIN_IDS:
        return j({"detail": "پشتیبانی هنوز تنظیم نشده است."}, 503)
    name = ((tg.get("first_name") or "") + " " + (tg.get("last_name") or "")).strip() or "کاربر"
    uname = ("@" + tg["username"]) if tg.get("username") else "ندارد"
    e = _html.escape
    msg = ("🎫 <b>تیکت جدید از مینی‌اپ</b>\n\n"
           f"👤 از: <a href='tg://user?id={uid}'>{e(name)}</a>\n"
           f"🔗 یوزرنیم: {e(uname)}\n🆔 آیدی عددی: <code>{uid}</code>\n\n"
           f"📌 موضوع: {e(subject)}\n\n💬 {e(text)}")
    ok = 0
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as cs:
        for aid in config.ADMIN_IDS:
            try:
                async with cs.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                                   json={"chat_id": aid, "text": msg, "parse_mode": "HTML",
                                         "disable_web_page_preview": True}) as r:
                    if r.status == 200:
                        ok += 1
                    else:
                        log.warning("ticket to %s failed: HTTP %s", aid, r.status)
            except Exception:
                log.exception("ticket to %s failed", aid)
    if not ok:
        return j({"detail": "ارسال تیکت ناموفق بود؛ از دکمه‌ی گفتگو در تلگرام استفاده کنید."}, 502)
    TICKET_LAST[uid] = time.time()
    await db.ev("miniapp_ticket", uid, subject[:100])
    return j({"ok": True})


async def on_start(app):
    await db.init()


app = web.Application()
app.on_startup.append(on_start)
app.router.add_get("/api/me", me)
app.router.add_get("/api/panels", products)
app.router.add_post("/api/orders", orders)
app.router.add_post("/api/support", support)
web.run_app(app, host="127.0.0.1", port=8090)
