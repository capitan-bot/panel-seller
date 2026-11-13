"""Report group with forum topics. Set up from inside the bot: /admin -> 📣 گزارش (or /setreport inside the group)."""
from __future__ import annotations

import asyncio
import logging
import os
from html import escape as h

from . import config, db  # noqa: F401  (config loads .env)
from .tg import TgError

log = logging.getLogger("report")
ENV_CHAT = int(os.getenv("REPORT_CHAT_ID", "0") or 0)   # optional default from .env
CHAT_ID = ENV_CHAT                                      # kept for old imports; use chat_id() for the live value

TOPICS = {
    "test": ("🧪 تست", 9367192),
    "buy": ("🛒 خرید", 16766590),
    "volume": ("➕ حجم اضافه", 7322096),
    "wallet": ("💰 کیف پول", 13338331),
    "join": ("👤 ورود کاربر", 16749490),
    "admin": ("🛠 اقدامات ادمین", 16478047),
    "manage": ("⚙️ مدیریت پنل", 7322096),
    "error": ("🚨 خطا", 16478047),
    "backup": ("💾 بکاپ", 13338331),
}
_EV = {
    "delete": ("admin", "🗑 حذف پنل"), "block": ("admin", "⛔️ تغییر وضعیت مسدودی کاربر"),
    "balance": ("admin", "💰 تغییر موجودی توسط ادمین"), "admin_gb": ("admin", "📊 تغییر حجم پنل"),
    "pw": ("manage", "🔑 تغییر رمز پنل"), "uname": ("manage", "✏️ تغییر نام‌کاربری پنل"),
    "transfer": ("manage", "🔁 انتقال پنل"),
    "code": ("buy", "🎟 استفاده از کد تخفیف"), "giftcode": ("wallet", "🎁 استفاده از کد هدیه"),
}
_bot = None
_lock = asyncio.Lock()
_tasks: set = set()


def init(bot) -> None:
    global _bot
    _bot = bot


def _spawn(coro) -> None:
    t = asyncio.get_running_loop().create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


async def chat_id() -> int:
    """The report group: saved by the setup wizard, else REPORT_CHAT_ID from .env, else 0 (not connected)."""
    v = (await db.get_setting("report_chat")).strip()
    if v == "0":
        return 0                      # disconnected on purpose
    if v.lstrip("-").isdigit():
        return int(v)
    return ENV_CHAT


async def _thread(kind: str, force: bool = False) -> int:
    key = f"rt_{kind}"
    async with _lock:
        cid = await chat_id()
        v = await db.get_setting(key)
        rc = await db.get_setting("rt_chat")
        if v.isdigit() and not force and rc in ("", str(cid)):
            if not rc:
                await db.set_setting("rt_chat", str(cid))
            return int(v)
        r = await _bot.api("createForumTopic", chat_id=cid, name=TOPICS[kind][0], icon_color=TOPICS[kind][1])
        await db.set_setting(key, str(r["message_thread_id"]))
        await db.set_setting("rt_chat", str(cid))
        return r["message_thread_id"]


async def send(kind: str, text: str) -> bool:
    cid = await chat_id()
    if not (_bot and cid and kind in TOPICS):
        return False
    try:
        for attempt in (0, 1):
            tid = await _thread(kind, force=bool(attempt))
            try:
                await _bot.api("sendMessage", chat_id=cid, message_thread_id=tid, text=text, parse_mode="HTML",
                               link_preview_options={"is_disabled": True})
                return True
            except TgError as e:
                if attempt or "thread" not in str(e).lower():
                    raise
    except Exception as e:
        log.warning("report %s failed: %s", kind, e)
    return False


async def send_file(kind: str, filename: str, data: bytes, caption: str) -> bool:
    """Sends a file into the topic of `kind`. False when no report group is set or sending failed."""
    cid = await chat_id()
    if not (_bot and cid and kind in TOPICS):
        return False
    try:
        for attempt in (0, 1):
            tid = await _thread(kind, force=bool(attempt))
            try:
                await _bot.send_document(cid, filename, data, caption, tid)
                return True
            except TgError as e:
                if attempt or "thread" not in str(e).lower():
                    raise
    except Exception as e:
        log.warning("report file %s failed: %s", kind, e)
    return False


async def ensure_topics(bot):
    """Creates the topics that do not exist yet. -> (created names, failed names)."""
    init(bot)
    created, failed = [], []
    for kind, (name, _c) in TOPICS.items():
        before = await db.get_setting(f"rt_{kind}")
        try:
            await _thread(kind)
        except Exception as e:
            log.warning("topic %s: %s", kind, e)
            failed.append(name)
            continue
        if await db.get_setting(f"rt_{kind}") != before:
            created.append(name)
            await send(kind, f"✅ تاپیک «{h(name)}» فعال شد؛ گزارش‌های این بخش اینجا می‌آید.")
    return created, failed


