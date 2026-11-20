from __future__ import annotations

import logging
import re
import time

from . import config, db, report
from .progress import Progress
from .tg import Callback, Message, Router
from .panel import PanelError, PanelTaken, gen_password, gen_username, get_pg
from . import invoice
from .ui import (WAIT, xbtn, btn, chunk, fdate, fgb, fmt, h, kb, main_menu, notify_admins, num, panel_label, panel_text,
                 show, waiting)

router = Router()
log = logging.getLogger(__name__)

BUY: dict[int, dict] = {}   # draft of the purchase in progress: {pid, gb, price, user, pw, sugg}
USER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,19}$")
GB_RE = re.compile(r"^(\d+(?:\.\d+)?)\s*(tb|t|ترا|ترابایت|gb|g|گیگ|گیگابایت)?$")
_DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def parse_gb(s: str) -> int | None:
    """'300' -> 300, '2tb' / '2 ترا' -> 2048 (GB). Returns None when it is not a volume."""
    m = GB_RE.match((s or "").translate(_DIG).strip().lower().replace("٫", "."))
    if not m:
        return None
    v = float(m.group(1)) * (1024 if (m.group(2) or "g")[0] in ("t", "ت") else 1)
    return int(round(v))


def pw_problem(pw: str) -> str | None:
    if not pw.isascii() or re.search(r"\s", pw):
        return "رمز فقط حروف انگلیسی، عدد و علامت باشد (بدون فاصله)."
    if len(pw) < 8 or len(pw) > 64:
        return "رمز باید بین ۸ تا ۶۴ کاراکتر باشد."
    if len(re.findall(r"\d", pw)) < 2:
        return "رمز باید حداقل ۲ رقم داشته باشد."
    return None


async def welcome(user) -> str:
    t = h(await db.get_setting("welcome"))
    return t.replace("{name}", h(user.full_name)).replace("{shop}", h(await db.get_setting("shop")))


async def new_panel(uid: int, product_id: int | None, gb: float, is_test: bool = False,
                    username: str | None = None, password: str | None = None):
    """Creates the reseller admin (with its volume) on PasarGuard and records it. Returns (username, password, base_url).
    Without username/password, random ones are generated (used for the test panel)."""
    sid = 0
    if product_id:
        pr = await db.row("SELECT server_id FROM products WHERE id=?", product_id)
        sid = pr["server_id"] if pr else 0
    pg = await get_pg(sid)
    if username:
        name, pw = username, password
        await pg.create_admin(name, pw, gb=gb)
    else:
        name = pw = ""
        for _ in range(5):
            name, pw = gen_username(), gen_password()
            try:
                await pg.create_admin(name, pw, gb=gb)
                break
            except PanelTaken:
                continue
        else:
            raise PanelError("ساخت نام کاربری یکتا ناموفق بود.")
    try:
        await db.run("INSERT INTO panels(user_id,product_id,gb,admin_username,expires,is_test,created,pw,server_id) VALUES(?,?,?,?,0,?,?,?,?)",
                     uid, product_id, gb, name, int(is_test), int(time.time()), db.enc(pw), pg.sid)
    except Exception:
        try:
            await pg.delete_admin(name)
        except Exception:
            log.exception("cleanup of %s failed", name)
        raise
    return name, pw, pg.base


def creds_text(name: str, pw: str, gb: float, base: str) -> str:
    return (f"✅ <b>پنل شما آماده است</b>\n\n🌐 آدرس پنل:\n<code>{h(base)}/dashboard</code>\n\n"
            f"👤 نام کاربری: <code>{h(name)}</code>\n🔑 رمز: با دکمهٔ «کپی رمز» بردار\n\n"
            f"💎 حجم: {fgb(gb)}\n⏳ اعتبار: نامحدود\n\n⚠️ رمز را جای امنی ذخیره کن.")


