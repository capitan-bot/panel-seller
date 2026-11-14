from __future__ import annotations

import json
from pathlib import Path

from . import config, db
from .tg import Callback, Message, Router
from .ui import PE, WAIT, h, kb, load_ov, show, waiting

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)
PRESET = Path(__file__).parent / "preset_emojis.json"
PAGE = 8


def B(text: str, data: str, style: str = "") -> dict:
    b = {"text": text, "callback_data": data}
    if style in ("primary", "success", "danger"):
        b["style"] = style
    return b


def norm(s: str) -> str:
    return s.replace("\ufe0f", "").strip()


def is_plain(t: str) -> bool:
    return bool(t) and len(t) <= 16 and not any(ch.isalpha() for ch in t) and any(ord(ch) > 0x2000 for ch in t)


async def ensure() -> None:
    await db.run("CREATE TABLE IF NOT EXISTS pemoji(plain TEXT PRIMARY KEY, emoji_id TEXT NOT NULL)")


async def num(sql: str) -> int:
    try:
        r = await db.row(sql)
        return int(r["n"]) if r else 0
    except Exception:
        return 0


async def upsert(plain: str, eid: str):
    old = await db.row("SELECT emoji_id FROM pemoji WHERE plain=?", plain)
    await db.run("INSERT INTO pemoji(plain, emoji_id) VALUES(?,?) "
                 "ON CONFLICT(plain) DO UPDATE SET emoji_id=excluded.emoji_id", plain, eid)
    return old["emoji_id"] if old else None


async def hub(ev) -> None:
    await ensure()
    await load_ov()
    pe = await num("SELECT COUNT(*) AS n FROM pemoji")
    rn = await num("SELECT COUNT(*) AS n FROM ubtn WHERE title != ''")
    co = await num("SELECT COUNT(*) AS n FROM ubtn WHERE style != ''")
    text = ("🛠 <b>مدیریت تغییرات ظاهری ربات</b>\n\n"
            f"✨ ایموجی‌های پریمیوم ثبت‌شده: {pe}\n"
            f"✏️ تغییر نام دکمه‌ها: {rn}\n"
            f"🎨 دکمه‌های رنگ‌شده: {co}\n\n"
            "از طریق دکمه‌های زیر می‌توانید ظاهر ربات را شخصی‌سازی کنید.")
    await show(ev, text, kb([
        [B("✨ ایموجی پریمیوم", "ux:e"), B("✏️ تغییر نام دکمه‌ها", "b:m")],
        [B("🎨 رنگ دکمه‌ها", "b:m"), B("🔄 بازنشانی کل ظاهر", "ux:r", "danger")],
        [B("🧩 سبک منو و چیدمان", "mn:m")],
        [B("🔙 بازگشت به پنل مدیریت", "a:home")],
    ]))


async def emenu(ev, note: str = "") -> None:
    await ensure()
    await load_ov()
    total = await num("SELECT COUNT(*) AS n FROM pemoji")
    text = (f"{note}✨ <b>ایموجی پریمیوم</b>\n"
            f"ثبت‌شده: {total} | فعال در ربات: {len(PE)}\n\n"
            "هر دکمه‌ای که ایموجی ساده‌ی ثبت‌شده را داشته باشد، با نسخه‌ی پریمیومش نمایش داده می‌شود.")
    await show(ev, text, kb([
        [B("➕ افزودن ایموجی", "ux:a", "success")],
        [B("✨ ایموجی آماده", "ux:p", "primary"), B("📋 لیست و حذف", "ux:l:0")],
        [B("🔎 تشخیص", "ux:g"), B("🧹 حذف همه", "ux:x", "danger")],
        [B("🔙 بازگشت", "ux:m")],
    ]))


