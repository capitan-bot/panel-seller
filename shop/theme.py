from __future__ import annotations

import html

from aiohttp import web

from web import app as A

TITLE = A.env("SHOP_TITLE") or "CAPITAN PANEL"
FA = str.maketrans("0123456789,", "۰۱۲۳۴۵۶۷۸۹٬")
FG = str.maketrans("0123456789.", "۰۱۲۳۴۵۶۷۸۹٫")
TABS = (("home", "/", "🛍", "فروشگاه"), ("panels", "/panels", "🖥", "پنل‌ها"), ("wallet", "/wallet", "💳", "کیف پول"))
LOGO = ('<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#fff" stroke-width="1.8" stroke-linecap="round" '
        'stroke-linejoin="round"><path d="M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z"/><path d="M9 12l2 2 4-4"/></svg>')


def esc(s):
    return html.escape(str(s))


def fa(v):
    try:
        return "{:,}".format(int(float(v))).translate(FA)
    except Exception:
        return "۰"


def fg(v):
    try:
        return ("%g" % float(v)).translate(FG)
    except Exception:
        return "۰"


def bot_user():
    u = A.env("SHOP_BOT").lstrip("@")
    if u:
        return u
    try:
        s = (A.DATA / "web_slug.txt").read_text().strip()
        return "" if s.isdigit() else s
    except OSError:
        return ""


