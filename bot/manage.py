from __future__ import annotations

import logging
import re

from . import db
from .panel import PanelError, gen_password, get_pg
from .tg import Callback, Router
from .ui import WAIT, xbtn, btn, fdate, fgb, fmt, h, kb, notify_admins, num, show, waiting
from .user import USER_RE, pw_problem

router = Router()
log = logging.getLogger(__name__)
CH = re.compile(r"^[^<>]{2,32}$")


async def get_panel(uid: int, pid: int):
    return await db.row("SELECT * FROM panels WHERE id=? AND user_id=?", pid, uid)


async def base_url() -> str:
    try:
        return (await get_pg()).base
    except PanelError:
        return ""


def nick(x) -> str:
    return x["nick"] or x["admin_username"]


def bar(used: float, limit: float) -> str:
    pc = min(100, int(used * 100 / limit)) if limit else 0
    k = pc // 10
    return f"%{pc} [{'█' * k}{'░' * (10 - k)}]"


async def live(x) -> dict:
    """Live data of the admin from PasarGuard (never raises)."""
    try:
        i = await (await get_pg(x["server_id"])).admin_info(x["admin_username"])
    except Exception as e:
        log.warning("admin_info failed: %s", e)
        return {"state": "❓ نامشخص (ارتباط با پنل برقرار نشد)", "limit": None, "used": None, "users": None}
    if i is None:
        return {"state": "❌ در پنل پیدا نشد", "limit": None, "used": None, "users": None}
    if i["disabled"]:
        i["state"] = "⛔ غیرفعال"
    elif i["limit"] and i["used"] is not None and i["used"] >= i["limit"]:
        i["state"] = "⚠️ حجم تمام شده"
    else:
        i["state"] = "✅ فعال"
    return i


def g(v) -> str:
    return "—" if v is None else fgb(v)


def gl(v) -> str:
    return "نامحدود" if v == 0 else g(v)


def home_markup(x, base: str) -> dict:
    i = x["id"]
    return kb([
        *([[xbtn("🖥 ورود به پنل وب", url=f"{base}/dashboard")]] if base else []),
        [btn("📊 مشخصات و مصرف", f"m:i:{i}", style="success"), btn("🔑 تغییر رمز", f"m:pw:{i}", style="primary")],
        [btn("👤 تغییر نام کاربری", f"m:un:{i}", style="primary"), btn("✏️ تغییر نام سرویس", f"m:nn:{i}", style="primary")],
        [btn("💳 خرید حجم", f"m:bv:{i}", style="success"), btn("📥 انتقال مالکیت", f"m:tr:{i}", style="primary")],
        [btn("🪪 کارت مصرف", f"cd:{i}", style="success")],
        [btn("🔄 بروزرسانی", f"m:r:{i}", style="primary")],
        [btn("📦 پنل‌های من", "u:panels", style="success")]])


async def page(ev, x) -> None:
    base = await base_url()
    v = await live(x)
    users = "—" if v["users"] is None else v["users"]
    t = (f"⚙️ <b>پنل مدیریت سرویس</b>\n\n🖥 <b>{h(nick(x))}</b>\n"
         f"• وضعیت زنده: {v['state']}\n• حجم کل زنده: {gl(v['limit'])}\n"
         f"• کاربران ساخته‌شده: {users}\n• مصرف فعلی: {g(v['used'])}\n\n"
         "📌 وضعیت، حجم، مصرف و تعداد کاربران مستقیماً از پاسارگارد خوانده می‌شوند.")
    await show(ev, t, home_markup(x, base))


