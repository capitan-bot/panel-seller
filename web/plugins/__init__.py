from __future__ import annotations

import html
import importlib
import json
import logging
import os
import pkgutil

from aiohttp import web

from web import app as A

log = logging.getLogger("web.plugins")
REG: dict = {}
FAILED: dict = {}
STATE = A.DATA / "plugins.json"
CARD = "background:#131318;border:1px solid #23232b;border-radius:18px;padding:18px"


def esc(s):
    return html.escape(str(s))


def enabled() -> set:
    try:
        return set(json.loads(STATE.read_text(encoding="utf-8")).get("enabled", []))
    except (OSError, ValueError):
        return set()


def save(ids) -> None:
    A.DATA.mkdir(exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps({"enabled": sorted(ids)}), encoding="utf-8")
    os.replace(tmp, STATE)


def render(active, title, body):
    from web import pages
    r = pages.page(active, title, body)
    if isinstance(r, str):
        r = web.Response(text=r, content_type="text/html")
    return r


def sync_nav() -> None:
    """Menu = core pages + the plugins that are switched on right now."""
    try:
        from web import pages
    except Exception:
        log.exception("cannot sync nav")
        return
    nav, on = pages.NAV, enabled()
    nav[:] = [n for n in nav if not str(n[0]).startswith("pl_") and n[0] != "plugins"]
    for pid, m in sorted(REG.items()):
        menu = m.META.get("menu")
        if pid in on and menu:
            nav.append(("pl_" + pid, menu[0], menu[1], m.META.get("icon", "🧩")))
    nav.append(("plugins", "/plugins", "افزونه‌ها", "🧩"))


class Ctx:
    """What a plugin gets: routes that answer 404 while the plugin is off."""

    def __init__(self, app, pid):
        self.app, self.pid = app, pid

    def _wrap(self, fn):
        pid = self.pid

        async def h(req):
            if pid not in enabled():
                raise web.HTTPNotFound()
            return await fn(req)
        return h

    def get(self, path, fn):
        self.app.router.add_get(path, self._wrap(fn))

    def post(self, path, fn):
        self.app.router.add_post(path, self._wrap(fn))

    def page(self, title, body):
        return render("pl_" + self.pid, title, body)


def btn(color):
    return ("width:100%;margin-top:12px;padding:10px;border:0;border-radius:12px;background:" + color +
            ";color:#fff;font-family:inherit;font-size:14px;cursor:pointer")


async def manager(req):
    on, cards = enabled(), ""
    for pid, m in sorted(REG.items()):
        M, live = m.META, pid in on
        cards += ('<div style="' + CARD + '"><div style="font-size:28px">' + esc(M.get("icon", "🧩")) + "</div>"
                  '<h3 style="margin:8px 0 4px">' + esc(M.get("name", pid)) + "</h3>"
                  '<div style="opacity:.7;font-size:13px;min-height:36px">' + esc(M.get("desc", "")) + "</div>"
                  '<div style="opacity:.55;font-size:12px;margin-top:6px">نسخه ' + esc(M.get("version", "1.0")) +
                  " · " + ("فعال ✅" if live else "غیرفعال") + "</div>"
                  '<form method="post" action="/plugins/toggle"><input type="hidden" name="id" value="' + esc(pid) + '">'
                  '<button style="' + btn("#7f1d1d" if live else "#6d4df0") + '">' +
                  ("غیرفعال کردن" if live else "فعال کردن") + "</button></form></div>")
    bad = "".join("<div>⚠️ <b>" + esc(k) + "</b>: " + esc(v) + "</div>" for k, v in FAILED.items())
    if bad:
        bad = '<div style="' + CARD + ';border-color:#7f1d1d;margin-bottom:14px;direction:ltr;font-size:13px">' + bad + "</div>"
    body = (bad + '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px">' +
            (cards or '<div style="' + CARD + '">افزونه‌ای در web/plugins پیدا نشد.</div>') + "</div>")
    return render("plugins", "افزونه‌ها", body)


async def toggle(req):
    f = await req.post()
    pid = str(f.get("id", ""))
    if pid in REG:
        s = enabled()
        s.symmetric_difference_update({pid})
        save(s)
        sync_nav()
    raise web.HTTPFound("/plugins")


def install(app) -> None:
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        try:
            m = importlib.import_module("%s.%s" % (__name__, mod.name))
            pid = m.META["id"]
            m.setup(Ctx(app, pid))
            REG[pid] = m
        except Exception as e:
            FAILED[mod.name] = "%s: %s" % (type(e).__name__, e)
            log.exception("plugin %s failed to load", mod.name)
    app.router.add_get("/plugins", manager)
    app.router.add_post("/plugins/toggle", toggle)
    sync_nav()
