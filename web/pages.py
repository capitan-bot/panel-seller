from __future__ import annotations

import asyncio
import html
import re
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

from aiohttp import web

from . import app as A

NAV = [("dash", "/", "داشبورد", "▦"), ("users", "/users", "کاربران", "👥"), ("shop", "/shop", "فروشگاه", "🛍"),
       ("reports", "/reports", "گزارش‌ها", "📊"), ("panels", "/panels", "مدیریت پنل‌ها", "🖥"),
       ("settings", "/settings", "تنظیمات", "⚙")]
SECRET = re.compile(r"pass|^pw$|token|secret|enc", re.I)
XCSS = (".tw{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{padding:10px 12px;"
        "border-bottom:1px solid var(--bd);text-align:right;white-space:nowrap}th{color:var(--mu);font-weight:400}"
        ".btn{padding:6px 12px;border-radius:10px;border:1px solid var(--bd);background:#241f45;color:var(--tx);"
        "font-family:inherit;cursor:pointer;text-decoration:none;display:inline-block}.btn.r{background:#331818;color:var(--dn)}"
        "input.s,textarea.s{padding:9px;border-radius:10px;border:1px solid var(--bd);background:#0f0f14;color:var(--tx);"
        "font-family:inherit}.kv td:first-child{color:var(--mu)}h2{margin:18px 0 10px}")


def esc(s):
    return html.escape(str(s))


def side(active):
    it = "".join(f'<a class="it{" act" if k == active else ""}" href="{u}">{t} <span>{i}</span></a>' for k, u, t, i in NAV)
    return ('<aside class="side" id="side"><div class="mt">منوی اصلی</div>' + it +
            '<form class="lo" method="post" action="/logout"><button>خروج از پنل</button></form></aside>')


def patch_main(h):
    return re.sub(r'<aside class="side".*?</aside>', lambda m: side("dash"), h, flags=re.S)


def page(active, title, body):
    css = re.search(r"<style>(.*?)</style>", A.MAIN_HTML, re.S).group(1)
    t = (f'<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" '
         f'content="width=device-width,initial-scale=1"><title>{esc(title)}</title><style>{css}{XCSS}</style></head><body>'
         f'<div class="ov" id="ov"></div>{side(active)}<header class="top"><button class="burger" id="bg">☰</button>'
         f'<b>{esc(A.TITLE)}</b></header><main class="main"><h1>{esc(title)}</h1>{body}</main><script>'
         "const tg=()=>{document.getElementById('side').classList.toggle('open');document.getElementById('ov').classList.toggle('on')};"
         "document.getElementById('bg').onclick=tg;document.getElementById('ov').onclick=tg;</script></body></html>")
    return web.Response(text=t, content_type="text/html")


def same_origin(req):
    o = req.headers.get("Origin") or req.headers.get("Referer")
    if o and urlparse(o).netloc != req.host:
        raise web.HTTPForbidden()


def cols(t):
    return [r[1] for r in A.q(f"PRAGMA table_info({t})") if not SECRET.search(r[1])]


def qc(c):
    return '"' + c + '"'


def rw(sql, args=()):
    con = sqlite3.connect(A.db_path(), timeout=10)
    try:
        con.execute(sql, args)
        con.commit()
    finally:
        con.close()


def fv(c, v):
    if v is None:
        return "—"
    if isinstance(v, int) and c in ("created", "expires", "ts", "time"):
        if v == 0:
            return "بدون انقضا" if c == "expires" else "—"
        if v > 10 ** 9:
            return datetime.fromtimestamp(v, A.TZI).strftime("%Y-%m-%d %H:%M")
    if isinstance(v, int) and re.search("price|balance|amount|value", c):
        return f"{v:,}"
    return esc(v)


def tbl(head, rows):
    th = "".join(f"<th>{esc(x)}</th>" for x in head)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows) or \
         f'<tr><td colspan="{len(head)}">موردی نیست</td></tr>'
    return f'<div class="card tw"><table><tr>{th}</tr>{tr}</table></div>'


def dbt(cl, rows, act=None):
    out = []
    for r in rows:
        d = dict(zip(cl, r))
        out.append([fv(c, d[c]) for c in cl] + ([act(d)] if act else []))
    return tbl(cl + (["عملیات"] if act else []), out)


def sel(t, cl, extra=" ORDER BY 1 DESC LIMIT 200"):
    return A.q("SELECT " + ",".join(map(qc, cl)) + f" FROM {t}" + extra)


