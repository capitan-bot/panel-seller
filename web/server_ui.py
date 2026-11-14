from __future__ import annotations

import asyncio
import json

from aiohttp import web

from . import app as A
from . import pages as P

_pg: dict = {}

CSS = r"""<style>
.sh{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;margin-bottom:16px}
.live{display:inline-flex;align-items:center;gap:8px;font-size:13px;color:var(--mu)}
.live i{width:9px;height:9px;border-radius:50%;background:#34d399;animation:pl 1.8s infinite}
@keyframes pl{0%{box-shadow:0 0 0 0 #34d39988}70%{box-shadow:0 0 0 10px #34d39900}100%{box-shadow:0 0 0 0 #34d39900}}
.rings{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:14px;margin-bottom:18px}
.rc{position:relative;overflow:hidden;text-align:center;padding:22px 12px 18px;border-radius:24px;border:1px solid #262633;background:linear-gradient(165deg,#181822,#101015)}
.rc:before{content:"";position:absolute;inset:-40% -20% auto;height:70%;background:radial-gradient(closest-side,#7c5cf033,transparent);pointer-events:none}
.rg{position:relative;width:150px;height:150px;margin:0 auto 10px}
.rg svg{width:100%;height:100%;transform:rotate(-90deg)}
.rg circle{fill:none;stroke-width:10;stroke-linecap:round}
.rg .tr{stroke:#23232f}
.rg .pg{transition:stroke-dashoffset 1.3s cubic-bezier(.22,1,.36,1),filter .4s}
.ct{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px}
.ct b{font-size:28px}.ct span{font-size:20px;opacity:.85}
.lb{font-weight:700}.sb{color:var(--mu);font-size:13px;margin-top:4px;min-height:18px}
.chips{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:18px}
.ch{background:#16161f;border:1px solid #262633;border-radius:14px;padding:10px 14px;font-size:14px;min-width:96px}
.ch small{color:var(--mu)}.ch b{display:block;font-size:19px;margin-top:2px}
.nodes{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px}
.nd{padding:18px;border-radius:20px;border:1px solid #262633;background:linear-gradient(165deg,#181822,#101015)}
.nd h3{margin:0 0 4px;display:flex;align-items:center;gap:8px;font-size:17px}
.nd .sub{margin-bottom:0}.dot{width:10px;height:10px;border-radius:50%;display:inline-block}
.vs{display:flex;flex-wrap:wrap;gap:6px;margin-top:10px}
.vs span{background:#241f45;color:#c4b5fd;padding:3px 10px;border-radius:99px;font-size:12px}
.er{background:#331818;color:var(--dn);padding:12px;border-radius:14px;margin-bottom:14px;direction:ltr;text-align:left;font-size:13px}
details{margin-top:18px}summary{cursor:pointer;color:var(--mu)}
pre{white-space:pre-wrap;word-break:break-all;direction:ltr;text-align:left;font-size:12px;color:#c8c8d4}
</style>"""