async def deliver(c, name: str, pw: str, gb: float, base: str) -> None:
    """Message 1: thanks. Message 2: panel info (password hidden, copy buttons)."""
    x = await db.row("SELECT id FROM panels WHERE admin_username=?", name)
    rows = [[xbtn("🖥 ورود به پنل", url=f"{base}/dashboard")],
            [xbtn("🔑 کپی رمز", copy_text={"text": pw}), xbtn("👤 کپی نام کاربری", copy_text={"text": name})]]
    if x:
        rows.append([btn("⚙️ مدیریت سرویس", f"u:p:{x['id']}", style="primary")])
    rows.append([btn("🏠 منوی اصلی", "u:home")])
    await show(c, "🎉 ممنون از خرید شما!\nسرویس شما با موفقیت ساخته شد؛ اطلاعات پنل در پیام بعدی است.", None)
    await c.message.answer(creds_text(name, pw, gb, base), kb(rows), effect="5046509860389126442")  # 🎉


async def extend_panel(p, days: int) -> None:
    """Legacy time-based panels only (volume panels never expire)."""
    new = max(int(time.time()), p["expires"]) + days * 86400
    if p["status"] != "active":
        pg = await get_pg()
        await pg.set_disabled(p["admin_username"], False)
    await db.run("UPDATE panels SET expires=?, status='active' WHERE id=?", new, p["id"])


def detail_text(x, gb: float, price: int, title: str) -> str:
    t = (f"{title}\n\n• حجم ثابت پکیج: {gb:g} گیگابایت\n• قیمت ثابت پکیج: {fmt(price)} تومان\n"
         "• مدت اعتبار: نامحدود (بدون انقضا)")
    if x["descr"]:
        t += f"\n\n📝 توضیحات پکیج:\n{h(x['descr'])}"
    return t


async def ask_password(ev, uid: int) -> None:
    st = BUY[uid]
    st["sugg"] = [gen_password() for _ in range(3)]
    WAIT[uid] = ("u_pw", None)
    rows = [[btn(f"🔑 {s}", f"u:pp:{i}", style="success" if i % 2 == 0 else "primary")] for i, s in enumerate(st["sugg"])]
    rows += [[btn("🎲 پیشنهادهای جدید", "u:pn")], [btn("❌ لغو", "u:buy", style="danger")]]
    await show(ev, "🔑 <b>رمز پنل</b>\n\nیکی از رمزهای پیشنهادی را بزن، یا <b>رمز دلخواهت</b> را همین‌جا تایپ کن\n"
                   "(حداقل ۸ کاراکتر و حداقل ۲ رقم، بدون فاصله).", kb(rows))


async def auto_code(uid: int, st: dict) -> None:
    """Applies the discount code saved in the wallet, if it is still valid for this order."""
    if st.get("code_id"):
        return
    pc = await db.get_setting(f"pc_{uid}")
    if not pc:
        return
    r, err = await db.code_check(pc, uid, ("percent", "amount"), st["price"])
    d = db.code_discount(r, st["price"]) if r else 0
    if r and d > 0:
        st["orig"], st["price"], st["code_id"], st["code"] = st["price"], st["price"] - d, r["id"], r["code"]
    elif not (err and "حداقل" in err):
        await db.set_setting(f"pc_{uid}", "")


async def confirm(ev, uid: int) -> None:
    st = BUY[uid]
    await auto_code(uid, st)
    x = await db.row("SELECT * FROM products WHERE id=?", st["pid"])
    bal = (await db.row("SELECT balance FROM users WHERE tg_id=?", uid))["balance"]
    text = (f"🧾 <b>تایید سفارش</b>\n\n📦 محصول: {h(x['name'] if x else '-')}\n💎 حجم: {fgb(st['gb'])}\n"
            f"⏳ اعتبار: نامحدود\n👤 نام کاربری: <code>{h(st['user'])}</code>\n🔑 رمز: <code>{h(st['pw'])}</code>\n\n"
            + (f"💵 قیمت: <s>{fmt(st['orig'])}</s> ➜ <b>{fmt(st['price'])}</b> تومان\n🎟 کد: <code>{h(st['code'])}</code>\n"
               if st.get("code_id") else f"💵 قیمت: {fmt(st['price'])} تومان\n")
            + f"💰 موجودی تو: {fmt(bal)} تومان")
    rows = ([[btn("✅ پرداخت و ساخت پنل", "u:pay", style="success")]] if bal >= st["price"]
            else [[btn("💰 شارژ کیف پول", "u:charge", style="primary")]])
    rows += [[btn("❌ حذف کد تخفیف", "u:dcx") if st.get("code_id") else btn("🎟 کد تخفیف", "u:dc")]]
    rows += [[btn("✏️ تغییر نام کاربری", "u:go"), btn("🔑 تغییر رمز", "u:pn")], [btn("❌ لغو", "u:buy", style="danger")]]
    await show(ev, text, kb(rows))


