"""Live card-to-card invoice: 10-minute countdown, copy/cancel buttons, small-print rules."""
from __future__ import annotations

import asyncio
import logging
import random
import time

from . import db
from .tg import EMPTY_KB, Callback, Router, TgError
from .ui import WAIT, btn, chunk, fmt, h, kb, show, xbtn

log = logging.getLogger(__name__)
router = Router()
TTL = 600      # invoice lifetime (seconds)
TICK = 30      # edit interval (seconds)
PRESETS = [50_000, 100_000, 200_000, 500_000, 1_000_000]   # مبلغ‌های پیشنهادی شارژ (تومان)
MAX_OFFSET = 999    # حداکثر اختلاف تصادفی مبلغ فاکتور (تومان)
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")

INV: dict[int, dict] = {}      # uid -> open invoice
SENT: dict[int, tuple] = {}    # receipt id -> (chat_id, message_id)

# قوانین پرداخت: هر خط یک قانون. {m} = مهلت فاکتور به دقیقه
RULES = [
    "مبلغ واریزی باید <b>دقیقاً</b> برابر مبلغ فاکتور باشد.",
    "واریز بیشتر یا کمتر از مبلغ فاکتور خودکار تایید نمی‌شود و باید با پشتیبانی هماهنگ شود.",
    "فقط به <b>همین شماره کارت</b> واریز کن؛ واریز به کارت دیگر یا اشتباه پیگیری نمی‌شود.",
    "رسید باید <b>کامل و واضح</b> باشد (تاریخ، ساعت، مبلغ و شماره کارت مقصد).",
    "رسید ویرایش‌شده، تکراری یا قدیمی رد می‌شود.",
    "واریز بعد از <b>{m} دقیقه</b> (انقضای فاکتور) خودکار شارژ نمی‌شود.",
    "هر رسید فقط برای <b>یک فاکتور</b> قابل استفاده است.",
    "بررسی رسید ممکن است چند دقیقه تا چند ساعت طول بکشد.",
    "رسید رد شد یا اشتباه واریز کردی؟ به پشتیبانی پیام بده.",
]