CSS = """
@font-face{font-family:V;src:url(/static/Vazirmatn-Regular.ttf)}
@font-face{font-family:V;font-weight:700;src:url(/static/Vazirmatn-Bold.ttf)}
:root{--card:#12121a;--bd:#232331;--tx:#eceef5;--mu:#9a9db0;--up:#34d399;--wn:#fbbf24;--dn:#f87171}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
html{background:#07070c}
body{margin:0;min-height:100vh;padding-bottom:86px;color:var(--tx);font-family:V,Tahoma,sans-serif;background:radial-gradient(700px 480px at 92% -8%,#7c5cf033,transparent 65%),radial-gradient(560px 420px at 0 100%,#22d3ee22,transparent 65%),#07070c}
a{color:inherit;text-decoration:none}
.top{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:10px;padding:11px 16px;background:#0a0a10;border-bottom:1px solid var(--bd)}
.logo{width:38px;height:38px;border-radius:12px;display:grid;place-items:center;background:linear-gradient(135deg,#7c5cf0,#22d3ee)}
.brand{font-weight:700}.lo{margin-right:auto}
.lo button{background:#171722;border:1px solid var(--bd);color:var(--dn);border-radius:10px;padding:7px 12px;font-family:inherit;font-size:13px;cursor:pointer}
.tabs{position:fixed;bottom:0;left:0;right:0;z-index:30;display:flex;gap:6px;padding:8px 10px calc(8px + env(safe-area-inset-bottom));background:#0b0b12;border-top:1px solid var(--bd)}
.tb{flex:1;display:flex;flex-direction:column;align-items:center;gap:2px;padding:7px 0;border-radius:14px;color:var(--mu);font-size:12px}
.tb i{font-style:normal;font-size:20px}.tb.on{color:#fff;background:#251f4a}
@media(min-width:900px){body{padding-bottom:0}.tabs{position:static;justify-content:center;border:0;background:none;padding:12px}.tb{flex:none;flex-direction:row;gap:8px;padding:9px 18px;font-size:14px}}
.main{max-width:980px;margin:auto;padding:14px 16px 30px}
h1{margin:6px 0 4px;font-size:27px;background:linear-gradient(90deg,#fff,#c4b5fd 60%,#67e8f9);-webkit-background-clip:text;background-clip:text;color:transparent}
h2{margin:24px 0 12px;font-size:18px}.sub{color:var(--mu);font-size:14px;margin-bottom:14px}.mu{color:var(--mu);font-size:13px;margin-top:5px}
.card{background:linear-gradient(165deg,#161621,#10101a);border:1px solid var(--bd);border-radius:22px;padding:18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px}
.rv{animation:rv .5s cubic-bezier(.22,1,.36,1) both}
.grid>:nth-child(2){animation-delay:.06s}.grid>:nth-child(3){animation-delay:.12s}.grid>:nth-child(4){animation-delay:.18s}.grid>:nth-child(n+5){animation-delay:.24s}
@keyframes rv{from{opacity:0;transform:translateY(14px)}}
.hero{position:relative;overflow:hidden;border-radius:26px;padding:22px;background:linear-gradient(135deg,#2d2366,#153b55 62%,#1b1b3c);border:1px solid #3b3573}
.hero:before{content:"";position:absolute;width:230px;height:230px;border-radius:50%;left:-70px;top:-90px;background:radial-gradient(closest-side,#a78bfa55,transparent)}
.hero>*{position:relative}.big{font-size:38px;font-weight:700;margin:4px 0 2px}.big small{font-size:15px;font-weight:400;color:#cbd5e1}
.hs{display:flex;gap:8px;margin-top:16px}.hs div{flex:1;background:#00000055;border-radius:14px;padding:10px 12px}.hs b{display:block;font-size:19px}.hs span{font-size:12px;color:#b6bdd0}
.pc{padding:1px;border-radius:23px;background:linear-gradient(135deg,#a78bfa77,#22d3ee33,#2a2a3a)}
.pi{height:100%;border-radius:22px;padding:18px;background:#11111a}
.ph{display:flex;align-items:center;gap:12px;margin-bottom:6px}.ph h3{margin:0;font-size:18px}
.pe{width:46px;height:46px;border-radius:14px;display:grid;place-items:center;font-size:24px;background:#251f4a;flex:none}
.pl{display:inline-flex;gap:6px;margin:8px 0 0 6px;padding:7px 12px;border-radius:12px;background:#1b1b2a;border:1px solid #2c2c41;font-size:13px}.pl b{color:#c4b5fd}
.cta{display:block;margin-top:16px;text-align:center;padding:12px;border-radius:14px;background:linear-gradient(135deg,#a78bfa,#7c5cf0 55%,#22d3ee);color:#fff;font-weight:700}.cta.off{background:#23232f;color:var(--mu)}
.pn{display:flex;align-items:center;gap:16px}
.rg{position:relative;width:88px;height:88px;flex:none}.rg svg{width:100%;height:100%;transform:rotate(-90deg)}
.rg circle{fill:none;stroke-width:5;stroke-linecap:round}.rg .t{stroke:#232331}.rg .p{animation:dr 1.1s .1s cubic-bezier(.22,1,.36,1) both}
@keyframes dr{from{stroke-dasharray:0 113.1}}
.rc{position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center}.rc b{font-size:22px}.rc small{color:var(--mu);font-size:11px}
.pf{flex:1;min-width:0}.pu{font-weight:700;font-size:17px;text-align:right;overflow:hidden;text-overflow:ellipsis}
.st{display:inline-block;margin:5px 0;padding:3px 10px;border-radius:99px;font-size:12px;background:#23232f}.st.ok{background:#0f2e24;color:var(--up)}.st.no{background:#331818;color:var(--dn)}
.cp{margin-top:8px;background:#1b1b2a;border:1px solid #2c2c41;color:var(--tx);border-radius:10px;padding:6px 12px;font-family:inherit;font-size:13px;cursor:pointer}
.wc{position:relative;overflow:hidden;border-radius:24px;padding:22px;background:linear-gradient(135deg,#7c5cf0,#4338ca 50%,#0e7490);box-shadow:0 14px 34px #7c5cf044}
.wc:after{content:"";position:absolute;width:200px;height:200px;border-radius:50%;left:-60px;bottom:-110px;background:#ffffff1a}
.wc>*{position:relative;z-index:1}.wc .mu{color:#ddd6fe}.wid{margin-top:14px;font-family:monospace;letter-spacing:2px;direction:ltr;text-align:right;color:#e0e7ff}
.tx{display:flex;justify-content:space-between;align-items:center;gap:10px;padding:13px 0;border-bottom:1px solid #1d1d2a}.tx:last-child{border:0}.tx b{white-space:nowrap}.tx small{color:var(--mu)}
.bx{width:min(92vw,420px);margin:9vh auto 0;padding:30px 24px}
.bx:before{content:"🛡";display:grid;place-items:center;width:64px;height:64px;margin:0 auto 14px;border-radius:20px;background:linear-gradient(135deg,#7c5cf0,#22d3ee);font-size:30px}
.bx h1{text-align:center}.bx p{text-align:center;color:var(--mu);font-size:14px;margin:0 0 16px}
input{width:100%;padding:14px;border-radius:14px;border:1px solid #2c2c36;background:#0d0d13;color:#fff;font-size:18px;font-family:inherit;direction:ltr;text-align:center;letter-spacing:2px}
input:focus{outline:2px solid #7c5cf0;border-color:transparent}
.go{width:100%;margin-top:16px;padding:14px;border:0;border-radius:14px;background:linear-gradient(135deg,#a78bfa,#7c5cf0 55%,#22d3ee);color:#fff;font-weight:700;font-size:16px;font-family:inherit;cursor:pointer}
.err{min-height:18px;margin-top:12px;color:var(--dn);font-size:13px;text-align:center}.lk{display:block;text-align:center;margin-top:14px;color:var(--mu);font-size:13px}
@media(prefers-reduced-motion:reduce){.rv,.rg .p{animation:none}}
"""

