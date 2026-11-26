import time
from . import db, lic, config

FEATS = ("ai", "site")
NAMES = {"ai": "🤖 هوش مصنوعی", "site": "🌐 ساخت سایت"}
_ready = False

async def _init():
    global _ready
    if _ready:
        return
    await db.run("CREATE TABLE IF NOT EXISTS vip(feat TEXT PRIMARY KEY, until INTEGER, uid INTEGER)")
    await db.run("CREATE TABLE IF NOT EXISTS vip_used(nonce TEXT PRIMARY KEY, uid INTEGER, ts INTEGER)")
    for col in ("feats TEXT", "rev INTEGER DEFAULT 0"):
        try:
            await db.run("ALTER TABLE vip_used ADD COLUMN " + col)
        except Exception:
            pass
    _ready = True

async def until(feat):
    await _init()
    r = await db.row("SELECT until FROM vip WHERE feat=?", feat)
    return int(r["until"]) if r else 0

async def on(feat):
    await _sync()
    return await until(feat) > int(time.time())

async def status():
    await _sync()
    return {f: await until(f) for f in FEATS}

async def activate(uid, code):
    await _init()
    if uid not in config.ADMIN_IDS:
        return False, "⛔ فقط ادمین‌های ربات می‌توانند VIP را فعال کنند."
    d = lic.check(code or "", uid)
    if not d:
        return False, "❌ کد نامعتبر است یا برای این حساب صادر نشده."
    feats = [f for f in d.get("f", []) if f in FEATS]
    days = int(d.get("d", 0))
    if not feats or days <= 0:
        return False, "❌ کد نامعتبر است."
    try:
        await db.run("INSERT INTO vip_used(nonce, uid, ts, feats) VALUES(?,?,?,?)", d["n"], uid, int(time.time()), ",".join(feats))
    except Exception:
        return False, "❌ این کد قبلاً استفاده شده است."
    now = int(time.time())
    for f in feats:
        base = max(now, await until(f))
        await db.run("INSERT INTO vip(feat, until, uid) VALUES(?,?,?) ON CONFLICT(feat) DO UPDATE SET until=excluded.until, uid=excluded.uid", f, base + days * 86400, uid)
    names = " + ".join(NAMES[f] for f in feats)
    return True, "✅ VIP فعال شد\n🧩 %s\n⏳ %d روز" % (names, days)


from .tg import Router
from . import ui

PRICE = "۱۰۰٬۰۰۰ تومان"
CONTACT = ""

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)

