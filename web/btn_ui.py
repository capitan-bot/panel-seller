import glob
import os
import re
import sqlite3

from aiohttp import web

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STYLES = ("", "primary", "success", "danger", "none")


def dbp():
    f = glob.glob(os.path.join(ROOT, "data", "*.db")) + glob.glob(os.path.join(ROOT, "data", "*.sqlite3"))
    return f[0]


def default_labels():
    """Read SECTIONS from bot/btnadm.py without importing the bot."""
    src = open(os.path.join(ROOT, "bot", "btnadm.py"), encoding="utf-8").read()
    m = re.search(r"^SECTIONS\s*=\s*(\[.*?^\])", src, re.S | re.M)
    ns = {}
    exec("SECTIONS = " + m.group(1), {}, ns)
    return ns["SECTIONS"]


def read():
    c = sqlite3.connect(dbp(), timeout=10)
    c.row_factory = sqlite3.Row
    try:
        main = [dict(r) for r in c.execute("SELECT key,title,style,enabled FROM buttons ORDER BY sort")]
        ov = {r["key"]: dict(r) for r in c.execute("SELECT key,title,style FROM ubtn")}
    finally:
        c.close()
    secs = []
    for name, labels in default_labels():
        secs.append({"name": name, "items": [
            {"key": t, "title": (ov.get(t, {}).get("title") or ""), "style": ov.get(t, {}).get("style", "")}
            for t in labels]})
    return {"main": main, "sections": secs}


async def api_get(req):
    return web.json_response(read())


async def api_save(req):
    try:
        data = await req.json()
        main, secs = data["main"], data["sections"]
        assert isinstance(main, list) and len(main) < 100 and isinstance(secs, list)
    except Exception:
        return web.json_response({"ok": False}, status=400)
    allowed = {t for _, ls in default_labels() for t in ls}
    c = sqlite3.connect(dbp(), timeout=10)
    try:
        for i, d in enumerate(main):
            t = str(d.get("title", "")).strip()[:64]
            if not t:
                continue
            s = d.get("style", "")
            s = s if s in STYLES[:4] else ""
            c.execute("UPDATE buttons SET title=?,style=?,enabled=?,sort=? WHERE key=?",
                      (t, s, 1 if d.get("enabled") else 0, i, str(d.get("key", ""))))
        for sec in secs:
            for d in sec.get("items", []):
                k = str(d.get("key", ""))
                if k not in allowed:
                    continue
                t = str(d.get("title", "")).strip()[:64]
                s = d.get("style", "")
                s = s if s in STYLES else ""
                c.execute("INSERT INTO ubtn(key) VALUES(?) ON CONFLICT(key) DO NOTHING", (k,))
                c.execute("UPDATE ubtn SET title=?,style=? WHERE key=?", (t, s, k))
        c.commit()
    finally:
        c.close()
    return web.json_response({"ok": True})


