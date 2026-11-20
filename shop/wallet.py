from __future__ import annotations

import hmac
import json
import logging
import random
import time

import aiohttp
from aiohttp import web

from bot import config, db
from bot.invoice import MAX_OFFSET, PRESETS, RULES, TTL
from web import app as A

from .auth import DIG, hit, same_origin, sig
from .theme import esc, fa, shell

log = logging.getLogger("shop.wallet")
MAX_AMOUNT = 100_000_000
MAX_IMG = 5 * 1024 * 1024
OPEN, INVS, RCPS = {}, {}, {}

ST = ("<style>.ps{display:flex;flex-wrap:wrap;margin:6px 0 12px}.ps .pl{color:#eceef5;font-family:inherit;cursor:pointer}"
      ".amt{font-size:30px;font-weight:700;margin:6px 0}.amt small{font-size:15px;font-weight:400;color:#cbd5e1}"
      ".cdn{color:#fbbf24;font-weight:700}.rl{color:#9a9db0;font-size:13px;line-height:1.9;padding-right:18px}"
      ".wm{margin-top:14px}</style>")


def charge_box():
    pre = "".join('<button class="pl" name="p" value="%d">%s تومان</button>' % (a, fa(a)) for a in PRESETS)
    return (ST + '<h2>شارژ کیف پول</h2><form class="card" method="post" action="/wallet/invoice">'
            '<div class="mu">یک مبلغ را انتخاب کن یا مبلغ دلخواه (به تومان) بنویس.</div><div class="ps">' + pre + "</div>"
            '<input name="amount" inputmode="numeric" placeholder="مبلغ دلخواه، مثلاً 250000" autocomplete="off">'
            '<button class="go">ساخت فاکتور</button></form>')


def msg(text, status=200):
    return shell("شارژ کیف پول", '<div class="card"><div>%s</div><a class="cta" href="/wallet">بازگشت به کیف پول</a></div>'
                 % esc(text), "wallet", status=status)


