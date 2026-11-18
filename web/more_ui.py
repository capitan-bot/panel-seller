import asyncio
import glob
import gzip
import json
import os
import sqlite3
import tempfile
import time
import urllib.parse
import urllib.request

from aiohttp import web

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BK = os.path.join(ROOT, "backups")
TEXTS = {"welcome": "پیام خوش‌آمد (برای نام کاربر {name} بنویس)", "faq": "سوالات متداول",
         "support": "پیام پشتیبانی", "shop": "نام فروشگاه"}


def dbp():
    return (glob.glob(os.path.join(ROOT, "data", "*.db")) + glob.glob(os.path.join(ROOT, "data", "*.sqlite3")))[0]


def conn():
    c = sqlite3.connect(dbp(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def q(sql, a=()):
    c = conn()
    try:
        return [dict(r) for r in c.execute(sql, a)]
    finally:
        c.close()


def ex(sql, a=()):
    c = conn()
    try:
        c.execute(sql, a)
        c.commit()
    finally:
        c.close()


def need(req):
    if req.headers.get("X-Req") != "1":
        raise web.HTTPForbidden()


def env(k):
    try:
        for l in open(os.path.join(ROOT, ".env"), encoding="utf-8"):
            if l.startswith(k + "="):
                return l.split("=", 1)[1].strip().strip("\"'")
    except OSError:
        pass
    return ""


def log(kind, uid, arg):
    ex("INSERT INTO events(ts,kind,user_id,arg) VALUES(?,?,?,?)", (int(time.time()), kind, uid, str(arg)[:200]))


# ---- texts ----
async def texts_get(req):
    d = {r["key"]: r["value"] for r in q("SELECT key,value FROM settings")}
    return web.json_response([{"key": k, "label": v, "value": d.get(k, "")} for k, v in TEXTS.items()])


async def texts_set(req):
    need(req)
    d = await req.json()
    k = str(d.get("key"))
    if k not in TEXTS:
        return web.json_response({"ok": False}, status=400)
    ex("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
       (k, str(d.get("value", ""))[:4000]))
    log("web_text", 0, k)
    return web.json_response({"ok": True})


# ---- users ----
async def users_list(req):
    s = req.query.get("q", "").strip()[:40]
    if s:
        like = "%" + s + "%"
        rs = q("SELECT tg_id,name,username,balance,blocked FROM users WHERE CAST(tg_id AS TEXT)=? OR name LIKE ? "
               "OR username LIKE ? ORDER BY created DESC LIMIT 30", (s, like, like))
    else:
        rs = q("SELECT tg_id,name,username,balance,blocked FROM users ORDER BY created DESC LIMIT 30")
    return web.json_response(rs)


async def user_get(req):
    uid = int(req.query.get("id", 0))
    u = q("SELECT * FROM users WHERE tg_id=?", (uid,))
    if not u:
        return web.json_response({"ok": False}, status=404)
    return web.json_response({"u": u[0],
        "panels": q("SELECT id,nick,admin_username,expires,status,gb FROM panels WHERE user_id=? ORDER BY id DESC LIMIT 20", (uid,)),
        "sales": q("SELECT panel,kind,gb,price,created FROM sales WHERE user_id=? ORDER BY id DESC LIMIT 10", (uid,))})


async def user_balance(req):
    need(req)
    d = await req.json()
    uid, amt = int(d["id"]), int(d["amount"])
    if abs(amt) > 100000000 or amt == 0:
        return web.json_response({"ok": False}, status=400)
    ex("UPDATE users SET balance=balance+? WHERE tg_id=?", (amt, uid))
    log("web_balance", uid, amt)
    return web.json_response({"ok": True, "balance": q("SELECT balance FROM users WHERE tg_id=?", (uid,))[0]["balance"]})


async def user_block(req):
    need(req)
    uid = int((await req.json())["id"])
    ex("UPDATE users SET blocked=1-blocked WHERE tg_id=?", (uid,))
    log("web_block", uid, "")
    return web.json_response({"ok": True, "blocked": q("SELECT blocked FROM users WHERE tg_id=?", (uid,))[0]["blocked"]})


def _send(uid, text):
    data = urllib.parse.urlencode({"chat_id": uid, "text": text}).encode()
    r = urllib.request.urlopen("https://api.telegram.org/bot%s/sendMessage" % env("BOT_TOKEN"), data, timeout=20)
    return json.load(r).get("ok")


async def user_msg(req):
    need(req)
    d = await req.json()
    text = str(d.get("text", "")).strip()[:3500]
    if not text:
        return web.json_response({"ok": False}, status=400)
    try:
        ok = await asyncio.to_thread(_send, int(d["id"]), text)
    except Exception:
        ok = False
    return web.json_response({"ok": bool(ok)})


# ---- backup ----
def _snap():
    os.makedirs(BK, mode=0o700, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    a, b = sqlite3.connect(dbp()), sqlite3.connect(tmp)
    try:
        a.backup(b)
    finally:
        b.close()
        a.close()
    data = gzip.compress(open(tmp, "rb").read(), 6)
    os.remove(tmp)
    name = time.strftime("web-%Y%m%d-%H%M%S.db.gz")
    with open(os.path.join(BK, name), "wb") as f:
        f.write(data)
    os.chmod(os.path.join(BK, name), 0o600)
    return name, data


def _files():
    if not os.path.isdir(BK):
        return []
    fs = [f for f in os.listdir(BK) if f.endswith((".gz", ".zip", ".sql"))]
    fs.sort(key=lambda f: os.path.getmtime(os.path.join(BK, f)), reverse=True)
    return [{"name": f, "size": os.path.getsize(os.path.join(BK, f)), "ts": int(os.path.getmtime(os.path.join(BK, f)))} for f in fs[:30]]


async def bk_list(req):
    return web.json_response(_files())


async def bk_now(req):
    name, data = await asyncio.to_thread(_snap)
    log("web_backup", 0, name)
    return web.Response(body=data, headers={"Content-Type": "application/gzip",
                                            "Content-Disposition": 'attachment; filename="%s"' % name})


async def bk_get(req):
    n = os.path.basename(req.query.get("f", ""))
    if n not in [f["name"] for f in _files()]:
        raise web.HTTPNotFound()
    return web.FileResponse(os.path.join(BK, n), headers={"Content-Disposition": 'attachment; filename="%s"' % n})


PAGE = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>مدیریت بات</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b0b10;color:#e8e8f0;font-family:V,Vazirmatn,Tahoma,sans-serif;padding:18px;max-width:640px;margin:auto}
a{color:#a78bfa;text-decoration:none}h1{font-size:24px;margin:10px 0 14px}
.tabs{display:flex;gap:6px;background:#0f0f16;border:1px solid #26263a;border-radius:14px;padding:4px;margin-bottom:14px}
.tabs button{flex:1;padding:10px;border:0;border-radius:10px;background:none;color:#9a9aa8;font-family:inherit;font-size:14px;cursor:pointer}.tabs .on{background:#241f45;color:#c4b5fd}
.c{background:#14141c;border:1px solid #26263a;border-radius:18px;padding:14px;margin-bottom:10px}.lb{font-size:13px;color:#9a9aa8;margin-bottom:8px}
input,textarea{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #2a2a40;background:#0f0f16;color:#fff;font-family:inherit;font-size:15px}
textarea{min-height:150px;resize:vertical;line-height:1.7}
.bt{display:block;width:100%;padding:13px;border:0;border-radius:12px;background:linear-gradient(90deg,#6d4aff,#a78bfa);color:#fff;font-family:inherit;font-size:15px;cursor:pointer;margin-top:10px;text-align:center}
.bt.g{background:#2eaa5c}.bt.r{background:#d9424e}.bt.d{background:#1b1b28;border:1px solid #2a2a40;color:#c4b5fd}.bt:active{transform:scale(.97)}
.row{display:flex;gap:8px}.row>*{flex:1}.it{display:flex;justify-content:space-between;align-items:center;padding:13px;border-radius:14px;background:#14141c;border:1px solid #26263a;margin-bottom:8px;cursor:pointer}
.mu{color:#9a9aa8;font-size:12px}.mo{position:fixed;inset:0;background:#000a;display:flex;align-items:flex-end;justify-content:center;z-index:50}
.mo>div{background:#14141c;border:1px solid #2a2a40;border-radius:20px 20px 0 0;padding:18px;width:100%;max-width:640px;max-height:88vh;overflow:auto}
.kv{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #20202c;font-size:14px}
#ts{position:fixed;top:14px;left:50%;transform:translateX(-50%);background:#2eaa5c;color:#fff;padding:9px 18px;border-radius:12px;display:none;z-index:99}
</style></head><body><a href="./">→ بازگشت به داشبورد</a><h1>مدیریت بات</h1><div id="ts"></div>
<div class="tabs"><button data-t="t" class="on">متن‌ها</button><button data-t="u">کاربران</button><button data-t="b">بکاپ</button></div>
<div id="v"></div>
<script>
const H={'Content-Type':'application/json','X-Req':'1'},$=s=>document.querySelector(s),fa=n=>Number(n||0).toLocaleString('fa-IR');
const api=(p,b)=>fetch('api/'+p,b?{method:'POST',headers:H,body:JSON.stringify(b)}:{}).then(r=>r.json());
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const dt=t=>t?new Date(t*1000).toLocaleString('fa-IR'):'-';
function toast(m,bad){const t=$('#ts');t.textContent=m;t.style.background=bad?'#d9424e':'#2eaa5c';t.style.display='block';setTimeout(()=>t.style.display='none',1800)}
function modal(h){const m=document.createElement('div');m.className='mo';m.innerHTML='<div>'+h+'</div>';m.onclick=e=>{if(e.target===m)m.remove()};document.body.appendChild(m);return m}
async function T(){const d=await api('texts');const v=$('#v');v.innerHTML='';
d.forEach(x=>{const c=document.createElement('div');c.className='c';c.innerHTML='<div class="lb"></div><textarea></textarea><button class="bt">ذخیره</button>';
c.querySelector('.lb').textContent=x.label;const ta=c.querySelector('textarea');ta.value=x.value;if(x.key==='shop')ta.style.minHeight='50px';
c.querySelector('button').onclick=async()=>{const r=await api('texts',{key:x.key,value:ta.value});toast(r.ok?'ذخیره شد':'خطا',!r.ok)};v.appendChild(c)})}
async function U(q){const v=$('#v');if(q===undefined){v.innerHTML='<input id="sq" placeholder="جستجو: آیدی، نام یا یوزرنیم"><div id="ul" style="margin-top:12px"></div>';
let tm;$('#sq').oninput=e=>{clearTimeout(tm);tm=setTimeout(()=>U(e.target.value),350)}}
const d=await api('users?q='+encodeURIComponent(q||''));const l=$('#ul');l.innerHTML='';
d.forEach(u=>{const x=document.createElement('div');x.className='it';x.innerHTML='<span></span><span class="mu"></span>';
x.firstChild.textContent=(u.name||'?')+(u.blocked?' 🚫':'');x.lastChild.textContent=fa(u.balance)+' تومان • '+u.tg_id;x.onclick=()=>UD(u.tg_id);l.appendChild(x)});
if(!d.length)l.innerHTML='<div class="mu">کاربری پیدا نشد</div>'}
async function UD(id){const d=await api('user?id='+id),u=d.u;
const m=modal('<h3>'+esc(u.name||'?')+'</h3><div class="kv"><span>آیدی</span><b>'+u.tg_id+'</b></div><div class="kv"><span>یوزرنیم</span><b>'+esc(u.username||'-')+'</b></div>'+
'<div class="kv"><span>موجودی</span><b id="bl">'+fa(u.balance)+' تومان</b></div><div class="kv"><span>وضعیت</span><b id="st">'+(u.blocked?'🚫 مسدود':'✅ فعال')+'</b></div>'+
'<div class="lb" style="margin-top:12px">تغییر موجودی (مثبت = شارژ، منفی = کسر)</div><div class="row"><input id="am" type="number" placeholder="مثلاً 50000 یا -20000"><button class="bt" id="ab" style="margin:0">اعمال</button></div>'+
'<div class="lb" style="margin-top:12px">ارسال پیام از طرف بات</div><textarea id="mt" style="min-height:80px"></textarea><button class="bt d" id="mb">ارسال پیام</button>'+
'<button class="bt '+(u.blocked?'g':'r')+'" id="bb">'+(u.blocked?'رفع مسدودی':'مسدود کردن')+'</button>'+
'<div class="lb" style="margin-top:14px">پنل‌ها ('+d.panels.length+')</div><div id="pn"></div><div class="lb" style="margin-top:10px">خریدهای اخیر</div><div id="sl"></div>');
const pn=m.querySelector('#pn');d.panels.forEach(p=>{const e=document.createElement('div');e.className='kv';e.innerHTML='<span></span><span class="mu"></span>';e.firstChild.textContent=(p.nick||p.admin_username||'#'+p.id);e.lastChild.textContent=(p.gb||0)+' گیگ • '+dt(p.expires);pn.appendChild(e)});
const sl=m.querySelector('#sl');d.sales.forEach(s=>{const e=document.createElement('div');e.className='kv';e.innerHTML='<span></span><span class="mu"></span>';e.firstChild.textContent=s.kind+' '+(s.gb||'')+' گیگ';e.lastChild.textContent=fa(s.price)+' • '+dt(s.created);sl.appendChild(e)});
m.querySelector('#ab').onclick=async()=>{const a=parseInt(m.querySelector('#am').value);if(!a)return;if(!confirm('موجودی '+u.tg_id+' به اندازه‌ی '+fa(a)+' تغییر کند؟'))return;
const r=await api('user/balance',{id:u.tg_id,amount:a});if(r.ok){m.querySelector('#bl').textContent=fa(r.balance)+' تومان';m.querySelector('#am').value='';toast('اعمال شد')}else toast('خطا',1)};
m.querySelector('#bb').onclick=async e=>{if(!confirm('مطمئنی؟'))return;const r=await api('user/block',{id:u.tg_id});if(r.ok){m.remove();toast(r.blocked?'مسدود شد':'رفع مسدودی شد')}};
m.querySelector('#mb').onclick=async()=>{const t=m.querySelector('#mt').value;if(!t.trim())return;const r=await api('user/msg',{id:u.tg_id,text:t});toast(r.ok?'ارسال شد':'ارسال نشد (کاربر بات را بلاک کرده؟)',!r.ok);if(r.ok)m.querySelector('#mt').value=''}}
async function B(){const d=await api('backups');const v=$('#v');
v.innerHTML='<a class="bt g" href="api/backup/now">📦 گرفتن و دانلود بکاپ جدید</a><div class="mu" style="margin:10px 2px">بکاپ دیتابیس (gz). برای بازگردانی از منوی pgbot گزینه ۶ استفاده کن.</div><div id="bl"></div>';
d.forEach(f=>{const a=document.createElement('a');a.className='it';a.href='api/backup/get?f='+encodeURIComponent(f.name);a.innerHTML='<span></span><span class="mu"></span>';
a.firstChild.textContent=f.name;a.lastChild.textContent=Math.max(1,Math.round(f.size/1024))+' KB • '+dt(f.ts);$('#bl').appendChild(a)})}
function go(t){document.querySelectorAll('.tabs button').forEach(b=>b.classList.toggle('on',b.dataset.t===t));({t:T,u:()=>U(),b:B})[t]()}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>go(b.dataset.t));go('t');
</script></body></html>"""


async def page(req):
    return web.Response(text=PAGE, content_type="text/html")


def install(sub):
    r = sub.router
    r.add_get("/manage", page)
    r.add_get("/api/texts", texts_get)
    r.add_post("/api/texts", texts_set)
    r.add_get("/api/users", users_list)
    r.add_get("/api/user", user_get)
    r.add_post("/api/user/balance", user_balance)
    r.add_post("/api/user/block", user_block)
    r.add_post("/api/user/msg", user_msg)
    r.add_get("/api/backups", bk_list)
    r.add_get("/api/backup/now", bk_now)
    r.add_get("/api/backup/get", bk_get)
