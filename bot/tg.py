"""Minimal Telegram Bot API client + router (httpx only). Replaces aiogram to keep RAM low."""
from __future__ import annotations

import asyncio
import logging

import httpx

log = logging.getLogger("tg")
EMPTY_KB = {"inline_keyboard": []}


class TgError(Exception):
    def __init__(self, desc: str, code: int = 0):
        super().__init__(desc)
        self.code = code


class User:
    def __init__(self, d: dict):
        self.id = d["id"]
        self.is_bot = bool(d.get("is_bot"))
        self.username = d.get("username") or ""
        self.full_name = " ".join(x for x in (d.get("first_name"), d.get("last_name")) if x) or str(self.id)


class Bot:
    def __init__(self, token: str, transport=None):
        self.http = httpx.AsyncClient(base_url=f"https://api.telegram.org/bot{token}/",
                                      timeout=httpx.Timeout(70.0, connect=10.0), transport=transport)

    async def api(self, method: str, **params):
        try:
            from .premtext import premium_params
            premium_params(method, params)
        except Exception:
            pass
        params = {k: v for k, v in params.items() if v is not None}
        try:
            r = await self.http.post(method, json=params)
        except httpx.HTTPError as e:
            raise TgError(f"network: {type(e).__name__}")
        try:
            j = r.json()
        except ValueError:
            raise TgError(f"bad response HTTP {r.status_code}", r.status_code)
        if not j.get("ok"):
            raise TgError(j.get("description", "error"), j.get("error_code", 0))
        return j["result"]

    async def send_message(self, chat_id: int, text: str, reply_markup=None, effect: str | None = None):
        kw = dict(chat_id=chat_id, text=text, parse_mode="HTML", reply_markup=reply_markup,
                  link_preview_options={"is_disabled": True})
        if effect:
            try:
                return await self.api("sendMessage", message_effect_id=effect, **kw)
            except TgError as e:
                log.warning("effect failed, sending plain: %s", e)
        return await self.api("sendMessage", **kw)

    async def edit_message(self, chat_id: int, message_id: int, text: str, reply_markup=None):
        return await self.api("editMessageText", chat_id=chat_id, message_id=message_id, text=text, parse_mode="HTML",
                              reply_markup=reply_markup or EMPTY_KB, link_preview_options={"is_disabled": True})

    async def send_photo(self, chat_id: int, photo: str, caption: str | None = None, reply_markup=None):
        return await self.api("sendPhoto", chat_id=chat_id, photo=photo, caption=caption, parse_mode="HTML",
                              reply_markup=reply_markup)

    async def send_document(self, chat_id: int, filename: str, data: bytes, caption: str | None = None,
                            thread_id: int | None = None):
        form = {"chat_id": str(chat_id), "parse_mode": "HTML"}
        if caption:
            form["caption"] = caption
        if thread_id:
            form["message_thread_id"] = str(thread_id)
        try:
            r = await self.http.post("sendDocument", data=form, files={"document": (filename, data, "application/gzip")},
                                     timeout=httpx.Timeout(120.0, connect=10.0))
        except httpx.HTTPError as e:
            raise TgError(f"network: {type(e).__name__}")
        try:
            j = r.json()
        except ValueError:
            raise TgError(f"bad response HTTP {r.status_code}", r.status_code)
        if not j.get("ok"):
            raise TgError(j.get("description", "error"), j.get("error_code", 0))
        return j["result"]

    async def close(self):
        await self.http.aclose()


