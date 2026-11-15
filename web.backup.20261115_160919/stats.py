from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from aiohttp import web

from . import app as A
from . import pages as P

D = 86400
LBL = {"active": "فعال", "expired": "منقضی", "disabled": "غیرفعال", "deleted": "حذف‌شده", "limited": "محدودشده"}

CSS = r"""<style>
.cg{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin:16px 0}
.cc{padding:18px;overflow:hidden}.cc h3{margin:0 0 12px;font-size:16px}.cc.wide{grid-column:1/-1}
.em{color:var(--mu);text-align:center;padding:24px 0}
.dn{display:flex;align-items:center;gap:18px;flex-wrap:wrap;justify-content:center}
.dw{position:relative;width:170px;height:170px;flex:none}.dw svg{width:100%;height:100%;transform:rotate(-90deg)}
.dw circle{fill:none;stroke-width:15}.dw .dt{stroke:#23232f}
.sg{transition:stroke-dasharray 1.1s cubic-bezier(.22,1,.36,1);cursor:pointer}.sg:hover{filter:brightness(1.3)}
.dc{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}
.dc b{font-size:20px}.dc small{color:var(--mu);font-size:12px}
.lg{flex:1;min-width:150px;display:flex;flex-direction:column;gap:7px}
.lgi{display:flex;align-items:center;gap:8px;font-size:13px}.lgi i{width:10px;height:10px;border-radius:50%;flex:none}
.lgi span{flex:1}.lgi small{color:var(--mu);min-width:44px;text-align:left}
.sv{width:100%;height:auto}.sv text{fill:#9a9aa8;font-size:13px}.ax{stroke:#2a2a33}.pt{fill:#a78bfa;opacity:0}.pt:hover{opacity:1}
.br{transform:scaleY(0);transition:transform .9s cubic-bezier(.22,1,.36,1)}.br:hover{filter:brightness(1.3)}
.hb{display:flex;flex-direction:column;gap:12px}.hl{display:flex;justify-content:space-between;font-size:13px;margin-bottom:5px;gap:8px}
.ht{height:10px;border-radius:99px;background:#23232f;overflow:hidden}
.hf{height:100%;width:0;border-radius:99px;transition:width 1.1s cubic-bezier(.22,1,.36,1)}
.spk{width:100%;height:34px;margin-top:6px}
</style>"""

