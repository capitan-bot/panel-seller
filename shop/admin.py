from __future__ import annotations

import asyncio
import importlib
import io
import json
import logging
import os
import pkgutil
import re
import time
import zipfile

from aiohttp import web

from web import app as A

from . import auth, theme
from .theme import esc

log = logging.getLogger("shop.admin")
SET = A.DATA / "admin_settings.json"
PLG = A.DATA / "shop_plugins.json"
REG, FAILED = {}, {}
SLUG = re.compile(r"^[a-z0-9-]{1,40}$")
CORE = [("dash", "/admin", "🏠", "داشبورد"), ("site", "/admin/site", "✏️", "ویرایش سایت"),
        ("pages", "/admin/pages", "📄", "صفحه‌ها"), ("plugins", "/admin/plugins", "🧩", "افزونه‌ها"),
        ("support", "/support/admin", "🎧", "پشتیبانی"),
        ("settings", "/admin/settings", "⚙️", "تنظیمات"), ("backup", "/admin/backup", "💾", "بکاپ")]
CSS = ("<style>.adm{display:grid;grid-template-columns:210px 1fr;gap:16px;align-items:start}"
       ".am{display:flex;flex-direction:column;gap:4px;position:sticky;top:70px;padding:10px;background:var(--card);"
       "border:1px solid var(--bd);border-radius:18px}.am a{padding:10px 12px;border-radius:12px;color:var(--mu);font-size:14px}"
       ".am a.on{background:#251f4a;color:#fff}"
       "@media(max-width:800px){.adm{grid-template-columns:1fr}.am{flex-direction:row;overflow-x:auto;position:static}"
       ".am a{white-space:nowrap}}"
       ".adm input,.adm textarea{direction:rtl;text-align:right;font-size:15px;letter-spacing:0;padding:11px;border-radius:12px;"
       "border:1px solid #2c2c36;background:#0d0d13;color:#fff;font-family:inherit;width:100%}"
       ".adm label{display:block;margin:12px 0 6px;color:var(--mu);font-size:13px}"
       ".adm .b{display:inline-block;padding:9px 16px;border:0;border-radius:12px;background:#6d4df0;color:#fff;"
       "font-family:inherit;cursor:pointer;margin-top:12px}.adm .b.r{background:#7f1d1d}.adm .c{margin-top:14px}</style>")


def rj(p, d):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return d


def wj(p, v):
    A.DATA.mkdir(exist_ok=True)
    t = p.with_suffix(".tmp")
    t.write_text(json.dumps(v, ensure_ascii=False), encoding="utf-8")
    os.replace(t, p)


def cfg():
    c = rj(SET, {})
    return c if isinstance(c, dict) else {}


def on():
    v = rj(PLG, [])
    return set(v) if isinstance(v, list) else set()


def need(req, post=False):
    uid = req.get("uid")
    if uid is None or uid not in A.admin_ids():
        raise web.HTTPFound("/")
    if post:
        auth.same_origin(req)
    return uid


def layout(active, title, body):
    act = on()
    items = list(CORE)
    for pid, m in sorted(REG.items()):
        mn = m.META.get("menu")
        if pid in act and mn:
            items.append(("pl_" + pid, mn[0], m.META.get("icon", "🧩"), mn[1]))
    nav = "".join('<a class="%s" href="%s">%s %s</a>' % ("on" if k == active else "", u, i, esc(t)) for k, u, i, t in items)
    return theme.shell(title, '<div class="adm"><nav class="am">' + nav + "</nav><div>" + body + "</div></div>" + CSS, "home")


def card(inner):
    return '<div class="card c">' + inner + "</div>"


def go(url):
    raise web.HTTPFound(url)


async def dash(req):
    need(req)
    s = cfg()
    cells = [("/admin/site", "✏️", "ویرایش سایت", "متن‌ها و تصویر صفحه‌ی اصلی"),
             ("/admin/pages", "📄", "صفحه‌ها", "%d صفحه" % len(s.get("pages", {}))),
             ("/admin/plugins", "🧩", "افزونه‌ها", "%d فعال از %d" % (len(on() & set(REG)), len(REG))),
             ("/support/admin", "🎧", "پشتیبانی", "گفتگوهای کاربران و تنظیمات هوش مصنوعی"),
             ("/admin/settings", "⚙️", "تنظیمات", "عنوان سایت و اطلاعیه"),
             ("/admin/backup", "💾", "بکاپ", "دانلود zip")]
    body = '<div class="grid">' + "".join(
        '<a class="card rv" href="%s"><div style="font-size:28px">%s</div><h3 style="margin:8px 0 4px">%s</h3>'
        '<div class="mu">%s</div></a>' % (u, i, t, d) for u, i, t, d in cells) + "</div>"
    return layout("dash", "مدیریت", body)