async def test_all(bot) -> int:
    init(bot)
    n = 0
    for kind in TOPICS:
        if await send(kind, "🧪 تست ارسال — اگر این پیام را می‌بینی، گزارش این تاپیک کار می‌کند."):
            n += 1
    return n


async def setup_chat(bot, cid: int):
    """Validates the group, saves it and creates the topics. -> (ok, text)."""
    init(bot)
    if cid >= 0:
        return False, "این باید ID یک گروه باشد (عددی که با -100 شروع می‌شود)."
    try:
        chat = await bot.api("getChat", chat_id=cid)
    except TgError as e:
        return False, f"❌ ربات به این گروه دسترسی ندارد ({h(str(e))}).\nربات را به گروه اضافه و ادمین کن."
    if chat.get("type") != "supergroup":
        return False, "❌ گروه باید «سوپرگروه» باشد. در تنظیمات گروه، گزینه‌ی Topics را روشن کن تا خودکار سوپرگروه شود."
    if not chat.get("is_forum"):
        return False, "❌ قابلیت «Topics» در این گروه روشن نیست. تنظیمات گروه ← Topics را روشن کن."
    try:
        me = await bot.api("getMe")
        mem = await bot.api("getChatMember", chat_id=cid, user_id=me["id"])
    except TgError as e:
        return False, f"❌ بررسی دسترسی ربات ممکن نشد: {h(str(e))}"
    if mem.get("status") == "administrator":
        if not mem.get("can_manage_topics"):
            return False, "❌ ربات ادمین است ولی دسترسی «Manage Topics» (مدیریت تاپیک‌ها) را ندارد. آن را به ربات بده."
    elif mem.get("status") != "creator":
        return False, "❌ ربات باید در گروه «ادمین» باشد (با دسترسی Manage Topics)."
    old = await chat_id()
    await db.set_setting("report_chat", str(cid))
    if old != cid:                    # another group: the old topic ids are meaningless
        for k in TOPICS:
            await db.set_setting(f"rt_{k}", "")
        await db.set_setting("rt_chat", str(cid))
    created, failed = await ensure_topics(bot)
    t = f"✅ گروه «{h(chat.get('title', ''))}» به‌عنوان گروه گزارش متصل شد.\n🗂 {len(created)} تاپیک ساخته شد."
    if failed:
        t += "\n⚠️ ساخته نشد: " + "، ".join(failed)
    return True, t


async def who(uid: int) -> str:
    r = await db.row("SELECT name, username FROM users WHERE tg_id=?", uid)
    if not r:
        return f"<code>{uid}</code>"
    un = f" @{h(r['username'])}" if r["username"] else ""
    return f'<a href="tg://user?id={uid}">{h(str(r["name"] or uid))}</a>{un} | <code>{uid}</code>'


async def _sale(uid, panel, kind, gb, price):
    k = {"panel": "buy", "volume": "volume", "gift": "admin"}.get(kind, "buy")
    t = {"panel": "🛒 خرید پنل جدید", "volume": "➕ خرید حجم اضافه", "gift": "🎁 هدیه حجم (ادمین)"}.get(kind, kind)
    await send(k, f"{t}\n\n👤 {await who(uid)}\n📦 پنل: <code>{h(str(panel))}</code>\n"
                  f"💎 حجم: {gb:g} گیگ\n💵 مبلغ: {price:,} تومان")


async def _ev(kind, uid, arg):
    k, t = _EV[kind]
    await send(k, f"{t}\n\n👤 {await who(uid)}" + (f"\n📝 <code>{h(str(arg))}</code>" if arg else ""))


async def _test(uid, name, gb):
    await send("test", f"🧪 پنل تست ساخته شد\n\n👤 {await who(uid)}\n📦 <code>{h(name)}</code>\n💎 حجم: {gb:g} گیگ")


async def _join(u):
    un = f" @{h(u.username)}" if u.username else ""
    await send("join", f"👤 کاربر جدید\n\n<a href=\"tg://user?id={u.id}\">{h(u.full_name)}</a>{un} | <code>{u.id}</code>")


def on_sale(uid, panel, kind, gb, price): _spawn(_sale(uid, panel, kind, gb, price))


def on_event(kind, uid, arg=""):
    if kind in _EV:
        _spawn(_ev(kind, uid, arg))


def on_test(uid, name, gb): _spawn(_test(uid, name, gb))
def on_new_user(u): _spawn(_join(u))
def on_error(text): _spawn(send("error", text))