JS = r"""
var PAL=['#a78bfa','#34d399','#fbbf24','#f87171','#22d3ee','#f472b6','#60a5fa','#fb923c','#a3e635','#94a3b8'];
function $(s){return document.querySelector(s)}
function fa(n,d){return Number(n).toLocaleString('fa-IR',{maximumFractionDigits:d||0})}
function E(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function tl(t,st){var d=new Date(t*1000);return st&&st<86400?d.toLocaleTimeString('fa-IR',{hour:'2-digit',minute:'2-digit',timeZone:'Asia/Tehran'}):d.toLocaleDateString('fa-IR',{day:'numeric',month:'short',timeZone:'Asia/Tehran'})}
function tf(t){return new Date(t*1000).toLocaleString('fa-IR',{dateStyle:'short',timeStyle:'short',timeZone:'Asia/Tehran'})}
var EM='<div class="em">داده‌ای برای نمایش نیست</div>';
function donut(c){var it=c.items||[],tot=0;it.forEach(function(x){tot+=x.v});if(!tot)return EM;
var C=2*Math.PI*46,off=0,seg='',lg='';
it.forEach(function(x,i){var f=x.v/tot,l=f*C,col=PAL[i%PAL.length];
seg+='<circle class="sg" cx="60" cy="60" r="46" stroke="'+col+'" data-l="'+l.toFixed(2)+'" data-c="'+C.toFixed(2)+'" style="stroke-dasharray:0 '+C.toFixed(2)+';stroke-dashoffset:'+(-off).toFixed(2)+'"><title>'+E(x.l)+': '+fa(x.v)+'</title></circle>';
off+=l;
lg+='<div class="lgi"><i style="background:'+col+'"></i><span>'+E(x.l)+'</span><b>'+fa(x.v)+'</b><small>٪'+fa(f*100,1)+'</small></div>'});
return '<div class="dn"><div class="dw"><svg viewBox="0 0 120 120"><circle class="dt" cx="60" cy="60" r="46"/>'+seg+'</svg><div class="dc"><b>'+fa(tot)+'</b><small>'+E(c.unit||'کل')+'</small></div></div><div class="lg">'+lg+'</div></div>'}
function bars(c){var s=c.items||c.s||[];if(!s.length)return EM;
var W=420,H=220,L=10,R=10,T=20,B=32,mx=1;s.forEach(function(a){mx=Math.max(mx,a.v)});
var n=s.length,bw=(W-L-R)/n,b='';
s.forEach(function(a,i){var h=(H-T-B)*a.v/mx,x=L+i*bw+bw*.16,y=H-B-h;
b+='<rect class="br" x="'+x.toFixed(1)+'" y="'+y.toFixed(1)+'" width="'+(bw*.68).toFixed(1)+'" height="'+Math.max(h,0).toFixed(1)+'" rx="'+Math.min(5,bw*.3).toFixed(1)+'" fill="url(#bgr)" style="transform-origin:0 '+(H-B)+'px"><title>'+E(a.l!=null?a.l:tl(a.t,c.step))+': '+fa(a.v)+(c.unit?' '+E(c.unit):'')+'</title></rect>'});
var ix=[0,Math.floor(n/3),Math.floor(2*n/3),n-1].filter(function(v,i,a){return a.indexOf(v)===i}),tk='';
ix.forEach(function(i){var a=s[i];tk+='<text x="'+(L+i*bw+bw/2).toFixed(1)+'" y="'+(H-9)+'" text-anchor="middle">'+E(a.l!=null?a.l:tl(a.t,c.step))+'</text>'});
return '<svg class="sv" viewBox="0 0 '+W+' '+H+'" dir="ltr"><defs><linearGradient id="bgr" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a78bfa"/><stop offset="1" stop-color="#6d4fe0"/></linearGradient></defs><line class="ax" x1="'+L+'" x2="'+(W-R)+'" y1="'+(H-B)+'" y2="'+(H-B)+'"/><text x="'+L+'" y="'+(T-6)+'">'+fa(mx)+'</text>'+b+tk+'</svg>'}
function area(c){var s=c.s||[];if(!s.length)return EM;
var st=c.step,W=480,H=230,L=14,R=14,T=18,B=34,mx=1;s.forEach(function(a){mx=Math.max(mx,a.v)});
function X(i){return L+(W-L-R)*(s.length>1?i/(s.length-1):.5)}function Y(v){return T+(H-T-B)*(1-v/mx)}
var ln=s.map(function(a,i){return (i?'L':'M')+X(i).toFixed(1)+' '+Y(a.v).toFixed(1)}).join(' ');
var ar=ln+' L'+X(s.length-1).toFixed(1)+' '+(H-B)+' L'+X(0).toFixed(1)+' '+(H-B)+' Z';
var n=s.length-1,ix=[0,Math.floor(n/3),Math.floor(2*n/3),n].filter(function(v,i,a){return a.indexOf(v)===i});
var tk=ix.map(function(i){return '<text x="'+X(i).toFixed(1)+'" y="'+(H-10)+'" text-anchor="middle">'+tl(s[i].t,st)+'</text>'}).join('');
var dt=s.length<=40?s.map(function(a,i){return '<circle class="pt" cx="'+X(i).toFixed(1)+'" cy="'+Y(a.v).toFixed(1)+'" r="6"><title>'+tl(a.t,st)+': '+fa(a.v)+(c.unit?' '+E(c.unit):'')+'</title></circle>'}).join(''):'';
return '<svg class="sv" viewBox="0 0 '+W+' '+H+'" dir="ltr"><defs><linearGradient id="agx" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#a78bfa" stop-opacity=".45"/><stop offset="1" stop-color="#a78bfa" stop-opacity="0"/></linearGradient></defs><line class="ax" x1="'+L+'" x2="'+(W-R)+'" y1="'+(H-B)+'" y2="'+(H-B)+'"/><text x="'+L+'" y="'+(T-5)+'">'+fa(mx)+'</text><path class="ar" d="'+ar+'" fill="url(#agx)" style="opacity:0;transition:opacity 1.2s"/><path class="ln" pathLength="1" d="'+ln+'" fill="none" stroke="#a78bfa" stroke-width="3" stroke-linejoin="round" stroke-linecap="round" style="stroke-dasharray:1;stroke-dashoffset:1;transition:stroke-dashoffset 1.3s ease"/>'+dt+tk+'</svg>'}
function hbars(c){var it=c.items||[];if(!it.length)return EM;var mx=1;it.forEach(function(x){mx=Math.max(mx,x.v)});
return '<div class="hb">'+it.map(function(x,i){return '<div><div class="hl"><span>'+E(x.l)+'</span><b>'+fa(x.v)+(c.unit?' '+E(c.unit):'')+'</b></div><div class="ht"><div class="hf" data-w="'+(x.v*100/mx).toFixed(1)+'" style="background:linear-gradient(90deg,'+PAL[i%PAL.length]+',#22d3ee)"></div></div></div>'}).join('')+'</div>'}
function heat(c){var m=c.m||[],mx=1;m.forEach(function(r){r.forEach(function(v){mx=Math.max(mx,v)})});
var dn=['شنبه','یکشنبه','دوشنبه','سه‌شنبه','چهارشنبه','پنجشنبه','جمعه'],cw=22,ch=22,L=74,W=L+24*cw,H=7*ch+26,g='',j;
m.forEach(function(r,i){g+='<text x="'+(L-8)+'" y="'+(i*ch+15)+'" text-anchor="end">'+dn[i]+'</text>';
r.forEach(function(v,j){g+='<rect x="'+(L+j*cw+1)+'" y="'+(i*ch+1)+'" width="'+(cw-2)+'" height="'+(ch-2)+'" rx="5" fill="#a78bfa" fill-opacity="'+(v?(.18+.82*v/mx).toFixed(2):'.06')+'"><title>'+dn[i]+' ساعت '+fa(j)+': '+fa(v)+' فروش</title></rect>'})});
for(j=0;j<24;j+=3)g+='<text x="'+(L+j*cw+cw/2)+'" y="'+(H-6)+'" text-anchor="middle">'+fa(j)+'</text>';
return '<div class="tw"><svg class="sv" style="min-width:540px" viewBox="0 0 '+W+' '+H+'" dir="ltr">'+g+'</svg></div>'}
function tbl(c){function cell(v){return v&&typeof v==='object'?(v.t?tf(v.t):E(v.n)):typeof v==='number'?fa(v):E(v)}
var rs=c.rows||[];return '<div class="tw"><table><tr>'+c.head.map(function(h){return '<th>'+E(h)+'</th>'}).join('')+'</tr>'+(rs.length?rs.map(function(r){return '<tr>'+r.map(function(v){return '<td>'+cell(v)+'</td>'}).join('')+'</tr>'}).join(''):'<tr><td colspan="'+c.head.length+'">موردی نیست</td></tr>')+'</table></div>'}
var TYPES={donut:donut,bars:bars,area:area,heat:heat,hbars:hbars,table:tbl};
function paint(el,list){el.innerHTML=list.map(function(c){var f=TYPES[c.type];return '<section class="card cc'+(c.wide?' wide':'')+'"><h3>'+E(c.title)+'</h3>'+(f?f(c):'')+'</section>'}).join('');go(el)}
function go(el){requestAnimationFrame(function(){requestAnimationFrame(function(){
el.querySelectorAll('.sg').forEach(function(s){s.style.strokeDasharray=s.dataset.l+' '+(parseFloat(s.dataset.c)-parseFloat(s.dataset.l)).toFixed(2)});
el.querySelectorAll('.br').forEach(function(r){r.style.transform='scaleY(1)'});
el.querySelectorAll('.hf').forEach(function(f){f.style.width=f.dataset.w+'%'});
el.querySelectorAll('.ln').forEach(function(p){p.style.strokeDashoffset=0});
el.querySelectorAll('.ar').forEach(function(p){p.style.opacity=1})})})}
function cnt(el,to){var t0=performance.now();(function f(t){var k=Math.min(1,(t-t0)/900),e=1-Math.pow(1-k,3);el.textContent=fa(to*e);if(k<1)requestAnimationFrame(f)})(t0)}
function spark(s,col){if(!s||s.length<2)return '';var mx=1;s.forEach(function(a){mx=Math.max(mx,a.v)});
var p=s.map(function(a,i){return (i?'L':'M')+(100*i/(s.length-1)).toFixed(1)+' '+(27-24*a.v/mx).toFixed(1)}).join(' ');
return '<svg class="spk" viewBox="0 0 100 30" preserveAspectRatio="none"><path d="'+p+' L100 30 L0 30 Z" fill="'+col+'" fill-opacity=".14"/><path d="'+p+'" fill="none" stroke="'+col+'" stroke-width="2" vector-effect="non-scaling-stroke"/></svg>'}
"""

