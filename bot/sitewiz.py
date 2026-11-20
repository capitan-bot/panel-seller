import asyncio
import os
import re
import socket

from . import config
from . import site_setup as S
from .tg import Callback, Message, Router, TgError
from .ui import WAIT, btn, h, kb, show

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)

SITE_PORT = 8788
DATA_DIR = os.environ.get("PGBOT_DATA", os.path.join(os.getcwd(), "data"))
DOM_FILE = os.path.join(DATA_DIR, "site_domain.txt")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
PENDING = {}
LOCK = asyncio.Lock()


def current():
    try:
        return open(DOM_FILE, encoding="utf-8").read().strip()
    except OSError:
        return ""


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


import glob
import ssl
import urllib.error
import urllib.request

DOM_RE = re.compile(r"[a-z0-9][a-z0-9.-]*\.[a-z]{2,}", re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
CONF_GLOBS = ("/etc/nginx/sites-enabled/*", "/etc/nginx/conf.d/*.conf", "/etc/apache2/sites-enabled/*",
              "/etc/caddy/Caddyfile", "/etc/caddy/conf.d/*")


def _fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=8) as r:
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
            if str(SITE_PORT) not in t:
                continue
            for line in t.splitlines():
                l = line.strip()
                if re.match(r"(server_name|ServerName|ServerAlias)\s", l):
                    found.update(d.lower() for d in DOM_RE.findall(l.split(None, 1)[1]))
                elif l.endswith("{") and "/" not in l:
                    found.update(d.lower() for d in DOM_RE.findall(l))
    try:
        for n in os.listdir("/etc/letsencrypt/live"):
            found.add(n.lower())
    except OSError:
        pass
    return sorted(d for d in found if S.clean_domain(d))


async def find_site():
    loop = asyncio.get_running_loop()
    if not port_up():
        return None, "سرویس سایت روی پورت %d بالا نیست." % SITE_PORT
    code, body = await loop.run_in_executor(None, _fetch, "http://127.0.0.1:%d/" % SITE_PORT)
    if code is None:
        return None, "جواب سایت محلی گرفته نشد."
    mine = (code, _title(body))
    cands = await loop.run_in_executor(None, _candidates)
    hits = []
    for d in cands:
        ok, ip, got = await S.check_dns(d)
        if not ok:
            continue
        c2, b2 = await loop.run_in_executor(None, _fetch, "https://" + d + "/")
        if c2 is None:
            continue
        if c2 == mine[0] and _title(b2) == mine[1]:
            hits.append(d)
    return hits, "%d دامنه بررسی شد." % len(cands)


async def menu(ev, note=""):
    cur = current()
    if cur:
        text = note + "🌐 <b>وب‌سایت</b>\n\n✅ سایت فعال:\n<code>" + h("https://" + cur) + "</code>"
        rows = [[{"text": "🌐 باز کردن سایت", "url": "https://" + cur}],
                [btn("🔄 تغییر دامنه", "sw:go")]]
    else:
        text = (note + "🌐 <b>ساخت وب‌سایت</b>\n\n"
                "با چند مرحله برای فروشگاهت سایت می‌سازم و گواهی SSL هم می‌گیرم.\n"
                "فقط یه دامنه لازم داری.")
        rows = [[btn("🚀 ساخت وب‌سایت", "sw:go", style="success")],
                [btn("🔍 پیدا کردن سایتِ نصب‌شده", "sw:find")]]
    rows.append([btn("🔙 مدیریت", "a:home")])
    await show(ev, text, kb(rows))


async def ask_domain(ev):
    ip = await S.server_ip() or "(نامشخص)"
    WAIT[ev.from_user.id] = ("sw_domain", None)
    text = ("📘 <b>راهنمای DNS</b>\n\n"
            "۱) وارد پنل دامنه‌ات (یا کلودفلر) شو.\n"
            "۲) یه رکورد بساز:\n"
            "• نوع: <code>A</code>\n"
            "• نام: <code>@</code> (یا اسم ساب‌دامنه مثل <code>store</code>)\n"
            "• مقدار: <code>" + h(ip) + "</code>\n"
            "۳) اگه کلودفلر داری، ابر نارنجی (Proxy) رو <b>خاموش</b> کن تا خاکستری بشه.\n"
            "۴) چند دقیقه صبر کن تا DNS پخش بشه.\n\n"
            "حالا دامنه‌ات رو بفرست، مثلاً <code>store.example.com</code>")
    await show(ev, text, kb([[btn("🔙 انصراف", "sw:m")]]))