async def info_page(ev, x) -> None:
    base = await base_url()
    v = await live(x)
    lim, used = v["limit"], v["used"]
    pw = db.dec(x["pw"]) if x["pw"] else None
    t = (f"🧾 <b>مشخصات سرویس</b>\n\n📌 این اطلاعات برای ورود به پنل و پیگیری سرویس شماست.\n\n"
         f"🏷 نام نمایشی: {h(nick(x))}\n👤 نام کاربری ورود: <code>{h(x['admin_username'])}</code>\n"
         f"🔐 رمز پنل: " + (f"<code>{h(pw)}</code>" if pw else "ذخیره نشده (با «تغییر رمز» رمز جدید بساز)") +
         f"\n🆔 کد سرویس: {x['id']}\n\n"
         f"📦 سقف حجم: {gl(lim)}\n📥 مصرف‌شده: {g(used)}\n")
    if lim and used is not None:
        t += f"📤 باقی‌مانده: {g(max(lim - used, 0))}\n📈 نمودار مصرف: {bar(used, lim)}\n"
    t += (f"\n👥 کاربران ساخته‌شده: {'—' if v['users'] is None else v['users']}\n"
          f"🟢 وضعیت: {v['state']}\n⌛ پایان اعتبار: بدون محدودیت زمانی\n📅 تاریخ ساخت: {fdate(x['created'])}\n\n"
          "📌 برای ورود از دکمه «ورود به پنل وب» استفاده کنید.\n🔐 رمز را فقط در جای امن نگهداری کنید.")
    await show(ev, t, kb([*([[xbtn("🖥 ورود به پنل وب", url=f"{base}/dashboard")]] if base else []),
                          [btn("🔄 بروزرسانی", f"m:i:{x['id']}", style="primary")],
                          [btn("🔙 بازگشت", f"m:m:{x['id']}", style="danger")]]))


async def apply_pw(ev, x, pw: str) -> None:
    back = kb([[btn("🔙 بازگشت", f"m:m:{x['id']}")]])
    try:
        await (await get_pg(x["server_id"])).set_password(x["admin_username"], pw)
    except Exception as e:
        log.exception("pw change failed")
        await notify_admins(ev.bot, f"⚠️ تغییر رمز <code>{h(x['admin_username'])}</code> ناموفق بود:\n{h(e)}")
        return await show(ev, f"⚠️ تغییر رمز ناموفق بود:\n<code>{h(e)}</code>", back)
    await db.run("UPDATE panels SET pw=? WHERE id=?", db.enc(pw), x["id"])
    await db.ev("pw", x["user_id"], x["admin_username"])
    await show(ev, f"✅ رمز عوض شد.\n\n🔑 رمز جدید: <code>{h(pw)}</code>", back)


async def do_username(ev, x, new: str) -> None:
    back = kb([[btn("🔙 بازگشت", f"m:m:{x['id']}")]])
    if not USER_RE.match(new):
        return await show(ev, "نام کاربری معتبر نیست؛ فقط حروف انگلیسی، عدد و _ ، ۴ تا ۲۰ کاراکتر و شروع با حرف.\n"
                              "دوباره بفرست:", None)
    if new.lower() == x["admin_username"].lower():
        return await show(ev, "این همان نام کاربری فعلی است.", back)
    if await db.row("SELECT 1 FROM panels WHERE lower(admin_username)=lower(?)", new):
        return await show(ev, "این نام کاربری قبلاً گرفته شده؛ یک نام دیگر بفرست:", None)
    pw = db.dec(x["pw"]) if x["pw"] else gen_password()
    try:
        await (await get_pg(x["server_id"])).set_username(x["admin_username"], new, pw)
    except PanelError as e:
        if "گرفته" in str(e):
            return await show(ev, "این نام کاربری در پنل وجود دارد؛ یک نام دیگر بفرست:", None)
        log.warning("rename failed: %s", e)
        return await show(ev, f"⚠️ تغییر نام کاربری ممکن نشد:\n{h(e)}", back)
    except Exception as e:
        log.exception("rename failed")
        await notify_admins(ev.bot, f"⚠️ تغییر نام کاربری <code>{h(x['admin_username'])}</code> ناموفق بود:\n{h(e)}")
        return await show(ev, "⚠️ تغییر نام کاربری ناموفق بود؛ مدیر مطلع شد.", back)
    WAIT.pop(ev.from_user.id, None)
    await db.run("UPDATE panels SET admin_username=?, pw=? WHERE id=?", new, db.enc(pw), x["id"])
    await db.ev("uname", x["user_id"], f"{x['admin_username']}>{new}")
    await show(ev, f"✅ نام کاربری عوض شد.\n\n👤 نام کاربری جدید: <code>{h(new)}</code>\n🔑 رمز: <code>{h(pw)}</code>", back)