BLOCK = r"""<div class="cg" id="stx"><div class="card">در حال بارگذاری آمار...</div></div><script>__JS__
(function(){fetch('/api/stats/__K__',{credentials:'same-origin'}).then(function(r){if(r.status===401){location='/login';return null}return r.json()}).then(function(d){if(!d)return;var el=document.getElementById('stx');if(d.error){el.innerHTML='<div class="card">خطا: '+E(d.error)+'</div>';return}paint(el,d.charts||[])}).catch(function(e){document.getElementById('stx').innerHTML='<div class="card">خطا: '+E(e)+'</div>'})})();</script>"""

DASH_BODY = """<div class="sub" id="date"></div><div class="grid" id="kpi"></div>
<section class="card"><h2>روند درآمد</h2><div class="sub" id="rsum"></div>
<div class="tabs" id="tabs"><button data-r="24h">۲۴ ساعت</button><button data-r="week" class="on">هفته</button><button data-r="3m">۳ ماه</button><button data-r="custom">روز دلخواه</button></div>
<div id="cus" hidden><input type="date" id="f"><input type="date" id="t"><button id="ap">اعمال</button></div><div id="rev"></div></section>
<div class="cg" id="cg"></div>"""

DASH_JS = r"""
var rng='week',painted=false;
function chip(p){return p==null?'<span class="chip">—</span>':'<span class="chip '+(p>=0?'up':'dn')+'">'+(p>=0?'▲':'▼')+' ٪'+fa(Math.abs(p))+'</span>'}
function kpi(d){var b=d.base,sp=d.spark;
var C=[['تعداد کل کاربران',b.users_total,'👥','<span class="chip up">▲ '+fa(b.users_week)+'+ این هفته</span>',sp.users,'#a78bfa'],
['تعداد کل سفارشات',b.orders_total,'🛒',chip(b.orders_pct),sp.orders,'#f472b6'],
['جمع کل فروش (تومان)',b.sales_total,'💰',chip(b.sales_pct),sp.sales,'#34d399'],
['کاربران جدید (۲۴ ساعت)',b.new24,'➕',chip(b.new24_pct),sp.users,'#22d3ee'],
['میانگین هر سفارش (تومان)',d.avg,'🧾','',null,''],
['موجودی کل کیف پول‌ها (تومان)',d.wallets,'💳','',null,''],
['حجم فروخته‌شده (GB)',d.gb,'📦','',null,''],
['پنل‌های فعال',b.panels_active,'🖥','<span class="chip">'+fa(b.panels_off)+' غیرفعال/منقضی</span>',null,'']];
$('#kpi').innerHTML=C.map(function(c){return '<div class="card"><div class="k"><div><div class="l">'+c[0]+'</div><div class="v" data-n="'+c[1]+'">۰</div></div><div class="ic">'+c[2]+'</div></div>'+c[3]+spark(c[4],c[5])+'</div>'}).join('');
document.querySelectorAll('#kpi .v').forEach(function(e){cnt(e,parseFloat(e.dataset.n)||0)})}
function load(){var u='/api/stats/dash?range='+rng;if(rng==='custom')u+='&from='+$('#f').value+'&to='+$('#t').value;
fetch(u,{credentials:'same-origin'}).then(function(r){if(r.status===401){location='/login';return null}return r.json()}).then(function(d){if(!d)return;
if(d.error){$('#kpi').innerHTML='<div class="card">خطا: '+E(d.error)+'</div>';return}
kpi(d);$('#rsum').textContent='جمع این بازه: '+fa(d.base.range_sales)+' تومان از '+fa(d.base.range_orders)+' سفارش';
$('#rev').innerHTML=area({s:d.base.series,step:d.base.step,unit:'تومان'});go($('#rev'));
if(!painted){paint($('#cg'),d.charts);painted=true}})}
$('#date').textContent=new Intl.DateTimeFormat('fa-IR',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Tehran'}).format(new Date());
$('#tabs').onclick=function(e){var b=e.target.closest('button');if(!b)return;rng=b.dataset.r;document.querySelectorAll('#tabs button').forEach(function(x){x.classList.toggle('on',x===b)});$('#cus').hidden=rng!=='custom';if(rng!=='custom')load()};
$('#ap').onclick=function(){if($('#f').value&&$('#t').value)load()};
load();setInterval(function(){if(rng!=='custom')load()},60000);
"""