async def after_domain(ev, d):
    ok, ip, got = await S.check_dns(d)
    PENDING[ev.from_user.id] = d
    if not ok:
        text = ("❌ DNS هنوز به این سرور اشاره نمی‌کنه.\n\n"
                "دامنه: <code>" + h(d) + "</code>\n"
                "IP سرور: <code>" + h(str(ip)) + "</code>\n"
                "IP فعلی دامنه: <code>" + h(", ".join(got) or "پیدا نشد") + "</code>\n\n"
                "رکورد A رو درست کن، چند دقیقه صبر کن و «بررسی دوباره» رو بزن.")
        return await show(ev, text, kb([[btn("🔄 بررسی دوباره", "sw:re")], [btn("🔙 انصراف", "sw:m")]]))
    WAIT[ev.from_user.id] = ("sw_email", None)
    await show(ev, "✅ DNS درسته.\n\nیه ایمیل بفرست (برای ثبت گواهی SSL لازمه، مثلاً هشدار تمدید به همین می‌رسه):",
               kb([[btn("🔙 انصراف", "sw:m")]]))


@router.command("site")
async def site_cmd(m: Message):
    WAIT.pop(m.from_user.id, None)
    await menu(m)


@router.callback("sw:")
async def swcb(c: Callback):
    uid = c.from_user.id
    if c.data == "sw:go":
        return await ask_domain(c)
    if c.data == "sw:find":
        await show(c, "🔍 در حال جستجوی سایت روی سرور...", kb([]))
        hits, note = await find_site()
        if not hits:
            msg = note if hits is None else "❌ سایتی پیدا نشد. (" + note + ")\nاگه دستی نصب کردی، دامنه‌ش رو با «ساخت وب‌سایت» ثبت کن."
            return await show(c, msg, kb([[btn("🚀 ساخت وب‌سایت", "sw:go", style="success")],
                                           [btn("🔙 بازگشت", "sw:m")]]))
        os.makedirs(DATA_DIR, exist_ok=True)
        open(DOM_FILE, "w", encoding="utf-8").write(hits[0])
        extra = ("\nدامنه‌های دیگه: " + ", ".join(hits[1:])) if len(hits) > 1 else ""
        return await menu(c, "✅ سایت پیدا و ثبت شد.\n\n" + h(extra) + ("\n\n" if extra else ""))
    if c.data == "sw:re":
        d = PENDING.get(uid)
        if not d:
            return await ask_domain(c)
        return await after_domain(c, d)
    WAIT.pop(uid, None)
    await menu(c)


def _pred(m):
    return bool(m.from_user) and WAIT.get(m.from_user.id, ("",))[0] in ("sw_domain", "sw_email")


@router.message(_pred)
async def swmsg(m: Message):
    uid = m.from_user.id
    kind = WAIT[uid][0]
    text = (m.text or "").strip()
    if kind == "sw_domain":
        d = S.clean_domain(text)
        if not d:
            return await m.answer("دامنه معتبر نیست. مثال: <code>store.example.com</code>")
        return await after_domain(m, d)

    if not EMAIL_RE.match(text):
        return await m.answer("ایمیل معتبر نیست؛ دوباره بفرست.")
    d = PENDING.get(uid)
    WAIT.pop(uid, None)
    if not d:
        return await ask_domain(m)
    if LOCK.locked():
        return await m.answer("⏳ یه ساخت سایت در حال انجامه.")
    if not port_up():
        return await m.answer("❌ سرویس سایت روی پورت %d بالا نیست.\nاول این رو بزن:\n"
                              "<code>systemctl status pgbot-shop</code>" % SITE_PORT)
    r = await m.answer(h(S.render(10, 0, 0)))
    mid = r["message_id"] if isinstance(r, dict) else r.message_id
    last = {"t": ""}

    async def progress(t):
        if t == last["t"]:
            return
        last["t"] = t
        try:
            await m.bot.api("editMessageText", chat_id=m.chat_id, message_id=mid,
                            text=h(t), parse_mode="HTML")
        except TgError:
            pass

    async with LOCK:
        ok, msg = await S.run_setup(d, SITE_PORT, text, progress)
    if ok:
        os.makedirs(DATA_DIR, exist_ok=True)
        open(DOM_FILE, "w", encoding="utf-8").write(d)
        await m.answer("🎉 سایت آماده شد!\n<code>" + h(msg) + "</code>",
                       kb([[{"text": "🌐 باز کردن سایت", "url": msg}], [btn("🔙 مدیریت", "a:home")]]))
    else:
        await m.answer("❌ ساخت سایت کامل نشد. تغییرات برگردونده شد.",
                       kb([[btn("🔁 تلاش دوباره", "sw:go")], [btn("🔙 مدیریت", "a:home")]]))
