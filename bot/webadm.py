from __future__ import annotations

import asyncio

from . import config
from .tg import Callback, Message, Router
from .ui import WAIT, h, kb, show

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)


def B(text: str, data: str, style: str = "") -> dict:
    b = {"text": text, "callback_data": data}
    if style in ("primary", "success", "danger"):
        b["style"] = style
    return b


def info():
    from web import app as W
    dom = W.env("WEB_DOMAIN").replace("https://", "").replace("http://", "").strip("/ ")
    slug = W.get_slug()
    return dom, (f"https://{dom}/{slug}/" if dom else "")


async def page(ev, note: str = "") -> None:
    dom, url = await asyncio.to_thread(info)
    uid = ev.from_user.id
    if not dom:
        text = (f"{note}🌐 <b>پنل وب</b>\n\nدامنه تنظیم نشده. روی سرور بزن:\n"
                "<code>echo 'WEB_DOMAIN=web.example.com' >> /opt/pgbot/.env</code>\n"
                "بعد دوباره همین صفحه را باز کن.")
        rows = []
    else:
        text = (f"{note}🌐 <b>پنل وب</b>\n\n🔗 آدرس:\n<code>{h(url)}</code>\n\n"
                f"👤 نام کاربری: <code>{uid}</code>\n"
                "🔑 رمز: با «ساخت رمز جدید» ساخته می‌شود و فقط همان لحظه نشان داده می‌شود.")
        rows = [[{"text": "🌐 باز کردن پنل", "url": url}]]
    rows.append([B("🔑 ساخت رمز جدید", "wb:pw", "success")])
    rows.append([B("🔙 بازگشت", "ux:m")])
    await show(ev, text, kb(rows))


@router.command("web")
async def cmd(m: Message):
    WAIT.pop(m.from_user.id, None)
    await page(m)


@router.callback("wb:")
async def wbcb(c: Callback):
    WAIT.pop(c.from_user.id, None)
    try:
        if c.data == "wb:pw":
            from web import app as W
            pw = await asyncio.to_thread(W.set_password)
            return await page(c, f"✅ رمز جدید پنل وب:\n<code>{h(pw)}</code>\nنشست‌های قبلی بسته شد؛ این پیام را بعد از ذخیره پاک کن.\n\n")
        await page(c)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await show(c, "❌ خطا: <code>" + h(repr(e)) + "</code>", kb([[B("🔙 بازگشت", "ux:m")]]))