def n(x):
    return f"{int(x or 0):,}"


async def users(req):
    s = req.query.get("q", "").strip()
    cl = cols("users")
    sql, args = "SELECT " + ",".join(map(qc, cl)) + " FROM users", ()
    if s:
        sql += " WHERE " + " OR ".join(f"CAST({qc(c)} AS TEXT) LIKE ?" for c in cl)
        args = (f"%{s}%",) * len(cl)

    def act(d):
        return ('<form method="post" action="/users/act" style="display:flex;gap:6px">'
                f'<input type="hidden" name="id" value="{esc(d.get("tg_id"))}"><input class="s" name="delta" '
                'placeholder="± تومان" size="9"><button class="btn" name="a" value="bal">اعمال</button>'
                f'<button class="btn r" name="a" value="blk">{"رفع مسدودی" if d.get("blocked") else "مسدود"}</button></form>')
    body = (f'<form class="sub"><input class="s" name="q" value="{esc(s)}" placeholder="جستجو (آیدی، نام...)"> '
            '<button class="btn">جستجو</button></form>' + dbt(cl, A.q(sql + " ORDER BY created DESC LIMIT 200", args), act))
    return page("users", "کاربران", body)


async def users_act(req):
    same_origin(req)
    f = await req.post()
    try:
        uid = int(f["id"])
        if f.get("a") == "blk":
            rw("UPDATE users SET blocked=1-blocked WHERE tg_id=?", (uid,))
        elif f.get("a") == "bal":
            d = int((f.get("delta") or "0").replace(",", "").replace("+", "").strip() or 0)
            rw("UPDATE users SET balance=MAX(0,balance+?) WHERE tg_id=?", (d, uid))
    except (ValueError, KeyError):
        pass
    raise web.HTTPFound(req.headers.get("Referer") or "/users")


async def shop(req):
    def tog(t):
        return lambda d: (f'<form method="post" action="/shop/act"><input type="hidden" name="t" value="{t}">'
                          f'<input type="hidden" name="id" value="{esc(d["id"])}"><button class="btn'
                          f'{"" if d.get("active") else " r"}">{"فعال ✓" if d.get("active") else "غیرفعال ✗"}</button></form>')
    out = ""
    for t, title in (("products", "محصولات"), ("packages", "پکیج‌ها"), ("codes", "کدهای تخفیف")):
        cl = cols(t)
        out += f"<h2>{title}</h2>" + dbt(cl, sel(t, cl), tog(t))
    return page("shop", "فروشگاه", out)


async def shop_act(req):
    same_origin(req)
    f = await req.post()
    if f.get("t") in ("products", "packages", "codes"):
        try:
            rw(f"UPDATE {f['t']} SET active=1-active WHERE id=?", (int(f["id"]),))
        except (ValueError, KeyError):
            pass
    raise web.HTTPFound("/shop")


async def reports(req):
    import time
    a = int(time.time()) - 30 * 86400
    days = A.q("SELECT date(created+?,'unixepoch'), COUNT(*), SUM(price), SUM(gb) FROM sales WHERE created>=? "
               "GROUP BY 1 ORDER BY 1 DESC", (A.TZ, a))
    kinds = A.q("SELECT kind, COUNT(*), SUM(price) FROM sales GROUP BY kind ORDER BY 3 DESC")
    top = A.q("SELECT user_id, COUNT(*), SUM(price) FROM sales GROUP BY user_id ORDER BY 3 DESC LIMIT 10")
    body = ("<h2>فروش روزانه (۳۰ روز اخیر)</h2>" + tbl(["روز", "سفارش", "فروش (تومان)", "حجم (GB)"],
            [[esc(d), n(c), n(s), f"{(g or 0):.1f}"] for d, c, s, g in days]) +
            "<h2>بر اساس نوع</h2>" + tbl(["نوع", "تعداد", "فروش (تومان)"], [[esc(k), n(c), n(s)] for k, c, s in kinds]) +
            "<h2>برترین خریداران</h2>" + tbl(["آیدی کاربر", "تعداد", "جمع خرید (تومان)"],
                                             [[esc(u), n(c), n(s)] for u, c, s in top]))
    return page("reports", "گزارش‌ها", body)