PAGE = """<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>دکمه‌های بات</title><style>
*{box-sizing:border-box}body{margin:0;background:#0b0b10;color:#e8e8f0;font-family:V,Vazirmatn,Tahoma,sans-serif;padding:18px 18px 90px;max-width:640px;margin:auto}
a.back{color:#a78bfa;text-decoration:none;font-size:14px}h1{font-size:24px;margin:10px 0 4px}.sub{color:#9a9aa8;font-size:13px;margin-bottom:14px}
.tabs{display:flex;gap:6px;background:#0f0f16;border:1px solid #26263a;border-radius:14px;padding:4px;margin-bottom:14px}
.tabs button{flex:1;padding:10px;border:0;border-radius:10px;background:none;color:#9a9aa8;font-family:inherit;font-size:14px;cursor:pointer}.tabs .on{background:#241f45;color:#c4b5fd}
.h{color:#a78bfa;font-size:14px;margin:18px 4px 8px}
.c{background:#14141c;border:1px solid #26263a;border-radius:18px;padding:14px;margin-bottom:10px;transition:.2s}.c.off{opacity:.5}
.r{display:flex;gap:8px;align-items:center}.r+.r{margin-top:10px}.lb{font-size:12px;color:#9a9aa8;margin-bottom:6px}
input[type=text]{flex:1;min-width:0;padding:11px 12px;border-radius:12px;border:1px solid #2a2a40;background:#0f0f16;color:#fff;font-family:inherit;font-size:15px}
.ar{display:flex;flex-direction:column;gap:4px}.ar button{border:1px solid #2a2a40;background:#1b1b28;color:#c4b5fd;border-radius:10px;width:38px;height:30px;font-size:15px;cursor:pointer}
.ar button:active{transform:scale(.9)}
.col{display:flex;gap:6px;flex:1}.col b{flex:1;height:34px;border-radius:10px;border:2px solid transparent;cursor:pointer;font-size:11px;display:flex;align-items:center;justify-content:center;color:#fff;transition:.15s;text-align:center}
.col b.on{border-color:#fff;box-shadow:0 0 12px #fff3}.s0{background:#2a2a38}.s1{background:#2b7de9}.s2{background:#2eaa5c}.s3{background:#d9424e}.s4{background:#15151d;border:1px dashed #444}
.tg{font-size:13px;color:#9a9aa8;display:flex;align-items:center;gap:6px;cursor:pointer}
.ac{background:#14141c;border:1px solid #26263a;border-radius:18px;margin-bottom:10px;overflow:hidden}.ac>.hd{display:flex;align-items:center;justify-content:space-between;padding:15px 16px;cursor:pointer;font-size:15px;color:#e8e8f0}.ac>.hd small{color:#9a9aa8;font-size:12px;margin-inline-start:8px}.ac>.hd i{font-style:normal;color:#a78bfa;transition:.2s}.ac.open>.hd i{transform:rotate(180deg)}.ac>.bd{display:none;padding:0 12px 6px}.ac.open>.bd{display:block}.ac .c{background:#0f0f16}.sg{display:grid;grid-template-columns:1fr 1fr;gap:10px}.sb{padding:18px 10px;border-radius:16px;border:1px solid #2a2a40;background:#14141c;color:#e8e8f0;font-family:inherit;font-size:14px;cursor:pointer;text-align:center;transition:.15s}.sb:active{transform:scale(.96)}.sb small{display:block;color:#9a9aa8;font-size:11px;margin-top:4px}.bk{background:none;border:0;color:#a78bfa;font-family:inherit;font-size:14px;cursor:pointer;padding:4px 2px;margin-bottom:10px}.tb{display:flex;flex-direction:column;gap:8px}.tb button{padding:14px;border-radius:14px;border:2px solid transparent;color:#fff;font-family:inherit;font-size:15px;cursor:pointer;transition:.15s;position:relative}.tb button:active{transform:scale(.97)}.tb button.ed:after{content:'✎';position:absolute;left:12px;opacity:.7;font-size:13px}.mo{position:fixed;inset:0;background:#000a;display:flex;align-items:flex-end;justify-content:center;z-index:50}.mo>div{background:#14141c;border:1px solid #2a2a40;border-radius:20px 20px 0 0;padding:18px;width:100%;max-width:640px}.mo .lb{margin-bottom:8px}.mo .r{margin-top:12px}.mo .ok{width:100%;margin-top:14px;padding:13px;border:0;border-radius:12px;background:#6d4aff;color:#fff;font-family:inherit;font-size:15px;cursor:pointer}.sv{position:fixed;bottom:14px;left:18px;right:18px;max-width:604px;margin:auto;padding:15px;border:0;border-radius:14px;background:linear-gradient(90deg,#6d4aff,#a78bfa);color:#fff;font-family:inherit;font-size:16px;cursor:pointer;box-shadow:0 6px 24px #6d4aff55}
.sv:active{transform:scale(.97)}
</style></head><body><a class="back" href="./">→ بازگشت به داشبورد</a><h1>دکمه‌های بات</h1>
<div class="sub">اسم و رنگ دکمه‌ها. بعد از ذخیره، چند ثانیه بعد در بات اعمال می‌شود. خالی گذاشتن اسم یعنی نام پیش‌فرض.</div>
<div class="tabs"><button class="on" data-t="m">منوی اصلی</button><button data-t="o">بقیه‌ی دکمه‌ها</button></div>
<div id="l"></div><button class="sv" id="sv">ذخیره تغییرات</button>
<script>
let D={main:[],sections:[]},T='m',SEC=-1;
const N=['پیش‌فرض','آبی','سبز','قرمز','بدون رنگ'],V=['','primary','success','danger','none'];
function cols(d,rd,max){const si=Math.max(0,V.indexOf(d.style));
return '<div class="col">'+V.slice(0,max).map((v,k)=>'<b class="s'+k+(k===si?' on':'')+'" data-s="'+k+'">'+N[k]+'</b>').join('')+'</div>'}
function bindCols(c,d){c.querySelectorAll('[data-s]').forEach(b=>b.onclick=()=>{d.style=V[+b.dataset.s];R()})}
function R(){const l=document.getElementById('l');l.innerHTML='';
if(T==='m'){D.main.forEach((d,i)=>{const c=document.createElement('div');c.className='c'+(d.enabled?'':' off');
c.innerHTML='<div class="r"><div class="ar"><button data-m="-1">▲</button><button data-m="1">▼</button></div><input type="text" maxlength="64"><label class="tg"><input type="checkbox" '+(d.enabled?'checked':'')+'>فعال</label></div><div class="r">'+cols(d,0,4)+'</div>';
const inp=c.querySelector('input[type=text]');inp.value=d.title;inp.oninput=()=>d.title=inp.value;
c.querySelector('input[type=checkbox]').onchange=e=>{d.enabled=e.target.checked?1:0;c.classList.toggle('off',!d.enabled)};
c.querySelectorAll('[data-m]').forEach(b=>b.onclick=()=>{const j=i+ +b.dataset.m;if(j<0||j>=D.main.length)return;[D.main[i],D.main[j]]=[D.main[j],D.main[i]];R()});
bindCols(c,d);l.appendChild(c)})}
else if(SEC<0){const g=document.createElement('div');g.className='sg';
D.sections.forEach((sec,si)=>{const x=document.createElement('button');x.className='sb';
x.textContent=sec.name;const sm=document.createElement('small');sm.textContent=sec.items.length+' دکمه';x.appendChild(sm);
x.onclick=()=>{SEC=si;R();window.scrollTo(0,0)};g.appendChild(x)});l.appendChild(g)}
else{const sec=D.sections[SEC];const bk=document.createElement('button');bk.className='bk';bk.textContent='→ بخش‌ها';
bk.onclick=()=>{SEC=-1;R()};l.appendChild(bk);
const h=document.createElement('div');h.className='h';h.textContent=sec.name;l.appendChild(h);
const tb=document.createElement('div');tb.className='tb';
sec.items.forEach(d=>{const x=document.createElement('button');x.className='ed s'+Math.max(0,V.indexOf(d.style));
x.textContent=d.title||d.key;x.onclick=()=>edit(d);tb.appendChild(x)});l.appendChild(tb)}}
function edit(d){const m=document.createElement('div');m.className='mo';
m.innerHTML='<div><div class="lb"></div><div class="r"><input type="text" maxlength="64"></div><div class="r">'+cols(d,0,5)+'</div><button class="ok">تأیید</button></div>';
m.querySelector('.lb').textContent='پیش‌فرض: '+d.key;
const inp=m.querySelector('input');inp.placeholder=d.key;inp.value=d.title;inp.oninput=()=>d.title=inp.value;
m.querySelectorAll('[data-s]').forEach(bt=>bt.onclick=()=>{d.style=V[+bt.dataset.s];m.querySelectorAll('[data-s]').forEach(z=>z.classList.toggle('on',z===bt))});
m.querySelector('.ok').onclick=()=>{m.remove();R()};
m.onclick=e=>{if(e.target===m){m.remove();R()}};document.body.appendChild(m)}
document.querySelectorAll('.tabs button').forEach(b=>b.onclick=()=>{T=b.dataset.t;SEC=-1;document.querySelectorAll('.tabs button').forEach(x=>x.classList.toggle('on',x===b));R();window.scrollTo(0,0)});
fetch('api/buttons').then(r=>r.json()).then(j=>{D=j;R()});
document.getElementById('sv').onclick=async e=>{const b=e.target;b.textContent='در حال ذخیره...';
const r=await fetch('api/buttons',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(D)});
b.textContent=r.ok?'✓ ذخیره شد':'خطا در ذخیره';setTimeout(()=>b.textContent='ذخیره تغییرات',1600)};
</script></body></html>"""


async def page(req):
    return web.Response(text=PAGE, content_type="text/html")


def install(sub):
    sub.router.add_get("/buttons", page)
    sub.router.add_get("/api/buttons", api_get)
    sub.router.add_post("/api/buttons", api_save)
