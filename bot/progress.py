"""Live progress bar shown while a panel is being created (edits one message)."""
from __future__ import annotations

import asyncio
import logging

from .tg import TgError

log = logging.getLogger(__name__)
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
LABELS = ["بررسی پرداخت", "ساخت پنل در پاسارگارد", "تنظیم حجم و دسترسی‌ها", "ثبت سفارش", "آماده‌سازی نهایی"]


def bar(pc: int, width: int = 10) -> str:
    n = round(pc * width / 100)
    return "▰" * n + "▱" * (width - n)


class Progress:
    """async with Progress(c.message): ... real work ...  -> bar moves while the work runs, hits 100% when done."""

    def __init__(self, msg, title: str = "در حال ساخت پنل", labels=None, interval: float = 1.0):
        self.msg, self.title, self.labels, self.interval = msg, title, labels or LABELS, interval
        self.pc, self._last, self._task, self._dead = 0, None, None, False

    def _text(self, done: bool = False) -> str:
        if done:
            head, line = "✅ <b>پنل ساخته شد</b>", ""
        else:
            head = f"⏳ <b>{self.title}</b>"
            line = self.labels[min(len(self.labels) - 1, self.pc // 20)] + "...\n"
        pct = f"{self.pc}٪".translate(_FA)
        return f"{head}\n\n<blockquote>{line}{bar(self.pc)}  <b>{pct}</b></blockquote>"

    async def _edit(self, done: bool = False) -> None:
        if self._dead:
            return
        t = self._text(done)
        if t == self._last:
            return
        self._last = t
        try:
            await self.msg.edit_text(t)
        except TgError as e:
            if "not modified" not in str(e):
                self._dead = True          # rate limit / message gone: stop animating, never break the purchase
                log.info("progress stopped: %s", e)

    async def _run(self) -> None:
        while self.pc < 90:
            await self._edit()
            await asyncio.sleep(self.interval)
            self.pc = min(90, self.pc + max(4, (90 - self.pc) // 4))

    async def __aenter__(self):
        self._task = asyncio.create_task(self._run())
        return self

    async def __aexit__(self, exc_type, exc, tb):
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        if exc_type is None:
            self.pc = 100
            await self._edit(done=True)
            await asyncio.sleep(0.6)
        else:
            try:
                from .ui import btn, kb
                await self.msg.edit_text("⚠️ ساخت پنل ناموفق بود.", kb([[btn("🏠 منوی اصلی", "u:home")]]))
            except Exception:
                pass
        return False
