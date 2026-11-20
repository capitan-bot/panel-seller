from __future__ import annotations

import asyncio
import glob
import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from aiohttp import web

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
AUTH = DATA / "web_auth.json"
ASSETS = ROOT / "bot" / "assets"
HOST = os.environ.get("WEB_HOST", "127.0.0.1")
PORT = int(os.environ.get("WEB_PORT", "8787"))
TITLE = os.environ.get("WEB_TITLE", "CAPITAN PANEL")
TZ = 12600
TZI = timezone(timedelta(seconds=TZ))
FAILS: dict = {}
PFX = ""
GWTOK = ""
SEC = {"X-Frame-Options": "DENY", "X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin",
       "Cache-Control": "no-store",
       "Content-Security-Policy": "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                  "script-src 'self' 'unsafe-inline'; img-src 'self' data:; "
                                  "form-action 'self'; frame-ancestors 'none'"}


def env(key: str) -> str:
    try:
        for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
            if line.startswith(key + "="):
                return line.split("=", 1)[1].strip().strip("\"' ")
    except OSError:
        pass
    return ""


def admin_ids() -> set:
    return {int(x) for x in env("ADMIN_TELEGRAM_IDS").split(",") if x.strip().isdigit()}


def db_path():
    if (DATA / "bot.db").exists():
        return str(DATA / "bot.db")
    for pat in ("*.db", "*.sqlite3"):
        f = sorted(glob.glob(str(DATA / pat)))
        if f:
            return f[0]
    return None


def q(sql: str, args: tuple = ()):
    con = sqlite3.connect(f"file:{db_path()}?mode=ro", uri=True, timeout=5)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


# ---------- auth ----------
def hash_pw(pw: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)


def load_auth():
    try:
        return json.loads(AUTH.read_text())
    except Exception:
        return None


def set_password(pw: str | None = None) -> str:
    pw = pw or secrets.token_urlsafe(12)
    salt = os.urandom(16)
    DATA.mkdir(exist_ok=True)
    AUTH.write_text(json.dumps({"salt": salt.hex(), "hash": hash_pw(pw, salt).hex(), "secret": secrets.token_hex(32)}))
    os.chmod(AUTH, 0o600)
    return pw


def sign(msg: str, secret: str) -> str:
    return hmac.new(bytes.fromhex(secret), msg.encode(), "sha256").hexdigest()


def make_cookie(uid: int, secret: str) -> str:
    m = f"{uid}.{int(time.time()) + 7 * 86400}"
    return f"{m}.{sign(m, secret)}"


def check_cookie(val: str, secret: str):
    try:
        uid, exp, sig = val.split(".")
        if hmac.compare_digest(sig, sign(f"{uid}.{exp}", secret)) and int(exp) > time.time() and int(uid) in admin_ids():
            return int(uid)
    except Exception:
        pass
    return None


def client_ip(req) -> str:
    if req.remote in ("127.0.0.1", "::1") or GWTOK:
        xf = req.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
        if xf:
            return xf
    return req.remote or "?"


def is_https(req) -> bool:
    return req.headers.get("X-Forwarded-Proto") == "https" or req.secure


def cookie_vals(req) -> list:
    out = []
    for part in req.headers.get("Cookie", "").split(";"):
        k, _, v = part.strip().partition("=")
        if k == "pgweb" and v:
            out.append(v)
    return out


def valid_uid(req, secret):
    for v in cookie_vals(req):
        u = check_cookie(v, secret)
        if u is not None:
            return u
    return None


@web.middleware
async def guard(req, handler):
    if not req.path[len(PFX):].startswith(("/login", "/static/")):
        a = load_auth()
        uid = valid_uid(req, a["secret"]) if a else None
        if uid is None:
            if req.path[len(PFX):].startswith("/api/"):
                raise web.HTTPUnauthorized()
            raise web.HTTPFound("/login")
        req["uid"] = uid
    resp = await handler(req)
    h = dict(SEC)
    if req.path.startswith("/static/"):
        h.pop("Cache-Control")
    resp.headers.update(h)
    return resp