async def settings(req):
    need(req)
    s = cfg()
    f = ('<form method="post" action="/admin/settings"><label>عنوان سایت (خالی = پیش‌فرض)</label>'
         '<input name="title" maxlength="60" value="%s"><label>اطلاعیه (بنر بالای صفحه‌ها؛ خالی = بدون بنر)</label>'
         '<textarea name="banner" rows="3" maxlength="300">%s</textarea><button class="b">ذخیره</button></form>'
         % (esc(s.get("title", "")), esc(s.get("banner", ""))))
    ok = '<div class="card c" style="color:var(--up)">ذخیره شد ✓</div>' if req.query.get("ok") else ""
    return layout("settings", "تنظیمات", ok + card(f))


async def settings_post(req):
    need(req, True)
    d = await req.post()
    s = cfg()
    s["title"] = str(d.get("title", "")).strip()[:60]
    s["banner"] = str(d.get("banner", "")).strip()[:300]
    await asyncio.to_thread(wj, SET, s)
    apply_title()
    go("/admin/settings?ok=1")


async def pages_list(req):
    need(req)
    ps = cfg().get("pages", {})
    e = str(req.query.get("e", ""))
    cur = ps.get(e, {"t": "", "b": ""})
    rows = "".join(
        '<div class="tx"><span>%s <small>/p/%s</small></span><span><a class="b" style="margin:0;padding:6px 12px" href="/admin/pages?e=%s">ویرایش</a> '
        '<form method="post" action="/admin/pages/del" style="display:inline"><input type="hidden" name="slug" value="%s" style="display:none">'
        '<button class="b r" style="margin:0;padding:6px 12px">حذف</button></form></span></div>'
        % (esc(v["t"]), esc(k), esc(k), esc(k)) for k, v in sorted(ps.items()))
    f = ('<form method="post" action="/admin/pages/save"><label>نشانی (فقط حروف انگلیسی کوچک، عدد و -) مثل rules</label>'
         '<input name="slug" value="%s" dir="ltr" required><label>عنوان</label><input name="t" value="%s" required>'
         '<label>متن</label><textarea name="b" rows="8" maxlength="8000">%s</textarea><button class="b">ذخیره</button></form>'
         % (esc(e), esc(cur["t"]), esc(cur["b"])))
    return layout("pages", "صفحه‌های ثابت", card(f) + card(rows or '<div class="mu">هنوز صفحه‌ای نیست؛ مثلاً قوانین یا تماس.</div>'))


async def pages_save(req):
    need(req, True)
    d = await req.post()
    slug = str(d.get("slug", "")).strip().lower()
    if not SLUG.match(slug):
        go("/admin/pages")
    s = cfg()
    s.setdefault("pages", {})[slug] = {"t": str(d.get("t", "")).strip()[:100], "b": str(d.get("b", ""))[:8000]}
    await asyncio.to_thread(wj, SET, s)
    go("/admin/pages")


async def pages_del(req):
    need(req, True)
    d = await req.post()
    s = cfg()
    s.get("pages", {}).pop(str(d.get("slug", "")), None)
    await asyncio.to_thread(wj, SET, s)
    go("/admin/pages")


async def page_view(req):
    p = cfg().get("pages", {}).get(req.match_info["slug"])
    if not p:
        raise web.HTTPNotFound()
    return theme.shell(p["t"], '<div class="card" style="white-space:pre-wrap;line-height:2">' + esc(p["b"]) + "</div>", "home")


async def plugins_page(req):
    need(req)
    act, cards = on(), ""
    for pid, m in sorted(REG.items()):
        M, live = m.META, pid in act
        cards += ('<div class="card rv"><div style="font-size:28px">%s</div><h3 style="margin:8px 0 4px">%s</h3>'
                  '<div class="mu">%s</div><div class="mu">نسخه %s · %s</div>'
                  '<form method="post" action="/admin/plugins/toggle"><input type="hidden" name="id" value="%s" style="display:none">'
                  '<button class="b%s">%s</button></form></div>'
                  % (esc(M.get("icon", "🧩")), esc(M.get("name", pid)), esc(M.get("desc", "")), esc(M.get("version", "1.0")),
                     "فعال ✅" if live else "غیرفعال", esc(pid), " r" if live else "", "غیرفعال کردن" if live else "فعال کردن"))
    bad = "".join("<div>⚠️ %s: %s</div>" % (esc(k), esc(v)) for k, v in FAILED.items())
    body = (card('<div style="direction:ltr;font-size:13px;color:var(--dn)">' + bad + "</div>") if bad else "") + \
        '<div class="grid c">' + (cards or '<div class="card">افزونه‌ای در shop/plugins نیست.</div>') + "</div>"
    return layout("plugins", "افزونه‌ها", body)