HTML = r"""
<div class="sh"><div class="sub" style="margin:0" dir="ltr">__URL__</div>
<div class="live"><i></i> زنده · <span id="tm">...</span> <span id="ver"></span></div></div>
<div id="err"></div><div class="rings" id="rings"></div><div class="chips" id="chips"></div>
<h2>نودها <span id="nn" class="chip"></span></h2>
<div class="nodes" id="nodes"><div class="card">در حال بارگذاری...</div></div>
<details><summary>داده‌های خام (برای عیب‌یابی)</summary><pre id="raw"></pre></details>
<br><a class="btn" href="/panels">بازگشت</a>
<script>
(function(){
const SID=__SID__,CIRC=2*Math.PI*54,R={};
const $=s=>document.querySelector(s);
const fa=(n,d)=>Number(n).toLocaleString('fa-IR',{maximumFractionDigits:d||0});
const E=s=>String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function flat(o,p,out){out=out||{};p=p||'';for(const k in o){const v=o[k];if(v&&typeof v==='object'&&!Array.isArray(v))flat(v,p+k+'.',out);else out[(p+k).toLowerCase()]=v}return out}
function num(f,re){for(const k in f){if(re.test(k)&&typeof f[k]==='number')return f[k]}return null}
const bytes=b=>b==null?'—':b>=Math.pow(2,30)?fa(b/Math.pow(2,30),1)+' GB':b>=Math.pow(2,20)?fa(b/Math.pow(2,20),1)+' MB':fa(b/1024,0)+' KB';
const col=p=>p<65?['#34d399','#22d3ee']:p<85?['#fbbf24','#f59e0b']:['#f87171','#ef4444'];
function tween(el,to){const from=parseFloat(el.dataset.v||'0');el.dataset.v=to;const t0=performance.now();(function f(t){const k=Math.min(1,(t-t0)/900),e=1-Math.pow(1-k,3);el.textContent=fa(from+(to-from)*e)+'٪';if(k<1)requestAnimationFrame(f)})(t0)}
function ring(key,label,pct,sub,icon){
 let r=R[key];
 if(!r){const d=document.createElement('div');d.className='rc';
  d.innerHTML='<div class="rg"><svg viewBox="0 0 120 120"><defs><linearGradient id="g'+key+'" x1="0" y1="0" x2="1" y2="1"><stop offset="0"/><stop offset="1"/></linearGradient></defs><circle class="tr" cx="60" cy="60" r="54"/><circle class="pg" cx="60" cy="60" r="54" stroke="url(#g'+key+')" style="stroke-dasharray:'+CIRC+';stroke-dashoffset:'+CIRC+'"/></svg><div class="ct"><b>۰٪</b><span></span></div></div><div class="lb"></div><div class="sb"></div>';
  $('#rings').appendChild(d);
  r=R[key]={d:d,pg:d.querySelector('.pg'),b:d.querySelector('b'),st:d.querySelectorAll('stop')};
  void r.pg.getBoundingClientRect();}
 const p=pct==null?0:Math.max(0,Math.min(100,pct)),c=col(p);
 r.st[0].setAttribute('stop-color',c[0]);r.st[1].setAttribute('stop-color',c[1]);
 r.pg.style.filter='drop-shadow(0 0 7px '+c[0]+'99)';
 requestAnimationFrame(function(){r.pg.style.strokeDashoffset=CIRC*(1-p/100)});
 if(pct==null){r.b.textContent='—';r.b.dataset.v=0}else tween(r.b,pct);
 r.d.querySelector('.ct span').textContent=icon;r.d.querySelector('.lb').textContent=label;r.d.querySelector('.sb').textContent=sub;
}
function render(d){
 const f=flat(d.stats||{});
 $('#err').innerHTML=(d.err&&(d.err.stats||d.err.nodes))?'<div class="er">'+E((d.err.stats||'')+' '+(d.err.nodes||''))+'</div>':'';
 const cpu=num(f,/cpu.*(usage|percent|load|used)/),cores=num(f,/cpu.*(core|count|num)/);
 const mu=num(f,/(mem|ram).*used/),mt=num(f,/(mem|ram).*total/),mp=num(f,/(mem|ram).*(percent|usage|pct)/);
 const mem=(mu!=null&&mt)?mu*100/mt:mp;
 const du=num(f,/disk.*used/),dt=num(f,/disk.*total/),dp=num(f,/disk.*(percent|usage|pct)/);
 const dsk=(du!=null&&dt)?du*100/dt:dp;
 const on=num(f,/online/),tot=num(f,/^total_?users?$/);
 if(cpu!=null)ring('cpu','پردازنده (CPU)',cpu,cores!=null?fa(cores)+' هسته':'','⚡');
 if(mem!=null)ring('mem','حافظه (RAM)',mem,(mu!=null&&mt)?bytes(mu)+' از '+bytes(mt):'','🧠');
 if(dsk!=null)ring('dsk','دیسک',dsk,(du!=null&&dt)?bytes(du)+' از '+bytes(dt):'','💾');
 if(on!=null&&tot)ring('onl','کاربران آنلاین',on*100/tot,fa(on)+' از '+fa(tot),'🟢');
 let ver='';for(const k in f){if(/version/.test(k)&&typeof f[k]==='string'){ver=f[k];break}}
 $('#ver').innerHTML=ver?'<span class="chip">'+E(ver)+'</span>':'';
 const C=[['کل کاربران',/^total_?users?$/],['آنلاین',/online/],['فعال',/^users_active$|^active_users$/],['منقضی',/expired/],['محدودشده',/limited/],['غیرفعال',/disabled/],['در انتظار',/on_hold/]];
 let h='';for(const x of C){const v=num(f,x[1]);if(v!=null)h+='<div class="ch"><small>'+x[0]+'</small><b>'+fa(v)+'</b></div>'}
 [['دانلود کل','incoming_bandwidth',''],['آپلود کل','outgoing_bandwidth',''],['سرعت دانلود','incoming_bandwidth_speed','/s'],['سرعت آپلود','outgoing_bandwidth_speed','/s']].forEach(function(x){if(typeof f[x[1]]==='number')h+='<div class="ch"><small>'+x[0]+'</small><b>'+bytes(f[x[1]])+x[2]+'</b></div>'});
 $('#chips').innerHTML=h;
 const nd=d.nodes;let nh='';
 (Array.isArray(nd)?nd:[]).forEach(function(n){
  const s=String(n.status||'').toLowerCase();
  const c=s==='connected'?'#34d399':(s==='connecting'?'#fbbf24':'#f87171');
  const vs=Object.keys(n).filter(function(k){return /version/i.test(k)&&n[k]}).map(function(k){return '<span>'+E(k.replace(/_/g,' '))+': '+E(n[k])+'</span>'}).join('');
  const ex=n.usage_coefficient!=null?'<span>ضریب: '+E(n.usage_coefficient)+'</span>':'';
  nh+='<div class="nd"><h3><i class="dot" style="background:'+c+';box-shadow:0 0 10px '+c+'"></i>'+E(n.name||n.id||'نود')+'</h3><div class="sub">'+E(n.address||'')+(n.port?':'+E(n.port):'')+'</div><div class="vs"><span>'+E(n.status||'—')+'</span>'+vs+ex+'</div>'+(n.message?'<div class="sub" style="margin-top:8px">'+E(String(n.message).slice(0,90))+'</div>':'')+'</div>';
 });
 $('#nodes').innerHTML=nh||'<div class="card">نودی ثبت نشده یا اطلاعاتی برنگشت.</div>';
 $('#nn').textContent=Array.isArray(nd)?fa(nd.length):'';
 $('#raw').textContent=JSON.stringify(d,null,1);
}
async function load(){
 try{const r=await fetch('/api/server/'+SID,{credentials:'same-origin'});
  if(r.status===401){location='/login';return}
  render(await r.json());$('#tm').textContent=new Date().toLocaleTimeString('fa-IR')}
 catch(e){$('#err').innerHTML='<div class="er">'+E(e)+'</div>'}
}
load();setInterval(load,10000);
})();
</script>"""