JS = """
var F=function(n){return Number(n).toLocaleString('fa-IR')};
document.querySelectorAll('.n').forEach(function(e){var to=+e.dataset.n||0,t0=performance.now();(function f(t){var k=Math.min(1,(t-t0)/800);e.textContent=F(Math.round(to*(1-Math.pow(1-k,3))));if(k<1)requestAnimationFrame(f)})(t0)});
document.querySelectorAll('.tm').forEach(function(e){var t=+e.dataset.t;if(!t)return;var d=new Date(t*1000),o={timeZone:'Asia/Tehran'};e.textContent=e.dataset.f==='dt'?d.toLocaleString('fa-IR',Object.assign({dateStyle:'short',timeStyle:'short'},o)):d.toLocaleDateString('fa-IR',Object.assign({year:'numeric',month:'long',day:'numeric'},o))});
document.querySelectorAll('.cp').forEach(function(b){b.onclick=function(){var v=b.dataset.c;(navigator.clipboard?navigator.clipboard.writeText(v):Promise.reject()).catch(function(){var t=document.createElement('textarea');t.value=v;document.body.appendChild(t);t.select();try{document.execCommand('copy')}catch(e){}t.remove()}).then(function(){var o=b.textContent;b.textContent='✓ کپی شد';setTimeout(function(){b.textContent=o},1500)})}});
"""


def shell(title, body, active="", nav=True, status=200, sub=""):
    head = tabs = ""
    if nav:
        head = ('<header class="top"><div class="logo">' + LOGO + '</div><div class="brand">' + esc(TITLE) + "</div>"
                '<form class="lo" method="post" action="/logout"><button>خروج</button></form></header>')
        tabs = '<nav class="tabs">' + "".join('<a class="tb%s" href="%s"><i>%s</i>%s</a>' % (
            " on" if k == active else "", u, ic, t) for k, u, ic, t in TABS) + "</nav>"
        main = ('<main class="main"><h1>' + esc(title) + "</h1>" + ('<div class="sub">' + sub + "</div>" if sub else "") +
                body + "</main>")
    else:
        main = body
    t = ('<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
         '<meta name="theme-color" content="#0a0a10"><title>' + esc(title) + "</title><style>" + CSS + "</style></head><body>" +
         head + tabs + main + "<script>" + JS + "</script></body></html>")
    return web.Response(text=t, content_type="text/html", status=status)
