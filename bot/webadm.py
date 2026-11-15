from __future__ import annotations

import asyncio
import os
import re

from . import config
from .tg import Callback, Message, Router
from .ui import WAIT, h, kb, show

router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)

APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SETUP_LOCK = asyncio.Lock()
_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def B(text: str, data: str, style: str = "") -> dict:
    b = {"text": text, "callback_data": data}
    if style in ("primary", "success", "danger"):
        b["style"] = style
    return b


def info():
    from web import app as W
    dom = W.env("WEB_DOMAIN").replace("https://", "").replace("http://", "").strip("/ ")
    slug = W.get_prefix()
    return dom, (f"https://{dom}/{slug}/" if dom else "")


async def page(ev, note: str = "") -> None:
    dom, url = await asyncio.to_thread(info)
    uid = ev.from_user.id
    if not dom:
        text = (f"{note}🌐 <b>پنل وب</b>\n\nپنل وب هنوز راه‌اندازی نشده.\n"
                "با دکمه‌ی زیر راه‌اندازی کن؛ حدود یک دقیقه طول می‌کشد.")
        rows = [[B("🚀 راه‌اندازی پنل وب", "wb:setup", "success")]]
    else:
        text = (f"{note}🌐 <b>پنل وب</b>\n\n🔗 آدرس:\n<code>{h(url)}</code>\n\n"
                f"👤 نام کاربری: <code>{uid}</code>\n"
                "🔑 رمز: با «ساخت رمز جدید» ساخته می‌شود و فقط همان لحظه نشان داده می‌شود.")
        rows = [[{"text": "🌐 باز کردن پنل", "url": url}],
                [B("🔑 ساخت رمز جدید", "wb:pw", "success")],
                [B("🔄 راه‌اندازی مجدد / ثبت دوباره", "wb:setup")]]
    rows.append([B("🔙 بازگشت", "ux:m")])
    await show(ev, text, kb(rows))


async def run_setup() -> str:
    proc = await asyncio.create_subprocess_exec(
        "bash", os.path.join(APP_DIR, "webpanel_setup.sh"),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
        stdin=asyncio.subprocess.DEVNULL, cwd=APP_DIR)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=240)
    except asyncio.TimeoutError:
        proc.kill()
        return "Timeout: setup took too long."
    return _ANSI.sub("", out.decode("utf-8", "replace")).strip()


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
        if c.data == "wb:setup":
            if _SETUP_LOCK.locked():
                return await page(c, "⏳ راه‌اندازی در حال انجام است.\n\n")
            async with _SETUP_LOCK:
                await show(c, "⏳ در حال راه‌اندازی پنل وب... (حدود یک دقیقه)", kb([]))
                out = await run_setup()
            if len(out) > 1500:
                out = "…" + out[-1500:]
            ok = "Web panel is ready" in out
            head = "✅ پنل وب آماده شد." if ok else "❌ راه‌اندازی کامل نشد."
            return await page(c, f"{head}\n<pre>{h(out)}</pre>\n"
                                 "رمز را همین حالا ذخیره کن و این پیام را پاک کن.\n\n")
        await page(c)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await show(c, "❌ خطا: <code>" + h(repr(e)) + "</code>", kb([[B("🔙 بازگشت", "ux:m")]]))