# ---------- data ----------
def pct(cur, prev):
    return None if not prev else round((cur - prev) * 100 / prev)


def agg(a: int, b: int):
    s = q("SELECT COALESCE(SUM(price),0), COUNT(*) FROM sales WHERE created>=? AND created<?", (a, b))[0]
    u = q("SELECT COUNT(*) FROM users WHERE created>=? AND created<?", (a, b))[0][0]
    return s[0], s[1], u


def dash(rng: str, frm: str, to: str) -> dict:
    now, D = int(time.time()), 86400
    if rng == "24h":
        start, end, step = now - D, now + 1, 3600
    elif rng == "3m":
        start, end, step = now - 90 * D, now + 1, D
    else:
        start, end, step = now - 7 * D, now + 1, D
        if rng == "custom":
            try:
                a = int(datetime.strptime(frm, "%Y-%m-%d").replace(tzinfo=TZI).timestamp())
                b = int(datetime.strptime(to, "%Y-%m-%d").replace(tzinfo=TZI).timestamp()) + D
                if 0 < b - a <= 366 * D:
                    start, end = a, b
            except ValueError:
                pass
    w, pw = agg(now - 7 * D, now + 1), agg(now - 14 * D, now - 7 * D)
    d1, pd1 = agg(now - D, now + 1), agg(now - 2 * D, now - D)
    rows = {r[0]: (r[1], r[2]) for r in q(
        "SELECT CAST((created+?)/? AS INTEGER) AS b, COALESCE(SUM(price),0), COUNT(*) FROM sales "
        "WHERE created>=? AND created<? GROUP BY b", (TZ, step, start, end))}
    series = []
    for b in range((start + TZ) // step, (end - 1 + TZ) // step + 1):
        v = rows.get(b, (0, 0))
        series.append({"t": b * step - TZ, "v": v[0], "n": v[1]})
    tot = q("SELECT COALESCE(SUM(price),0), COUNT(*) FROM sales")[0]
    return {
        "users_total": q("SELECT COUNT(*) FROM users")[0][0], "users_week": w[2],
        "orders_total": tot[1], "orders_pct": pct(w[1], pw[1]),
        "sales_total": tot[0], "sales_pct": pct(w[0], pw[0]),
        "new24": d1[2], "new24_pct": pct(d1[2], pd1[2]),
        "panels_active": q("SELECT COUNT(*) FROM panels WHERE status='active' AND is_test=0")[0][0],
        "panels_off": q("SELECT COUNT(*) FROM panels WHERE status!='active' AND is_test=0")[0][0],
        "step": step, "series": series, "range_sales": sum(s["v"] for s in series),
        "range_orders": sum(s["n"] for s in series)}


# ---------- pages ----------
LOGIN_HTML = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ورود به پنل</title><style>
@font-face{font-family:V;src:url(/static/Vazirmatn-Regular.ttf)}
@font-face{font-family:V;font-weight:700;src:url(/static/Vazirmatn-Bold.ttf)}
*{box-sizing:border-box}body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0b0b10;color:#e8e8ee;font-family:V,Tahoma,sans-serif}
.box{width:min(92vw,420px);background:#131318;border:1px solid #23232b;border-radius:20px;padding:32px 26px}
h1{margin:0 0 6px;font-size:26px;text-align:center}p{margin:0 0 22px;text-align:center;color:#9a9aa8;font-size:14px}
label{display:block;margin:14px 4px 6px;font-size:13px;color:#b5b5c3}
input{width:100%;padding:14px;border-radius:12px;border:1px solid #2c2c36;background:#0f0f14;color:#fff;font-size:16px;font-family:inherit;direction:ltr;text-align:left}
input:focus{outline:2px solid #7c5cf0;border-color:transparent}
button{width:100%;margin-top:22px;padding:14px;border:0;border-radius:12px;background:#a78bfa;color:#16102e;font-weight:700;font-size:16px;font-family:inherit;cursor:pointer}
.err{margin-top:14px;color:#f87171;font-size:13px;text-align:center}</style></head><body>
<form class="box" method="post" action="/login"><h1>__TITLE__</h1><p>برای ادامه، اطلاعات حساب خود را وارد کنید.</p>
<label>نام کاربری (آیدی عددی ادمین)</label><input name="username" inputmode="numeric" autocomplete="username" required>
<label>رمز عبور</label><input name="password" type="password" autocomplete="current-password" required>
<button>ورود به پنل</button><div class="err">__ERR__</div></form></body></html>"""

MAIN_HTML = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>__TITLE__</title><style>
@font-face{font-family:V;src:url(/static/Vazirmatn-Regular.ttf)}
@font-face{font-family:V;font-weight:700;src:url(/static/Vazirmatn-Bold.ttf)}
:root{--bg:#0b0b10;--card:#131318;--bd:#23232b;--tx:#e8e8ee;--mu:#9a9aa8;--ac:#a78bfa;--up:#34d399;--dn:#f87171}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);font-family:V,Tahoma,sans-serif}
.top{position:sticky;top:0;z-index:10;display:flex;align-items:center;gap:12px;padding:12px 16px;background:#0b0b10ee;border-bottom:1px solid var(--bd);backdrop-filter:blur(8px)}
.burger{background:var(--card);border:1px solid var(--bd);color:var(--tx);border-radius:12px;font-size:20px;padding:6px 12px;cursor:pointer}
.side{position:fixed;top:0;bottom:0;right:0;width:270px;background:#101015;border-left:1px solid var(--bd);transform:translateX(100%);transition:.25s;z-index:30;padding:20px 14px;display:flex;flex-direction:column;gap:4px}
.side.open{transform:none}.ov{position:fixed;inset:0;background:#0009;display:none;z-index:20}.ov.on{display:block}
.mt{color:var(--mu);font-size:12px;margin:14px 10px 4px}
.it{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-radius:12px;color:var(--tx);text-decoration:none;font-size:15px}
.act{background:#2a2250;color:#fff}.soon{opacity:.45}.soon i{font-size:11px;font-style:normal;background:#23232b;padding:2px 8px;border-radius:99px}
.lo{margin-top:auto}.lo button{width:100%;padding:12px;border-radius:12px;border:1px solid var(--bd);background:var(--card);color:var(--dn);font-family:inherit;font-size:15px;cursor:pointer}
.main{padding:18px 16px 40px;max-width:1100px;margin:auto}h1{margin:6px 0 4px;font-size:28px}h2{margin:0;font-size:20px}
.sub{color:var(--mu);font-size:14px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;margin-bottom:16px}
.card{background:var(--card);border:1px solid var(--bd);border-radius:20px;padding:20px}
.k{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.k .l{color:var(--mu);font-size:14px}.k .v{font-size:28px;font-weight:700;margin:4px 0 10px}
.ic{width:48px;height:48px;border-radius:14px;display:grid;place-items:center;font-size:22px;background:#241f45}
.chip{display:inline-block;padding:4px 12px;border-radius:99px;font-size:13px;background:#23232b;color:var(--mu)}.chip.up{background:#0f2e24;color:var(--up)}.chip.dn{background:#331818;color:var(--dn)}
.tabs{display:flex;gap:4px;background:#0f0f14;border:1px solid var(--bd);border-radius:14px;padding:4px;margin:14px 0}
.tabs button{flex:1;padding:9px 4px;border:0;border-radius:10px;background:none;color:var(--mu);font-family:inherit;font-size:14px;cursor:pointer}.tabs .on{background:#241f45;color:var(--ac)}
#cus{display:flex;gap:8px;margin-bottom:12px}#cus[hidden]{display:none}#cus input,#cus button{padding:9px;border-radius:10px;border:1px solid var(--bd);background:#0f0f14;color:var(--tx);font-family:inherit}
.svg{width:100%;height:auto}.svg text{fill:#9a9aa8;font-size:11px;font-family:V,sans-serif}.svg circle{fill:#a78bfa;opacity:.0}.svg circle:hover{opacity:1}.ax{stroke:#2a2a33}
@media(min-width:960px){.side{transform:none}.main{margin-right:270px;max-width:none}.top{margin-right:270px}.burger{display:none}.ov{display:none!important}}
.ic{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
.side .it{justify-content:flex-start;gap:10px;padding:13px 14px;border:1px solid transparent;position:relative;transition:background .2s,transform .12s,border-color .2s,color .2s}
.side .it .ic{margin-right:auto;color:var(--mu);transition:color .2s}
.side a.it:hover{background:#17161f;border-color:var(--bd)}
.side .it:active{transform:scale(.97)}
.side .it.act{background:linear-gradient(270deg,#3b2f8f,#241f45);border-color:#4c3fb3;color:#fff;box-shadow:0 0 18px #7c5cff33}
.side .it.act .ic{color:#c4b5fd}
.side .it.act:before{content:"";position:absolute;right:-14px;top:22%;bottom:22%;width:3px;border-radius:3px;background:#a78bfa}
.side .it.soon{opacity:.6;cursor:default}
.side .it i{font-style:normal;font-size:10px;padding:2px 8px;border-radius:20px;background:#1d1b2b;color:var(--mu)}
.side .lo{margin-top:auto}
.side .lo button{width:100%;display:flex;align-items:center;justify-content:center;gap:8px;padding:13px;border-radius:12px;border:1px solid #5b2a33;background:#2a1418;color:#f87171;font-family:inherit;font-size:15px;cursor:pointer;transition:background .15s,transform .12s}
.side .lo button:hover{background:#34181d}
.side .lo button:active{transform:scale(.97)}
.grp>.gh{width:100%;display:flex;align-items:center;gap:10px;padding:13px 14px;border-radius:12px;border:1px solid transparent;background:none;color:var(--tx);font-family:inherit;font-size:15px;cursor:pointer}.grp>.gh:hover{background:#17161f;border-color:var(--bd)}.grp>.gh .ic{margin-right:auto;color:var(--mu)}.grp>.gh .ar{color:var(--mu);font-size:12px;transition:.2s}.grp.open>.gh .ar{transform:rotate(180deg)}.grp>.sb{display:none;flex-direction:column;gap:2px;margin:2px 14px 6px 0;padding-right:12px;border-right:2px solid #2a2a40}.grp.open>.sb{display:flex}.grp>.sb a{padding:10px 12px;border-radius:10px;color:var(--mu);text-decoration:none;font-size:14px}.grp>.sb a:hover{background:#17161f;color:var(--tx)}
</style></head><body><div class="ov" id="ov"></div>
<aside class="side" id="side"><div class="mt">منوی اصلی</div><a class="it act">داشبورد <svg class="ic" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="9" rx="1.5"/><rect x="14" y="3" width="7" height="5" rx="1.5"/><rect x="14" y="12" width="7" height="9" rx="1.5"/><rect x="3" y="16" width="7" height="5" rx="1.5"/></svg></a><span class="it soon">فروشگاه <i>به‌زودی</i><svg class="ic" viewBox="0 0 24 24"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg></span><span class="it soon">کاربران <i>به‌زودی</i><svg class="ic" viewBox="0 0 24 24"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.9"/><path d="M16 3.1a4 4 0 0 1 0 7.8"/></svg></span><span class="it soon">گزارش‌ها <i>به‌زودی</i><svg class="ic" viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/></svg></span><div class="mt">مدیریت</div><span class="it soon">مدیریت پنل‌ها <i>به‌زودی</i><svg class="ic" viewBox="0 0 24 24"><rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/></svg></span><div class="mt">پیکربندی</div><span class="it soon">تنظیمات <i>به‌زودی</i><svg class="ic" viewBox="0 0 24 24"><path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/></svg></span><div class="mt">بات</div><a class="it" href="buttons">دکمه‌های بات</a><form class="lo" method="post" action="/logout"><button><svg class="ic" viewBox="0 0 24 24"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/></svg> خروج از پنل</button></form></aside>
<header class="top"><button class="burger" id="bg">☰</button><b>__TITLE__</b></header>
<main class="main"><h1>داشبورد</h1><div class="sub" id="date"></div><div class="grid" id="cards"></div>
<section class="card"><h2>روند درآمد</h2><div class="sub" id="rsum"></div>
<div class="tabs" id="tabs"><button data-r="24h">۲۴ ساعت</button><button data-r="week" class="on">هفته</button><button data-r="3m">۳ ماه</button><button data-r="custom">روز دلخواه</button></div>
<div id="cus" hidden><input type="date" id="f"><input type="date" id="t"><button id="ap">اعمال</button></div><div id="chart"></div></section></main>
<script>
const fa=n=>Number(n).toLocaleString('fa-IR'),$=s=>document.querySelector(s);let rng='week';
const chip=p=>p==null?'<span class="chip">—</span>':`<span class="chip ${p>=0?'up':'dn'}">${p>=0?'▲':'▼'} ٪${fa(Math.abs(p))}</span>`;
const lab=(t,st)=>{const d=new Date(t*1000);return st<86400?d.toLocaleTimeString('fa-IR',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Tehran'}):d.toLocaleDateString('fa-IR',{day:'numeric',month:'short',timeZone:'Asia/Tehran'})};
function draw(s,st){const W=640,H=250,L=14,R=14,T=16,B=34,mx=Math.max(1,...s.map(a=>a.v));
const X=i=>L+(W-L-R)*(s.length>1?i/(s.length-1):.5),Y=v=>T+(H-T-B)*(1-v/mx);
const ln=s.map((a,i)=>(i?'L':'M')+X(i).toFixed(1)+' '+Y(a.v).toFixed(1)).join(' ');
const ar=ln+` L${X(s.length-1).toFixed(1)} ${H-B} L${X(0).toFixed(1)} ${H-B} Z`;
const n=s.length-1,ix=[0,Math.floor(n/3),Math.floor(2*n/3),n].filter((v,i,a)=>a.indexOf(v)===i);
const tk=ix.map(i=>`<text x="${X(i).toFixed(1)}" y="${H-10}" text-anchor="middle">${lab(s[i].t,st)}</text>`).join('');
const dt=s.length<=40?s.map((a,i)=>`<circle cx="${X(i).toFixed(1)}" cy="${Y(a.v).toFixed(1)}" r="5"><title>${lab(a.t,st)}: ${fa(a.v)} تومان (${fa(a.n)} سفارش)</title></circle>`).join(''):'';
$('#chart').innerHTML=`<svg class="svg" viewBox="0 0 ${W} ${H}" dir="ltr"><defs><linearGradient id="g" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a78bfa" stop-opacity=".45"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></linearGradient></defs><line class="ax" x1="${L}" x2="${W-R}" y1="${H-B}" y2="${H-B}"/><text x="${L}" y="${T-3}">${fa(mx)}</text><path d="${ar}" fill="url(#g)"/><path d="${ln}" fill="none" stroke="#a78bfa" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/>${dt}${tk}</svg>`}
async function load(){let u='/api/dashboard?range='+rng;if(rng==='custom')u+='&from='+$('#f').value+'&to='+$('#t').value;
const r=await fetch(u,{credentials:'same-origin'});if(r.status===401){location='/login';return}const d=await r.json();
if(d.error){$('#cards').innerHTML='<div class="card">خطا: '+d.error+'</div>';return}
const C=[['تعداد کل کاربران',fa(d.users_total),`<span class="chip up">▲ ${fa(d.users_week)}+ این هفته</span>`,'👥'],
['تعداد کل سفارشات',fa(d.orders_total),chip(d.orders_pct),'🛒'],['جمع کل فروش',fa(d.sales_total)+' تومان',chip(d.sales_pct),'💰'],
['کاربران جدید (۲۴ ساعت)',fa(d.new24),chip(d.new24_pct),'➕'],['پنل‌ها',fa(d.panels_active)+' فعال',`<span class="chip">${fa(d.panels_off)} غیرفعال/منقضی</span>`,'🖥']];
$('#cards').innerHTML=C.map(c=>`<div class="card"><div class="k"><div><div class="l">${c[0]}</div><div class="v">${c[1]}</div></div><div class="ic">${c[3]}</div></div>${c[2]}</div>`).join('');
$('#rsum').textContent=`جمع این بازه: ${fa(d.range_sales)} تومان از ${fa(d.range_orders)} سفارش`;draw(d.series,d.step)}
$('#date').textContent=new Intl.DateTimeFormat('fa-IR',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Tehran'}).format(new Date());
$('#tabs').onclick=e=>{const b=e.target.closest('button');if(!b)return;rng=b.dataset.r;document.querySelectorAll('#tabs button').forEach(x=>x.classList.toggle('on',x===b));$('#cus').hidden=rng!=='custom';if(rng!=='custom')load()};
$('#ap').onclick=()=>{if($('#f').value&&$('#t').value)load()};
const tg=()=>{$('#side').classList.toggle('open');$('#ov').classList.toggle('on')};$('#bg').onclick=tg;$('#ov').onclick=tg;
load();setInterval(()=>{if(rng!=='custom')load()},60000);
</script></body></html>"""


def login_page(err: str = "", status: int = 200):
    return web.Response(text=LOGIN_HTML.replace("__TITLE__", html.escape(TITLE)).replace("__ERR__", html.escape(err)),
                        content_type="text/html", status=status)


async def login_get(req):
    return login_page()


async def login_post(req):
    ip, a = client_ip(req), load_auth()
    now = time.time()
    FAILS[ip] = [t for t in FAILS.get(ip, []) if now - t < 600]
    if len(FAILS[ip]) >= 5:
        return login_page("تلاش‌های ناموفق زیاد بود؛ ۱۰ دقیقه بعد دوباره امتحان کن.", 429)
    f = await req.post()
    u, p = (f.get("username") or "").strip(), f.get("password") or ""
    ok = False
    if a and u.isdigit() and int(u) in admin_ids():
        hh = await asyncio.to_thread(hash_pw, p, bytes.fromhex(a["salt"]))
        ok = hmac.compare_digest(hh.hex(), a["hash"])
    if not ok:
        FAILS[ip].append(now)
        await asyncio.sleep(1)
        return login_page("نام کاربری یا رمز اشتباه است.", 401)
    resp = web.HTTPFound("/")
    resp.set_cookie("pgweb", make_cookie(int(u), a["secret"]), max_age=7 * 86400, httponly=True,
                    samesite="Lax", secure=is_https(req), path=(PFX or "/"))
    resp.headers.add("Set-Cookie", "pgweb=; Max-Age=0; Path=/")
    raise resp


async def logout(req):
    resp = web.HTTPFound("/login")
    resp.del_cookie("pgweb", path=(PFX or "/"))
    raise resp


async def index(req):
    return web.Response(text=MAIN_HTML.replace("__TITLE__", html.escape(TITLE)), content_type="text/html")


async def api_dash(req):
    try:
        data = await asyncio.to_thread(dash, req.query.get("range", "week"), req.query.get("from", ""), req.query.get("to", ""))
    except Exception as e:
        return web.json_response({"error": repr(e)}, status=500)
    return web.json_response(data)


def get_slug() -> str:
    s = re.sub(r"[^a-z0-9_]", "", env("WEB_SLUG").lower())
    if s:
        return s
    f = DATA / "web_slug.txt"
    try:
        s = f.read_text().strip()
        if s:
            return s
    except OSError:
        pass
    try:
        import urllib.request
        with urllib.request.urlopen("https://api.telegram.org/bot%s/getMe" % env("BOT_TOKEN"), timeout=10) as r:
            s = re.sub(r"[^a-z0-9_]", "", json.loads(r.read())["result"]["username"].lower())
    except Exception:
        s = ""
    if not s:
        ids = sorted(admin_ids())
        s = str(ids[0]) if ids else "panel"
    try:
        DATA.mkdir(exist_ok=True)
        f.write_text(s)
    except OSError:
        pass
    return s


def get_prefix() -> str:
    parts = [re.sub(r"[^a-z0-9_]", "", x.lower()) for x in env("WEB_PREFIX").strip("/ ").split("/")]
    parts = [x for x in parts if x]
    return "/".join(parts) or get_slug()


async def gw_ping(req):
    return web.json_response({"ok": True, "id": hashlib.sha256(GWTOK.encode()).hexdigest()})


def fix(t: str) -> str:
    p = PFX
    for a, b in (('href="/', 'href="%s/' % p), ('action="/', 'action="%s/' % p), ("url(/static/", "url(%s/static/" % p),
                 ("'/api/", "'%s/api/" % p), ("location='/login'", "location='%s/login'" % p)):
        t = t.replace(a, b)
    return t


@web.middleware
async def prefix_mw(req, handler):
    if GWTOK and not hmac.compare_digest(req.headers.get("X-GW-Token", ""), GWTOK):
        return web.Response(status=403, text="forbidden")
    try:
        resp = await handler(req)
    except web.HTTPFound as e:
        loc = e.headers.get("Location", "")
        if loc.startswith("/") and loc != PFX and not loc.startswith(PFX + "/"):
            e.headers["Location"] = PFX + loc
        raise
    if isinstance(resp, web.Response) and resp.content_type == "text/html" and resp.text:
        resp.text = fix(resp.text)
    return resp


def main():
    global PFX, MAIN_HTML, GWTOK
    GWTOK = env("WEB_GW_TOKEN")
    if len(sys.argv) > 1 and sys.argv[1] == "setpass":
        print("password:", set_password(sys.argv[2] if len(sys.argv) > 2 else None))
        return
    PFX = "/" + get_prefix()
    print("db:", db_path(), "| admins:", sorted(admin_ids()), "| listen:", f"{HOST}:{PORT}", "| path:", PFX, flush=True)
    if not load_auth():
        print("No password set. Run: python -m web.app setpass", flush=True)
    from . import pages, server_ui, btn_ui, more_ui, codes_ui
    MAIN_HTML = pages.patch_main(MAIN_HTML)
    sub = web.Application(middlewares=[guard])
    sub.router.add_get("/", index)
    sub.router.add_get("/login", login_get)
    sub.router.add_post("/login", login_post)
    sub.router.add_post("/logout", logout)
    sub.router.add_get("/api/dashboard", api_dash)
    server_ui.install(sub)
    pages.install(sub)
    btn_ui.install(sub)
    more_ui.install(sub)
    codes_ui.install(sub)
    try:
        from . import plugins
        plugins.install(sub)
    except Exception:
        import traceback
        traceback.print_exc()
    sub.router.add_static("/static/", ASSETS)

    async def bare(req):
        raise web.HTTPFound(PFX + "/")

    root = web.Application(middlewares=[prefix_mw])
    root.router.add_get(PFX, bare)
    root.router.add_get("/__gw/ping", gw_ping)
    root.add_subapp(PFX, sub)
    ctx = None
    if env("WEB_TLS_CERT") and env("WEB_TLS_KEY"):
        import ssl
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(env("WEB_TLS_CERT"), env("WEB_TLS_KEY"))
    web.run_app(root, host=HOST, port=PORT, ssl_context=ctx, access_log=None, print=None)


if __name__ == "__main__":
    main()
