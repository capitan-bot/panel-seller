import re
import secrets
import time

from aiohttp import web

from .more_ui import q, ex, need, log


async def lst(req):
    return web.json_response(q("SELECT * FROM codes ORDER BY id DESC LIMIT 200"))


async def new(req):
    need(req)
    d = await req.json()
    kind = d.get("kind")
    code = str(d.get("code", "")).strip().upper()
    if not code or code == "AUTO":
        code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
    try:
        value, mx, days, minp = [int(d.get(k) or 0) for k in ("value", "max_uses", "days", "min_price")]
    except Exception:
        return web.json_response({"ok": False, "err": "مقدارها باید عدد باشند"}, status=400)
    if kind not in ("percent", "amount", "gift") or not re.fullmatch(r"[A-Z0-9_-]{3,24}", code):
        return web.json_response({"ok": False, "err": "کد فقط حروف انگلیسی، عدد، _ و - (۳ تا ۲۴ کاراکتر)"}, status=400)
    if value <= 0 or min(mx, days, minp) < 0 or (kind == "percent" and value > 100):
        return web.json_response({"ok": False, "err": "مقدار نامعتبر است"}, status=400)
    exp = int(time.time()) + days * 86400 if days else 0
    try:
        ex("INSERT INTO codes(code,kind,value,max_uses,expires,min_price,created) VALUES(?,?,?,?,?,?,?)",
           (code, kind, value, mx, exp, 0 if kind == "gift" else minp, int(time.time())))
    except Exception:
        return web.json_response({"ok": False, "err": "این کد قبلاً ساخته شده"}, status=400)
    log("web_code_new", 0, code)
    return web.json_response({"ok": True, "code": code})


async def toggle(req):
    need(req)
    cid = int((await req.json())["id"])
    ex("UPDATE codes SET active=1-active WHERE id=?", (cid,))
    log("web_code_toggle", 0, cid)
    return web.json_response({"ok": True})


async def delete(req):
    need(req)
    cid = int((await req.json())["id"])
    ex("DELETE FROM code_uses WHERE code_id=?", (cid,))
    ex("DELETE FROM codes WHERE id=?", (cid,))
    log("web_code_del", 0, cid)
    return web.json_response({"ok": True})