def clean(o):
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items() if not P.SECRET.search(str(k))}
    if isinstance(o, list):
        return [clean(x) for x in o]
    return o


async def get_pg(sid: int):
    r = A.q("SELECT id,url,username,password FROM servers WHERE id=?", (sid,))
    if not r:
        return None
    _, url, user, pw = r[0]
    key = (url, user, pw)
    hit = _pg.get(sid)
    if hit and hit[0] == key:
        return hit[1]
    from bot import config as C, db as D
    from bot.panel import PG
    pg = PG(url, user, D.dec(pw), C.VERIFY_SSL)
    _pg[sid] = (key, pg)
    return pg


async def api(req):
    sid = int(req.match_info["sid"])
    try:
        pg = await get_pg(sid)
        if pg is None:
            raise web.HTTPNotFound()
        st, nd = await asyncio.gather(asyncio.wait_for(pg.system_stats(), 25),
                                      asyncio.wait_for(pg.nodes(), 25), return_exceptions=True)
    except web.HTTPException:
        raise
    except Exception as e:
        st = nd = e
    out = {"stats": None if isinstance(st, Exception) else clean(st),
           "nodes": None if isinstance(nd, Exception) else clean(nd),
           "err": {"stats": repr(st) if isinstance(st, Exception) else None,
                   "nodes": repr(nd) if isinstance(nd, Exception) else None}}
    return web.json_response(out, dumps=lambda o: json.dumps(o, default=str))


async def server(req):
    sid = int(req.match_info["sid"])
    r = A.q("SELECT url FROM servers WHERE id=?", (sid,))
    if not r:
        raise web.HTTPNotFound()
    body = CSS + HTML.replace("__SID__", str(sid)).replace("__URL__", P.esc(r[0][0]))
    return P.page("panels", "اطلاعات سرور", body)


def install(app):
    app.router.add_get(r"/panels/server/{sid:\d+}", server)
    app.router.add_get(r"/api/server/{sid:\d+}", api)