def _left(u):
    n = u - int(time.time())
    return 0 if n <= 0 else -(-n // 86400)

async def status_text():
    st = await status()
    out = ["💎 <b>اشتراک VIP</b>", ""]
    for f in FEATS:
        d = _left(st[f])
        out.append("%s: %s" % (NAMES[f], ("✅ فعال | %d روز مانده" % d) if d else "🔒 غیرفعال"))
    return "\n".join(out)

def _kb():
    return ui.kb([[ui.btn("🔑 فعال‌سازی با کد", "vp:act")],
                  [ui.btn("🛒 خرید VIP", "vp:buy")],
                  [ui.btn("🔙 مدیریت", "a:home")]])

def _kb_buy():
    return ui.kb([[ui.btn("🔑 فعال‌سازی با کد", "vp:act")],
                  [ui.btn("🔙 مدیریت", "a:home")]])

def _buy_body():
    t = "💰 قیمت: %s (ماهانه)\n🧩 شامل: هوش مصنوعی + ساخت سایت\n\n" % PRICE
    if CONTACT:
        t += "برای خرید به %s پیام بدهید. بعد از پرداخت، کد فعال‌سازی برایتان ارسال می‌شود.\n\n" % CONTACT
    else:
        t += "برای خرید با فروشنده تماس بگیرید. بعد از پرداخت، کد فعال‌سازی برایتان ارسال می‌شود.\n\n"
    return t + "سپس «🔑 فعال‌سازی با کد» را بزنید و کد را بفرستید."

async def locked(ev, feat):
    head = "🔒 <b>%s یک قابلیت VIP است</b>\n\n" % NAMES[feat]
    await ui.show(ev, head + _buy_body(), _kb())


@router.command("vip")
async def vip_cmd(m):
    ui.WAIT.pop(m.from_user.id, None)
    await ui.show(m, await status_text(), _kb())

@router.callback("vp:")
async def vip_cb(c):
    a = c.data.split(":")[1]
    uid = c.from_user.id
    ui.WAIT.pop(uid, None)
    if a == "buy":
        return await ui.show(c, await status_text() + "\n\n" + _buy_body(), _kb_buy())
    if a == "act":
        ui.WAIT[uid] = ("vip_code",)
        return await ui.show(c, "🔑 کد فعال‌سازی را بفرستید:", ui.kb([[ui.btn("🔙 انصراف", "vp:home")]]))
    await ui.show(c, await status_text(), _kb())

@router.message(ui.waiting("vip_"))
async def vip_code(m):
    ui.WAIT.pop(m.from_user.id, None)
    ok, msg = await activate(m.from_user.id, (m.text or "").strip())
    await ui.show(m, msg + "\n\n" + await status_text(), _kb())



LIC_URL = "http://91.107.189.97:8799/revoked"
_last = 0

async def _sync():
    global _last
    now = time.time()
    if now - _last < 240:
        return
    _last = now
    try:
        await _init()
        rows = await db.rows("SELECT nonce, feats FROM vip_used WHERE COALESCE(rev,0)=0 ORDER BY ts DESC LIMIT 50")
        if not rows:
            return
        import httpx
        async with httpx.AsyncClient(timeout=5) as h:
            r = await h.get(LIC_URL, params={"n": ",".join(x["nonce"] for x in rows)})
        bad = set(r.json().get("revoked", []))
        for x in rows:
            if x["nonce"] in bad:
                for f in (x["feats"] or ",".join(FEATS)).split(","):
                    await db.run("UPDATE vip SET until=0 WHERE feat=?", f)
                await db.run("UPDATE vip_used SET rev=1 WHERE nonce=?", x["nonce"])
    except Exception:
        _last = now


import asyncio
from . import site_setup as _S

SHOP = "pgbot-shop"

async def _notify(bot, text):
    if bot is None:
        return
    try:
        await ui.notify_admins(bot, text)
    except Exception:
        pass

async def _svc_active():
    code, out = await _S._sh("systemctl is-active " + SHOP, 15)
    return (out or "").strip() == "active"

async def enforce(bot=None):
    await _init()
    st = await status()
    now = int(time.time())
    for f in FEATS:
        u = st[f]
        is_on = u > now
        prev = await db.get_setting("vip_state_" + f)
        if prev == "1" and not is_on:
            await _notify(bot, "🔒 اشتراک VIP تمام شد\n%s خاموش شد.\nاطلاعات شما پاک نشده و با تمدید دوباره فعال می‌شود." % NAMES[f])
        await db.set_setting("vip_state_" + f, "1" if is_on else "0")
        if is_on and u - now < 3 * 86400 and await db.get_setting("vip_warn_" + f) != str(u):
            await db.set_setting("vip_warn_" + f, str(u))
            await _notify(bot, "⏰ اشتراک VIP رو به پایان است\n%s: %d روز مانده.\nبرای تمدید از «💎 خرید VIP» اقدام کنید." % (NAMES[f], _left(u)))
    row = await db.row("SELECT until FROM vip WHERE feat=?", "site")
    if row is None:
        return
    if st["site"] <= now:
        if await _svc_active():
            await _S._sh("systemctl stop " + SHOP, 30)
            await db.set_setting("vip_site_stopped", "1")
    elif await db.get_setting("vip_site_stopped") == "1":
        await _S._sh("systemctl start " + SHOP, 30)
        await db.set_setting("vip_site_stopped", "0")

async def vip_loop(bot):
    await asyncio.sleep(30)
    while True:
        try:
            await enforce(bot)
        except Exception:
            pass
        await asyncio.sleep(300)
