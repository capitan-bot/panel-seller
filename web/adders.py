from __future__ import annotations

import asyncio
import re
import time

from aiohttp import web

from . import app as A
from . import pages as P

_DONE = [False]
TABLES = {
    "products": ("افزودن محصول", "shop"),
    "packages": ("افزودن پکیج", "shop"),
    "codes": ("افزودن کد تخفیف", "shop"),
    "servers": ("افزودن پنل (سرور پاسارگارد)", "panels"),
}
LABEL = {
    "name": "نام", "descr": "توضیحات", "price_gb": "قیمت هر گیگ (تومان)", "min_gb": "حداقل حجم (GB)",
    "max_gb": "حداکثر حجم (GB)", "sort": "ترتیب نمایش", "server_id": "سرور پاسارگارد", "gb": "حجم (GB)",
    "price": "قیمت (تومان)", "product_id": "محصول", "code": "کد", "kind": "نوع", "value": "مقدار",
    "max_uses": "سقف دفعات استفاده (۰ = نامحدود)", "min_price": "حداقل مبلغ خرید (تومان)", "active": "وضعیت",
    "url": "آدرس پنل (مثل https://panel.example.com:8000)", "username": "نام کاربری ادمین پنل", "password": "رمز ادمین پنل",
    ("codes", "expires"): "اعتبار (روز؛ ۰ = بدون انقضا)", ("codes", "value"): "مقدار (درصد یا مبلغ، بر اساس نوع)",
}
DIG = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
SKIP = {"created", "ts"}
CSS = """<style>.ac{display:flex;gap:8px;flex-wrap:wrap}
.fm{display:grid;gap:14px;max-width:560px;padding:20px}.fr label{display:block;color:var(--mu);font-size:13px;margin-bottom:6px}
.fr input,.fr select,.fr textarea{width:100%;font-size:15px}
select.s{padding:9px;border-radius:10px;border:1px solid var(--bd);background:#0f0f14;color:var(--tx);font-family:inherit}
.er{background:#331818;color:var(--dn);padding:12px;border-radius:14px;max-width:560px;margin-bottom:12px}
.ok{background:#0f2e24;color:var(--up);padding:12px;border-radius:14px;margin:10px 0}</style>"""


def isnum(typ):
    return any(k in typ for k in ("INT", "REAL", "FLOA", "DOUB"))


def fields(t):
    out = []
    for _c, name, typ, nn, dflt, pk in A.q("PRAGMA table_info(%s)" % t):
        if pk or name in SKIP:
            continue
        out.append({"name": name, "typ": (typ or "").upper(), "nn": bool(nn), "dflt": dflt})
    return out


def options(n):
    if n == "server_id":
        return [(r[0], "%s · %s" % (r[0], r[1])) for r in A.q("SELECT id,url FROM servers ORDER BY id")]
    if n == "product_id":
        return [(r[0], "%s · %s" % (r[0], r[1])) for r in A.q("SELECT id,name FROM products ORDER BY id")]
    return None


def label(t, n):
    return LABEL.get((t, n)) or LABEL.get(n) or n


def form(t, vals=None, err=""):
    vals = vals or {}
    title, back = TABLES[t]
    rows, blocked = [], False
    for f in fields(t):
        n, typ, v = f["name"], f["typ"], vals.get(f["name"], "")
        req = f["nn"] and f["dflt"] is None and n != "active"
        lab = label(t, n) + (" *" if req else "")
        opts = options(n)
        ph = ""
        if f["dflt"] is not None and n not in ("active", "password"):
            ph = ' placeholder="پیش‌فرض: %s"' % P.esc(str(f["dflt"]).strip("'\""))
        if opts is not None:
            if not opts:
                blocked = True
                inp = '<div class="sub">ابتدا یک مورد در بخش مربوط اضافه کن.</div>'
            else:
                inp = '<select class="s" name="%s">%s</select>' % (n, "".join(
                    '<option value="%s"%s>%s</option>' % (o, " selected" if str(o) == str(v) else "", P.esc(l))
                    for o, l in opts))
        elif n == "active":
            inp = ('<select class="s" name="active"><option value="1">فعال</option>'
                   '<option value="0"%s>غیرفعال</option></select>' % (" selected" if v == "0" else ""))
        elif n == "password":
            inp = '<input class="s" type="password" name="password" autocomplete="new-password">'
        elif n == "descr":
            inp = '<textarea class="s" name="descr" rows="3">%s</textarea>' % P.esc(v)
        elif n == "code":
            inp = ('<div class="ac"><input class="s" name="code" value="%s" style="flex:1" autocomplete="off">'
                   '<button type="button" class="btn" id="gc">🎲 ساخت</button></div>' % P.esc(v))
        else:
            dl, lst = "", ""
            if n == "kind":
                vs = [r[0] for r in A.q("SELECT DISTINCT kind FROM %s WHERE kind!='' LIMIT 8" % t)]
                dl = '<datalist id="dl_kind">%s</datalist>' % "".join('<option value="%s">' % P.esc(x) for x in vs)
                lst = ' list="dl_kind"'
            inp = '<input class="s" name="%s" value="%s"%s%s%s>%s' % (
                n, P.esc(v), ' inputmode="decimal"' if isnum(typ) else "", lst, ph, dl)
        rows.append('<div class="fr"><label>%s</label>%s</div>' % (P.esc(lab), inp))
    if t == "servers":
        rows.append('<label class="fr"><input type="checkbox" name="notest" value="1"> ذخیره بدون تست اتصال</label>')
    eh = '<div class="er">%s</div>' % P.esc(err) if err else ""
    body = (CSS + eh + '<form class="card fm" method="post" action="/add/%s">%s<div class="ac"><button class="btn"%s>ذخیره</button>'
            '<a class="btn r" href="/%s">انصراف</a></div></form>' % (t, "".join(rows), " disabled" if blocked else "", back))
    body += ("<script>var g=document.getElementById('gc');if(g)g.onclick=function(){var a='ABCDEFGHJKLMNPQRSTUVWXYZ23456789',s='',i;"
             "for(i=0;i<8;i++)s+=a.charAt(Math.floor(Math.random()*a.length));document.querySelector('[name=code]').value=s}</script>")
    return P.page(back, title, body)


