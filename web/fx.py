from __future__ import annotations

import html

from aiohttp import web

from . import app as A

_DONE = [False]

BGCSS = r"""
@font-face{font-family:V;src:url(/static/Vazirmatn-Regular.ttf)}
@font-face{font-family:V;font-weight:700;src:url(/static/Vazirmatn-Bold.ttf)}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#07070c;color:#e8e8ee;font-family:V,Tahoma,sans-serif;overflow:hidden}
.bg,.gd,canvas{position:fixed;inset:0;pointer-events:none}
.bg{z-index:0;overflow:hidden}
.bg i{position:absolute;border-radius:50%;filter:blur(90px);opacity:.55;animation:fl 14s ease-in-out infinite alternate}
.bg i:nth-child(1){width:520px;height:520px;background:#6d4fe0;top:-170px;right:-130px}
.bg i:nth-child(2){width:460px;height:460px;background:#0ea5c6;bottom:-180px;left:-130px;animation-delay:-5s}
.bg i:nth-child(3){width:320px;height:320px;background:#d946a8;top:42%;left:52%;opacity:.26;animation-delay:-9s}
@keyframes fl{to{transform:translate(50px,-40px) scale(1.15)}}
.gd{z-index:0;background-image:linear-gradient(#ffffff09 1px,transparent 1px),linear-gradient(90deg,#ffffff09 1px,transparent 1px);background-size:46px 46px;-webkit-mask-image:radial-gradient(ellipse at 50% 40%,#000 15%,transparent 72%);mask-image:radial-gradient(ellipse at 50% 40%,#000 15%,transparent 72%)}
canvas{z-index:0}
@media(prefers-reduced-motion:reduce){.bg i{animation:none}}
"""
BGHTML = '<div class="bg"><i></i><i></i><i></i></div><div class="gd"></div>'

