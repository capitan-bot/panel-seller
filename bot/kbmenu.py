from __future__ import annotations

import copy
import html
import json
import logging
import os
import tempfile
from pathlib import Path

from . import config, user
from .tg import Callback, Dispatcher, Message, Router
from .ui import WAIT, h, kb, show

log = logging.getLogger("kbmenu")
router = Router(guard=lambda ev: ev.from_user.id in config.ADMIN_IDS)
CFG = Path(__file__).resolve().parent.parent / "data" / "menu_layout.json"
DEFAULT = {"mode": "glass", "cols": 0, "order": [], "hidden": [], "map": {}}
_cache = {"mt": None, "cfg": None}


def load() -> dict:
    try:
        mt = CFG.stat().st_mtime_ns
    except OSError:
        return copy.deepcopy(DEFAULT)
    if _cache["mt"] != mt:
        try:
            d = json.loads(CFG.read_text(encoding="utf-8"))
        except Exception:
            d = {}
        c = copy.deepcopy(DEFAULT)
        for k in DEFAULT:
            if k in d:
                c[k] = d[k]
        _cache["mt"], _cache["cfg"] = mt, c
    return copy.deepcopy(_cache["cfg"])


def save(c: dict) -> None:
    CFG.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(CFG.parent), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(c, f, ensure_ascii=False)
    os.replace(tmp, CFG)
    _cache["mt"] = None


def key(b: dict) -> str:
    return b.get("callback_data") or ("url:" + str(b.get("text", "")))


def split(mk):
    rows = mk.get("inline_keyboard") if isinstance(mk, dict) else None
    if not rows:
        return None, None
    return [b for r in rows for b in r], [len(r) for r in rows]


def arrange(flat: list, c: dict, with_hidden: bool = False) -> list:
    pos = {k: i for i, k in enumerate(c["order"])}
    idx = sorted(range(len(flat)), key=lambda i: (pos.get(key(flat[i]), 10_000), i))
    items = [flat[i] for i in idx]
    if not with_hidden:
        hid = set(c["hidden"])
        items = [b for b in items if key(b) not in hid]
    return items


def rebuild(items: list, shape: list, cols: int) -> list:
    if not items:
        return []
    if cols in (1, 2):
        return [items[i:i + cols] for i in range(0, len(items), cols)]
    rows, k = [], 0
    for n in shape:
        if k >= len(items):
            break
        rows.append(items[k:k + n])
        k += n
    if k < len(items):
        rows.append(items[k:])
    return rows


_orig_main_menu = getattr(user, "main_menu")


async def main_menu(*a, **k):
    mk = await _orig_main_menu(*a, **k)
    c = load()
    flat, shape = split(mk)
    if flat is None:
        return mk
    custom = bool(c["order"] or c["hidden"] or c["cols"] in (1, 2))
    rows = rebuild(arrange(flat, c), shape, c["cols"]) if custom else mk["inline_keyboard"]
    if c["mode"] != "keyboard":
        return {**mk, "inline_keyboard": rows} if custom else mk
    krows, mp = [], {}
    for r in rows:
        kr = []
        for b in r:
            if not b.get("callback_data"):
                continue
            x = {"text": b["text"]}
            for f in ("icon_custom_emoji_id", "style"):
                if b.get(f):
                    x[f] = b[f]
            kr.append(x)
            mp[b["text"]] = b["callback_data"]
        if kr:
            krows.append(kr)
    if not krows:
        return mk
    if any(c["map"].get(t) != v for t, v in mp.items()):
        c["map"].update(mp)
        save(c)
    return {"keyboard": krows, "resize_keyboard": True, "is_persistent": True}


user.main_menu = main_menu


class _Msg(Message):
    async def edit_text(self, text, reply_markup=None):
        return await self.answer(text, reply_markup)

    async def edit_caption(self, caption, reply_markup=None):
        return await self.answer(caption, reply_markup)

    async def delete(self):
        return None


class _Cb(Callback):
    async def answer(self, text=None, show_alert=False):
        if text:
            await self.message.answer(html.escape(text))


_orig_edit = Message.edit_text


async def _edit(self, text, reply_markup=None):
    if isinstance(reply_markup, dict) and "keyboard" in reply_markup:
        try:
            await self.delete()
        except Exception:
            pass
        return await self.answer(text, reply_markup)
    return await _orig_edit(self, text, reply_markup)


Message.edit_text = _edit
_orig_feed = Dispatcher.feed


async def _feed(self, bot, upd):
    route = None
    try:
        m = upd.get("message")
        if (m and m.get("text") and not m["text"].startswith("/") and m.get("from")
                and not m["from"].get("is_bot") and m.get("chat", {}).get("type", "private") == "private"):
            c = load()
            cbd = c["map"].get(m["text"])
            if cbd:
                route = ("cb", cbd) if c["mode"] == "keyboard" and cbd not in c["hidden"] else (
                    ("stale", None) if c["mode"] != "keyboard" else None)
    except Exception:
        log.exception("kbmenu route")
    if route is None:
        return await _orig_feed(self, bot, upd)
    m = upd["message"]
    if route[0] == "stale":
        ev0 = Message(bot, m)
        if ev0.from_user is None or (self.gate and not await self.gate(ev0)):
            return
        staff = ev0.from_user.id in config.ADMIN_IDS or ev0.from_user.id in config.OPERATOR_IDS
        await bot.api("sendMessage", chat_id=ev0.chat_id, text="🔄 منو به‌روزرسانی شد.",
                      reply_markup={"remove_keyboard": True})
        return await bot.send_message(ev0.chat_id, await user.welcome(ev0.from_user), await user.main_menu(staff))
    ev = _Cb(bot, {"id": "kb", "from": m["from"], "data": route[1], "message": m})
    ev.message = _Msg(bot, m)
    if self.gate and not await self.gate(ev):
        return
    for r in self.routers:
        fn = r.find("callback", ev)
        if fn:
            return await fn(ev)