async def form_get(req):
    t = req.match_info["t"]
    if t not in TABLES:
        raise web.HTTPNotFound()
    return form(t)


async def save(req):
    P.same_origin(req)
    t = req.match_info["t"]
    if t not in TABLES:
        raise web.HTTPNotFound()
    f = await req.post()
    fl = fields(t)
    vals = {x["name"]: str(f.get(x["name"], "")) for x in fl if x["name"] != "password"}
    cols, args, plain = [], [], ""
    for x in fl:
        n, typ = x["name"], x["typ"]
        raw = str(f.get(n, "")).strip()
        if raw == "":
            if x["nn"] and x["dflt"] is None and n != "active":
                return form(t, vals, "پر کردن «%s» لازم است." % label(t, n))
            continue
        if isnum(typ):
            num = raw.translate(DIG).replace(",", "").replace("٬", "")
            try:
                val = int(num) if "INT" in typ else float(num)
            except ValueError:
                return form(t, vals, "«%s» باید عدد باشد." % label(t, n))
            if val < 0:
                return form(t, vals, "«%s» نمی‌تواند منفی باشد." % label(t, n))
            if t == "codes" and n == "expires":
                val = int(time.time() + val * 86400) if val > 0 else 0
        else:
            val = raw[:2000]
            if n == "url":
                val = re.sub(r"/(dashboard/?)?$", "", val.rstrip("/"))
                if not re.match(r"^https?://", val):
                    return form(t, vals, "آدرس باید با http:// یا https:// شروع شود.")
            if n == "password":
                plain = raw
        cols.append(n)
        args.append(val)
    d = dict(zip(cols, args))
    if t == "codes" and "code" in d and A.q("SELECT 1 FROM codes WHERE lower(code)=lower(?)", (d["code"],)):
        return form(t, vals, "این کد قبلاً ثبت شده.")
    if t == "servers":
        if not f.get("notest"):
            try:
                from bot import config as C
                from bot.panel import PG
                pg = PG(d["url"], d["username"], plain, C.VERIFY_SSL)
                await asyncio.wait_for(pg.test(), 25)
            except Exception as e:
                return form(t, vals, "اتصال به پنل ناموفق بود: %r — اگر مطمئنی درست است «ذخیره بدون تست» را بزن." % (e,))
        from bot import db as D
        args[cols.index("password")] = D.enc(plain)
    if "created" in {r[1] for r in A.q("PRAGMA table_info(%s)" % t)}:
        cols.append("created")
        args.append(int(time.time()))
    if cols:
        sql = 'INSERT INTO %s(%s) VALUES(%s)' % (t, ",".join('"%s"' % c for c in cols), ",".join("?" * len(cols)))
    else:
        sql = "INSERT INTO %s DEFAULT VALUES" % t
    try:
        await asyncio.to_thread(P.rw, sql, tuple(args))
    except Exception as e:
        return form(t, vals, "ذخیره نشد: %r" % (e,))
    raise web.HTTPFound("/%s?added=1" % TABLES[t][1])


def btns(kind):
    items = ([("/add/products", "➕ محصول جدید"), ("/add/packages", "➕ پکیج جدید"), ("/add/codes", "➕ کد تخفیف")]
             if kind == "shop" else [("/add/servers", "➕ افزودن پنل")])
    return (CSS + '<div class="ac" style="margin:10px 0 16px">' +
            "".join('<a class="btn" href="%s">%s</a>' % i for i in items) + "</div>")


def wrap(old, kind):
    async def h(req):
        resp = await old(req)
        try:
            if isinstance(resp, web.Response) and resp.text and "</h1>" in resp.text:
                note = '<div class="ok">✅ با موفقیت اضافه شد.</div>' if req.query.get("added") else ""
                resp.text = resp.text.replace("</h1>", "</h1>" + note + btns(kind), 1)
        except Exception:
            pass
        return resp
    return h


def routes(app, path):
    out = []
    for res in app.router.resources():
        if getattr(res, "canonical", None) == path:
            out += [rt for rt in res if rt.method == "GET"]
    return out


def install(app):
    if _DONE[0]:
        return
    _DONE[0] = True
    app.router.add_get("/add/{t}", form_get)
    app.router.add_post("/add/{t}", save)
    for path, kind in (("/shop", "shop"), ("/panels", "panels")):
        for rt in routes(app, path):
            rt._handler = wrap(rt.handler, kind)