LOGIN_T = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ورود به پنل</title><style>__BGCSS__
.box{position:relative;z-index:1;width:min(92vw,420px);padding:32px 26px 24px;border-radius:26px;background:linear-gradient(160deg,#181823cc,#0f0f16cc);border:1px solid #ffffff1a;-webkit-backdrop-filter:blur(22px);backdrop-filter:blur(22px);box-shadow:0 30px 80px #000b,inset 0 1px #ffffff14;animation:in .7s cubic-bezier(.22,1,.36,1) both}
.box:before{content:"";position:absolute;inset:-1px;border-radius:27px;padding:1px;background:conic-gradient(from var(--a,0deg),#a78bfa,#22d3ee,#f472b6,#a78bfa);-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;opacity:.6;animation:sp 7s linear infinite;pointer-events:none}
@property --a{syntax:'<angle>';initial-value:0deg;inherits:false}
@keyframes sp{to{--a:360deg}}
@keyframes in{from{opacity:0;transform:translateY(24px) scale(.96)}}
.box.shake{animation:sh .55s}
@keyframes sh{20%,60%{transform:translateX(-9px)}40%,80%{transform:translateX(9px)}}
.lg{width:74px;height:74px;margin:0 auto 14px;border-radius:24px;display:grid;place-items:center;background:linear-gradient(135deg,#7c5cf0,#22d3ee);box-shadow:0 12px 36px #7c5cf070;animation:bob 4s ease-in-out infinite}
@keyframes bob{50%{transform:translateY(-6px)}}
h1{margin:0 0 6px;font-size:26px;text-align:center;background:linear-gradient(90deg,#fff,#c4b5fd 55%,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}
p{margin:0 0 18px;text-align:center;color:#9a9aa8;font-size:14px}
label{display:block;margin:14px 4px 6px;font-size:13px;color:#b5b5c3}
.f{position:relative}
.ic{position:absolute;right:14px;top:50%;transform:translateY(-50%);font-size:16px;opacity:.75;pointer-events:none}
input{width:100%;padding:15px 44px;border-radius:14px;border:1px solid #2e2e3a;background:#0b0b11cc;color:#fff;font-size:16px;font-family:inherit;direction:ltr;text-align:left;transition:border-color .2s,box-shadow .2s}
input:focus{outline:0;border-color:#8b6cf6;box-shadow:0 0 0 4px #7c5cf033}
.eye{position:absolute;left:8px;top:50%;transform:translateY(-50%);background:none;border:0;font-size:18px;cursor:pointer;opacity:.7;padding:6px}
.go{position:relative;overflow:hidden;width:100%;margin-top:22px;padding:15px;border:0;border-radius:14px;background:linear-gradient(135deg,#a78bfa,#7c5cf0 55%,#22d3ee);color:#fff;font-weight:700;font-size:16px;font-family:inherit;cursor:pointer;box-shadow:0 12px 30px #7c5cf055;transition:transform .15s}
.go:active{transform:scale(.98)}
.go:before{content:"";position:absolute;inset:0;background:linear-gradient(110deg,transparent 30%,#ffffff40 50%,transparent 70%);transform:translateX(120%);animation:sm 3.2s ease-in-out infinite}
@keyframes sm{60%,100%{transform:translateX(-120%)}}
.go.ld{pointer-events:none;opacity:.8}
.err{min-height:18px;margin-top:14px;color:#f87171;font-size:13px;text-align:center}
.ft{margin-top:10px;text-align:center;color:#6b6b7b;font-size:12px}
</style></head><body>__BGHTML__<canvas id="pc"></canvas>
<form class="box" id="bx" method="post" action="/login">
<div class="lg"><svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/></svg></div>
<h1>__TITLE__</h1><p>برای ادامه، اطلاعات حساب خود را وارد کنید.</p>
<label>نام کاربری (آیدی عددی ادمین)</label><div class="f"><span class="ic">👤</span><input name="username" inputmode="numeric" autocomplete="username" required></div>
<label>رمز عبور</label><div class="f"><span class="ic">🔒</span><input id="pw" name="password" type="password" autocomplete="current-password" required><button type="button" class="eye" id="eye">👁</button></div>
<button class="go" id="go">ورود به پنل</button><div class="err" id="er">__ERR__</div><div class="ft">🔒 اتصال امن</div></form>
<script>
(function(){var bx=document.getElementById('bx'),er=document.getElementById('er'),go=document.getElementById('go');
if(er.textContent.replace(/\s/g,''))bx.classList.add('shake');
document.getElementById('eye').onclick=function(){var p=document.getElementById('pw');p.type=p.type==='password'?'text':'password'};
bx.onsubmit=function(){go.classList.add('ld');go.textContent='در حال ورود...'};
if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;
var c=document.getElementById('pc'),x=c.getContext('2d'),W,H,P=[],i;
function rs(){W=c.width=innerWidth;H=c.height=innerHeight}rs();addEventListener('resize',rs);
for(i=0;i<46;i++)P.push({x:Math.random()*W,y:Math.random()*H,r:Math.random()*1.8+.4,v:Math.random()*.35+.08,a:Math.random()*.5+.15});
(function f(){x.clearRect(0,0,W,H);P.forEach(function(p){p.y-=p.v;if(p.y<-5){p.y=H+5;p.x=Math.random()*W}x.beginPath();x.arc(p.x,p.y,p.r,0,6.283);x.fillStyle='rgba(196,181,253,'+p.a+')';x.fill()});requestAnimationFrame(f)})()})();
</script></body></html>"""

WELCOME_T = r"""<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>ورود موفق</title>
<meta http-equiv="refresh" content="7;url=./"><style>__BGCSS__
.w{position:relative;z-index:2;text-align:center;padding:24px}
.ring{position:relative;width:150px;height:150px;margin:0 auto 26px}
.ring svg{position:relative;width:100%;height:100%;z-index:1}
.rc{fill:rgba(52,211,153,.08);stroke:#34d399;stroke-width:4;stroke-linecap:round;stroke-dasharray:327;stroke-dashoffset:327;animation:dr .85s .1s cubic-bezier(.65,0,.35,1) forwards}
.ck{fill:none;stroke:#6ee7b7;stroke-width:6;stroke-linecap:round;stroke-linejoin:round;stroke-dasharray:70;stroke-dashoffset:70;animation:dr .5s .85s ease-out forwards}
@keyframes dr{to{stroke-dashoffset:0}}
.gl{position:absolute;inset:-34px;border-radius:50%;background:radial-gradient(closest-side,#34d39966,transparent);opacity:0;animation:gl .9s .85s forwards}
@keyframes gl{to{opacity:1}}
.pu{position:absolute;inset:0;border-radius:50%;border:2px solid #34d39988;opacity:0;animation:pu 2s 1.1s ease-out infinite}
.pu.b{animation-delay:1.8s}
@keyframes pu{0%{opacity:.9;transform:scale(1)}100%{opacity:0;transform:scale(1.9)}}
h1{margin:0 0 8px;font-size:30px;background:linear-gradient(90deg,#fff,#6ee7b7 55%,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent;opacity:0;transform:translateY(14px);animation:up .6s 1.05s forwards}
.sb{color:#9ca3b4;margin:0 0 24px;font-size:15px;opacity:0;animation:up .6s 1.25s forwards}
@keyframes up{to{opacity:1;transform:none}}
.pb{width:min(70vw,260px);height:6px;margin:0 auto;border-radius:99px;background:#ffffff14;overflow:hidden;opacity:0;animation:up .4s 1.3s forwards}
.pb i{display:block;height:100%;width:0;border-radius:99px;background:linear-gradient(90deg,#34d399,#22d3ee);animation:fb 1.6s 1.4s linear forwards}
@keyframes fb{to{width:100%}}
.sk{display:inline-block;margin-top:16px;color:#7c7c8c;font-size:13px;text-decoration:none}
</style></head><body>__BGHTML__<canvas id="cf" style="z-index:3"></canvas>
<div class="w"><div class="ring"><div class="gl"></div><div class="pu"></div><div class="pu b"></div>
<svg viewBox="0 0 120 120"><circle class="rc" cx="60" cy="60" r="52" transform="rotate(-90 60 60)"/><path class="ck" d="M38 62 L54 77 L84 45"/></svg></div>
<h1>ورود با موفقیت انجام شد</h1><div class="sb">خوش آمدی ادمین __UID__ · در حال انتقال به پنل...</div>
<div class="pb"><i></i></div><div><a class="sk" href="./">ورود فوری به پنل</a></div></div>
<script>
setTimeout(function(){location.replace('./')},3200);
(function(){if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;
var c=document.getElementById('cf'),x=c.getContext('2d'),W,H,P=[],col=['#a78bfa','#34d399','#fbbf24','#f472b6','#22d3ee','#ffffff'];
function rs(){W=c.width=innerWidth;H=c.height=innerHeight}rs();
setTimeout(function(){for(var i=0;i<110;i++){var a=Math.random()*6.283,s=Math.random()*9+4;P.push({x:W/2,y:H*.38,vx:Math.cos(a)*s,vy:Math.sin(a)*s-5,w:Math.random()*8+4,h:Math.random()*5+3,r:Math.random()*6,vr:(Math.random()-.5)*.4,c:col[i%6],l:1})}
(function f(){x.clearRect(0,0,W,H);P=P.filter(function(p){p.x+=p.vx;p.y+=p.vy;p.vy+=.28;p.vx*=.985;p.r+=p.vr;p.l-=.011;if(p.l<=0)return false;x.save();x.globalAlpha=Math.max(p.l,0);x.translate(p.x,p.y);x.rotate(p.r);x.fillStyle=p.c;x.fillRect(-p.w/2,-p.h/2,p.w,p.h);x.restore();return true});if(P.length)requestAnimationFrame(f)})()},950)})();
</script></body></html>"""

LOGIN = LOGIN_T.replace("__BGCSS__", BGCSS).replace("__BGHTML__", BGHTML)

EXTRA = r"""
/*fx*/
html{background:#07070c}
body{background:transparent!important}
body:before{content:"";position:fixed;inset:0;z-index:-2;background:radial-gradient(620px 420px at 88% -6%,#7c5cf02b,transparent 62%),radial-gradient(520px 400px at 4% 104%,#22d3ee1f,transparent 62%),radial-gradient(420px 320px at 52% 48%,#f472b612,transparent 62%);animation:fxa 20s ease-in-out infinite alternate}
body:after{content:"";position:fixed;inset:0;z-index:-1;pointer-events:none;background-image:linear-gradient(#ffffff07 1px,transparent 1px),linear-gradient(90deg,#ffffff07 1px,transparent 1px);background-size:44px 44px;-webkit-mask-image:radial-gradient(ellipse at 50% 15%,#000 10%,transparent 70%);mask-image:radial-gradient(ellipse at 50% 15%,#000 10%,transparent 70%)}
@keyframes fxa{to{transform:translate3d(0,-2.5%,0) scale(1.07);filter:hue-rotate(28deg)}}
.top{background:#0b0b1080!important;-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}
.side{background:#0e0e16ee!important;-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}
.card{background:linear-gradient(165deg,#161621,#101016)!important;transition:transform .25s,border-color .25s,box-shadow .25s}
.grid .card:hover,.cg .card:hover{transform:translateY(-3px);border-color:#3d3570;box-shadow:0 16px 44px #7c5cf022}
h1{background:linear-gradient(90deg,#fff,#c4b5fd 60%,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}
.main{animation:fxu .5s ease both}
@keyframes fxu{from{opacity:0;transform:translateY(10px)}}
.it{transition:background .2s}.it:hover{background:#1b1b28}
.act{background:linear-gradient(90deg,#2d2560,#1d1a3a)!important;box-shadow:inset -3px 0 #a78bfa}
::-webkit-scrollbar{width:9px;height:9px}::-webkit-scrollbar-thumb{background:#2c2c3a;border-radius:9px}
@media(prefers-reduced-motion:reduce){body:before,.main{animation:none}}
"""


def esc(s):
    return html.escape(str(s))


def routes(app, path, method=None):
    out = []
    for res in app.router.resources():
        if getattr(res, "canonical", None) == path:
            out += [rt for rt in res if method is None or rt.method == method]
    return out


def wrap_login(old):
    async def h(req):
        try:
            return await old(req)
        except web.HTTPFound as e:
            if e.headers.get("Location") == "/":
                e.headers["Location"] = "/welcome"
            raise
    return h


async def welcome(req):
    t = (WELCOME_T.replace("__BGCSS__", BGCSS).replace("__BGHTML__", BGHTML)
         .replace("__UID__", esc(req.get("uid", ""))))
    return web.Response(text=t, content_type="text/html")


def install(app):
    if _DONE[0]:
        return
    _DONE[0] = True
    gl = {}
    for rt in routes(app, "/login", "GET"):
        gl = rt.handler.__globals__
    for g in (A.__dict__, gl):
        if "LOGIN_HTML" in g:
            g["LOGIN_HTML"] = LOGIN
        if "MAIN_HTML" in g and "/*fx*/" not in g["MAIN_HTML"]:
            g["MAIN_HTML"] = g["MAIN_HTML"].replace("</style>", EXTRA + "</style>", 1)
    app.router.add_get("/welcome", welcome)
    for rt in routes(app, "/login", "POST"):
        rt._handler = wrap_login(rt.handler)


# ---- lite mode (light on phones)
BGCSS += """
.bg i{filter:none!important;animation:none!important;opacity:.5!important;background:radial-gradient(closest-side,var(--c),#0000)!important}
.bg i:nth-child(1){--c:#6d4fe0}.bg i:nth-child(2){--c:#0ea5c6}.bg i:nth-child(3){--c:#d946a8;opacity:.3!important}
.gd{display:none}
canvas#pc{display:none!important}
.box{-webkit-backdrop-filter:none!important;backdrop-filter:none!important;background:#13131c!important;box-shadow:0 12px 30px #0009!important}
.box:before{animation:none!important;background:linear-gradient(135deg,#a78bfa,#22d3ee,#f472b6)!important}
.lg{animation:none!important}
.go:before{display:none}
"""
LOGIN_T = LOGIN_T.replace(
    "if(matchMedia('(prefers-reduced-motion:reduce)').matches)return;\nvar c=document.getElementById('pc')",
    "return;\nvar c=document.getElementById('pc')", 1)
LOGIN = LOGIN_T.replace("__BGCSS__", BGCSS).replace("__BGHTML__", BGHTML)
EXTRA = EXTRA.replace(";animation:fxa 20s ease-in-out infinite alternate}", "}")
EXTRA = EXTRA.replace("background:#0b0b1080!important;-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)", "background:#0b0b10!important")
EXTRA = EXTRA.replace("background:#0e0e16ee!important;-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)", "background:#0e0e16!important")
EXTRA += "\nbody:after{display:none}\n.top{-webkit-backdrop-filter:none!important;backdrop-filter:none!important}\n"