async def elist(ev, page: int, note: str = "") -> None:
    await ensure()
    data = await db.rows("SELECT rowid AS id, plain, emoji_id FROM pemoji ORDER BY rowid DESC")
    pages = max(1, -(-len(data) // PAGE))
    page = max(0, min(page, pages - 1))
    part = data[page * PAGE:(page + 1) * PAGE]
    lines = [f"{h(r['plain'])} ➔ <code>{h(str(r['emoji_id']))}</code>" for r in part] or ["خالی است."]
    text = (f"{note}📋 <b>لیست ایموجی‌ها</b> ({page + 1}/{pages})\n"
            "جدیدترین‌ها بالاست. برای حذف روی دکمه‌ی هر مورد بزن.\n\n" + "\n".join(lines))
    rows = [[B(f"🗑 {r['plain']}  …{str(r['emoji_id'])[-6:]}", f"ux:d:{r['id']}:{page}")] for r in part]
    nav = []
    if page > 0:
        nav.append(B("⬅️ قبلی", f"ux:l:{page - 1}"))
    if page < pages - 1:
        nav.append(B("بعدی ➡️", f"ux:l:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([B("🔙 بازگشت", "ux:e")])
    await show(ev, text, kb(rows))


async def diag(ev) -> None:
    from . import ui
    await ensure()
    await load_ov()
    n_db = await num("SELECT COUNT(*) AS n FROM pemoji")
    last = await db.row("SELECT plain, emoji_id FROM pemoji ORDER BY rowid DESC LIMIT 1")
    lines = [f"دیتابیس: {n_db}", f"حافظه‌ی ربات: {len(PE)}"]
    if n_db != len(PE):
        lines.append("⚠️ حافظه با دیتابیس یکی نیست.")
    if last:
        t = ui._build(f"{last['plain']} تست", "", "", True, {"callback_data": "x"})
        ok = str(t.get("icon_custom_emoji_id", "")) == str(last["emoji_id"])
        lines.append(f"آخرین ثبت: {h(last['plain'])} ➔ <code>{h(str(last['emoji_id']))}</code>")
        lines.append("تست نمایش روی دکمه: " + ("✅ اعمال می‌شود" if ok else "❌ اعمال نمی‌شود"))
    else:
        lines.append("هنوز ایموجی‌ای ثبت نشده.")
    await show(ev, "🔎 <b>تشخیص</b>\n\n" + "\n".join(lines), kb([[B("🔄 بررسی دوباره", "ux:g")], [B("🔙 بازگشت", "ux:e")]]))


async def _cb(c: Callback) -> None:
    p = c.data.split(":", 3)
    a, uid = p[1], c.from_user.id
    WAIT.pop(uid, None)
    if a == "m":
        return await hub(c)
    if a == "e":
        return await emenu(c)
    if a == "a":
        WAIT[uid] = ("ux_plain", "")
        return await show(c, "مرحله ۱ از ۳\nیک <b>ایموجی ساده (معمولی)</b> بفرست؛ همانی که در دکمه‌ها هست. مثلاً 🛒",
                          kb([[B("❌ انصراف", "ux:e")]]))
    if a == "l":
        return await elist(c, int(p[2]))
    if a == "d":
        await ensure()
        await db.run("DELETE FROM pemoji WHERE rowid=?", int(p[2]))
        await load_ov()
        return await elist(c, int(p[3]), "🗑 حذف شد.\n\n")
    if a == "g":
        return await diag(c)
    if a == "p":
        try:
            data = json.loads(PRESET.read_text(encoding="utf-8"))
        except Exception as e:
            return await emenu(c, f"❌ فایل ایموجی‌های آماده پیدا نشد: <code>{h(repr(e))}</code>\n\n")
        await ensure()
        for plain, eid in data.items():
            await upsert(norm(plain), str(eid))
        await load_ov()
        return await emenu(c, f"✅ {len(data)} ایموجی آماده فعال شد.\n\n")
    if a == "x":
        return await show(c, "⚠️ همه‌ی ایموجی‌های ثبت‌شده حذف شود؟",
                          kb([[B("⚠️ بله، حذف همه", "ux:xc", "danger")], [B("❌ انصراف", "ux:e")]]))
    if a == "xc":
        await ensure()
        await db.run("DELETE FROM pemoji")
        await load_ov()
        return await emenu(c, "🧹 همه حذف شد.\n\n")
    if a == "ok":
        eid, plain = p[2], norm(p[3])
        if not eid.isdigit() or not plain:
            return await emenu(c, "❌ اطلاعات نامعتبر بود؛ دوباره «➕ افزودن» را بزن.\n\n")
        await ensure()
        old = await upsert(plain, eid)
        await load_ov()
        if old is None:
            note = f"✅ {h(plain)} جدید اضافه شد.\n\n"
        elif str(old) == eid:
            note = f"ℹ️ {h(plain)} با همین شناسه از قبل ثبت بود؛ تغییری نکرد.\n\n"
        else:
            note = f"♻️ {h(plain)} قبلاً ثبت بود و جایگزین شد.\n\n"
        return await emenu(c, note)
    if a == "r":
        return await show(c, "⚠️ آیا از پاکسازی و بازنشانی تمام تنظیمات ظاهری اطمینان دارید؟",
                          kb([[B("⚠️ بله، پاکسازی کامل", "ux:rc", "danger")], [B("❌ انصراف", "ux:m")]]))
    if a == "rc":
        await ensure()
        await db.run("DELETE FROM ubtn")
        await db.run("DELETE FROM pemoji")
        await load_ov()
        return await hub(c)
    await hub(c)


@router.callback("ux:")
async def uxcb(c: Callback):
    try:
        await _cb(c)
    except Exception as e:
        import traceback
        traceback.print_exc()
        WAIT.pop(c.from_user.id, None)
        await show(c, "❌ خطا: <code>" + h(repr(e)) + "</code>", kb([[B("🔙 بازگشت", "ux:m")]]))


@router.message(waiting("ux_"))
async def uxwait(m: Message):
    uid = m.from_user.id
    try:
        kind, val = WAIT[uid]
        text = (m.text or "").strip()
        ids = [e["custom_emoji_id"] for e in (m.entities or []) if e.get("type") == "custom_emoji"]
        if kind == "ux_plain":
            if ids or not is_plain(text):
                return await m.answer("یک ایموجی ساده (معمولی) بفرست، نه پریمیوم و نه متن.")
            WAIT[uid] = ("ux_prem", norm(text))
            return await m.answer("مرحله ۲ از ۳\nحالا ایموجی پریمیوم همین ایموجی را بفرست.")
        if kind == "ux_prem":
            eid = ids[0] if ids else (text if text.isdigit() and len(text) > 10 else "")
            if not eid:
                return await m.answer("ایموجی پریمیوم دریافت نشد. یک ایموجی پریمیوم بفرست.")
            WAIT.pop(uid, None)
            return await show(m, f"مرحله ۳ از ۳\n{h(val)} ➔ <code>{h(str(eid))}</code>\nبرای ذخیره «✅ ثبت» را بزن.",
                              kb([[B("✅ ثبت", f"ux:ok:{eid}:{val}", "success")], [B("❌ لغو", "ux:e")]]))
        WAIT.pop(uid, None)
    except Exception as e:
        import traceback
        traceback.print_exc()
        WAIT.pop(uid, None)
        await m.answer("خطا: " + repr(e))
