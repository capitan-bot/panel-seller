from __future__ import annotations

import json
import os
import time
from datetime import datetime

from aiohttp import web

from web import app as A

from . import CARD, btn, esc

META = {"id": "notes", "name": "یادداشت‌ها", "icon": "📝", "version": "1.0",
        "desc": "دفترچه یادداشت ساده برای مدیر؛ نمونه‌ای از ساخت افزونه.", "menu": ("/notes", "یادداشت‌ها")}
FILE = A.DATA / "notes.json"


def load() -> list:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def store(items: list) -> None:
    A.DATA.mkdir(exist_ok=True)
    tmp = FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, FILE)


def setup(ctx):
    async def index(req):
        rows = ""
        for n in reversed(load()):
            when = datetime.fromtimestamp(n["ts"], A.TZI).strftime("%Y-%m-%d %H:%M")
            rows += ('<div style="' + CARD + ';margin-top:12px"><div style="white-space:pre-wrap">' + esc(n["t"]) + "</div>"
                     '<div style="opacity:.55;font-size:12px;margin-top:8px">' + when + "</div>"
                     '<form method="post" action="/notes/del"><input type="hidden" name="id" value="' + str(int(n["id"])) + '">'
                     '<button style="' + btn("#7f1d1d") + ';width:auto;padding:6px 14px">حذف</button></form></div>')
        form = ('<form method="post" action="/notes/add" style="' + CARD + '">'
                '<textarea name="t" rows="3" maxlength="500" required placeholder="یادداشت جدید..." '
                'style="width:100%;box-sizing:border-box;padding:12px;border-radius:12px;border:1px solid #2c2c36;'
                'background:#0f0f14;color:#fff;font-family:inherit"></textarea>'
                '<button style="' + btn("#6d4df0") + '">ذخیره</button></form>')
        return ctx.page("یادداشت‌ها", form + rows)

    async def add(req):
        t = str((await req.post()).get("t", "")).strip()[:500]
        if t:
            items = load()
            items.append({"id": int(time.time() * 1000), "t": t, "ts": int(time.time())})
            store(items[-200:])
        raise web.HTTPFound("/notes")

    async def delete(req):
        try:
            nid = int((await req.post()).get("id", 0))
        except ValueError:
            nid = 0
        store([n for n in load() if n["id"] != nid])
        raise web.HTTPFound("/notes")

    ctx.get("/notes", index)
    ctx.post("/notes/add", add)
    ctx.post("/notes/del", delete)