def img_kind(b):
    if b[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


async def unique(amount):
    now = time.time()
    for k in [k for k, v in OPEN.items() if v < now]:
        OPEN.pop(k, None)
    taken = set(OPEN)
    try:
        taken |= {r["amount"] for r in await db.rows("SELECT amount FROM receipts WHERE status='pending'")}
    except Exception:
        pass
    for _ in range(300):
        a = amount + random.randint(11, MAX_OFFSET)
        if a not in taken:
            return a
    return amount + random.randint(1, MAX_OFFSET)


def invoice_page(uid, pay, exp, card, holder):
    t = sig("inv|%d|%d|%d" % (uid, pay, exp))
    digits = "".join(ch for ch in card if ch.isdigit()) or card
    rules = "".join("<li>%s</li>" % r.replace("{m}", str(max(1, TTL // 60))) for r in RULES)
    body = (ST + '<div class="card"><h3>💳 در انتظار پرداخت</h3>'
            '<div class="mu">زمان باقی‌مانده: <span class="cdn" id="cd" data-e="' + str(exp) + '"></span></div>'
            '<div class="mu wm">مبلغ دقیق واریزی</div><div class="amt">' + fa(pay) + ' <small>تومان</small></div>'
            '<div class="mu">⚠️ <b>دقیقاً همین مبلغ</b> را واریز کن؛ چند رقم آخر برای شناسایی پرداخت توست و کل مبلغ واریزی به کیف پولت اضافه می‌شود.</div>'
            '<div class="mu wm">شماره کارت مقصد</div><div class="amt" dir="ltr" style="font-size:22px;letter-spacing:2px">' + esc(card) + "</div>"
            '<div class="mu">' + esc(holder) + "</div>"
            '<button type="button" class="cp" data-c="' + str(pay) + '">💰 کپی مبلغ</button> '
            '<button type="button" class="cp" data-c="' + esc(digits) + '">📋 کپی شماره کارت</button></div>'
            '<form class="card wm" method="post" action="/wallet/receipt" enctype="multipart/form-data">'
            '<h3>📸 ارسال رسید</h3><div class="mu">بعد از واریز، عکس رسید (کامل و واضح) را اینجا بفرست. JPG، PNG یا WebP تا ۵ مگابایت.</div>'
            '<input type="hidden" name="amount" value="' + str(pay) + '"><input type="hidden" name="exp" value="' + str(exp) + '">'
            '<input type="hidden" name="t" value="' + t + '"><input type="file" name="file" accept="image/*" required style="margin-top:12px">'
            '<button class="go">ارسال رسید برای تأیید</button></form>'
            '<div class="card wm"><details><summary>📜 قوانین پرداخت</summary><ol class="rl">' + rules + "</ol></details></div>"
            "<script>(function(){var e=document.getElementById('cd'),x=+e.dataset.e;function f(){var l=Math.max(0,x-Math.floor(Date.now()/1000));"
            "e.textContent=l?Number(Math.floor(l/60)).toLocaleString('fa-IR',{minimumIntegerDigits:2})+':'+Number(l%60).toLocaleString('fa-IR',{minimumIntegerDigits:2}):'منقضی شد'}"
            "f();setInterval(f,1000)})();</script>")
    return shell("پرداخت کارت‌به‌کارت", body, "wallet")


async def invoice_post(req):
    same_origin(req)
    uid = req["uid"]
    f = await req.post()
    raw = str(f.get("p") or f.get("amount") or "").translate(DIG).replace(",", "").replace("٬", "").strip()
    if not raw.isdigit() or len(raw) > 12:
        return msg("مبلغ معتبر نیست.", 400)
    base = int(raw)
    try:
        minc = int(await db.get_setting("min_charge") or 0)
    except ValueError:
        minc = 0
    if base < max(minc, 1):
        return msg("حداقل مبلغ شارژ %s تومان است." % fa(minc), 400)
    if base > MAX_AMOUNT:
        return msg("حداکثر مبلغ شارژ %s تومان است." % fa(MAX_AMOUNT), 400)
    if not hit(INVS, uid, 20, 3600):
        return msg("درخواست‌های زیادی ثبت شد؛ بعداً امتحان کن.", 429)
    card, holder = await db.get_setting("card"), await db.get_setting("holder")
    if not card:
        return msg("شماره کارت هنوز توسط مدیر ثبت نشده است.", 503)
    pay = await unique(base)
    exp = int(time.time()) + TTL
    OPEN[pay] = exp
    return invoice_page(uid, pay, exp, card, holder)


async def notify_admins(rid, uid, amount, img, ext, ctype):
    ids = set(config.ADMIN_IDS)
    try:
        ids |= {r["tg_id"] for r in await db.rows("SELECT tg_id FROM staff")}
    except Exception:
        pass
    cap = "🧾 رسید #%d\nکاربر: <code>%d</code>\nمبلغ: %s تومان\n🌐 ثبت‌شده از سایت" % (rid, uid, fa(amount))
    mk = json.dumps({"inline_keyboard": [[
        {"text": "✅ تایید", "callback_data": "a:rc:ok:%d" % rid, "style": "success"},
        {"text": "❌ رد", "callback_data": "a:rc:no:%d" % rid, "style": "danger"}]]})
    url = "https://api.telegram.org/bot%s/sendPhoto" % A.env("BOT_TOKEN")
    fid = ""
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as s:
        for cid in sorted(ids):
            try:
                fd = aiohttp.FormData()
                fd.add_field("chat_id", str(cid))
                fd.add_field("caption", cap)
                fd.add_field("parse_mode", "HTML")
                fd.add_field("reply_markup", mk)
                if fid:
                    fd.add_field("photo", fid)
                else:
                    fd.add_field("photo", img, filename="receipt." + ext, content_type=ctype)
                async with s.post(url, data=fd) as r:
                    js = await r.json()
                if js.get("ok"):
                    fid = fid or js["result"]["photo"][-1]["file_id"]
                else:
                    log.warning("sendPhoto %s: %s", cid, js.get("description"))
            except Exception:
                log.exception("sendPhoto failed for %s", cid)
    return fid


async def receipt_post(req):
    same_origin(req)
    uid = req["uid"]
    f, img = {}, b""
    try:
        rd = await req.multipart()
        while True:
            part = await rd.next()
            if part is None:
                break
            if part.name == "file":
                buf = bytearray()
                while True:
                    ch = await part.read_chunk(65536)
                    if not ch:
                        break
                    buf += ch
                    if len(buf) > MAX_IMG:
                        return msg("حجم عکس بیشتر از ۵ مگابایت است.", 413)
                img = bytes(buf)
            elif part.name in ("amount", "exp", "t"):
                f[part.name] = (await part.text())[:80]
    except Exception:
        return msg("آپلود ناموفق بود؛ دوباره امتحان کن.", 400)
    try:
        amount, exp = int(f["amount"]), int(f["exp"])
        ok = hmac.compare_digest(f["t"], sig("inv|%d|%d|%d" % (uid, amount, exp)))
    except Exception:
        ok = False
    if not ok:
        return msg("فاکتور نامعتبر است؛ دوباره فاکتور بساز.", 400)
    if exp < time.time():
        return msg("فاکتور منقضی شده؛ فاکتور جدید بساز.", 400)
    kind = img_kind(img)
    if not kind:
        return msg("فقط عکس JPG، PNG یا WebP قبول است.", 400)
    if not hit(RCPS, uid, 5, 3600):
        return msg("درخواست‌های زیادی ثبت شد؛ بعداً امتحان کن.", 429)
    if await db.row("SELECT id FROM receipts WHERE user_id=? AND amount=? AND created>?", uid, amount, exp - TTL - 60):
        return msg("برای این فاکتور قبلاً رسید فرستاده‌ای.", 409)
    rid, _ = await db.run("INSERT INTO receipts(user_id,amount,file_id,created) VALUES(?,?,?,?)", uid, amount, "web", db.now())
    fid = await notify_admins(rid, uid, amount, img, kind[0], kind[1])
    if not fid:
        await db.run("DELETE FROM receipts WHERE id=?", rid)
        return msg("ارسال رسید ناموفق بود؛ دوباره امتحان کن یا رسید را از ربات بفرست.", 502)
    await db.run("UPDATE receipts SET file_id=? WHERE id=?", fid, rid)
    return shell("رسید ارسال شد", '<div class="card"><h3>🧾 رسید دریافت شد</h3><div class="mu">مبلغ: <b>%s</b> تومان</div>'
                 '<div class="mu">⏳ در انتظار تأیید مدیر. بعد از تأیید، پیام در تلگرام می‌رسد و موجودی کیف پولت بالا می‌رود.</div>'
                 '<a class="cta" href="/wallet">بازگشت به کیف پول</a></div>' % fa(amount), "wallet")


def install(app):
    app.router.add_post("/wallet/invoice", invoice_post)
    app.router.add_post("/wallet/receipt", receipt_post)