def rows(sql, args=()):
    try:
        return A.q(sql, args)
    except Exception as e:
        if os.environ.get("STATS_DEBUG"):
            print("SQL ERR:", repr(e), "|", sql[:90], file=sys.stderr)
        return []


def one(sql, args=(), d=0):
    r = rows(sql, args)
    return d if not r or r[0][0] is None else r[0][0]


def cols_of(t):
    return {r[1] for r in rows(f"PRAGMA table_info({t})")}


def by_bucket(table, expr, step, n):
    now = int(time.time())
    b1 = (now + A.TZ) // step
    b0 = b1 - n + 1
    got = {r[0]: r[1] for r in rows(
        f"SELECT CAST((created+?)/? AS INTEGER) AS b, {expr} FROM {table} WHERE created>=? GROUP BY b",
        (A.TZ, step, b0 * step - A.TZ))}
    return [{"t": b * step - A.TZ, "v": got.get(b) or 0} for b in range(b0, b1 + 1)]


def users_aligned(ss, step):
    if not ss:
        return []
    got = {r[0]: r[1] for r in rows(
        "SELECT CAST((created+?)/? AS INTEGER) AS b, COUNT(*) FROM users WHERE created>=? AND created<? GROUP BY b",
        (A.TZ, step, ss[0]["t"], ss[-1]["t"] + step))}
    return [{"t": s["t"], "v": got.get(int((s["t"] + A.TZ) // step), 0)} for s in ss]


def names(ids):
    ids = [i for i in ids if i is not None]
    c = cols_of("users")
    col = next((x for x in ("username", "full_name", "name", "first_name") if x in c), None)
    if not col or not ids:
        return {}
    ph = ",".join("?" * len(ids))
    return {r[0]: r[1] for r in rows(f'SELECT tg_id, "{col}" FROM users WHERE tg_id IN ({ph})', tuple(ids)) if r[1]}


def who(nm, uid):
    return f"{nm[uid]} ({uid})" if nm.get(uid) else str(uid)


def donut(title, items, unit=""):
    return {"type": "donut", "title": title, "unit": unit, "items": [{"l": str(l), "v": v} for l, v in items if v]}


def tbars(title, s, step, unit="", wide=True):
    return {"type": "bars", "title": title, "unit": unit, "wide": wide, "items": s, "step": step}


def hbars(title, items, unit=""):
    return {"type": "hbars", "title": title, "unit": unit, "items": [{"l": str(l), "v": v} for l, v in items]}


def table(title, head, rs):
    return {"type": "table", "title": title, "wide": True, "head": head, "rows": rs}


def kind_charts():
    k = rows("SELECT kind, COUNT(*), COALESCE(SUM(price),0) FROM sales GROUP BY kind ORDER BY 2 DESC")
    return [donut("فروش بر اساس نوع (تعداد)", [(a, b) for a, b, c in k], "فروش"),
            donut("درآمد بر اساس نوع (تومان)", [(a, c) for a, b, c in k], "تومان")]


def heat_chart(days=90):
    m = [[0] * 24 for _ in range(7)]
    for w, hh, c in rows(
            "SELECT CAST(strftime('%w', created+?, 'unixepoch') AS INTEGER), "
            "CAST(strftime('%H', created+?, 'unixepoch') AS INTEGER), COUNT(*) FROM sales WHERE created>=? GROUP BY 1, 2",
            (A.TZ, A.TZ, int(time.time()) - days * D)):
        m[(w + 1) % 7][hh] = c
    return {"type": "heat", "title": "زمان‌های پرفروش (۹۰ روز اخیر)", "m": m, "wide": True}


def top_buyers():
    tb = rows("SELECT user_id, COALESCE(SUM(price),0) FROM sales GROUP BY user_id ORDER BY 2 DESC LIMIT 8")
    nm = names([r[0] for r in tb])
    return hbars("برترین خریداران (تومان)", [(who(nm, u), s) for u, s in tb], "تومان")


def plan_items():
    return rows("SELECT COALESCE(pl.name,'بدون پلن'), COUNT(*) FROM panels p LEFT JOIN plans pl ON pl.id=p.plan_id "
                "WHERE p.is_test=0 GROUP BY 1 ORDER BY 2 DESC")


def dash_payload(rng, frm, to):
    base = A.dash(rng, frm, to)
    now = int(time.time())
    ss = base["series"]
    c = cols_of("users")
    total = base["users_total"]
    blocked = one("SELECT COUNT(*) FROM users WHERE blocked=1") if "blocked" in c else 0
    spark = {"sales": by_bucket("sales", "COALESCE(SUM(price),0)", D, 14), "orders": by_bucket("sales", "COUNT(*)", D, 14),
             "users": by_bucket("users", "COUNT(*)", D, 14)}
    ch = [donut("وضعیت پنل‌ها", [(LBL.get(a, a), b) for a, b in rows(
              "SELECT status, COUNT(*) FROM panels WHERE is_test=0 GROUP BY status")], "پنل")]
    ch += kind_charts()
    ch.append(donut("وضعیت کاربران", [("فعال", total - blocked), ("مسدود", blocked)], "کاربر"))
    ch.append(donut("پنل‌ها بر اساس پلن", plan_items(), "پنل"))
    ch.append(heat_chart())
    ch.append(top_buyers())
    ch.append(tbars("کاربران جدید در بازه", users_aligned(ss, base["step"]), base["step"], "کاربر"))
    rs = rows("SELECT created, user_id, kind, panel, gb, price FROM sales ORDER BY id DESC LIMIT 10")
    ch.append(table("آخرین فروش‌ها", ["زمان", "کاربر", "نوع", "پنل", "حجم (GB)", "مبلغ (تومان)"],
                    [[{"t": a}, str(b), str(c_), str(d or "—"), f"{(e or 0):g}", int(f or 0)] for a, b, c_, d, e, f in rs]))
    ex = rows("SELECT admin_username, expires, user_id FROM panels WHERE status='active' AND is_test=0 "
              "AND expires>? AND expires<? ORDER BY expires LIMIT 10", (now, now + 7 * D))
    ch.append(table("پنل‌هایی که تا ۷ روز دیگر منقضی می‌شوند", ["یوزرنیم پنل", "انقضا", "کاربر"],
                    [[str(a), {"t": b}, str(u)] for a, b, u in ex]))
    to_, ts_ = base["orders_total"], base["sales_total"]
    return {"base": base, "spark": spark, "avg": (ts_ // to_) if to_ else 0,
            "wallets": one("SELECT COALESCE(SUM(balance),0) FROM users") if "balance" in c else 0,
            "gb": round(one("SELECT COALESCE(SUM(gb),0) FROM sales")), "charts": ch}


def users_payload():
    c = cols_of("users")
    total = one("SELECT COUNT(*) FROM users")
    blocked = one("SELECT COUNT(*) FROM users WHERE blocked=1") if "blocked" in c else 0
    buyers = one("SELECT COUNT(DISTINCT user_id) FROM sales")
    ch = [donut("وضعیت کاربران", [("فعال", total - blocked), ("مسدود", blocked)], "کاربر"),
          donut("خریدار و بدون خرید", [("خریدار", buyers), ("بدون خرید", max(total - buyers, 0))], "کاربر")]
    if "test_used" in c:
        t = one("SELECT COUNT(*) FROM users WHERE test_used=1")
        ch.append(donut("استفاده از اکانت تست", [("تست گرفته", t), ("بدون تست", total - t)], "کاربر"))
    if "balance" in c:
        nb = ["بدون موجودی", "زیر ۱۰۰ هزار", "۱۰۰ تا ۵۰۰ هزار", "۵۰۰ هزار تا ۱ میلیون", "بالای ۱ میلیون"]
        got = dict(rows("SELECT CASE WHEN balance<=0 THEN 0 WHEN balance<100000 THEN 1 WHEN balance<500000 THEN 2 "
                        "WHEN balance<1000000 THEN 3 ELSE 4 END AS b, COUNT(*) FROM users GROUP BY b"))
        ch.append(hbars("توزیع موجودی کیف پول", [(nb[i], got.get(i, 0)) for i in range(5)], "کاربر"))
        tb = rows("SELECT tg_id, balance FROM users WHERE balance>0 ORDER BY balance DESC LIMIT 8")
        nm = names([r[0] for r in tb])
        ch.append(hbars("بیشترین موجودی (تومان)", [(who(nm, u), b) for u, b in tb], "تومان"))
    ch.append(tbars("کاربران جدید (۳۰ روز اخیر)", by_bucket("users", "COUNT(*)", D, 30), D, "کاربر"))
    return {"charts": ch}


def shop_payload():
    pa = one("SELECT COUNT(*) FROM products WHERE active=1")
    pt = one("SELECT COUNT(*) FROM products")
    ch = [donut("محصولات", [("فعال", pa), ("غیرفعال", pt - pa)], "محصول"),
          donut("پکیج‌ها در هر محصول", rows(
              "SELECT COALESCE(pr.name,'نامشخص'), COUNT(*) FROM packages pk LEFT JOIN products pr ON pr.id=pk.product_id "
              "GROUP BY 1 ORDER BY 2 DESC"), "پکیج")]
    u, r = (rows("SELECT COALESCE(SUM(used),0), COALESCE(SUM(CASE WHEN max_uses>0 THEN max_uses-used ELSE 0 END),0) "
                 "FROM codes") or [(0, 0)])[0]
    ch.append(donut("مصرف کدهای تخفیف", [("استفاده‌شده", u), ("باقی‌مانده", r)], "بار"))
    ch.append(hbars("پرمصرف‌ترین کدها", rows("SELECT code, used FROM codes WHERE used>0 ORDER BY used DESC LIMIT 8"), "بار"))
    ch += kind_charts()
    ch.append(tbars("درآمد ۳۰ روز اخیر (تومان)", by_bucket("sales", "COALESCE(SUM(price),0)", D, 30), D, "تومان"))
    return {"charts": ch}


def reports_payload():
    ch = [tbars("درآمد روزانه (۳۰ روز اخیر، تومان)", by_bucket("sales", "COALESCE(SUM(price),0)", D, 30), D, "تومان"),
          tbars("درآمد هفتگی (۱۲ هفته اخیر، تومان)", by_bucket("sales", "COALESCE(SUM(price),0)", 7 * D, 12), 7 * D, "تومان"),
          tbars("تعداد سفارش روزانه", by_bucket("sales", "COUNT(*)", D, 30), D, "سفارش"),
          tbars("حجم فروخته‌شده روزانه (GB)", by_bucket("sales", "COALESCE(SUM(gb),0)", D, 30), D, "GB")]
    ch += kind_charts()
    ch.append(heat_chart())
    ch.append(top_buyers())
    return {"charts": ch}


def panels_payload():
    now = int(time.time())
    c = cols_of("panels")
    ch = [donut("وضعیت پنل‌ها", [(LBL.get(a, a), b) for a, b in rows(
              "SELECT status, COUNT(*) FROM panels WHERE is_test=0 GROUP BY status")], "پنل"),
          donut("واقعی و تست", [("واقعی", one("SELECT COUNT(*) FROM panels WHERE is_test=0")),
                                ("تست", one("SELECT COUNT(*) FROM panels WHERE is_test=1"))], "پنل"),
          donut("پنل‌ها بر اساس پلن", plan_items(), "پنل")]
    if "server_id" in c:
        ch.append(donut("پنل‌ها در هر سرور", [(str(a).replace("https://", "").replace("http://", "").strip("/"), n)
                                              for a, n in rows(
            "SELECT COALESCE(s.url,'نامشخص'), COUNT(*) FROM panels p LEFT JOIN servers s ON s.id=p.server_id "
            "WHERE p.is_test=0 GROUP BY 1 ORDER BY 2 DESC")], "پنل"))
    lab = ["منقضی‌شده", "تا ۳ روز دیگر", "۳ تا ۷ روز", "۷ تا ۳۰ روز", "بیش از ۳۰ روز", "بدون انقضا"]
    got = dict(rows("SELECT CASE WHEN expires=0 THEN 5 WHEN expires<? THEN 0 WHEN expires<? THEN 1 WHEN expires<? THEN 2 "
                    "WHEN expires<? THEN 3 ELSE 4 END AS b, COUNT(*) FROM panels WHERE is_test=0 GROUP BY b",
                    (now, now + 3 * D, now + 7 * D, now + 30 * D)))
    ch.append(hbars("زمان انقضای پنل‌ها", [(lab[i], got.get(i, 0)) for i in range(6)], "پنل"))
    ow = rows("SELECT user_id, COUNT(*) FROM panels WHERE is_test=0 GROUP BY user_id ORDER BY 2 DESC LIMIT 8")
    nm = names([r[0] for r in ow])
    ch.append(hbars("بیشترین پنل (به‌ازای هر کاربر)", [(who(nm, u), n) for u, n in ow], "پنل"))
    ch.append(tbars("پنل‌های ساخته‌شده (۳۰ روز اخیر)", by_bucket("panels", "COUNT(*)", D, 30), D, "پنل"))
    return {"charts": ch}


PAYLOADS = {"users": users_payload, "shop": shop_payload, "reports": reports_payload, "panels": panels_payload}


async def api(req):
    kind = req.match_info["kind"]
    try:
        if kind == "dash":
            q = req.query

            def fn():
                return dash_payload(q.get("range", "week"), q.get("from", ""), q.get("to", ""))
        else:
            fn = PAYLOADS.get(kind)
            if fn is None:
                raise web.HTTPNotFound()
        data = await asyncio.to_thread(fn)
    except web.HTTPException:
        raise
    except Exception as e:
        return web.json_response({"error": repr(e)}, status=500)
    return web.json_response(data, dumps=lambda o: json.dumps(o, default=str))


async def dash_page(req):
    return P.page("dash", "داشبورد", CSS + DASH_BODY + "<script>" + JS + DASH_JS + "</script>")


def block(kind):
    return CSS + BLOCK.replace("__JS__", JS).replace("__K__", kind)


def wrap(old, kind):
    async def h(req):
        resp = await old(req)
        try:
            if isinstance(resp, web.Response) and resp.text and "</h1>" in resp.text:
                resp.text = resp.text.replace("</h1>", "</h1>" + block(kind), 1)
        except Exception:
            pass
        return resp
    return h


def routes(app, path, method="GET"):
    out = []
    for res in app.router.resources():
        if getattr(res, "canonical", None) == path:
            out += [rt for rt in res if rt.method == method]
    return out


def install(app):
    app.router.add_get("/api/stats/{kind}", api)
    for rt in routes(app, "/"):
        rt._handler = dash_page
    for path, kind in (("/users", "users"), ("/shop", "shop"), ("/reports", "reports"), ("/panels", "panels")):
        for rt in routes(app, path):
            rt._handler = wrap(rt.handler, kind)
