from __future__ import annotations

import asyncio

from aiohttp import web

from . import app as A
from . import pages as P

_DONE = [False]
LIMIT = 30

BTN = ('<button id="lvb" type="button" aria-label="اعلان‌ها" style="margin-left:auto;position:relative;background:var(--card);'
       'border:1px solid var(--bd);color:var(--tx);border-radius:12px;font-size:19px;padding:5px 11px;cursor:pointer">🔔'
       '<b id="lvn"></b></button>')

CSS = r"""<style>
#bell{display:none!important}
#lvn{position:absolute;top:-6px;left:-8px;min-width:18px;height:18px;padding:0 5px;border-radius:99px;background:#ef4444;color:#fff;font-size:11px;line-height:18px;text-align:center;display:none}
#lvp{position:fixed;top:60px;left:10px;width:min(94vw,380px);max-height:72vh;overflow:auto;background:#12121a;border:1px solid var(--bd);border-radius:18px;box-shadow:0 20px 50px #000a;z-index:70}
.lvh{display:flex;justify-content:space-between;align-items:center;padding:12px 14px;border-bottom:1px solid var(--bd);gap:8px}
.lvh button{background:#1c1c28;border:1px solid var(--bd);color:var(--tx);border-radius:9px;padding:4px 9px;font-family:inherit;font-size:12px;cursor:pointer;margin-right:4px}
.lvi{display:flex;justify-content:space-between;gap:10px;padding:11px 14px;border-bottom:1px solid #1d1d28;color:var(--tx);text-decoration:none}
.lvi.nw{background:#1c1838}.lvi small{color:var(--mu);white-space:nowrap;font-size:11px}
.lvs{color:var(--mu);font-size:12px;margin-top:3px}
.lvq{display:block;padding:10px 14px;background:#241f45;color:#c4b5fd;text-decoration:none;font-size:13px}
.lve{padding:26px;text-align:center;color:var(--mu)}
#lvt{position:fixed;top:64px;left:50%;transform:translateX(-50%);width:min(94vw,380px);z-index:80;display:flex;flex-direction:column;gap:8px;pointer-events:none}
.lvto{pointer-events:auto;cursor:pointer;background:#181826;border:1px solid #3d3570;border-radius:16px;padding:12px 14px;box-shadow:0 14px 36px #000b;animation:lvin .4s cubic-bezier(.22,1,.36,1)}
.lvto.out{opacity:0;transform:translateY(-10px);transition:.35s}
@keyframes lvin{from{opacity:0;transform:translateY(-16px) scale(.96)}}
</style>
<div id="lvp" hidden></div><div id="lvt"></div>
<a hidden id="h_sale" href="/reports"></a><a hidden id="h_receipt" href="/receipts"></a>
<a hidden id="h_user" href="/users"></a><a hidden id="h_panel" href="/panels"></a><a hidden id="h_x" href="/"></a>"""