PAGE = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>کد تخفیف و هدیه</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b0b10;color:#e8e8f0;font-family:V,Vazirmatn,Tahoma,sans-serif;padding:18px;max-width:640px;margin:auto}
a{color:#a78bfa;text-decoration:none}h1{font-size:24px;margin:10px 0 14px}
.c{background:#14141c;border:1px solid #26263a;border-radius:18px;padding:14px;margin-bottom:10px}.c.off{opacity:.5}
.lb{font-size:12px;color:#9a9aa8;margin:10px 0 6px}.mu{color:#9a9aa8;font-size:12px}
input,select{width:100%;padding:11px 12px;border-radius:12px;border:1px solid #2a2a40;background:#0f0f16;color:#fff;font-family:inherit;font-size:15px}
.bt{display:block;width:100%;padding:13px;border:0;border-radius:12px;background:linear-gradient(90deg,#6d4aff,#a78bfa);color:#fff;font-family:inherit;font-size:15px;cursor:pointer;margin-top:12px}
.sm{padding:8px 14px;border-radius:10px;border:1px solid #2a2a40;background:#1b1b28;color:#c4b5fd;font-family:inherit;cursor:pointer;font-size:13px}.sm.r{color:#f87171;border-color:#5b2a33;background:#2a1418}
.row{display:flex;gap:8px;align-items:center;justify-content:space-between}.g2{display:grid;grid-template-columns:1fr 1fr;gap:8px}
code{background:#0f0f16;padding:3px 8px;border-radius:8px;font-size:15px;direction:ltr;display:inline-block}
#ts{position:fixed;top:14px;left:50%;transform:translateX(-50%);background:#2eaa5c;color:#fff;padding:9px 18px;border-radius:12px;display:none;z-index:99}
</style></head><body><a href="./">→ بازگشت به داشبورد</a><h1>🎟 کد تخفیف و هدیه</h1><div id="ts"></div>
<div class="c"><b>ساخت کد جدید</b>
<div class="lb">نوع</div><select id="k"><option value="percent">تخفیف درصدی</option><option value="amount">تخفیف مبلغی (تومان)</option><option value="gift">کد هدیه (شارژ کیف پول)</option></select>
<div class="lb">خود کد (خالی = تصادفی)</div><input id="cd" placeholder="مثلاً OFF20" style="direction:ltr">
<div class="g2"><div><div class="lb" id="vl">درصد تخفیف</div><input id="v" type="number"></div><div><div class="lb">سقف استفاده (۰ = نامحدود)</div><input id="m" type="number" value="0"></div></div>
<div class="g2"><div><div class="lb">اعتبار به روز (۰ = بدون انقضا)</div><input id="d" type="number" value="0"></div><div id="mpw"><div class="lb">حداقل خرید (تومان)</div><input id="mp" type="number" value="0"></div></div>
<button class="bt" id="mk">ساخت کد</button></div>
<div id="l"></div>
<script>
const H={'Content-Type':'application/json','X-Req':'1'},$=s=>document.querySelector(s),fa=n=>Number(n||0).toLocaleString('fa-IR');
const api=(p,b)=>fetch('api/'+p,b?{method:'POST',headers:H,body:JSON.stringify(b)}:{}).then(r=>r.json());
function toast(m,bad){const t=$('#ts');t.textContent=m;t.style.background=bad?'#d9424e':'#2eaa5c';t.style.display='block';setTimeout(()=>t.style.display='none',2200)}
const KN={percent:'تخفیف درصدی',amount:'تخفیف مبلغی',gift:'کد هدیه'};
$('#k').onchange=()=>{const k=$('#k').value;$('#vl').textContent=k==='percent'?'درصد تخفیف':'مبلغ (تومان)';$('#mpw').style.display=k==='gift'?'none':'block'};
async function L(){const d=await api('codes'),l=$('#l');l.innerHTML='';const now=Date.now()/1000;
d.forEach(r=>{const dead=!r.active||(r.expires&&r.expires<now)||(r.max_uses&&r.used>=r.max_uses);
const c=document.createElement('div');c.className='c'+(dead?' off':'');
c.innerHTML='<div class="row"><code></code><span class="mu"></span></div><div class="mu" style="margin:8px 0" id="i"></div><div class="row"><button class="sm" id="t"></button><button class="sm r" id="x">حذف</button></div>';
c.querySelector('code').textContent=r.code;
c.querySelector('.row .mu').textContent=(r.kind==='gift'?'🎁 ':'🎟 ')+KN[r.kind];
c.querySelector('#i').textContent=(r.kind==='percent'?r.value+'٪':fa(r.value)+' تومان')+' • استفاده '+r.used+'/'+(r.max_uses||'∞')+' • '+(r.expires?'تا '+new Date(r.expires*1000).toLocaleDateString('fa-IR'):'بدون انقضا')+(r.min_price?' • حداقل '+fa(r.min_price):'');
const t=c.querySelector('#t');t.textContent=r.active?'غیرفعال کردن':'فعال کردن';t.onclick=async()=>{await api('code/toggle',{id:r.id});L()};
c.querySelector('#x').onclick=async()=>{if(confirm('کد '+r.code+' حذف شود؟')){await api('code/delete',{id:r.id});L()}};l.appendChild(c)});
if(!d.length)l.innerHTML='<div class="mu">هنوز کدی نساخته‌ای</div>'}
$('#mk').onclick=async()=>{const r=await api('code/new',{kind:$('#k').value,code:$('#cd').value,value:$('#v').value,max_uses:$('#m').value,days:$('#d').value,min_price:$('#mp').value});
if(r.ok){toast('ساخته شد: '+r.code);$('#cd').value='';$('#v').value='';L()}else toast(r.err||'خطا',1)};
L();
</script></body></html>"""


async def page(req):
    return web.Response(text=PAGE, content_type="text/html")


def install(sub):
    r = sub.router
    r.add_get("/codes", page)
    r.add_get("/api/codes", lst)
    r.add_post("/api/code/new", new)
    r.add_post("/api/code/toggle", toggle)
    r.add_post("/api/code/delete", delete)