@router.command("start")
async def start(m: Message):
    WAIT.pop(m.from_user.id, None)
    BUY.pop(m.from_user.id, None)
    await m.answer(await welcome(m.from_user), reply_markup=await main_menu(m.from_user.id in config.ADMIN_IDS or m.from_user.id in config.OPERATOR_IDS))


@router.callback("u:")
async def ucb(c: Callback):
    p = c.data.split(":")
    a, uid = p[1], c.from_user.id
    WAIT.pop(uid, None)
    home = kb([[btn("🏠 منوی اصلی", "u:home")]])

    if a == "home":
        BUY.pop(uid, None)
        return await show(c, await welcome(c.from_user), await main_menu(uid in config.ADMIN_IDS or uid in config.OPERATOR_IDS))

    if a == "account":
        u = await db.row("SELECT * FROM users WHERE tg_id=?", uid)
        n = (await db.row("SELECT COUNT(*) c FROM panels WHERE user_id=? AND is_test=0", uid))["c"]
        return await show(c, f"👤 <b>حساب کاربری</b>\n\n🆔 آیدی: <code>{uid}</code>\n"
                             f"💰 موجودی: {fmt(u['balance'])} تومان\n📦 پنل‌ها: {n}", home)

    if a in ("faq", "support"):
        title = "❓ سوالات متداول" if a == "faq" else "🎧 پشتیبانی"
        return await show(c, f"{title}\n\n{h(await db.get_setting(a))}", home)

    if a == "wallet":
        u = await db.row("SELECT balance FROM users WHERE tg_id=?", uid)
        pc = await db.get_setting(f"pc_{uid}")
        wt = f"💰 <b>کیف پول</b>\n\nموجودی: {fmt(u['balance'])} تومان"
        if pc:
            wt += f"\n🎟 کد تخفیف ثبت‌شده: <code>{h(pc)}</code> (در خرید بعدی اعمال می‌شود)"
        return await show(c, wt, kb([
            [btn("➕ افزایش موجودی", "u:charge", style="success")],
            [btn("🎟 کد تخفیف", "u:wdc", style="primary"), btn("🎁 کد هدیه", "u:gift", style="primary")],
            [btn("🏠 منوی اصلی", "u:home")]]))

    if a == "charge":
        WAIT[uid] = ("u_charge", None)
        minc = int(await db.get_setting("min_charge") or 0)
        return await show(c, f"مبلغ شارژ را به تومان بفرست (حداقل {fmt(minc)}).", home)

    # ---------- buy: product -> package -> details -> username -> password -> confirm ----------
    if a == "buy":
        BUY.pop(uid, None)
        ps = await db.rows("SELECT * FROM products WHERE active=1 ORDER BY sort, id")
        if not ps:
            return await show(c, "فعلاً محصولی برای فروش ثبت نشده است.", home)
        rows = [[btn(f"📦 {x['name']}", f"u:bp:{x['id']}", style="success")] for x in ps]
        return await show(c, "🛒 <b>خرید پنل</b>\n\nمحصول مورد نظر را انتخاب کنید.",
                          kb(rows + [[btn("⬅️ بازگشت", "u:home", style="danger")]]))

    if a == "bp":
        x = await db.row("SELECT * FROM products WHERE id=? AND active=1", int(p[2]))
        if not x:
            return await c.answer("این محصول دیگر موجود نیست.", show_alert=True)
        BUY.pop(uid, None)
        ks = await db.rows("SELECT * FROM packages WHERE product_id=? AND active=1 ORDER BY gb DESC", x["id"])
        rows = chunk([btn(f"💎 {fgb(k['gb'])}", f"u:bk:{k['id']}", style="success" if i % 2 == 0 else "primary")
                      for i, k in enumerate(ks)], 2)
        if x["price_gb"] > 0:
            rows.append([btn("✏️ حجم دلخواه", f"u:bc:{x['id']}", style="primary")])
        rows.append([btn("⬅️ بازگشت به محصولات", "u:buy", style="danger")])
        if not ks and x["price_gb"] <= 0:
            return await show(c, "برای این محصول هنوز پکیجی ثبت نشده است.", kb(rows))
        return await show(c, "📦 <b>پکیج‌های حجم ثابت</b>\n\nپکیج موردنظر را انتخاب کنید؛ جزئیات و توضیحات آن در مرحله بعد "
                             "نمایش داده می‌شود.", kb(rows))

    if a == "bk":
        k = await db.row("SELECT * FROM packages WHERE id=? AND active=1", int(p[2]))
        x = await db.row("SELECT * FROM products WHERE id=? AND active=1", k["product_id"]) if k else None
        if not k or not x:
            return await c.answer("این پکیج دیگر موجود نیست.", show_alert=True)
        BUY[uid] = {"pid": x["id"], "gb": k["gb"], "price": k["price"]}
        return await show(c, detail_text(x, k["gb"], k["price"], f"💎 {fgb(k['gb'])}"),
                          kb([[btn("✅ انتخاب و ادامه خرید", "u:go", style="success")],
                              [btn("⬅️ بازگشت به پکیج‌های محصول", f"u:bp:{x['id']}", style="danger")]]))

    if a == "bc":
        x = await db.row("SELECT * FROM products WHERE id=? AND active=1", int(p[2]))
        if not x or x["price_gb"] <= 0:
            return await c.answer("حجم دلخواه برای این محصول فعال نیست.", show_alert=True)
        WAIT[uid] = ("u_cgb", x["id"])
        return await show(c, f"✏️ <b>حجم دلخواه</b>\n\nحجم را بفرست؛ از {fgb(x['min_gb'])} تا {fgb(x['max_gb'])}.\n"
                             "مثال: <code>300</code> (گیگابایت) یا <code>2tb</code>\n"
                             f"💵 قیمت هر گیگابایت: {fmt(x['price_gb'])} تومان",
                          kb([[btn("⬅️ بازگشت", f"u:bp:{x['id']}", style="danger")]]))

    if a == "go":
        if uid not in BUY:
            return await c.answer("سفارش منقضی شد؛ دوباره از «خرید پنل» شروع کن.", show_alert=True)
        WAIT[uid] = ("u_uname", None)
        return await show(c, "👤 <b>نام کاربری</b>\n\nنام کاربری دلخواهت برای ورود به پنل را بفرست.\n"
                             "• فقط حروف انگلیسی، عدد و _\n• ۴ تا ۲۰ کاراکتر و شروع با حرف\n"
                             "مثال: <code>ali_panel</code>", kb([[btn("❌ لغو", "u:buy", style="danger")]]))

    if a in ("pn", "pp"):
        st = BUY.get(uid)
        if not st or "user" not in st:
            return await c.answer("سفارش منقضی شد؛ دوباره از «خرید پنل» شروع کن.", show_alert=True)
        if a == "pn":
            return await ask_password(c, uid)
        try:
            st["pw"] = st["sugg"][int(p[2])]
        except (KeyError, IndexError, ValueError):
            return await ask_password(c, uid)
        return await confirm(c, uid)

    if a == "gift":
        WAIT[uid] = ("u_gift", None)
        return await show(c, "🎁 <b>کد هدیه</b>\n\nکد هدیه‌ات را بفرست تا مبلغ آن به کیف پولت اضافه شود:",
                          kb([[btn("🔙 بازگشت", "u:wallet")]]))

    if a == "wdc":
        WAIT[uid] = ("u_wdc", None)
        return await show(c, "🎟 <b>کد تخفیف</b>\n\nکد تخفیف را بفرست؛ در خرید بعدی خودکار روی سفارشت اعمال می‌شود:",
                          kb([[btn("🔙 بازگشت", "u:wallet")]]))

    if a in ("dc", "dcx", "dcb"):
        st = BUY.get(uid)
        if not st or "pw" not in st:
            return await c.answer("سفارش منقضی شد؛ دوباره از «خرید پنل» شروع کن.", show_alert=True)
        if a == "dc":
            WAIT[uid] = ("u_dc", None)
            return await show(c, "🎟 <b>کد تخفیف</b>\n\nکد تخفیف را بفرست:", kb([[btn("🔙 بازگشت", "u:dcb")]]))
        if a == "dcx":
            await db.set_setting(f"pc_{uid}", "")
        if a == "dcx" and st.get("code_id"):
            st["price"] = st.pop("orig", st["price"])
            st.pop("code_id", None)
            st.pop("code", None)
        return await confirm(c, uid)

    if a == "pay":
        st = BUY.pop(uid, None)
        if not st or "pw" not in st:
            return await c.answer("سفارش منقضی شد؛ دوباره از «خرید پنل» شروع کن.", show_alert=True)
        if not await db.debit(uid, st["price"]):
            BUY[uid] = st
            return await c.answer("موجودی کافی نیست؛ اول کیف پول را شارژ کن.", show_alert=True)
        if st.get("code_id") and not await db.code_use(st["code_id"], uid):
            await db.credit(uid, st["price"])
            st["price"] = st.pop("orig", st["price"])
            st.pop("code_id", None)
            st.pop("code", None)
            BUY[uid] = st
            await c.answer("این کد تخفیف دیگر معتبر نیست؛ قیمت به حالت عادی برگشت.", show_alert=True)
            return await confirm(c, uid)
        try:
            async with Progress(c.message):
                name, pw, base = await new_panel(uid, st["pid"], st["gb"], False, st["user"], st["pw"])
        except Exception as e:
            await db.credit(uid, st["price"])
            await db.code_release(st.get("code_id"), uid)
            msg = str(e)
            low = msg.lower()
            if isinstance(e, PanelTaken):
                BUY[uid] = st
                WAIT[uid] = ("u_uname", None)
                return await show(c, "⚠️ این نام کاربری روی پنل گرفته شده است؛ یک نام دیگر بفرست:",
                                  kb([[btn("❌ لغو", "u:buy", style="danger")]]))
            if isinstance(e, PanelError) and "password" in low and "http 422" in low:
                BUY[uid] = st
                await c.message.answer(f"⚠️ پنل این رمز را نپذیرفت:\n<code>{h(msg[:200])}</code>\nرمز دیگری انتخاب کن.")
                return await ask_password(c, uid)
            if isinstance(e, PanelError) and "username" in low and "http 422" in low:
                BUY[uid] = st
                WAIT[uid] = ("u_uname", None)
                return await show(c, f"⚠️ پنل این نام کاربری را نپذیرفت:\n<code>{h(msg[:200])}</code>\nنام دیگری بفرست:",
                                  kb([[btn("❌ لغو", "u:buy", style="danger")]]))
            log.exception("buy failed")
            await notify_admins(c.bot, f"⚠️ ساخت پنل برای کاربر <code>{uid}</code> ناموفق بود:\n{h(e)}")
            return await show(c, "❌ ساخت پنل ناموفق بود و مبلغ به کیف پولت برگشت. به پشتیبانی خبر بده.", home)
        if st.get("code_id"):
            await db.ev("code", uid, f"{st['code']} (-{fmt(st['orig'] - st['price'])})")
            await db.set_setting(f"pc_{uid}", "")
        await db.sale(uid, name, "panel", st["gb"], st["price"])
        return await deliver(c, name, pw, st["gb"], base)

    if a == "test":
        try:
            gb = float(await db.get_setting("test_gb") or 0)
        except ValueError:
            gb = 0
        if gb <= 0:
            return await c.answer("تست پنل فعال نیست.", show_alert=True)
        _, n = await db.run("UPDATE users SET test_used=1 WHERE tg_id=? AND test_used=0", uid)
        if n != 1:
            return await c.answer("قبلاً از تست استفاده کرده‌ای.", show_alert=True)
        try:
            async with Progress(c.message, "در حال ساخت پنل تست"):
                name, pw, base = await new_panel(uid, None, gb, True)
        except Exception as e:
            await db.run("UPDATE users SET test_used=0 WHERE tg_id=?", uid)
            log.exception("test failed")
            await notify_admins(c.bot, f"⚠️ ساخت پنل تست برای <code>{uid}</code> ناموفق بود:\n{h(e)}")
            return await c.answer("خطا در ساخت پنل تست؛ بعداً دوباره امتحان کن.", show_alert=True)
        report.on_test(uid, name, gb)
        return await deliver(c, name, pw, gb, base)

    # ---------- my panels ----------
    if a == "panels":
        ps = await db.rows("SELECT * FROM panels WHERE user_id=? ORDER BY id DESC LIMIT 20", uid)
        if not ps:
            return await show(c, "هنوز پنلی نداری.", home)
        rows = [[btn(panel_label(x), f"u:p:{x['id']}")] for x in ps]
        return await show(c, "📦 <b>پنل‌های من</b>", kb(rows + [[btn("🏠 منوی اصلی", "u:home")]]))

    if a in ("p", "pw"):
        x = await db.row("SELECT * FROM panels WHERE id=? AND user_id=?", int(p[2]), uid)
        if not x:
            return await c.answer("پنل پیدا نشد.", show_alert=True)
        back = kb([[btn("🔙 بازگشت", f"u:p:{x['id']}")]])
        if a == "p":
            from . import manage
            return await manage.page(c, x)
        try:
            pw = gen_password()
            await (await get_pg(x["server_id"])).set_password(x["admin_username"], pw)
        except Exception as e:
            log.exception("pw reset failed")
            await notify_admins(c.bot, f"⚠️ تغییر رمز <code>{h(x['admin_username'])}</code> ناموفق بود:\n{h(e)}")
            return await c.answer("تغییر رمز ناموفق بود.", show_alert=True)
        return await show(c, f"🔑 رمز جدید: <code>{h(pw)}</code>", back)

    await c.answer()