def _rules() -> str:
    mins = str(max(1, TTL // 60)).translate(_FA)
    return "\n".join(f"{str(i).translate(_FA)}. {t.replace('{m}', mins)}" for i, t in enumerate(RULES, 1))


def _bar(left: int, width: int = 10) -> str:
    n = max(0, min(width, -(-left * width // TTL)))
    return "▰" * n + "▱" * (width - n)


def _clock(left: int) -> str:
    left = max(0, left)
    return f"{left // 60:02d}:{left % 60:02d}".translate(_FA)


def _text(inv: dict, left: int) -> str:
    return (f"💳 <b>در انتظار پرداخت</b>\n\n"
            f"<blockquote>{_bar(left)}  <b>{_clock(left)}</b> مانده\n"
            f"💰 مبلغ: <b>{fmt(inv['amount'])}</b> تومان</blockquote>\n\n"
            f"⚠️ <b>دقیقاً همین مبلغ</b> را واریز کن؛ چند رقم آخر برای شناسایی پرداخت توست و کل مبلغ واریزی به کیف پولت اضافه می‌شود.\n\n"
            f"مبلغ را به کارت زیر واریز کن:\n<code>{h(inv['card'])}</code>\n{h(inv['holder'])}\n\n"
            "بعد از واریز، <b>عکس رسید</b> را همین‌جا بفرست.\n\n"
            f"<blockquote expandable>📜 <b>قوانین پرداخت</b>\n{_rules()}</blockquote>")


def _markup(inv: dict) -> dict:
    card = "".join(ch for ch in str(inv["card"]) if ch.isdigit()) or str(inv["card"])
    return kb([[btn("📸 ارسال رسید", "inv:r", style="success")],
               [xbtn("💰 کپی مبلغ", copy_text={"text": str(inv["amount"])}),
                xbtn("📋 کپی شماره کارت", copy_text={"text": card})],
               [btn("❌ انصراف از پرداخت", "inv:c", style="danger")]])


async def _edit(bot, inv: dict, text: str, markup: dict | None = None) -> None:
    try:
        await bot.api("editMessageText", chat_id=inv["chat"], message_id=inv["mid"], text=text,
                      parse_mode="HTML", reply_markup=markup or EMPTY_KB,
                      link_preview_options={"is_disabled": True})
    except TgError as e:
        if "not modified" not in str(e):
            log.info("invoice edit: %s", e)


async def _run(bot, uid: int, inv: dict) -> None:
    while True:
        left = inv["exp"] - int(time.time())
        await asyncio.sleep(max(1, min(TICK, left)))
        left = inv["exp"] - int(time.time())
        if INV.get(uid) is not inv or WAIT.get(uid, ("",))[0] != "u_receipt":
            if INV.get(uid) is inv:
                INV.pop(uid, None)
            return await _edit(bot, inv, "❌ این فاکتور لغو شد.")
        if left <= 0:
            INV.pop(uid, None)
            WAIT.pop(uid, None)
            return await _edit(
                bot, inv,
                f"⌛ <b>فاکتور منقضی شد</b>\n\n<blockquote>💰 مبلغ: {fmt(inv['amount'])} تومان\n"
                "مهلت پرداخت تمام شد.</blockquote>\n\nاگر هنوز پرداخت نکرده‌ای، فاکتور جدید بساز.",
                kb([[btn("🔄 فاکتور جدید", "u:charge", style="primary")]]))
        await _edit(bot, inv, _text(inv, left), _markup(inv))


async def _unique(amount: int) -> int:
    """Base amount + small random offset, different from every open invoice and pending receipt."""
    taken = {v["amount"] for v in INV.values()}
    try:
        taken |= {r["amount"] for r in await db.rows("SELECT amount FROM receipts WHERE status='pending'")}
    except Exception:
        pass
    for _ in range(300):
        a = amount + random.randint(11, MAX_OFFSET)
        if a not in taken:
            return a
    return amount + random.randint(1, MAX_OFFSET)



async def start(m, uid: int, amount: int, card, holder, replace=None) -> None:
    pay = await _unique(amount)             # اختلاف چند تومانی برای شناسایی پرداخت هر کاربر
    WAIT[uid] = ("u_receipt", pay)
    inv = {"amount": pay, "base": amount, "card": card, "holder": holder, "chat": m.chat_id, "exp": int(time.time()) + TTL}
    INV.pop(uid, None)                       # an older invoice notices this and marks itself cancelled
    mid = None
    if replace is not None:                  # turn the amount-picker message into the invoice
        try:
            await m.bot.api("editMessageText", chat_id=m.chat_id, message_id=replace.message_id,
                            text=_text(inv, TTL), parse_mode="HTML", reply_markup=_markup(inv),
                            link_preview_options={"is_disabled": True})
            mid = replace.message_id
        except TgError as e:
            log.info("invoice replace failed: %s", e)
    if mid is None:
        mid = (await m.answer(_text(inv, TTL), _markup(inv)))["message_id"]
    inv["mid"] = mid
    INV[uid] = inv
    inv["task"] = asyncio.create_task(_run(m.bot, uid, inv))


async def on_receipt(bot, uid: int, rid: int) -> None:
    inv = INV.pop(uid, None)
    if not inv:
        return
    if inv.get("task"):
        inv["task"].cancel()
    if len(SENT) > 500:
        SENT.pop(next(iter(SENT)), None)
    SENT[rid] = (inv["chat"], inv["mid"])
    await _edit(bot, inv, f"🧾 <b>رسید دریافت شد</b>\n\n<blockquote>💰 مبلغ: {fmt(inv['amount'])} تومان\n"
                          "⏳ در انتظار تایید مدیر</blockquote>")


async def settle(bot, rid: int, ok: bool, r) -> None:
    """Admin reviewed the receipt: turn the user's invoice message into the final state. Never raises."""
    try:
        info = SENT.pop(rid, None)
        if not info:
            return
        text = (f"✅ <b>پرداخت تایید شد</b>\n\n<blockquote>💰 {fmt(r['amount'])} تومان به کیف پولت اضافه شد</blockquote>"
                if ok else "❌ <b>رسید رد شد</b>\n\n<blockquote>اگر اشتباه است به پشتیبانی پیام بده.</blockquote>")
        await bot.api("editMessageText", chat_id=info[0], message_id=info[1], text=text,
                      parse_mode="HTML", reply_markup=EMPTY_KB)
    except Exception as e:
        log.info("invoice settle: %s", e)


async def _answer(c: Callback, text: str | None = None, alert: bool = False) -> None:
    try:
        await c.answer(text, alert)
    except TgError:
        pass


@router.callback("inv:r")
async def hint_receipt(c: Callback):
    await _answer(c, "📸 عکس رسید را همین‌جا، توی همین چت بفرست.", True)


@router.callback("inv:c")
async def cancel_invoice(c: Callback):
    uid = c.from_user.id
    inv = INV.get(uid)
    if inv is None or c.message is None or inv.get("mid") != c.message.message_id:
        return await _answer(c, "این فاکتور دیگر فعال نیست.", True)
    INV.pop(uid, None)
    if WAIT.get(uid, ("",))[0] == "u_receipt":
        WAIT.pop(uid, None)
    if inv.get("task"):
        inv["task"].cancel()
    await _edit(c.bot, inv, "❌ <b>پرداخت لغو شد</b>\n\nهر وقت خواستی می‌تونی دوباره کیف پولت رو شارژ کنی.",
                kb([[btn("🏠 منوی اصلی", "u:home")]]))
    await _answer(c, "لغو شد")


async def _min() -> int:
    try:
        return int(await db.get_setting("min_charge") or 0)
    except ValueError:
        return 0


@router.callback("u:charge")
async def chooser(c: Callback):
    uid = c.from_user.id
    WAIT[uid] = ("u_charge", None)           # typing an amount directly keeps working
    minc = await _min()
    try:
        bal = (await db.row("SELECT balance FROM users WHERE tg_id=?", uid))["balance"]
    except Exception:
        bal = None
    rows = [[btn("✏️ مبلغ دلخواه", "inv:x", style="primary")]]
    rows += chunk([btn(f"💵 {fmt(a)} تومان", f"inv:a:{a}", style="success") for a in PRESETS if a >= minc], 2)
    rows.append([btn("🏠 منوی اصلی", "u:home")])
    text = ("💰 <b>شارژ کیف پول</b>\n\n"
            + (f"موجودی فعلی: <b>{fmt(bal)}</b> تومان\n" if bal is not None else "")
            + "یکی از مبلغ‌های پیشنهادی را بزن یا «مبلغ دلخواه» را انتخاب کن.\nمبلغ نهایی فاکتور چند تومان با رقم انتخابی فرق دارد (برای شناسایی پرداخت تو)؛ کل مبلغ واریزی شارژ می‌شود."
            + (f"\nحداقل شارژ: {fmt(minc)} تومان" if minc else ""))
    await show(c, text, kb(rows))


@router.callback("inv:x")
async def custom_amount(c: Callback):
    WAIT[c.from_user.id] = ("u_charge", None)
    minc = await _min()
    await show(c, "✏️ <b>مبلغ دلخواه</b>\n\nمبلغ را به <b>تومان</b> بفرست"
               + (f" (حداقل {fmt(minc)} تومان)" if minc else "") + ".\nمثلاً: <code>250000</code>",
               kb([[btn("🔙 برگشت", "u:charge")]]))


@router.callback("inv:a:")
async def pick_amount(c: Callback):
    uid = c.from_user.id
    try:
        amount = int(c.data.split(":")[2])
    except (IndexError, ValueError):
        return await _answer(c)
    minc = await _min()
    if amount < max(minc, 1):
        return await _answer(c, f"حداقل مبلغ شارژ {fmt(minc)} تومان است.", True)
    card, holder = await db.get_setting("card"), await db.get_setting("holder")
    if not card:
        return await _answer(c, "شماره کارت هنوز توسط مدیر ثبت نشده است.", True)
    if c.message is None:
        return await _answer(c)
    WAIT[uid] = ("u_receipt", amount)
    await _answer(c)
    await start(c.message, uid, amount, card, holder, replace=c.message)