Dispatcher.feed = _feed


def B(text: str, data: str, style: str = "") -> dict:
    b = {"text": text, "callback_data": data}
    if style in ("primary", "success", "danger"):
        b["style"] = style
    return b


async def full_items():
    flat, shape = split(await _orig_main_menu(True))
    return flat or [], shape or []


async def home(ev, note: str = "") -> None:
    c = load()
    flat, _ = await full_items()
    total, hid = len(flat), len([b for b in flat if key(b) in set(c["hidden"])])
    kbm = c["mode"] == "keyboard"
    cols = {0: "خودکار", 1: "۱", 2: "۲"}.get(c["cols"], "خودکار")
    text = (f"{note}🧩 <b>سبک منو و چیدمان</b>\n\n"
            f"حالت فعلی: {'⌨️ کیبورد (پایین صفحه)' if kbm else '🪟 شیشه‌ای (زیر پیام)'}\n"
            f"ستون‌ها: {cols}\n"
            f"دکمه‌های منوی اصلی: {total} (مخفی: {hid})\n\n"
            "تغییر حالت برای همه‌ی کاربران اعمال می‌شود؛ کاربران با /start یا زدن «🏠 منوی اصلی» منوی جدید را می‌بینند.")
    await show(ev, text, kb([
        [B(("✅ " if not kbm else "") + "🪟 شیشه‌ای", "mn:g"), B(("✅ " if kbm else "") + "⌨️ کیبورد", "mn:k")],
        [B("↕️ چیدمان و مخفی کردن دکمه‌ها", "mn:l")],
        [B(f"📐 ستون‌ها: {cols}", "mn:c"), B("♻️ بازنشانی چیدمان", "mn:x", "danger")],
        [B("🔙 بازگشت", "ux:m")],
    ]))


async def layout(ev, note: str = "") -> None:
    c = load()
    flat, _ = await full_items()
    items = arrange(flat, c, True)
    hid = set(c["hidden"])
    lines, rows = [], []
    for i, b in enumerate(items):
        off = key(b) in hid
        lines.append(f"{i + 1}. {'🚫' if off else '✅'} {h(b['text'])}")
        rows.append([B("⬆️", f"mn:u:{i}"), B("⬇️", f"mn:d:{i}"),
                     B(("🚫 " if off else "👁 ") + b["text"][:14], f"mn:h:{i}")])
    rows.append([B("🔙 بازگشت", "mn:m")])
    await show(ev, f"{note}↕️ <b>چیدمان دکمه‌های منوی اصلی</b>\n"
                   "⬆️ ⬇️ جابه‌جایی؛ دکمه‌ی سوم مخفی/نمایان می‌کند (🚫 = مخفی).\n\n" + "\n".join(lines), kb(rows))


async def push_menu(c: Callback) -> None:
    uid = c.from_user.id
    if load()["mode"] != "keyboard":
        await c.bot.api("sendMessage", chat_id=uid, text="✅ منوی شیشه‌ای فعال شد.",
                        reply_markup={"remove_keyboard": True})
    await c.bot.send_message(uid, await user.welcome(c.from_user), await user.main_menu(True))


async def _cb(c: Callback) -> None:
    WAIT.pop(c.from_user.id, None)
    p = c.data.split(":")
    a = p[1] if len(p) > 1 else "m"
    cfg = load()
    if a in ("g", "k"):
        cfg["mode"] = "glass" if a == "g" else "keyboard"
        save(cfg)
        await home(c)
        return await push_menu(c)
    if a == "l":
        return await layout(c)
    if a in ("u", "d", "h"):
        flat, _ = await full_items()
        items = arrange(flat, cfg, True)
        i, note = int(p[2]), ""
        if 0 <= i < len(items):
            if a == "h":
                k, hid = key(items[i]), set(cfg["hidden"])
                if k in hid:
                    hid.discard(k)
                elif len([b for b in items if key(b) not in hid]) > 1:
                    hid.add(k)
                else:
                    note = "⚠️ حداقل یک دکمه باید نمایش داده شود.\n\n"
                cfg["hidden"] = sorted(hid)
            else:
                j = i - 1 if a == "u" else i + 1
                if 0 <= j < len(items):
                    items[i], items[j] = items[j], items[i]
            cfg["order"] = [key(b) for b in items]
            save(cfg)
        return await layout(c, note)
    if a == "c":
        cfg["cols"] = (cfg["cols"] + 1) % 3
        save(cfg)
    elif a == "x":
        cfg["order"], cfg["hidden"], cfg["cols"] = [], [], 0
        save(cfg)
    await home(c)


@router.callback("mn:")
async def mncb(c: Callback):
    try:
        await _cb(c)
    except Exception as e:
        import traceback
        traceback.print_exc()
        await show(c, "❌ خطا: <code>" + h(repr(e)) + "</code>", kb([[B("🔙 بازگشت", "ux:m")]]))