async def buy_volume(c, x, a: str, p: list) -> None:
    i, uid = x["id"], c.from_user.id
    back = kb([[btn("🔙 بازگشت", f"m:m:{i}", style="danger")]])
    pid = x["product_id"] or (await db.row("SELECT id FROM products WHERE active=1 ORDER BY sort, id") or {"id": 0})["id"]
    if a == "bv":
        ks = await db.rows("SELECT * FROM packages WHERE product_id=? AND active=1 ORDER BY gb", pid)
        if not ks:
            return await show(c, "برای این سرویس پکیج حجم تعریف نشده؛ به پشتیبانی پیام بده.", back)
        rows = [[btn(f"💎 {fgb(k['gb'])} — {fmt(k['price'])} تومان", f"m:bg:{i}:{k['id']}", style="success")] for k in ks]
        return await show(c, "💳 <b>خرید حجم</b>\n\nحجمی که به همین سرویس اضافه شود را انتخاب کن:", kb(rows + back["inline_keyboard"]))
    k = await db.row("SELECT * FROM packages WHERE id=? AND product_id=? AND active=1", int(p[3]), pid)
    if not k:
        return await c.answer("پکیج پیدا نشد.", show_alert=True)
    bal = (await db.row("SELECT balance FROM users WHERE tg_id=?", uid))["balance"]
    if a == "bg":
        ok = bal >= k["price"]
        rows = [[btn("✅ پرداخت و افزودن حجم", f"m:bp:{i}:{k['id']}", style="success")] if ok
                else [btn("💰 شارژ کیف پول", "u:charge", style="primary")], [btn("🔙 بازگشت", f"m:bv:{i}")]]
        return await show(c, f"💳 افزودن <b>{fgb(k['gb'])}</b> به <b>{h(nick(x))}</b>\n\nقیمت: {fmt(k['price'])} تومان\n"
                             f"موجودی تو: {fmt(bal)} تومان" + ("" if ok else "\n\n⚠️ موجودی کافی نیست."), kb(rows))
    if not await db.debit(uid, k["price"]):
        return await c.answer("موجودی کافی نیست.", show_alert=True)
    try:
        v = await live(x)
        cur = v["limit"] if v["limit"] is not None else (x["gb"] or 0)
        if not cur:
            raise PanelError("حجم فعلی سرویس نامشخص است.")
        await (await get_pg(x["server_id"])).set_limit(x["admin_username"], cur + k["gb"])
    except Exception as e:
        await db.credit(uid, k["price"])
        log.exception("buy volume failed")
        await notify_admins(c.bot, f"⚠️ خرید حجم <code>{h(x['admin_username'])}</code> ناموفق بود (پول برگشت):\n{h(e)}")
        return await show(c, "⚠️ افزودن حجم ناموفق بود و مبلغ به کیف پولت برگشت؛ دوباره امتحان کن.", back)
    await db.run("UPDATE panels SET gb=?, warn=0 WHERE id=?", cur + k["gb"], i)
    await db.sale(uid, x["admin_username"], "volume", k["gb"], k["price"])
    await show(c, f"✅ <b>{fgb(k['gb'])}</b> به سرویس اضافه شد.\nحجم کل جدید: {fgb(cur + k['gb'])}",
               kb([[btn("⚙️ مدیریت سرویس", f"m:m:{i}", style="primary")]]))