async def plugins_toggle(req):
    need(req, True)
    pid = str((await req.post()).get("id", ""))
    if pid in REG:
        s = on()
        s.symmetric_difference_update({pid})
        await asyncio.to_thread(wj, PLG, sorted(s))
    go("/admin/plugins")


def mkzip():
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for n in ["site.json", "admin_settings.json"] + [p.name for p in A.DATA.glob("shop_*.json")]:
            p = A.DATA / n
            if p.is_file():
                z.write(p, n)
        sd = A.DATA / "site"
        for f in sd.rglob("*") if sd.exists() else []:
            if f.is_file():
                z.write(f, "site/" + f.relative_to(sd).as_posix())
    return b.getvalue()


async def backup_page(req):
    need(req)
    f = ('<div class="mu" style="margin-bottom:8px">شامل تنظیمات سایت، تصویر بالای صفحه، صفحه‌ها و داده‌ی افزونه‌ها. '
         "دیتابیس و کلیدها داخلش نیست.</div>"
         '<form method="post" action="/admin/backup/dl"><button class="b">دانلود بکاپ (zip)</button></form>')
    return layout("backup", "بکاپ", card(f))


async def backup_dl(req):
    need(req, True)
    data = await asyncio.to_thread(mkzip)
    return web.Response(body=data, headers={"Content-Type": "application/zip", "Content-Disposition":
                        'attachment; filename="shop-backup-%s.zip"' % time.strftime("%Y%m%d-%H%M")})


class Ctx:
    def __init__(self, app, pid):
        self.app, self.pid, self.esc = app, pid, esc

    def _w(self, fn, post):
        pid = self.pid

        async def h(req):
            need(req, post)
            if pid not in on():
                raise web.HTTPNotFound()
            return await fn(req)
        return h

    def get(self, path, fn):
        self.app.router.add_get(path, self._w(fn, False))

    def post(self, path, fn):
        self.app.router.add_post(path, self._w(fn, True))

    def page(self, title, body):
        return layout("pl_" + self.pid, title, body)

    card = staticmethod(card)


def load_plugins(app):
    pkg = __package__ + ".plugins"
    try:
        base = importlib.import_module(pkg)
    except Exception:
        log.exception("plugins package")
        return
    for m in pkgutil.iter_modules(base.__path__):
        if m.name.startswith("_"):
            continue
        try:
            x = importlib.import_module(pkg + "." + m.name)
            x.setup(Ctx(app, x.META["id"]))
            REG[x.META["id"]] = x
        except Exception as e:
            FAILED[m.name] = "%s: %s" % (type(e).__name__, e)
            log.exception("plugin %s", m.name)


def apply_title():
    theme.TITLE = cfg().get("title") or A.env("SHOP_TITLE") or "CAPITAN PANEL"


_shell = theme.shell


def shell2(*a, **k):
    resp = _shell(*a, **k)
    b = cfg().get("banner")
    if b and "<body>" in resp.text:
        resp.text = resp.text.replace("<body>", '<body><div style="background:#251f4a;padding:9px 16px;text-align:center;font-size:14px">'
                                      + esc(b) + "</div>", 1)
    return resp


theme.shell = shell2
auth.shell = shell2

from . import pages  # noqa: E402

_prev = pages.install


def install(app):
    _prev(app)
    apply_title()
    r = app.router
    r.add_get("/admin", dash)
    r.add_get("/admin/settings", settings)
    r.add_post("/admin/settings", settings_post)
    r.add_get("/admin/pages", pages_list)
    r.add_post("/admin/pages/save", pages_save)
    r.add_post("/admin/pages/del", pages_del)
    r.add_get("/p/{slug}", page_view)
    r.add_get("/admin/plugins", plugins_page)
    r.add_post("/admin/plugins/toggle", plugins_toggle)
    r.add_get("/admin/backup", backup_page)
    r.add_post("/admin/backup/dl", backup_dl)
    load_plugins(app)


pages.install = install