JS = r"""<script>
(function(){
var KC='pglive_c',KF='pgfeed',KS='pglive_snd',MAXF=40,IV=6000;
function $(s){return document.querySelector(s)}
function fa(n){return Number(n).toLocaleString('fa-IR')}
function E(s){return String(s==null?'':s).replace(/[&<>"']/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]})}
function ld(k,d){try{var v=JSON.parse(localStorage.getItem(k));return v==null?d:v}catch(e){return d}}
function sv(k,v){try{localStorage.setItem(k,JSON.stringify(v))}catch(e){}}
var feed=ld(KF,[]),cur=ld(KC,null),snd=ld(KS,true),pend=null,base=document.title,ac=null;
if(cur&&Date.now()-cur.ts>1800000)cur=null;
function hr(k){var a=document.getElementById('h_'+k);return a?a.getAttribute('href'):'#'}
function ago(t){var s=Math.max(0,Math.round(Date.now()/1000-t));if(s<60)return 'چند ثانیه پیش';if(s<3600)return fa(Math.round(s/60))+' دقیقه پیش';if(s<86400)return fa(Math.round(s/3600))+' ساعت پیش';return fa(Math.round(s/86400))+' روز پیش'}
function actx(){try{ac=ac||new (window.AudioContext||window.webkitAudioContext)();if(ac.state==='suspended')ac.resume()}catch(e){}return ac}
document.addEventListener('click',function(){actx()},{once:true});
function beep(){if(!snd)return;var c=actx();if(!c)return;try{[880,1320].forEach(function(f,i){var o=c.createOscillator(),g=c.createGain(),t=c.currentTime+i*.13;o.type='sine';o.frequency.value=f;g.gain.setValueAtTime(.0001,t);g.gain.exponentialRampToValueAtTime(.18,t+.02);g.gain.exponentialRampToValueAtTime(.0001,t+.22);o.connect(g);g.connect(c.destination);o.start(t);o.stop(t+.25)})}catch(e){}}
function unread(){var n=0;feed.forEach(function(x){if(!x.s)n++});return n}
function badge(){var n=unread(),b=$('#lvn');b.textContent=n>99?'99+':fa(n);b.style.display=n?'block':'none';document.title=(n&&document.hidden?'('+n+') ':'')+base}
function toast(x){var d=document.createElement('div');d.className='lvto';d.innerHTML='<b>'+E(x.title)+'</b><div class="lvs">'+E(x.sub)+'</div>';
d.onclick=function(){location.href=hr(x.k)};$('#lvt').appendChild(d);
setTimeout(function(){d.classList.add('out');setTimeout(function(){d.remove()},400)},6500)}
function render(){var h='<div class="lvh"><b>اعلان‌ها</b><span><button id="lvx" type="button">🧪 تست</button><button id="lvs" type="button">'+(snd?'🔊':'🔇')+'</button><button id="lvr" type="button">✓ خوانده شد</button></span></div>';
if(pend!=null)h+='<a class="lvq" href="/receipts">🧾 رسیدهای در انتظار: <b>'+fa(pend)+'</b></a>';
h+=feed.length?feed.map(function(x){return '<a class="lvi'+(x.s?'':' nw')+'" href="'+E(hr(x.k))+'"><div><b>'+E(x.title)+'</b><div class="lvs">'+E(x.sub)+'</div></div><small>'+ago(x.t)+'</small></a>'}).join(''):'<div class="lve">هنوز اعلانی نیامده</div>';
$('#lvp').innerHTML=h;
$('#lvx').onclick=function(){var x={k:'x',t:Date.now()/1000,title:'🔔 تست اعلان',sub:'اعلان زنده درست کار می‌کند'};toast(x);beep()};
$('#lvs').onclick=function(){snd=!snd;sv(KS,snd);render();if(snd)beep()};
$('#lvr').onclick=function(){seen();render()}}
function seen(){feed.forEach(function(x){x.s=1});sv(KF,feed);badge()}
function open_(){return !$('#lvp').hidden}
function got(d){if(d.pending!=null)pend=d.pending;
if(d.c){cur={s:d.c.s,p:d.c.p,u:d.c.u,r:d.c.r,ts:Date.now()};sv(KC,cur)}
var ev=d.e||[];
if(ev.length){ev.forEach(function(x){feed.unshift({k:x.k,t:x.t,title:x.title,sub:x.sub,s:open_()?1:0})});feed=feed.slice(0,MAXF);sv(KF,feed);
ev.slice(-3).forEach(function(x,i){setTimeout(function(){toast(x)},i*350)});
if(ev.length>3)setTimeout(function(){toast({k:'x',title:'🔔 '+fa(ev.length-3)+' اعلان دیگر',sub:'برای دیدن، زنگوله را بزن'})},1100);
beep()}
badge();if(open_())render()}
function poll(){if(document.hidden)return;var q=cur?'?s='+cur.s+'&p='+cur.p+'&u='+cur.u+'&r='+cur.r:'';
fetch('/api/live'+q,{credentials:'same-origin'}).then(function(r){if(r.status===401){location='/login';return null}return r.ok?r.json():null}).then(function(d){if(d&&!d.error)got(d)}).catch(function(){})}
$('#lvb').onclick=function(e){e.stopPropagation();var p=$('#lvp');if(p.hidden){seen();render();p.hidden=false;badge()}else p.hidden=true};
document.addEventListener('click',function(e){var p=$('#lvp');if(!p.hidden&&!p.contains(e.target))p.hidden=true});
document.addEventListener('visibilitychange',function(){badge();if(!document.hidden)poll()});
badge();render();poll();setInterval(poll,IV);
})();
</script>"""


def q(sql, args=()):
    try:
        return A.q(sql, args)
    except Exception:
        return []


def mx(sql):
    r = q(sql)
    return int(r[0][0] or 0) if r else 0