@router.callback("m:")
async def mcb(c: Callback):
    p = c.data.split(":")
    a, uid = p[1], c.from_user.id
    WAIT.pop(uid, None)
    x = await get_panel(uid, int(p[2]))
    if not x:
        return await c.answer("پنل پیدا نشد.", show_alert=True)
    i = x["id"]
    back = kb([[btn("🔙 بازگشت", f"m:m:{i}")]])
    if a in ("m", "r"):
        return await page(c, x)
    if a == "i":
        return await info_page(c, x)
    if a == "pw":
        return await show(c, "🔑 <b>تغییر رمز</b>\n\nرمز جدید را چطور می‌خواهی؟",
                          kb([[btn("🎲 رمز تصادفی امن", f"m:pg:{i}", style="success")],
                              [btn("✍️ رمز دلخواه خودم", f"m:pc:{i}", style="primary")],
                              [btn("🔙 بازگشت", f"m:m:{i}", style="danger")]]))
    if a == "pg":
        return await apply_pw(c, x, gen_password())
    if a == "pc":
        WAIT[uid] = ("m_pw", i)
        return await show(c, "✍️ رمز جدید را بفرست (انگلیسی، حداقل ۸ کاراکتر و حداقل ۲ رقم، بدون فاصله).\n"
                             "پیام رمز بعد از ارسال پاک می‌شود. برای لغو /start را بزن.", back)
    if a == "un":
        WAIT[uid] = ("m_un", i)
        return await show(c, "👤 نام کاربری جدید را بفرست (حروف انگلیسی، عدد و _ ، ۴ تا ۲۰ کاراکتر، شروع با حرف).\n"
                             "⚠️ بعد از تغییر باید با نام کاربری جدید وارد پنل شوی. برای لغو /start را بزن.", back)
    if a in ("bv", "bg", "bp"):
        return await buy_volume(c, x, a, p)
    if a == "tr":
        WAIT[uid] = ("m_tr", i)
        return await show(c, "📥 <b>انتقال مالکیت</b>\n\nآیدی عددی تلگرام گیرنده را بفرست. گیرنده باید قبلاً ربات را استارت کرده باشد.\n"
                             "بعد از انتقال، سرویس از لیست تو پاک و به لیست او اضافه می‌شود؛ اطلاعات داخل پنل (کاربران و حجم) "
                             "سر جایش می‌ماند. برای لغو /start را بزن.", back)
    if a == "tc":
        to = int(p[3])
        if not await db.row("SELECT 1 FROM users WHERE tg_id=?", to) or to == uid:
            return await c.answer("گیرنده معتبر نیست.", show_alert=True)
        await db.run("UPDATE panels SET user_id=? WHERE id=? AND user_id=?", to, i, uid)
        await db.ev("transfer", uid, f"{x['admin_username']}>{to}")
        try:
            await c.bot.send_message(to, f"📥 سرویس <b>{h(nick(x))}</b> به تو منتقل شد.\n"
                                         "برای امنیت، بهتر است رمز پنل را عوض کنی.",
                                     kb([[btn("⚙️ مدیریت سرویس", f"m:m:{i}", style="primary")]]))
        except Exception:
            log.warning("cannot notify %s", to)
        return await show(c, "✅ سرویس منتقل شد و از لیست پنل‌های تو حذف شد.", kb([[btn("📦 پنل‌های من", "u:panels")]]))
    if a == "nn":
        WAIT[uid] = ("m_nn", i)
        return await show(c, "✏️ نام جدید سرویس را بفرست (فقط برای نمایش در ربات است). برای لغو /start را بزن.", back)
    await c.answer()


@router.message(waiting("m_"))
async def mwait(m):
    uid = m.from_user.id
    kind, i = WAIT[uid]
    text = (m.text or "").strip()
    x = await get_panel(uid, i)
    if not x:
        WAIT.pop(uid, None)
        return await m.answer("پنل پیدا نشد.")
    if kind == "m_pw":
        try:
            await m.delete()
        except Exception:
            pass
        bad = pw_problem(text)
        if bad:
            return await m.answer(f"⚠️ {bad}\nدوباره بفرست:")
        WAIT.pop(uid, None)
        return await apply_pw(m, x, text)
    if kind == "m_un":
        return await do_username(m, x, text)
    if kind == "m_tr":
        to = num(text)
        if not to or to == uid:
            return await m.answer("آیدی عددی معتبر بفرست (غیر از آیدی خودت). برای لغو /start را بزن.")
        u = await db.row("SELECT name FROM users WHERE tg_id=?", to)
        if not u:
            return await m.answer("این کاربر هنوز ربات را استارت نکرده؛ باید اول /start بزند. آیدی دیگری بفرست یا /start را بزن.")
        WAIT.pop(uid, None)
        return await m.answer(f"⚠️ سرویس <b>{h(nick(x))}</b> به کاربر <code>{to}</code> ({h(u['name'])}) منتقل شود؟\n"
                              "این کار برگشت‌پذیر نیست.",
                              kb([[btn("✅ بله، منتقل کن", f"m:tc:{i}:{to}", style="success")],
                                  [btn("❌ انصراف", f"m:m:{i}", style="danger")]]))
    if kind == "m_nn":
        if not CH.match(text):
            return await m.answer("نام معتبر نیست (۲ تا ۳۲ کاراکتر، بدون < یا >). دوباره بفرست:")
        WAIT.pop(uid, None)
        await db.run("UPDATE panels SET nick=? WHERE id=?", text, i)
        await db.ev("nick", uid, text)
        x = await get_panel(uid, i)
        return await page(m, x)
