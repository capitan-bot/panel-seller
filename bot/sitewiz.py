import asyncio
import glob
import os
import re
import socket
import urllib.error
import urllib.request

from . import config
from . import site_setup as S
from .tg import Callback, Message, Router, TgError
from .ui import WAIT, btn, h, kb, show

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)

SITE_PORT = 8788
SHOP_SERVICE = "pgbot-shop"
DATA_DIR = os.environ.get("PGBOT_DATA", os.path.join(os.getcwd(), "data"))
DOM_FILE = os.path.join(DATA_DIR, "site_domain.txt")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
DOM_RE = re.compile(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
CONF_GLOBS = ("/etc/nginx/sites-enabled/*", "/etc/nginx/conf.d/*.conf", "/etc/apache2/sites-enabled/*",
              "/etc/caddy/Caddyfile", "/etc/caddy/conf.d/*", "/etc/haproxy/haproxy.cfg")
SKIP = ("example.com", "localhost", "snakeoil")
PENDING = {}
SKIP = {}
LOCK = asyncio.Lock()


import sys

UNIT_PATH = "/etc/systemd/system/" + SHOP_SERVICE + ".service"
UNIT = """[Unit]
Description=PG Bot shop site
After=network-online.target

[Service]
WorkingDirectory=%s
ExecStart=%s -m shop.main
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


async def ensure_service():
    """Creates the shop systemd unit if missing. Returns an error text or empty string."""
    if os.path.exists(UNIT_PATH):
        return ""
    app = os.getcwd()
    if not os.path.isdir(os.path.join(app, "shop")):
        return "پوشه‌ی shop پیدا نشد. اول از منوی pgbot گزینه‌ی 3 (Update) رو بزن."
    await S._sh("%s -m pip install -q aiohttp pillow arabic-reshaper python-bidi" % sys.executable, 300)
    with open(UNIT_PATH, "w", encoding="utf-8") as f:
        f.write(UNIT % (app, sys.executable))
    await S._sh("systemctl daemon-reload && systemctl enable " + SHOP_SERVICE, 30)
    return ""


def current():
    try:
        return open(DOM_FILE, encoding="utf-8").read().strip()
    except OSError:
        return ""


def save(d):
    os.makedirs(DATA_DIR, exist_ok=True)
    open(DOM_FILE, "w", encoding="utf-8").write(d)


def port_up():
    s = socket.socket()
    s.settimeout(2)
    try:
        s.connect(("127.0.0.1", SITE_PORT))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _fetch(url, host=None):
    req = urllib.request.Request(url, headers={"User-Agent": "pgbot-check"})
    if host:
        req.add_header("Host", host)
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return r.status, r.read(200000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        try:
            return e.code, e.read(200000).decode("utf-8", "replace")
        except Exception:
            return e.code, ""
    except Exception:
        return None, ""


def _title(body):
    m = TITLE_RE.search(body or "")
    return m.group(1).strip() if m else ""


def _candidates():
    found = set()
    for g in CONF_GLOBS:
        for p in glob.glob(g):
            try:
                t = open(p, errors="replace").read()
            except OSError:
                continue
            for line in t.splitlines():
                l = line.strip()
                if l.startswith("#"):
                    continue
                if re.match(r"(server_name|ServerName|ServerAlias|acl|use_backend|host)\b", l, re.I) or \
                        (l.endswith("{") and "/" not in l):
                    found.update(d.lower() for d in DOM_RE.findall(l))
    try:
        for n in os.listdir("/etc/letsencrypt/live"):
            found.add(n.lower())
    except OSError:
        pass
    out = [d for d in sorted(found) if S.clean_domain(d) and not any(x in d for x in SKIP)]
    return out[:30]


async def verify(d):
    """Returns (ok, reason). Domain must point here and answer like the local site."""
    loop = asyncio.get_running_loop()
    c1, b1 = await loop.run_in_executor(None, _fetch, "http://127.0.0.1:%d/" % SITE_PORT, d)
    if c1 is None:
        return False, "سایت محلی جواب نمی‌ده."
    c2, b2 = await loop.run_in_executor(None, _fetch, "https://" + d + "/")
    if c2 is None:
        return False, "https://%s جواب نمی‌ده." % d
    if c1 == c2 and _title(b1) == _title(b2):
        return True, ""
    return False, "این دامنه به سایت دیگه‌ای اشاره می‌کنه، نه سایت این ربات."


async def find_site():
    if not port_up():
        return None, "سرویس سایت روی پورت %d بالا نیست." % SITE_PORT
    loop = asyncio.get_running_loop()
    cands = await loop.run_in_executor(None, _candidates)
    hits = []
    for d in cands:
        ok, _ = await verify(d)
        if ok:
            hits.append(d)
    return hits, "%d دامنه بررسی شد." % len(cands)


async def menu(ev, note=""):
    cur = current()
    if cur:
        up = port_up()
        text = (note + "🌐 <b>وب‌سایت</b>\n\n" + ("🟢 روشن" if up else "🔴 خاموش") + "\n"
                "🔗 سایت: <code>" + h("https://" + cur) + "</code>\n"
                "🛠 پنل ادمین: <code>" + h("https://" + cur + "/admin") + "</code>")
        toggle = btn("⏻ خاموش کردن وب‌سایت", "sw:off") if up else btn("▶️ روشن کردن وب‌سایت", "sw:on", style="success")
        rows = [[{"text": "🌐 ورود به وب‌سایت", "url": "https://" + cur}],
                [{"text": "🛠 ورود به پنل ادمین", "url": "https://" + cur + "/admin"}],
                [btn("🔄 تغییر دامنه", "sw:go"), btn("🔍 بررسی دوباره", "sw:find")],
                [toggle],
                [btn("🗑 حذف ثبت دامنه", "sw:fg")]]
    else:
        text = (note + "🌐 <b>وب‌سایت</b>\n\nهنوز دامنه‌ای برای سایت ثبت نشده.\n"
                "یا سایت جدید بساز، یا اگه قبلاً دستی نصب کردی پیداش کن.")
        rows = [[btn("🚀 ساخت وب‌سایت", "sw:go", style="success")],
                [btn("🔍 پیدا کردن خودکار", "sw:find"), btn("🔎 بررسی یه دامنه", "sw:chk")]]
    rows.append([btn("🔙 مدیریت", "a:home")])
    await show(ev, text, kb(rows))


async def ask_domain(ev):
    WAIT[ev.from_user.id] = ("sw_domain", None)
    text = ("📘 <b>راهنمای DNS</b>\n\n"
            "۱) وارد پنل دامنه‌ات (یا کلودفلر) شو.\n"
            "۲) یه رکورد بساز:\n"
            "• نوع: <code>A</code>\n"
            "• نام: <code>@</code> (یا اسم ساب‌دامنه مثل <code>store</code>)\n"
            "• مقدار: آی‌پی عمومی همین سرور (دکمه‌ی «نمایش IP سرور»)\n"
            "۳) اگه کلودفلر داری، ابر نارنجی (Proxy) رو <b>خاموش</b> کن تا خاکستری بشه.\n"
            "۴) چند دقیقه صبر کن تا DNS پخش بشه.\n\n"
            "حالا دامنه‌ات رو بفرست، مثلاً <code>store.example.com</code>")
    await show(ev, text, kb([[btn("📍 نمایش IP سرور", "sw:ip")], [btn("🔙 انصراف", "sw:m")]]))


async def after_domain(ev, d):
    ok, ip, got = await S.check_dns(d)
    PENDING[ev.from_user.id] = d
    SKIP.pop(ev.from_user.id, None)
    if not ok:
        text = ("❌ DNS هنوز به این سرور اشاره نمی‌کنه.\n\n"
                "دامنه: <code>" + h(d) + "</code>\n"
                "IP فعلی دامنه: <code>" + h(", ".join(got) or "پیدا نشد") + "</code>\n\n"
                "رکورد A رو درست کن، چند دقیقه صبر کن و «بررسی دوباره» رو بزن.")
        return await show(ev, text, kb([[btn("🔄 بررسی دوباره", "sw:re")], [btn("⏭ ادامه بدون چک DNS (تانل/پروکسی)", "sw:skip")],
                                        [btn("📍 نمایش IP سرور", "sw:ip")], [btn("🔙 انصراف", "sw:m")]]))
    await build(ev, d)


async def check_one(ev, d):
    ok, why = await verify(d)
    if ok:
        save(d)
        return await menu(ev, "✅ سایت پیدا و ثبت شد.\n\n")
    await show(ev, "❌ " + h(why), kb([[btn("🔎 دامنه‌ی دیگه", "sw:chk")], [btn("🔙 بازگشت", "sw:m")]]))


@router.command("site")
async def site_cmd(m: Message):
    WAIT.pop(m.from_user.id, None)
    await menu(m)


@router.callback("sw:")
async def swcb(c: Callback):
    uid = c.from_user.id
    d = c.data
    if d == "sw:ip":
        ip = await S.server_ip()
        return await c.answer(("IP سرور: " + ip) if ip else "IP سرور پیدا نشد.", show_alert=True)
    if d == "sw:go":
        return await ask_domain(c)
    if d == "sw:skip":
        if not PENDING.get(uid):
            return await ask_domain(c)
        SKIP[uid] = True
        return await build(c, PENDING[uid])
    if d == "sw:re":
        dom = PENDING.get(uid)
        return await (after_domain(c, dom) if dom else ask_domain(c))
    if d == "sw:chk":
        WAIT[uid] = ("sw_check", None)
        return await show(c, "🔎 دامنه‌ی سایتت رو بفرست (مثلاً <code>store.example.com</code>) تا چک کنم "
                             "روی همین سرور و برای همین ربات باشه.", kb([[btn("🔙 انصراف", "sw:m")]]))
    if d == "sw:find":
        await show(c, "🔍 در حال جستجو و بررسی دامنه‌ها... (ممکنه یه دقیقه طول بکشه)", kb([]))
        hits, note = await find_site()
        if not hits:
            msg = h(note) if hits is None else "❌ سایتی پیدا نشد. (" + h(note) + ")\nدامنه رو دستی چک کن."
            return await show(c, msg, kb([[btn("🔎 بررسی یه دامنه", "sw:chk")],
                                          [btn("🚀 ساخت وب‌سایت", "sw:go", style="success")],
                                          [btn("🔙 بازگشت", "sw:m")]]))
        save(hits[0])
        extra = ("دامنه‌های دیگه: " + ", ".join(hits[1:]) + "\n\n") if len(hits) > 1 else ""
        return await menu(c, "✅ سایت پیدا و ثبت شد.\n" + h(extra) + "\n")
    if d == "sw:off":
        return await show(c, "⚠️ با خاموش‌کردن سایت، <b>پنل ادمین سایت هم</b> از دسترس خارج می‌شه. مطمئنی؟",
                          kb([[btn("✅ بله، خاموش کن", "sw:offy", style="danger")], [btn("🔙 نه", "sw:m")]]))
    if d == "sw:offy":
        try:
            await c.answer("در حال خاموش‌کردن...")
        except TgError:
            pass
        await S._sh("systemctl stop --no-block " + SHOP_SERVICE, 15)
        for _ in range(10):
            if not port_up():
                break
            await asyncio.sleep(0.5)
        if port_up():
            await S._sh("systemctl kill -s KILL " + SHOP_SERVICE, 15)
            await asyncio.sleep(1)
        return await menu(c, "⏻ سایت خاموش شد.\n\n")
    if d == "sw:on":
        try:
            await c.answer("در حال روشن‌کردن...")
        except TgError:
            pass
        err = await ensure_service()
        if err:
            return await show(c, "❌ " + h(err), kb([[btn("🔙 بازگشت", "sw:m")]]))
        code, out = await S._sh("systemctl reset-failed %s; systemctl start --no-block %s" % (SHOP_SERVICE, SHOP_SERVICE), 15)
        for _ in range(40):
            if port_up():
                break
            await asyncio.sleep(0.5)
        if not port_up():
            _, lg = await S._sh("journalctl -u %s -n 8 --no-pager" % SHOP_SERVICE, 15)
            return await show(c, "❌ سایت روشن نشد.\n<pre>" + h((out + "\n" + lg)[-900:]) + "</pre>",
                              kb([[btn("🔁 تلاش دوباره", "sw:on")], [btn("🔙 بازگشت", "sw:m")]]))
        return await menu(c, "▶️ سایت روشن شد.\n\n")
    if d == "sw:fg":
        try:
            os.remove(DOM_FILE)
        except OSError:
            pass
        return await menu(c, "🗑 ثبت دامنه حذف شد (خود سایت دست‌نخورده است).\n\n")
    WAIT.pop(uid, None)
    await menu(c)


def _pred(m):
    return bool(m.from_user) and WAIT.get(m.from_user.id, ("",))[0] in ("sw_domain", "sw_email", "sw_check")


@router.message(_pred)
async def swmsg(m: Message):
    uid = m.from_user.id
    kind = WAIT[uid][0]
    text = (m.text or "").strip()
    if kind in ("sw_domain", "sw_check"):
        d = S.clean_domain(text)
        if not d:
            return await m.answer("دامنه معتبر نیست. مثال: <code>store.example.com</code>")
        WAIT.pop(uid, None)
        if kind == "sw_check":
            return await check_one(m, d)
        return await after_domain(m, d)

    WAIT.pop(uid, None)


async def build(ev, d):
    uid = ev.from_user.id
    m = getattr(ev, "message", None) or ev
    skip = SKIP.pop(uid, False)
    WAIT.pop(uid, None)
    if LOCK.locked():
        return await m.answer("⏳ یه ساخت سایت در حال انجامه.")
    err = await ensure_service()
    if err:
        return await m.answer("❌ " + h(err))
    if not port_up():
        await S._sh("systemctl start --no-block " + SHOP_SERVICE, 15)
    r = await m.answer(h(S.render(10, 0, 0)))
    mid = r["message_id"] if isinstance(r, dict) else r.message_id
    last = {"t": ""}

    async def progress(t):
        if t == last["t"]:
            return
        last["t"] = t
        try:
            await m.bot.api("editMessageText", chat_id=m.chat_id, message_id=mid, text=h(t), parse_mode="HTML")
        except TgError:
            pass

    async with LOCK:
        ok, msg = await S.run_setup(d, SITE_PORT, "", progress, skip_dns=skip)
    if ok:
        old = current()
        save(d)
        if old and old != d:
            await S._sh("rm -f /etc/nginx/sites-enabled/pgbot-%s /etc/nginx/sites-available/pgbot-%s "
                        "&& nginx -t && systemctl reload nginx" % (old, old))
        warn = "" if port_up() else "\n\n⚠️ سرویس سایت هنوز بالا نیست؛ چند ثانیه بعد صفحه رو تازه کن."
        await m.answer("🎉 سایت آماده شد!\n<code>" + h(msg) + "</code>" + warn,
                       kb([[{"text": "🌐 ورود به وب‌سایت", "url": msg}],
                           [{"text": "🛠 ورود به پنل ادمین", "url": msg + "/admin"}],
                           [btn("🔙 مدیریت", "a:home")]]))
    else:
        await m.answer("❌ ساخت سایت کامل نشد. تغییرات برگردونده شد.",
                       kb([[btn("🔁 تلاش دوباره", "sw:go")], [btn("🔙 مدیریت", "a:home")]]))