def names(ids):
    ids = {i for i in ids if i is not None}
    if not ids:
        return {}
    try:
        from . import stats as S
        return S.names(list(ids))
    except Exception:
        return {}


def who(nm, u):
    return "%s (%s)" % (nm[u], u) if nm.get(u) else str(u)


def money(v):
    try:
        return "{:,} تومان".format(int(float(v)))
    except Exception:
        return ""


def base():
    return {"s": mx("SELECT MAX(id) FROM sales"), "p": mx("SELECT MAX(id) FROM panels"),
            "u": mx("SELECT MAX(created) FROM users"), "r": mx("SELECT MAX(rowid) FROM receipts")}


def rc_rows(after):
    cl = [r[1] for r in q("PRAGMA table_info(receipts)")]
    if not cl:
        return []
    uc = next((x for x in ("user_id", "tg_id", "uid") if x in cl), None)
    ac = next((x for x in ("amount", "price", "value", "sum") if x in cl), None)
    sel = "rowid," + ('"%s"' % uc if uc else "NULL") + "," + ('"%s"' % ac if ac else "NULL")
    return q("SELECT %s FROM receipts WHERE rowid>? ORDER BY rowid LIMIT ?" % sel, (after, LIMIT))


def collect(cur):
    b = base()
    if cur is None:
        return {"c": b, "e": []}
    c = dict(cur)
    sales = q("SELECT id,created,user_id,kind,panel,gb,price FROM sales WHERE id>? ORDER BY id LIMIT ?", (cur["s"], LIMIT))
    panels = q("SELECT id,created,user_id,admin_username,is_test FROM panels WHERE id>? ORDER BY id LIMIT ?", (cur["p"], LIMIT))
    users = q("SELECT created,tg_id FROM users WHERE created>? ORDER BY created LIMIT ?", (cur["u"], LIMIT))
    rcs = rc_rows(cur["r"])
    nm = names({r[2] for r in sales} | {r[2] for r in panels} | {r[1] for r in users} | {r[1] for r in rcs})
    ev, now = [], 0
    for i, t, u, kind, panel, gb, price in sales:
        sub = " · ".join(x for x in (str(kind or ""), ("%g GB" % gb) if gb else "", money(price), who(nm, u)) if x)
        ev.append({"k": "sale", "t": t, "title": "🛒 فروش جدید", "sub": sub})
        c["s"] = max(c["s"], i)
    for i, t, u, name, test in panels:
        ev.append({"k": "panel", "t": t, "title": "🖥 پنل جدید" + (" (تست)" if test else ""),
                   "sub": "%s · %s" % (name, who(nm, u))})
        c["p"] = max(c["p"], i)
    for t, u in users:
        ev.append({"k": "user", "t": t, "title": "👤 کاربر جدید", "sub": who(nm, u)})
        c["u"] = max(c["u"], int(t or 0))
    for i, u, amt in rcs:
        sub = " · ".join(x for x in (money(amt) if amt is not None else "", who(nm, u) if u is not None else "") if x)
        ev.append({"k": "receipt", "t": now, "title": "🧾 رسید جدید", "sub": sub or "منتظر بررسی"})
        c["r"] = max(c["r"], i)
    import time
    for e in ev:
        if not e["t"]:
            e["t"] = int(time.time())
    ev.sort(key=lambda e: e["t"])
    return {"c": c, "e": ev}


def pending():
    try:
        from . import receipts as R
        return R.pending_count()
    except Exception:
        return None


async def live(req):
    try:
        try:
            cur = {k: int(req.query[k]) for k in "spur"}
        except (KeyError, ValueError):
            cur = None
        d = await asyncio.to_thread(collect, cur)
        d["pending"] = await asyncio.to_thread(pending)
    except Exception as e:
        return web.json_response({"error": repr(e)}, status=500)
    return web.json_response(d)


def install(app):
    if _DONE[0]:
        return
    _DONE[0] = True
    orig = P.page

    def page3(active, title, body):
        resp = orig(active, title, body)
        try:
            if resp.text and "</header>" in resp.text and 'id="lvb"' not in resp.text:
                resp.text = resp.text.replace("</header>", BTN + "</header>", 1).replace("</body>", CSS + JS + "</body>", 1)
        except Exception:
            pass
        return resp
    P.page = page3
    app.router.add_get("/api/live", live)