@router.message(waiting("u_"))
async def uwait(m: Message):
    uid = m.from_user.id
    kind, arg = WAIT[uid]
    text = (m.text or "").strip()

    if kind == "u_charge":
        amount = num(m.text or "")
        minc = int(await db.get_setting("min_charge") or 0)
        if not amount or amount < max(minc, 1):
            return await m.answer(f"مبلغ معتبر وارد کن (حداقل {fmt(minc)} تومان). برای لغو /start را بزن.")
        card, holder = await db.get_setting("card"), await db.get_setting("holder")
        if not card:
            WAIT.pop(uid, None)
            return await m.answer("شماره کارت هنوز توسط مدیر ثبت نشده است.")
        WAIT[uid] = ("u_receipt", amount)
        return await invoice.start(m, uid, amount, card, holder)

    if kind == "u_receipt":
        if not m.photo:
            return await m.answer("لطفاً عکس رسید را بفرست. برای لغو /start را بزن.")
        file_id = m.photo[-1]["file_id"]
        rid, _ = await db.run("INSERT INTO receipts(user_id,amount,file_id,created) VALUES(?,?,?,?)",
                              uid, arg, file_id, int(time.time()))
        WAIT.pop(uid, None)
        await invoice.on_receipt(m.bot, uid, rid)
        markup = kb([[btn("✅ تایید", f"a:rc:ok:{rid}", style="success"), btn("❌ رد", f"a:rc:no:{rid}", style="danger")]])
        for a in sorted(config.ADMIN_IDS | config.OPERATOR_IDS):
            try:
                await m.bot.send_photo(a, file_id, caption=f"🧾 رسید #{rid}\nکاربر: <code>{uid}</code>\nمبلغ: {fmt(arg)} تومان",
                                       reply_markup=markup)
            except Exception:
                log.warning("cannot send receipt to admin %s", a)
        return await m.answer("✅ رسید ثبت شد؛ بعد از تایید مدیر، موجودی‌ات شارژ می‌شود.")

    if kind == "u_dc":
        st = BUY.get(uid)
        if not st or "pw" not in st:
            WAIT.pop(uid, None)
            return await m.answer("سفارش منقضی شد؛ دوباره از «خرید پنل» شروع کن.")
        base_price = st.get("orig", st["price"])
        r, err = await db.code_check(m.text or "", uid, ("percent", "amount"), base_price)
        if not r:
            return await m.answer(f"❌ {err}\nکد دیگری بفرست، یا /start بزن.")
        d = db.code_discount(r, base_price)
        if d <= 0:
            return await m.answer("❌ این کد روی این سفارش تخفیفی ندارد.")
        st["orig"], st["price"], st["code_id"], st["code"] = base_price, base_price - d, r["id"], r["code"]
        WAIT.pop(uid, None)
        await m.answer(f"✅ کد تخفیف اعمال شد؛ {fmt(d)} تومان تخفیف گرفتی.")
        return await confirm(m, uid)

    if kind == "u_wdc":
        r, err = await db.code_check(m.text or "", uid, ("percent", "amount"))
        if not r:
            return await m.answer(f"❌ {err}\nکد دیگری بفرست، یا /start بزن.")
        await db.set_setting(f"pc_{uid}", r["code"])
        WAIT.pop(uid, None)
        val = f"{r['value']}٪" if r["kind"] == "percent" else f"{fmt(r['value'])} تومان"
        return await m.answer(f"✅ کد تخفیف <code>{h(r['code'])}</code> ({val}) ثبت شد؛ در خرید بعدی خودکار اعمال می‌شود.",
                              reply_markup=kb([[btn("💰 کیف پول", "u:wallet")], [btn("🏠 منوی اصلی", "u:home")]]))

    if kind == "u_gift":
        amount, err = await db.gift_redeem(m.text or "", uid)
        if not amount:
            return await m.answer(f"❌ {err}\nکد دیگری بفرست، یا /start بزن.")
        WAIT.pop(uid, None)
        bal = (await db.row("SELECT balance FROM users WHERE tg_id=?", uid))["balance"]
        return await m.answer(f"🎉 کد هدیه ثبت شد؛ <b>{fmt(amount)}</b> تومان به کیف پولت اضافه شد.\n💰 موجودی جدید: {fmt(bal)} تومان",
                              reply_markup=kb([[btn("🏠 منوی اصلی", "u:home")]]))

    # ---- purchase steps ----
    if kind == "u_cgb":
        x = await db.row("SELECT * FROM products WHERE id=? AND active=1", arg)
        if not x or x["price_gb"] <= 0:
            WAIT.pop(uid, None)
            return await m.answer("حجم دلخواه برای این محصول فعال نیست.")
        gb = parse_gb(text)
        if gb is None or not (x["min_gb"] <= gb <= x["max_gb"]):
            return await m.answer(f"حجم معتبر بفرست: از {fgb(x['min_gb'])} تا {fgb(x['max_gb'])}.\n"
                                  "مثال: <code>300</code> یا <code>2tb</code>")
        price = gb * x["price_gb"]
        BUY[uid] = {"pid": x["id"], "gb": gb, "price": price}
        WAIT.pop(uid, None)
        return await m.answer(detail_text(x, gb, price, f"💎 {fgb(gb)} (حجم دلخواه)"),
                              reply_markup=kb([[btn("✅ انتخاب و ادامه خرید", "u:go", style="success")],
                                               [btn("⬅️ بازگشت به پکیج‌های محصول", f"u:bp:{x['id']}", style="danger")]]))

    if kind in ("u_uname", "u_pw"):
        st = BUY.get(uid)
        if not st:
            WAIT.pop(uid, None)
            return await m.answer("سفارش منقضی شد؛ دوباره از «خرید پنل» شروع کن.")
        if kind == "u_uname":
            if not USER_RE.match(text):
                return await m.answer("نام کاربری معتبر نیست؛ فقط حروف انگلیسی، عدد و _ ، ۴ تا ۲۰ کاراکتر و شروع با حرف.\n"
                                      "دوباره بفرست:")
            if await db.row("SELECT 1 FROM panels WHERE lower(admin_username)=lower(?)", text):
                return await m.answer("این نام کاربری قبلاً گرفته شده؛ یک نام دیگر بفرست:")
            st["user"] = text
            st.pop("pw", None)
            return await ask_password(m, uid)
        try:
            await m.delete()           # the typed password should not stay in the chat
        except Exception:
            pass
        bad = pw_problem(text)
        if bad:
            return await m.answer(f"⚠️ {bad}\nدوباره بفرست یا یکی از پیشنهادها را بزن.")
        st["pw"] = text
        WAIT.pop(uid, None)
        return await confirm(m, uid)
