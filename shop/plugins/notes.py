from __future__ import annotations

import json
import os
import time

from aiohttp import web

from web import app as A

META = {"id": "notes", "name": "یادداشت‌ها", "icon": "📝", "version": "1.0",
        "desc": "دفترچه یادداشت ساده برای مدیر.", "menu": ("/admin/notes", "یادداشت‌ها")}
FILE = A.DATA / "shop_notes.json"


def load():
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def store(items):
    t = FILE.with_suffix(".tmp")
    t.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
    os.replace(t, FILE)


def setup(ctx):
    e = ctx.esc

    async def index(req):
        rows = "".join(
            '<div class="card c"><div style="white-space:pre-wrap">%s</div><div class="mu">%s</div>'
            '<form method="post" action="/admin/notes/del"><input type="hidden" name="id" value="%d" style="display:none">'
            '<button class="b r" style="padding:6px 14px">حذف</button></form></div>'
            % (e(n["t"]), time.strftime("%Y-%m-%d %H:%M", time.localtime(n["ts"])), int(n["id"])) for n in reversed(load()))
        form = ('<form method="post" action="/admin/notes/add"><textarea name="t" rows="3" maxlength="500" required '
                'placeholder="یادداشت جدید..."></textarea><button class="b">ذخیره</button></form>')
        return ctx.page("یادداشت‌ها", ctx.card(form) + rows)

    async def add(req):
        t = str((await req.post()).get("t", "")).strip()[:500]
        if t:
            it = load()
            it.append({"id": int(time.time() * 1000), "t": t, "ts": int(time.time())})
            store(it[-200:])
        raise web.HTTPFound("/admin/notes")

    async def delete(req):
        try:
            i = int((await req.post()).get("id", 0))
        except ValueError:
            i = 0
        store([n for n in load() if n["id"] != i])
        raise web.HTTPFound("/admin/notes")

    ctx.get("/admin/notes", index)
    ctx.post("/admin/notes/add", add)
    ctx.post("/admin/notes/del", delete)
