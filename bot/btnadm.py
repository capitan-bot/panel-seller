from __future__ import annotations

from . import config, db
from .tg import Callback, Message, Router
from .ui import WAIT, btn, kb, h, load_ov, pbtn, show, waiting

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)
COLORS = ["", "primary", "success", "danger", "none"]
CNAME = {"": "پیش‌فرض ربات", "primary": "آبی", "success": "سبز", "danger": "قرمز", "none": "بدون رنگ"}
SECTIONS = [
    ("🌐 عمومی (در همه صفحه‌ها)", ["🏠 منوی اصلی", "🔙 بازگشت", "⬅️ بازگشت", "❌ لغو"]),
    ("🛒 خرید پنل", ["✏️ حجم دلخواه", "⬅️ بازگشت به محصولات", "✅ انتخاب و ادامه خرید", "⬅️ بازگشت به پکیج‌های محصول",
                    "🎲 پیشنهادهای جدید", "✏️ تغییر نام کاربری", "✅ پرداخت و ساخت پنل", "💰 شارژ کیف پول"]),
    ("💳 کیف پول", ["➕ شارژ کارت‌به‌کارت"]),
    ("🎁 پیام تحویل سرویس", ["🖥 ورود به پنل", "🔑 کپی رمز", "👤 کپی نام کاربری"]),
    ("📦 پنل‌های من / مدیریت سرویس", ["⚙️ مدیریت سرویس", "🖥 ورود به پنل وب", "📊 مشخصات و مصرف", "🔑 تغییر رمز",
                                    "👤 تغییر نام کاربری", "✏️ تغییر نام سرویس", "📥 انتقال مالکیت", "🔄 بروزرسانی",
                                    "📦 پنل‌های من", "💳 خرید حجم", "✅ پرداخت و افزودن حجم", "🎲 رمز تصادفی امن", "✍️ رمز دلخواه خودم", "✅ بله، منتقل کن",
                                    "❌ انصراف"]),
]
CAT = [(si, t) for si, (_, ts) in enumerate(SECTIONS) for t in ts]


async def menu(ev) -> None:
    rows = [[btn("🏠 دکمه‌های منوی اصلی", "a:btn", style="primary")]]
    rows += [[btn(t, f"b:s:{i}")] for i, (t, _) in enumerate(SECTIONS)]
    await show(ev, "🎛 <b>دکمه‌ها</b>\nبخش را انتخاب کن؛ رنگ، نام و ایموجی پریمیوم هر دکمه "
                   "در همه جای ربات اعمال می‌شود.", kb(rows + [[btn("🔙 مدیریت", "a:home")]]))


async def section(ev, si: int) -> None:
    ts = SECTIONS[si][1]
    base = sum(len(x[1]) for x in SECTIONS[:si])
    rows = [[pbtn(t, f"b:k:{base + j}")] for j, t in enumerate(ts)]
    await show(ev, f"{SECTIONS[si][0]}\nروی هر دکمه بزن تا تنظیمش کنی (پیش‌نمایش همین‌جاست).",
               kb(rows + [[btn("🔙 بخش‌ها", "b:m")]]))


async def card(ev, n: int) -> None:
    si, t = CAT[n]
    o = await db.row("SELECT * FROM ubtn WHERE key=?", t) or {"title": "", "emoji_id": "", "style": ""}
    text = (f"🎛 <b>{h(t)}</b>\n\nنام فعلی: {h(o['title'] or t)}\nرنگ: {CNAME[o['style']]}\n"
            f"ایموجی پریمیوم: {'<code>' + h(o['emoji_id']) + '</code>' if o['emoji_id'] else 'ندارد'}")
    rows = [[btn("🎨 رنگ بعدی", f"b:c:{n}"), btn("✏️ تغییر نام", f"b:t:{n}")],
            [btn("✨ ایموجی پریمیوم", f"b:e:{n}"), btn("♻️ پیش‌فرض", f"b:r:{n}")],
            [pbtn(t, f"b:k:{n}")], [btn("🔙 بازگشت", f"b:s:{si}")]]
    await show(ev, text, kb(rows))


async def put(key: str, **kw) -> None:
    await db.run("INSERT INTO ubtn(key) VALUES(?) ON CONFLICT(key) DO NOTHING", key)
    for k, v in kw.items():
        await db.run(f"UPDATE ubtn SET {k}=? WHERE key=?", v, key)
    await load_ov()


@router.callback("b:")
async def bcb(c: Callback):
    p = c.data.split(":")
    a, uid = p[1], c.from_user.id
    WAIT.pop(uid, None)
    if a == "m":
        return await menu(c)
    n = int(p[2])
    if a == "s":
        return await section(c, n)
    t = CAT[n][1]
    if a == "k":
        return await card(c, n)
    if a == "c":
        o = await db.row("SELECT style FROM ubtn WHERE key=?", t)
        cur = o["style"] if o else ""
        await put(t, style=COLORS[(COLORS.index(cur) + 1) % len(COLORS)])
    elif a == "r":
        await put(t, title="", emoji_id="", style="")
    elif a == "t":
        WAIT[uid] = ("b_title", n)
        return await show(c, "نام جدید دکمه را بفرست (۱ تا ۳۰ حرف):", kb([[btn("🔙 بازگشت", f"b:k:{n}")]]))
    elif a == "e":
        WAIT[uid] = ("b_emoji", n)
        return await show(c, "یک <b>ایموجی پریمیوم</b> را همین‌جا بفرست (یا عدد 0 برای حذف).",
                          kb([[btn("🔙 بازگشت", f"b:k:{n}")]]))
    await card(c, n)


@router.message(waiting("b_"))
async def bwait(m: Message):
    uid = m.from_user.id
    kind, n = WAIT[uid]
    text = (m.text or "").strip()
    t = CAT[n][1]
    if kind == "b_title":
        if not text or len(text) > 30:
            return await m.answer("اسم باید بین ۱ تا ۳۰ حرف باشد.")
        await put(t, title="" if text == t else text)
    else:
        ids = [e["custom_emoji_id"] for e in m.entities if e.get("type") == "custom_emoji"]
        if ids:
            eid = ids[0]
        elif text == "0":
            eid = ""
        elif text.isdigit() and len(text) > 10:
            eid = text
        else:
            return await m.answer("ایموجی پریمیوم دریافت نشد. یک ایموجی پریمیوم بفرست یا 0 برای حذف.")
        await put(t, emoji_id=eid)
    WAIT.pop(uid, None)
    await card(m, n)