class Message:
    def __init__(self, bot: Bot, d: dict):
        self.bot = bot
        self.message_id = d["message_id"]
        self.chat_id = d["chat"]["id"]
        self.from_user = User(d["from"]) if d.get("from") else None
        self.text = d.get("text")
        self.caption = d.get("caption")
        self.photo = d.get("photo") or []
        self.entities = d.get("entities") or []

    async def answer(self, text: str, reply_markup=None, effect: str | None = None):
        return await self.bot.send_message(self.chat_id, text, reply_markup, effect)

    async def edit_text(self, text: str, reply_markup=None):
        return await self.bot.api("editMessageText", chat_id=self.chat_id, message_id=self.message_id, text=text,
                                  parse_mode="HTML", reply_markup=reply_markup or EMPTY_KB,
                                  link_preview_options={"is_disabled": True})

    async def edit_caption(self, caption: str, reply_markup=None):
        return await self.bot.api("editMessageCaption", chat_id=self.chat_id, message_id=self.message_id,
                                  caption=caption, parse_mode="HTML", reply_markup=reply_markup or EMPTY_KB)

    async def delete(self):
        return await self.bot.api("deleteMessage", chat_id=self.chat_id, message_id=self.message_id)


class Callback:
    def __init__(self, bot: Bot, d: dict):
        self.bot = bot
        self.id = d["id"]
        self.from_user = User(d["from"])
        self.data = d.get("data") or ""
        self.message = Message(bot, d["message"]) if d.get("message") else None

    async def answer(self, text: str | None = None, show_alert: bool = False):
        await self.bot.api("answerCallbackQuery", callback_query_id=self.id, text=text, show_alert=show_alert or None)


class Router:
    def __init__(self, guard=None):
        self.guard = guard
        self.cmds, self.msgs, self.cbs = [], [], []

    def command(self, name: str):
        def deco(fn):
            self.cmds.append((name, fn)); return fn
        return deco

    def message(self, pred):
        def deco(fn):
            self.msgs.append((pred, fn)); return fn
        return deco

    def callback(self, prefix: str):
        def deco(fn):
            self.cbs.append((prefix, fn)); return fn
        return deco

    def find(self, kind: str, ev):
        if self.guard and not self.guard(ev):
            return None
        if kind == "message":
            t = ev.text or ""
            if t.startswith("/"):
                cmd = t.split()[0][1:].split("@")[0].lower()
                for n, fn in self.cmds:
                    if n == cmd:
                        return fn
            for pred, fn in self.msgs:
                if pred(ev):
                    return fn
        else:
            for pre, fn in self.cbs:
                if ev.data.startswith(pre):
                    return fn
        return None


class Dispatcher:
    def __init__(self, gate=None):
        self.routers: list[Router] = []
        self.gate = gate
        self._tasks: set = set()

    def include(self, r: Router):
        self.routers.append(r)

    async def feed(self, bot: Bot, upd: dict):
        if "message" in upd:
            kind, ev = "message", Message(bot, upd["message"])
        elif "callback_query" in upd:
            kind, ev = "callback", Callback(bot, upd["callback_query"])
        else:
            return
        if ev.from_user is None or ev.from_user.is_bot:
            return
        if self.gate and not await self.gate(ev):
            return
        for r in self.routers:
            fn = r.find(kind, ev)
            if fn:
                return await fn(ev)
        if kind == "callback":
            try:
                await ev.answer()
            except TgError:
                pass

    async def _safe(self, bot: Bot, upd: dict):
        try:
            await self.feed(bot, upd)
        except Exception:
            log.exception("update failed")
            cq = upd.get("callback_query")
            if cq:
                try:
                    await bot.api("answerCallbackQuery", callback_query_id=cq["id"], text="خطایی رخ داد؛ دوباره امتحان کن.")
                except TgError:
                    pass

    async def poll(self, bot: Bot):
        offset = 0
        while True:
            try:
                ups = await bot.api("getUpdates", offset=offset, timeout=50, allowed_updates=["message", "callback_query"])
            except TgError as e:
                log.warning("getUpdates: %s", e)
                await asyncio.sleep(5)
                continue
            for u in ups:
                offset = u["update_id"] + 1
                t = asyncio.create_task(self._safe(bot, u))
                self._tasks.add(t)
                t.add_done_callback(self._tasks.discard)