async def panels(req):
    pc = ["id", "admin_username", "status", "expires", "user_id", "is_test", "created"]
    sc = cols("servers")
    body = ("<h2>سرورهای پاسارگارد</h2>" + dbt(sc, sel("servers", sc, " ORDER BY id"),
            lambda d: f'<a class="btn" href="/panels/server/{esc(d["id"])}">اطلاعات سرور</a>') +
            "<h2>پنل‌های ساخته‌شده</h2>" + dbt(pc, sel("panels", pc, " ORDER BY id DESC LIMIT 300")))
    return page("panels", "مدیریت پنل‌ها", body)


def hum(k, v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 1e6 and \
            re.search("mem|ram|disk|byte|traffic|used|total|usage", k, re.I):
        return f"{v / 2 ** 30:.2f} GB"
    return esc(v)


def render(o, d=0):
    if isinstance(o, dict):
        rows = "".join(f"<tr><td>{esc(k)}</td><td>{render(v, d + 1) if isinstance(v, (dict, list)) and d < 2 else hum(k, v)}</td></tr>"
                       for k, v in o.items() if not SECRET.search(str(k)))
        return f'<table class="kv">{rows}</table>'
    if isinstance(o, list):
        if o and all(isinstance(x, dict) for x in o):
            ks = [k for k, v in o[0].items() if not isinstance(v, (dict, list)) and not SECRET.search(k)][:10]
            return tbl(ks, [[hum(k, x.get(k)) for k in ks] for x in o])
        return esc(", ".join(map(str, o)))
    return esc(o)


async def server(req):
    r = A.q("SELECT id,url,username,password FROM servers WHERE id=?", (int(req.match_info["sid"]),))
    if not r:
        raise web.HTTPNotFound()
    sid, url, user, pw = r[0]
    try:
        from bot import config as C, db as D
        from bot.panel import PG
        pg = PG(url, user, D.dec(pw), C.VERIFY_SSL)
        res = await asyncio.gather(asyncio.wait_for(pg.system_stats(), 25), asyncio.wait_for(pg.nodes(), 25),
                                   return_exceptions=True)
    except Exception as e:
        res = [e, e]
    body = f'<div class="sub">{esc(url)}</div>'
    for title, v in (("منابع سیستم (RAM، CPU، هسته)", res[0]), ("نودها", res[1])):
        body += f"<h2>{title}</h2>" + ('<div class="card">خطا: ' + esc(repr(v)) + "</div>" if isinstance(v, Exception)
                                       else f'<div class="card tw">{render(v)}</div>')
    return page("panels", "اطلاعات سرور", body + '<br><a class="btn" href="/panels">بازگشت</a>')


async def settings(req):
    cl = [r[1] for r in A.q("PRAGMA table_info(settings)")]
    if not ("key" in cl and "value" in cl):
        return page("settings", "تنظیمات", dbt(cols("settings"), sel("settings", cols("settings"))))
    rows = A.q('SELECT "key","value" FROM settings ORDER BY 1')
    out = []
    for k, v in rows:
        if SECRET.search(k):
            out.append([esc(k), "•••", ""])
            continue
        out.append([esc(k), f'<form method="post" action="/settings/act" style="display:flex;gap:6px"><input type="hidden" '
                            f'name="k" value="{esc(k)}"><textarea class="s" name="v" rows="2" cols="34">{esc(v)}</textarea>'
                            '<button class="btn">ذخیره</button></form>', ""])
    note = '<div class="sub">اگر تغییری در ربات اعمال نشد، ربات را ری‌استارت کن.</div>'
    return page("settings", "تنظیمات", note + tbl(["کلید", "مقدار"], [r[:2] for r in out]))


async def settings_act(req):
    same_origin(req)
    f = await req.post()
    k = f.get("k", "")
    if k and not SECRET.search(k) and A.q('SELECT 1 FROM settings WHERE "key"=?', (k,)):
        rw('UPDATE settings SET "value"=? WHERE "key"=?', (f.get("v", ""), k))
    raise web.HTTPFound("/settings")


def install(app):
    r = app.router
    r.add_get("/users", users)
    r.add_post("/users/act", users_act)
    r.add_get("/shop", shop)
    r.add_post("/shop/act", shop_act)
    r.add_get("/reports", reports)
    r.add_get("/panels", panels)
    r.add_get(r"/panels/server/{sid:\d+}", server)
    r.add_get("/settings", settings)
    r.add_post("/settings/act", settings_act)
