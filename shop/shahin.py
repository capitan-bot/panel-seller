"""Storefront look copied from shahinluxe.com, in the shop's own dark palette, with a light/dark toggle.

Adds: new header (menu pill / logo / cart), 3-item bottom bar, new home page ("/"), /account page,
light theme overrides. Colors come from --pri/--acc (see appearance.py), so the "ظاهر سایت" panel still works.

Install: in main.py, right after `from . import admin` add `from . import shahin`.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time

from aiohttp import web

from web import app as A

from . import auth, landing, pages, theme
from .theme import bot_user, esc, fa, fg

log = logging.getLogger("shop.shahin")

GUEST_HOME = True              # False: guests keep the old landing/home handler
FLOAT_PATHS = ("/", "/buy")    # pages that get the support bubble + scroll-to-top button
ICONS = ["🚀", "⚡", "🛰", "💎", "🔥", "🌐"]
CART = re.compile(r"^[pc]:\d{1,9}$")
HDR = re.compile(r'<header class="top">.*?</header>', re.S)
NAV = re.compile(r'<nav class="(?:utabs|tabs)"[^>]*>.*?</nav>', re.S)


# ------------------------------------------------------------------ icons
def sv(p, w=1.6):
    return ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="%s" stroke-linecap="round" '
            'stroke-linejoin="round" aria-hidden="true">%s</svg>' % (w, p))


IC = {
    "store": '<path d="M3 9l1.5-5h15L21 9"/><path d="M4 9v11h16V9"/><path d="M3 9a3 3 0 0 0 6 0 3 3 0 0 0 6 0 3 3 0 0 0 6 0"/><path d="M10 20v-5h4v5"/>',
    "bag": '<path d="M5 8h14l-1 12H6L5 8z"/><path d="M9 8V6.5a3 3 0 0 1 6 0V8"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"/>',
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "panels": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "wallet": '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 10h18"/><circle cx="17" cy="15" r="1"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    "admin": '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="M20 20l-4-4"/>',
    "cart": '<circle cx="9" cy="20" r="1.3"/><circle cx="18" cy="20" r="1.3"/><path d="M2 3h3l2.5 12h11L21 7H6"/>',
    "l": '<path d="M15 5l-7 7 7 7"/>',
    "r": '<path d="M9 5l7 7-7 7"/>',
    "up": '<path d="M6 15l6-6 6 6"/>',
    "chat": '<path d="M4 5h16v11H9l-5 4V5z"/><path d="M8 10h.01M12 10h.01M16 10h.01"/>',
    "out": '<path d="M9 4H5v16h4"/><path d="M16 8l4 4-4 4M20 12H9"/>',
    "in": '<path d="M15 4h4v16h-4"/><path d="M8 8l-4 4 4 4M4 12h11"/>',
}

# emoji -> thin line icon
EM = {
    "⚡": '<path d="M13 2L4 14h7l-1 8 9-12h-7l1-8z"/>',
    "🔐": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3M12 15v2"/>',
    "💳": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 10h18M7 15h4"/>',
    "📊": '<path d="M4 20V10M10 20V4M16 20v-7M2 20h20"/>',
    "🤖": '<rect x="4" y="8" width="16" height="12" rx="3"/><path d="M12 4v4M9 13h.01M15 13h.01M9 17h6"/><circle cx="12" cy="3.5" r="1"/>',
    "🎧": '<path d="M4 14v-2a8 8 0 0 1 16 0v2"/><rect x="3" y="14" width="4" height="6" rx="1.5"/><rect x="17" y="14" width="4" height="6" rx="1.5"/><path d="M19 20a4 4 0 0 1-4 2h-2"/>',
    "🚀": '<path d="M5 15c-1 1-2 4-2 6 2 0 5-1 6-2"/><path d="M14 4c3-1 6-1 7-1 0 1 0 4-1 7l-6 6-6-6 6-6z"/><circle cx="15.5" cy="8.5" r="1.3"/>',
    "🛰": '<path d="M5 12a10 10 0 0 1 14 0M8 15a6 6 0 0 1 8 0"/><circle cx="12" cy="19" r="1"/>',
    "🌐": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>',
    "💎": '<path d="M6 4h12l4 6-10 11L2 10l4-6z"/><path d="M2 10h20M9 4l-2 6 5 11 5-11-2-6"/>',
    "🔥": '<path d="M12 22c4 0 7-3 7-7 0-3-2-5-3-7-1 2-2 3-4 3 0-3-1-5-3-7-2 3-4 6-4 10 0 4 3 8 7 8z"/>',
    "📦": '<path d="M3 8l9-5 9 5v8l-9 5-9-5V8z"/><path d="M3 8l9 5 9-5M12 13v8"/>',
    "✨": '<path d="M12 3l2 6 6 2-6 2-2 6-2-6-6-2 6-2 2-6z"/>',
    "✅": '<circle cx="12" cy="12" r="9"/><path d="M8 12l3 3 5-6"/>',
    "🛒": IC["cart"],
    "➕": '<path d="M12 5v14M5 12h14"/>',
    "⏰": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "☀": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/>',
    "🌙": '<path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z"/>',
    "👤": IC["user"],
    "⚠": '<path d="M12 3l10 18H2L12 3z"/><path d="M12 10v5M12 18h.01"/>',
}
_EMR = re.compile("(" + "|".join(re.escape(k) for k in sorted(EM, key=len, reverse=True)) + ")\ufe0f?")


def ico(e, w=1.4):
    p = EM.get((e or "").replace("\ufe0f", "").strip())
    return sv(p, w) if p else esc(e or "")


def emo(h):
    """turn emoji inside text nodes into line icons (never touches attributes)"""
    return re.sub(r">([^<>]*)<", lambda m: ">" + _EMR.sub(
        lambda e: '<span class="eic">%s</span>' % sv(EM[e.group(1)], 1.7), m.group(1)) + "<", h)


# ------------------------------------------------------------------ css / js
CSS = r"""
[hidden]{display:none!important}
:root{--bg:#07070c;--s2:#171724;--tile:#251f4a;--hdr:#0a0a10;--bar:#0b0b12}
html[data-theme=light]{--bg:#f4f5fa;--card:#fff;--bd:#e3e5ee;--tx:#14151f;--mu:#6b7085;--s2:#eef0f7;--tile:#ece8fd;--hdr:#fff;--bar:#fff;color-scheme:light}
html{background:var(--bg)}
/* header */
.sh-top{position:sticky;top:0;z-index:40;display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:8px;padding:10px 14px;background:var(--hdr);border-bottom:1px solid var(--bd)}
.sh-menu{justify-self:start;display:inline-flex;align-items:center;gap:8px;padding:10px 16px;border:0;border-radius:16px;color:#fff;font:700 15px V,Tahoma,sans-serif;cursor:pointer;background:linear-gradient(135deg,var(--pri,#7c5cf0),var(--acc,#22d3ee))}
.sh-menu svg{width:22px;height:22px}
.sh-logo{display:flex;align-items:center;gap:8px;color:var(--tx);font-weight:700;font-size:19px;white-space:nowrap;max-width:46vw;overflow:hidden;text-overflow:ellipsis}
.sh-logo img{height:34px;max-width:140px;object-fit:contain}
.sh-lm{flex:none;width:34px;height:34px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,var(--pri,#7c5cf0),var(--acc,#22d3ee))}
.sh-cart{justify-self:end;position:relative;width:44px;height:44px;display:grid;place-items:center;color:var(--tx)}
.sh-cart svg{width:30px;height:30px}
.sh-cart em,.sh-bi em{position:absolute;top:-3px;left:-5px;min-width:19px;height:19px;padding:0 4px;border-radius:10px;background:var(--pri,#7c5cf0);color:#fff;font:700 11px V,Tahoma,sans-serif;display:grid;place-items:center}
.sh-cart em,.sh-bi em{font-style:normal}
/* drawer */
.sh-ov{position:fixed;inset:0;z-index:65;background:#000a;opacity:0;pointer-events:none;transition:opacity .25s}
.sh-ov.open{opacity:1;pointer-events:auto}
.sh-dr{position:fixed;top:0;bottom:0;right:0;width:min(84vw,320px);z-index:70;display:flex;flex-direction:column;gap:2px;padding:16px 12px;overflow:auto;background:var(--card);border-left:1px solid var(--bd);transform:translateX(105%);transition:transform .28s cubic-bezier(.22,1,.36,1)}
.sh-dr.open{transform:none}
.sh-dr h4{margin:4px 8px 12px;font-size:17px}
.sh-dr a,.sh-row{display:flex;align-items:center;gap:12px;width:100%;padding:13px 12px;border:0;border-radius:14px;background:none;color:var(--tx);font:inherit;font-size:15px;text-align:right;cursor:pointer}
.sh-dr a:hover,.sh-row:hover{background:var(--s2)}
.sh-dr svg{width:22px;height:22px;flex:none;color:var(--pri,#a78bfa)}
.sh-dr hr{width:100%;border:0;border-top:1px solid var(--bd);margin:8px 0}
.sh-out{color:var(--dn)}.sh-out svg{color:var(--dn)}
.thl-l{display:none}
html[data-theme=light] .thl-d{display:none}
html[data-theme=light] .thl-l{display:inline}
/* bottom bar */
.sh-bar{position:fixed;bottom:0;left:0;right:0;z-index:45;display:flex;justify-content:space-around;padding:8px 6px calc(8px + env(safe-area-inset-bottom));background:var(--bar);border-top:1px solid var(--bd)}
.sh-bi{flex:1;max-width:170px;display:flex;flex-direction:column;align-items:center;gap:5px;padding:3px 0;color:var(--tx);font-size:13px;font-weight:700}
.sh-bi .ic{position:relative;display:block;width:30px;height:30px}
.sh-bi svg{width:30px;height:30px}
.sh-bi.on{color:var(--pri,#a78bfa)}
@media(min-width:900px){.sh-bar{left:50%;right:auto;bottom:14px;width:440px;transform:translateX(-50%);border:1px solid var(--bd);border-radius:22px}}
/* floating */
.sh-chat,.sh-up{position:fixed;z-index:42;border-radius:50%;display:grid;place-items:center;border:0;cursor:pointer;box-shadow:0 8px 22px #0005}
.sh-chat{right:16px;bottom:98px;width:60px;height:60px;color:#fff;background:var(--acc,#22d3ee)}
.sh-up{left:16px;bottom:156px;width:50px;height:50px;color:var(--tx);background:var(--card);border:1px solid var(--bd)}
.sh-chat svg,.sh-up svg{width:27px;height:27px}
/* home */
.shp{padding-top:14px}
.hm-s{margin-top:22px}
.hm-sec{display:flex;align-items:center;justify-content:space-between;margin:0 4px 12px;font-size:20px;font-weight:700}
.hm-sec a{font-size:13px;font-weight:400;color:var(--pri,#a78bfa)}
.hm-nt{display:block;margin-bottom:14px;padding:13px 16px;border-radius:16px;background:#2a2410;border:1px solid #6b5518;color:#fde68a;font-size:14px}
.hm-hero{position:relative;overflow:hidden;text-align:center;border-radius:28px;padding:40px 20px 30px;min-height:430px;display:flex;flex-direction:column;align-items:center;justify-content:center;gap:12px;color:#fff;background:linear-gradient(160deg,#25254a,#12121c 58%,#0c1c28);border:1px solid var(--bd);background-size:cover;background-position:center}
.hm-chip{padding:7px 14px;border-radius:99px;background:#ffffff1f;border:1px solid #ffffff2e;font-size:13px}
.hm-t{font-size:clamp(28px,7vw,44px);font-weight:700;line-height:1.5}
.hm-d{max-width:520px;color:#d5d8e8;font-size:16px;line-height:2}
.hm-bl{list-style:none;margin:4px 0 0;padding:0;display:grid;gap:8px;font-size:17px;color:#eceef5}
.hm-bl li:before{content:"«";margin-left:8px;color:var(--acc,#22d3ee)}
.hm-cta{display:flex;flex-wrap:wrap;gap:10px;justify-content:center;margin-top:10px}
.hm-b1,.hm-b2{padding:13px 24px;border-radius:16px;font-weight:700;font-size:15px;color:#fff}
.hm-b1{background:linear-gradient(135deg,var(--pri,#7c5cf0),var(--acc,#22d3ee))}
.hm-b2{background:#ffffff1c;border:1px solid #ffffff3a}
.hm-feat{border-radius:26px;padding:6px 20px;background:var(--card);border:1px solid var(--bd)}
.hm-fi{display:flex;align-items:center;gap:16px;padding:20px 0;border-bottom:1px solid var(--bd)}
.hm-fi:last-child{border:0}
.hm-fi h3{margin:0 0 6px;font-size:17px;color:var(--pri,#a78bfa)}
.hm-fi p{margin:0;color:var(--mu);font-size:14px;line-height:1.9}
.hm-ico{position:relative;flex:none;width:64px;height:64px;border-radius:20px;display:grid;place-items:center;font-size:30px;background:var(--tile)}
.hm-ico:after{content:"";position:absolute;top:-5px;left:-5px;width:24px;height:24px;border-radius:50%;background:var(--acc,#22d3ee);opacity:.28}
.hm-sr{border-radius:26px;padding:28px 18px;text-align:center;background:var(--s2);border:2px solid var(--bd)}
.hm-st{font-size:21px;font-weight:700;color:var(--pri,#a78bfa)}
.hm-si{position:relative;margin-top:16px}
.hm-si input{direction:rtl;text-align:right;letter-spacing:0;font-size:16px;padding:14px 14px 14px 46px;border-radius:12px;background:var(--card);color:var(--tx);border:1px solid var(--bd)}
.hm-si svg{position:absolute;left:14px;top:50%;width:22px;height:22px;margin-top:-11px;color:var(--mu)}
.hm-pr{position:relative;overflow:hidden;border-radius:28px;padding:34px 22px;text-align:center;color:#fff;background:linear-gradient(135deg,var(--pri,#7c5cf0),var(--acc,#22d3ee))}
.hm-pr>*{position:relative}
.hm-pr i{position:absolute;left:-14px;bottom:-26px;font-style:normal;font-size:130px;opacity:.22;line-height:1}
.hm-pp{font-size:14px;opacity:.9}
.hm-pt{margin:10px 0;font-size:25px;font-weight:700;line-height:1.6}
.hm-pr p{margin:0 0 18px;line-height:1.9}
.hm-wb{display:inline-flex;align-items:center;gap:8px;padding:13px 24px;border-radius:12px;background:#fff;color:#14151f;font-weight:700}
.hm-wb svg{width:22px;height:22px}
.hm-cw{position:relative}
.hm-car{display:flex;overflow-x:auto;scroll-snap-type:x mandatory;scrollbar-width:none;border:1px solid var(--bd);border-radius:20px;background:var(--card)}
.hm-car::-webkit-scrollbar{display:none}
.hm-pk{position:relative;flex:0 0 50%;scroll-snap-align:start;padding:12px 12px 16px;border-left:1px solid var(--bd)}
@media(min-width:700px){.hm-pk{flex-basis:33.333%}}
@media(min-width:960px){.hm-pk{flex-basis:25%}}
.hm-top{position:relative;margin-top:4px}
.hm-bd{position:absolute;top:6px;right:0;z-index:2;padding:5px 12px;border-radius:99px;background:#f59e0b;color:#1a1200;font-size:13px;font-weight:700}
.hm-im{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:4px;height:170px;margin-top:20px;border-radius:16px;background:radial-gradient(circle at 50% 42%,var(--tile),transparent 72%)}
.hm-im i{font-style:normal;font-size:58px;line-height:1}.hm-im b{font-size:22px}
.hm-add{position:absolute;right:0;bottom:0;width:50px;height:50px;border-radius:12px 0 12px 0;display:grid;place-items:center;background:#22a24a;color:#fff}
.hm-add svg{width:28px;height:28px}
.hm-nm{display:block;margin-top:12px;font-size:15px;line-height:1.8;color:var(--tx)}
.hm-ct{margin-top:4px;color:var(--mu);font-size:13px}
.hm-pc{margin-top:8px;font-weight:700;color:var(--pri,#a78bfa)}.hm-pc small{font-weight:400}
.hm-ar{position:absolute;top:50%;z-index:3;width:34px;height:44px;margin-top:-22px;border:0;background:none;color:var(--mu);cursor:pointer}
.hm-ar svg{width:26px;height:26px}.hm-ar.r{right:-6px}.hm-ar.l{left:-6px}
.hm-cats{display:grid;gap:14px}
.hm-cat{position:relative;display:flex;align-items:center;justify-content:flex-end;min-height:230px;padding:24px;border-radius:26px;overflow:hidden;color:var(--tx);background:linear-gradient(135deg,var(--tile),var(--s2));border:1px solid var(--bd)}
.hm-cat:nth-child(even){background:linear-gradient(135deg,var(--s2),var(--card))}
.hm-ci{position:absolute;right:22px;top:50%;font-style:normal;font-size:112px;line-height:1;transform:translateY(-50%)}
.hm-cx{position:relative;max-width:48%}
.hm-cx b{display:block;font-size:20px;line-height:1.7}
.hm-cx span{display:block;margin-top:4px;color:var(--mu);font-size:13px}
.hm-pill{display:inline-block;margin-top:14px;padding:9px 28px;border-radius:99px;background:linear-gradient(135deg,var(--pri,#7c5cf0),var(--acc,#22d3ee));color:#fff;font-weight:700;font-size:14px}
.hm-ft{margin-top:26px;border-radius:26px;padding:24px 20px;background:#1b1b26;color:#e6e8f3;border:1px solid #2a2a3a}
.hm-ft h3{margin:0 0 8px;font-size:19px}.hm-ft p{margin:0 0 14px;line-height:2;color:#c7cadb}
.hm-fq{margin-top:8px;border-radius:14px;background:#12121a;border:1px solid #2a2a3a;padding:2px 14px}
.hm-fq summary{cursor:pointer;padding:12px 0;font-weight:700}.hm-fq p{margin:0 0 12px}
.hm-fl{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}.hm-fl a{padding:9px 14px;border-radius:12px;background:#ffffff14;font-size:13px}
.hm-cp{margin-top:16px;color:#9a9db0;font-size:12px}
/* account */
.hm-av{flex:none;width:60px;height:60px;border-radius:20px;display:grid;place-items:center;font-size:30px;background:var(--tile)}
.hm-me{display:flex;align-items:center;gap:14px}.hm-me h3{margin:0 0 4px}
.hm-rows{display:grid;gap:10px;margin-top:14px}
.hm-rows a,.hm-rows button{display:flex;align-items:center;gap:14px;width:100%;padding:16px;border-radius:18px;background:var(--card);border:1px solid var(--bd);color:var(--tx);font:inherit;text-align:right;cursor:pointer}
.hm-rows svg{width:24px;height:24px;flex:none;color:var(--pri,#a78bfa)}
.hm-rows small{margin-right:auto;color:var(--mu)}
.hm-rows .out{color:var(--dn)}.hm-rows .out svg{color:var(--dn)}
.main{padding:22px 18px 40px}
.main .card+.card,.main .card+form,.main form+.card,.main form+form{margin-top:20px}
.main .grid{gap:20px}
.main h2{margin:36px 0 16px}
body{overflow-x:clip}
.main.shp{padding:26px 18px 0}
.hm-s{margin-top:44px}
.hm-s:first-child{margin-top:0}
.hm-hero{padding:48px 22px 38px;gap:16px}
.hm-fi{padding:26px 0}
.hm-sec{margin-bottom:18px}
.hm-cats{gap:24px}
.hm-sr{padding:34px 20px}
.hm-pr{padding:42px 24px}
.hm-pk{padding:16px 14px 20px}
body:has(.hm-band){padding-bottom:0!important}
.hm-band{margin:52px calc(50% - 50vw) 0;padding:46px calc(50vw - 50%) 130px;background:#2c2c33;color:#e6e8f3}
.hm-band .hm-feat{padding:10px 22px}
.hm-ab{margin:32px 0 0;font-size:19px;line-height:2.3;color:#e6e8f3}
.hm-band .hm-fq{margin-top:14px}
.hm-band .hm-fl{margin-top:26px}
.eic{display:inline-flex;vertical-align:middle}
.eic svg{width:1.2em;height:1.2em;margin-inline:.25em}
.hm-b1,.hm-b2,.hm-chip,.hm-nt{display:inline-flex;align-items:center;justify-content:center;gap:6px}
.hm-ico{width:76px;height:76px;background:none;color:var(--mu)}
.hm-ico svg{position:relative;z-index:1;width:46px;height:46px;stroke-width:1.3}
.hm-ico:after{z-index:0;top:6px;right:2px;left:auto;width:32px;height:32px;background:var(--pri,#7c5cf0);opacity:.28}
.hm-im i svg{width:72px;height:72px;color:var(--pri,#a78bfa);stroke-width:1.2}
.hm-ci svg{width:120px;height:120px;stroke-width:1;color:var(--pri,#a78bfa);opacity:.55}
.hm-pr i svg{width:150px;height:150px;color:#fff;stroke-width:1}
.hm-av svg{width:34px;height:34px;color:var(--pri,#a78bfa)}
@media(min-width:700px){
.main{max-width:560px}
.main:has(.adm){max-width:980px}
.sh-top{padding-inline:max(14px,calc(50% - 280px))}
body:has(.adm) .sh-top{padding-inline:14px}
.sh-bar{left:50%;right:auto;bottom:14px;width:min(520px,calc(100% - 24px));transform:translateX(-50%);border:1px solid var(--bd);border-radius:22px}
.sh-chat{right:max(16px,calc(50% - 264px))}
.sh-up{left:max(16px,calc(50% - 264px))}
.hm-pk{flex-basis:50%}
}
"""

# light-mode overrides for the existing pages (selectors are prefixed automatically)
_LIGHT = (
    ("body", "background:radial-gradient(700px 480px at 92% -8%,#7c5cf022,transparent 65%),radial-gradient(560px 420px at 0 100%,#22d3ee1c,transparent 65%),var(--bg);color:var(--tx)"),
    (".card,.fq,.ulc,.sh,.am,.pi,.qt", "background:#fff;border-color:var(--bd);box-shadow:0 2px 12px #1a1c2d0d"),
    (".tl", "background:#f7f8fc;border-color:var(--bd)"),
    (".tx,.cr,.ln", "border-bottom-color:#eceef5"),
    ("input,.ulc input,.adm input,.adm textarea,.ed input,.ed textarea", "background:#f6f7fb;color:#14151f;border-color:#dcdfe9"),
    (".pl,.cp,.ib,.no", "background:#f1f2f9;border-color:#e0e3ee;color:var(--tx)"),
    (".ulx", "background:#f1f2f9;color:#14151f;border-color:#e0e3ee"),
    (".ulc", "color:#14151f"),
    (".pe,.qt i", "background:var(--tile)"),
    (".st", "background:#eceef5"),
    (".st.ok", "background:#dcfce7;color:#15803d"),
    (".st.no", "background:#fee2e2;color:#b91c1c"),
    ("h1", "background:linear-gradient(90deg,#14151f,var(--pri,#7c5cf0) 60%,var(--acc,#22d3ee));-webkit-background-clip:text;background-clip:text;color:transparent"),
    (".stp i,.lst i", "background:#eef0f7;border-color:#e0e3ee"),
    (".stp .on,.lst .on", "color:var(--tx)"),
    (".bnr", "background:#fff7e0;border-color:#f0d88a;color:#7a5b00"),
    (".ofr", "background:#e7fbf4;border-color:#9fe0c8"),
    (".ofr b", "color:#047857"),
    (".er,.erb", "background:#fee2e2;color:#b91c1c"),
    (".okb", "background:#dcfce7;color:#15803d"),
    (".am a.on", "background:var(--tile);color:var(--pri,#7c5cf0)"),
    (".cta.off", "background:#e6e8f1;color:var(--mu)"),
    (".rg .t", "stroke:#e3e5ee"),
    (".hero,.wc", "color:#fff"),
    (".wr", "background:#fff1f1!important;border-color:#f3c0c0!important"),
    (".tp", "border-color:#b7e4d2!important"),
)
LIGHT = "".join(",".join("html[data-theme=light] " + s.strip() for s in sels.split(",")) + "{" + decl + "}"
                for sels, decl in _LIGHT)

EARLY = ("<script>try{var t=localStorage.getItem('pgtheme');document.documentElement.setAttribute('data-theme',"
         "t==='light'?'light':'dark')}catch(e){document.documentElement.setAttribute('data-theme','dark')}</script>")

JS = r"""(function(){
var d=document,h=d.documentElement;
function $(s){return d.querySelector(s)}
var dr=$('.sh-dr'),ov=$('.sh-ov'),mb=$('.sh-menu');
function op(v){if(!dr)return;dr.classList.toggle('open',v);ov.classList.toggle('open',v)}
if(mb)mb.onclick=function(){op(!dr.classList.contains('open'))};
if(ov)ov.onclick=function(){op(false)};
if(dr)dr.addEventListener('click',function(e){if(e.target.closest&&e.target.closest('a'))op(false)});
d.addEventListener('keydown',function(e){if(e.key==='Escape')op(false)});
var th=$('#shTh');
if(th)th.onclick=function(){var n=h.getAttribute('data-theme')==='light'?'dark':'light';h.setAttribute('data-theme',n);
try{localStorage.setItem('pgtheme',n)}catch(e){}var m=$('meta[name=theme-color]');if(m)m.setAttribute('content',n==='light'?'#ffffff':'#0a0a10')};
var up=$('.sh-up');
if(up){up.onclick=function(){window.scrollTo({top:0,behavior:'smooth'})};
addEventListener('scroll',function(){up.hidden=(window.pageYOffset||h.scrollTop)<500},{passive:true});up.hidden=true}
})();"""

HOME_JS = r"""<script>(function(){
var c=document.querySelector('.hm-car');
[].forEach.call(document.querySelectorAll('.hm-ar'),function(b){b.onclick=function(){if(c)c.scrollBy({left:(b.className.indexOf(' r')>0?1:-1)*c.clientWidth*.9,behavior:'smooth'})}});
var q=document.getElementById('hmq'),nr=document.getElementById('hmn');
function norm(s){return String(s).toLowerCase().replace(/[\u06F0-\u06F9]/g,function(x){return x.charCodeAt(0)-1776}).replace(/\u064A/g,'\u06CC').replace(/\u0643/g,'\u06A9')}
if(q)q.addEventListener('input',function(){var v=norm(q.value).trim(),n=0;
[].forEach.call(document.querySelectorAll('[data-q]'),function(e){var ok=!v||norm(e.getAttribute('data-q')).indexOf(v)>-1;e.hidden=!ok;if(ok)n++});
if(nr)nr.hidden=!v||n>0})})();</script>"""


# ------------------------------------------------------------------ chrome
def logo_html():
    try:
        from . import appearance
        u = appearance.logo_uri()
    except Exception:
        u = ""
    mark = '<img src="%s" alt="">' % u if u else '<span class="sh-lm">%s</span>' % theme.LOGO
    return mark + "<span>%s</span>" % esc(theme.TITLE)


def header(uid, n, admin):
    items = [("home", "/", "خانه", False), ("store", "/buy", "فروشگاه", False), ("bag", "/cart", "سبد خرید", False),
             ("panels", "/panels", "پنل‌های من", True), ("wallet", "/wallet", "کیف پول", True), ("info", "/about", "درباره‌ی ما", False)]
    if admin:
        items.append(("admin", "/admin", "مدیریت سایت", False))
        items.append(("info", "/admin/typography", "فونت و اندازه متن", False))
    rows = "".join('<a href="%s"%s>%s<span>%s</span></a>' % (
        u, ' data-login="%s"' % u if need and uid is None else "", sv(IC[ic]), t) for ic, u, t, need in items)
    rows += ('<hr><button type="button" class="sh-row" id="shTh"><span class="thl-d">☀️ حالت روشن</span>'
             '<span class="thl-l">🌙 حالت تیره</span></button>')
    if uid is None:
        rows += '<a href="/login" data-login="/">%s<span>ورود</span></a>' % sv(IC["in"])
    else:
        rows += ('<form method="post" action="/logout"><button class="sh-row sh-out">%s<span>خروج</span></button></form>' % sv(IC["out"]))
    return emo('<header class="top sh-top"><button type="button" class="sh-menu">%s<span>منو</span></button>'
            '<a class="sh-logo" href="/">%s</a><a class="sh-cart" href="/cart" aria-label="سبد خرید">%s<em>%s</em></a></header>'
            '<div class="sh-ov"></div><aside class="sh-dr"><h4>%s</h4>%s</aside>'
            % (sv(IC["menu"], 2), logo_html(), sv(IC["bag"], 1.5), fa(n), esc(theme.TITLE), rows))


def bar(uid, n, path):
    items = ((IC["store"], "/buy", "فروشگاه", ("/buy",), False),
             (IC["bag"], "/cart", "سبد خرید", ("/cart",), False),
             (IC["user"], "/account", "حساب کاربری من", ("/account", "/panels", "/wallet"), True))
    out = ""
    for ic, u, t, act, need in items:
        on = " on" if any(path == a or path.startswith(a + "/") for a in act) else ""
        attr = ' data-login="%s"' % u if need and uid is None else ""
        badge = "<em>%s</em>" % fa(n) if u == "/cart" else ""
        out += '<a class="sh-bi%s" href="%s"%s><span class="ic">%s%s</span><span>%s</span></a>' % (on, u, attr, sv(ic, 1.5), badge, t)
    return '<nav class="sh-bar">%s</nav>' % out


def floats(path):
    if path not in FLOAT_PATHS:
        return ""
    link = ""
    try:
        link = (landing.load().get("contact") or "").lstrip("@") or bot_user()
    except Exception:
        pass
    out = '<button type="button" class="sh-up" aria-label="بالا" hidden>%s</button>' % sv(IC["up"], 2)
    if link:
        out += ('<a class="sh-chat" href="https://t.me/%s" target="_blank" rel="noopener" aria-label="پشتیبانی">%s</a>'
                % (esc(link), sv(IC["chat"], 1.8)))
    return out


@web.middleware
async def mw(req, handler):
    resp = await handler(req)
    try:
        if type(resp) is not web.Response or resp.content_type != "text/html" or not resp.text:
            return resp
        txt = resp.text
        hm, nm = HDR.search(txt), NAV.search(txt)
        if not (hm or nm) or "</body>" not in txt or "</head>" not in txt:
            return resp
        uid = auth.read_cookie(req.cookies.get("pgshop", ""))
        n = 1 if CART.match(req.cookies.get("pgcart", "")) else 0
        admin = False
        if uid is not None:
            try:
                admin = uid in A.admin_ids()
            except Exception:
                pass
        if hm:
            txt = HDR.sub(lambda m: header(uid, n, admin), txt, 1)
        if nm:
            txt = NAV.sub(lambda m: bar(uid, n, req.path), txt, 1)
        txt = txt.replace("</head>", EARLY + "<style>" + CSS + LIGHT + typo_css() + "</style></head>", 1)
        txt = txt.replace("</body>", floats(req.path) + "<script>" + JS + "</script></body>", 1)
        resp.text = txt
        resp.headers.pop("Content-Length", None)
    except Exception:
        log.exception("shahin chrome failed")
    return resp


# ------------------------------------------------------------------ home
async def build_home(req):
    uid = req.get("uid")

    def work():
        now = int(time.time())
        bal, ex = 0, []
        if uid is not None:
            u = A.q("SELECT balance FROM users WHERE tg_id=?", (uid,))
            bal = int(u[0][0] or 0) if u else 0
            ex = A.q("SELECT admin_username, expires FROM panels WHERE user_id=? AND is_test=0 AND status='active' "
                     "AND expires>? AND expires<? ORDER BY expires LIMIT 1", (uid, now, now + 7 * 86400))
        best = A.q("SELECT k.id, k.gb, k.price FROM packages k JOIN products p ON p.id=k.product_id "
                   "WHERE k.active=1 AND p.active=1 AND k.gb>0 ORDER BY k.price*1.0/k.gb LIMIT 1")
        prs = A.q("SELECT id,name,descr,price_gb,min_gb,max_gb FROM products WHERE active=1 ORDER BY sort,id")
        pks = A.q("SELECT k.id,k.product_id,k.gb,k.price FROM packages k JOIN products p ON p.id=k.product_id "
                  "WHERE k.active=1 AND p.active=1 ORDER BY k.id DESC LIMIT 12")
        return bal, ex, best, prs, pks, now

    bal, ex, best, prs, pks, now = await asyncio.to_thread(work)
    d = await asyncio.to_thread(landing.load)
    guest = uid is None
    brand = d["brand"] or theme.TITLE

    # notice
    note = ""
    if ex:
        note = ('<a class="hm-nt" href="/panels">⏰ پنل <b dir="ltr">%s</b> حدود %s روز دیگر منقضی می‌شود.</a>'
                % (esc(ex[0][0]), fa(max(1, (ex[0][1] - now) // 86400))))

    # hero
    o = max(0, min(90, int(d["overlay"]))) / 100.0
    style = ""
    if landing.HERO.exists():
        style = (' style="background-image:linear-gradient(rgba(7,7,12,%.2f),rgba(7,7,12,%.2f)),url(/site/hero.jpg?v=%d)"'
                 % (o, min(o + .3, .97), int(landing.HERO.stat().st_mtime)))
    feats = [x for x in d["features"] if isinstance(x, dict)]
    bl = "".join("<li>%s</li>" % esc(x.get("t", "")) for x in feats[:4] if x.get("t"))
    chip = '' if guest else '<a class="hm-chip" href="/wallet">💳 موجودی: <b>%s</b> تومان</a>' % fa(bal)
    second = ('<a class="hm-b2" href="/login" data-login="/">🔐 ورود</a>' if guest
              else '<a class="hm-b2" href="/wallet">➕ شارژ کیف پول</a>')
    hero = ('<section class="hm-hero"%s>%s<div class="hm-t">%s</div><div class="hm-d">%s</div>%s'
            '<div class="hm-cta"><a class="hm-b1" href="/buy">🛒 مشاهده پکیج‌ها</a>%s</div></section>'
            % (style, chip, esc(d["hero_title"]), esc(d["hero_sub"]), '<ul class="hm-bl">%s</ul>' % bl if bl else "", second))

    # features
    fh = "".join('<div class="hm-fi"><div class="hm-ico">%s</div><div><h3>%s</h3><p>%s</p></div></div>' % (
        ico(x.get("i") or "✨"), esc(x.get("t", "")), esc(x.get("d", ""))) for x in feats[:4])
    feat = '<section class="hm-s"><div class="hm-feat">%s</div></section>' % fh if fh else ""

    # search
    search = ('<section class="hm-s"><div class="hm-sr"><div class="hm-st">دنبال پکیج خاصی می‌گردید؟</div>'
              '<div class="mu">در میان پکیج‌ها و محصولات جستجو کنید…</div><div class="hm-si">'
              '<input id="hmq" type="search" placeholder="جستجوی پکیج‌ها" autocomplete="off">%s</div>'
              '<div class="mu" id="hmn" hidden>نتیجه‌ای پیدا نشد.</div></div></section>' % sv(IC["search"]))

    # promo
    promo = ""
    if best:
        bid, bgb, bpr = best[0]
        promo = ('<section class="hm-s"><div class="hm-pr"><div class="hm-pp">پیشنهاد ویژه %s …</div>'
                 '<div class="hm-pt">به‌صرفه‌ترین پکیج: %s گیگ</div><p>فقط %s تومان · هر گیگ %s تومان</p>'
                 '<a class="hm-wb" href="/buy/p/%d">%s<span>خرید پکیج</span></a><i>%s</i></div></section>'
                 % (esc(brand), fg(bgb), fa(bpr), fa(round(bpr / bgb)), bid, sv(IC["cart"], 1.8), ico("💎", 1.1)))

    # newest packages carousel
    pm = {p[0]: (i, p[1], p[2] or "") for i, p in enumerate(prs)}
    cards = ""

    def card(href, add, badge, icon, big, title, cat, price, q):
        return ('<div class="hm-pk" data-q="%s"><div class="hm-top"><span class="hm-bd">%s</span>'
                '<a class="hm-im" href="%s"><i>%s</i><b>%s</b></a><a class="hm-add" href="%s" aria-label="افزودن به سبد">%s</a></div>'
                '<a class="hm-nm" href="%s">%s</a><div class="hm-ct">%s</div><div class="hm-pc">%s</div></div>'
                % (esc(q), esc(badge), href, icon, big, add, sv(IC["cart"], 1.8), href, esc(title), esc(cat), price))
    for kid, pid, gb, price in pks:
        if pid not in pm:
            continue
        i, pname, descr = pm[pid]
        cards += card("/buy/p/%d" % kid, "/cart/add/p/%d" % kid, pname, ico(ICONS[i % len(ICONS)]), "%s گیگ" % fg(gb),
                      "%s – %s گیگ" % (pname, fg(gb)), descr[:40], "%s <small>تومان</small>" % fa(price),
                      "%s %s %s گیگ" % (pname, descr, fg(gb)))
    for pid, pname, descr, pgb, mn, mx in prs:
        if pgb:
            i = pm[pid][0]
            cards += card("/buy/c/%d" % pid, "/cart/add/c/%d" % pid, pname, ico(ICONS[i % len(ICONS)]), "حجم دلخواه",
                          "%s – حجم دلخواه" % pname, (descr or "")[:40], "هر گیگ %s <small>تومان</small>" % fa(pgb),
                          "%s %s حجم دلخواه" % (pname, descr or ""))
    if cards:
        car = ('<section class="hm-s"><div class="hm-sec"><span>جدیدترین پکیج‌ها</span><a href="/buy">مشاهده همه</a></div>'
               '<div class="hm-cw"><div class="hm-car">%s</div><button type="button" class="hm-ar r" aria-label="قبلی">%s</button>'
               '<button type="button" class="hm-ar l" aria-label="بعدی">%s</button></div></section>' % (cards, sv(IC["r"], 2), sv(IC["l"], 2)))
    else:
        car = '<section class="hm-s"><div class="card">محصولی فعال نیست.</div></section>'

    # category banners
    cats = "".join(
        '<a class="hm-cat" href="/buy" data-q="%s"><i class="hm-ci">%s</i><div class="hm-cx"><b>%s</b><span>%s</span>'
        '<span class="hm-pill">خرید</span></div></a>' % (esc("%s %s" % (pname, descr or "")), ico(ICONS[i % len(ICONS)]),
                                                       esc(pname), esc((descr or "")[:60]))
        for i, (pid, pname, descr, pgb, mn, mx) in enumerate(prs))
    cats = '<section class="hm-s"><div class="hm-cats">%s</div></section>' % cats if cats else ""

    # footer
    faq = "".join('<details class="hm-fq"><summary>%s</summary><p>%s</p></details>' % (
        esc(x.get("q", "")), esc(x.get("a", "")).replace("\n", "<br>")) for x in d["faq"] if isinstance(x, dict) and x.get("q"))
    links = '<a href="/about">درباره‌ی ما</a>'
    bu = bot_user()
    if bu:
        links += '<a href="https://t.me/%s" target="_blank" rel="noopener">🤖 ربات تلگرام</a>' % esc(bu)
    ct = (d["contact"] or "").lstrip("@")
    if ct:
        links += '<a href="https://t.me/%s" target="_blank" rel="noopener">🎧 پشتیبانی</a>' % esc(ct)
    foot = ('<section class="hm-band">%s<p class="hm-ab">%s</p>%s<div class="hm-fl">%s</div><div class="hm-cp">%s</div></section>'
            % (('<div class="hm-feat">%s</div>' % fh) if fh else "", esc(d["about_text"]).replace("\n", "<br>"), faq, links,
               esc(d["footer"] or brand)))

    body = emo(note + hero + feat + search + promo + car + cats + foot) + HOME_JS
    r = theme.shell("فروشگاه", body, "home")
    t = r.text.replace('<main class="main"><h1>فروشگاه</h1>', '<main class="main shp">', 1)
    return web.Response(text=t, content_type="text/html")


_prev_home = pages.home


async def home(req):
    if req.get("uid") is None and not GUEST_HOME:
        return await _prev_home(req)
    try:
        return await build_home(req)
    except Exception:
        log.exception("shahin home failed, falling back")
        return await _prev_home(req)


# ------------------------------------------------------------------ account
async def account(req):
    uid = req["uid"]

    def work():
        u = A.q("SELECT balance, name FROM users WHERE tg_id=?", (uid,))
        pn = A.q("SELECT COUNT(*) FROM panels WHERE user_id=? AND is_test=0 AND status='active'", (uid,))[0][0]
        return (int(u[0][0] or 0), u[0][1] or "") if u else (0, ""), pn
    (bal, name), pn = await asyncio.to_thread(work)
    rows = "".join('<a href="%s">%s<span>%s</span><small>%s</small></a>' % (u, sv(IC[ic]), t, s) for ic, u, t, s in (
        ("panels", "/panels", "پنل‌های من", "%s پنل فعال" % fa(pn)),
        ("wallet", "/wallet", "کیف پول و شارژ", "%s تومان" % fa(bal)),
        ("store", "/buy", "خرید پنل یا حجم", ""),
        ("bag", "/cart", "سبد خرید", "")))
    bu = bot_user()
    if bu:
        rows += '<a href="https://t.me/%s" target="_blank" rel="noopener">%s<span>ربات تلگرام</span></a>' % (esc(bu), sv(IC["chat"]))
    rows += '<form method="post" action="/logout"><button class="out">%s<span>خروج از حساب</span></button></form>' % sv(IC["out"])
    body = ('<div class="card hm-me"><div class="hm-av">👤</div><div><h3>%s</h3><div class="mu">آیدی: <span dir="ltr">%s</span></div></div></div>'
            '<div class="hm-rows">%s</div>' % (esc(name or "کاربر"), uid, rows))
    return theme.shell("حساب کاربری من", emo(body), "account")


# ------------------------------------------------------------------ typography (font + text size)
import json
import os
import tempfile

TYPO = A.DATA / "typo.json"
FONTDIR = A.DATA / "fonts"
FONTS = {
    "vazir": ("وزیرمتن (پیش‌فرض)", "V,Tahoma,sans-serif"),
    "sys": ("فونت سیستم", 'system-ui,-apple-system,"Segoe UI",Tahoma,Roboto,sans-serif'),
    "tahoma": ("تاهوما", 'Tahoma,"Segoe UI",sans-serif'),
    "naskh": ("نسخ (سیستمی)", '"Noto Naskh Arabic","Droid Arabic Naskh","Traditional Arabic","Times New Roman",serif'),
    "custom": ("فونت آپلودشده", "UF,V,Tahoma,sans-serif"),
}
_tc = {"m": None, "t": None}

TYPO_CSS = r"""
body{font-size:calc(16px*var(--fs,1))}
h1{font-size:calc(27px*var(--fs,1))}
h2{font-size:calc(18px*var(--fs,1))}
.big{font-size:calc(38px*var(--fs,1))}
.mu{font-size:calc(13px*var(--fs,1))}
.sub{font-size:calc(14px*var(--fs,1))}
.pu{font-size:calc(17px*var(--fs,1))}
.cta,.go{font-size:calc(16px*var(--fs,1))}
.sh-menu{font-size:calc(15px*var(--fs,1))}
.sh-logo{font-size:calc(19px*var(--fs,1))}
.sh-bi{font-size:calc(13px*var(--fs,1))}
.sh-dr a,.sh-row{font-size:calc(15px*var(--fs,1))}
.hm-t{font-size:calc(clamp(26px,6.4vw,40px)*var(--fs,1))}
.hm-d{font-size:calc(16px*var(--fs,1))}
.hm-bl{font-size:calc(17px*var(--fs,1))}
.hm-b1,.hm-b2{font-size:calc(15px*var(--fs,1))}
.hm-fi h3{font-size:calc(17px*var(--fs,1))}
.hm-fi p{font-size:calc(14px*var(--fs,1))}
.hm-st{font-size:calc(21px*var(--fs,1))}
.hm-pt{font-size:calc(25px*var(--fs,1))}
.hm-sec{font-size:calc(20px*var(--fs,1))}
.hm-nm{font-size:calc(15px*var(--fs,1))}
.hm-cx b{font-size:calc(20px*var(--fs,1))}
.hm-ab{font-size:calc(19px*var(--fs,1))}
"""


def typo():
    try:
        m = TYPO.stat().st_mtime
    except OSError:
        m = None
    if _tc["t"] is not None and _tc["m"] == m:
        return _tc["t"]
    t = {"font": "vazir", "fs": 90}
    if m is not None:
        try:
            x = json.loads(TYPO.read_text(encoding="utf-8"))
            if isinstance(x, dict):
                if x.get("font") in FONTS:
                    t["font"] = x["font"]
                if isinstance(x.get("fs"), int):
                    t["fs"] = max(70, min(120, x["fs"]))
        except Exception:
            pass
    _tc["m"], _tc["t"] = m, t
    return t


def custom_font():
    try:
        for f in FONTDIR.iterdir():
            if f.name.startswith("custom."):
                return f
    except OSError:
        pass
    return None


def typo_css():
    t = typo()
    cf = custom_font()
    out = ":root{--fs:%s}" % (t["fs"] / 100.0)
    if t["font"] == "custom" and cf is not None:
        out += "@font-face{font-family:UF;src:url(/static/shopfonts/%s?v=%d)}" % (cf.name, int(cf.stat().st_mtime))
    if t["font"] != "vazir" and not (t["font"] == "custom" and cf is None):
        out += "*:not(.wid){font-family:%s!important}" % FONTS[t["font"]][1]
    return out + TYPO_CSS


def typo_view(req, ok=False, err=""):
    landing.need_admin(req)
    t, cf = typo(), custom_font()
    msg = ""
    if ok:
        msg += '<div class="okb">✅ ذخیره شد.</div>'
    if err:
        msg += '<div class="erb">%s</div>' % esc(err)
    opts = ""
    for k, (name, fam) in FONTS.items():
        if k == "custom" and cf is None:
            continue
        opts += ('<label class="rw"><input type="radio" name="font" value="%s"%s> <span style="font-family:%s">%s — نمونه ۱۲۳</span></label>'
                 % (k, " checked" if t["font"] == k else "", esc(fam), esc(name)))
    f1 = landing.card("فونت", opts + '<label>آپلود فونت دلخواه (ttf، otf، woff یا woff2؛ کمتر از ۱ مگابایت)</label>'
                      '<input type="file" name="font_file" accept=".ttf,.otf,.woff,.woff2">'
                      + ('<label class="rw"><input type="checkbox" name="font_del" value="1"> حذف فونت آپلودشده</label>' if cf else ""))
    f2 = landing.card("اندازه‌ی متن", '<label>اندازه: <b id="fsv">%d</b> درصد (۱۰۰ = بزرگ، ۹۰ = پیش‌فرض)</label>'
                      '<input type="range" name="fs" id="fs" min="70" max="120" step="2" value="%d">'
                      '<div class="card" id="fpv" style="margin-top:12px">این یک متن نمونه برای دیدن اندازه است.</div>' % (t["fs"], t["fs"]))
    js = ('<script>(function(){var r=document.getElementById("fs"),v=document.getElementById("fsv"),p=document.getElementById("fpv");'
          'function u(){v.textContent=r.value;p.style.fontSize=(16*r.value/100)+"px"}r.oninput=u;u()})();</script>')
    body = (landing.EDCSS + "<style>.rw{display:flex;align-items:center;gap:8px;margin:10px 0;color:var(--tx)}"
            ".ed input[type=radio]{width:auto}</style>" + msg +
            '<form method="post" action="/admin/typography" enctype="multipart/form-data">' + f1 + f2 +
            '<button class="go">💾 ذخیره</button></form>' + js)
    return theme.shell("فونت و اندازه متن", body, "home")


async def typo_get(req):
    return typo_view(req, ok=bool(req.query.get("ok")))


async def typo_save(req):
    auth.same_origin(req)
    landing.need_admin(req)
    try:
        f = await req.post()
    except web.HTTPRequestEntityTooLarge:
        return typo_view(req, err="حجم فایل باید کمتر از ۱ مگابایت باشد.")
    t = dict(typo())
    fk = f.get("font")
    if isinstance(fk, str) and fk in FONTS:
        t["font"] = fk
    try:
        t["fs"] = max(70, min(120, int(f.get("fs", 90))))
    except (TypeError, ValueError):
        pass
    err = ""
    FONTDIR.mkdir(parents=True, exist_ok=True)
    if f.get("font_del"):
        for x in FONTDIR.glob("custom.*"):
            x.unlink()
        if t["font"] == "custom":
            t["font"] = "vazir"
    fl = f.get("font_file")
    if fl is not None and not isinstance(fl, str) and getattr(fl, "filename", ""):
        data = fl.file.read()
        ext = fl.filename.rsplit(".", 1)[-1].lower() if "." in fl.filename else ""
        if ext not in ("ttf", "otf", "woff", "woff2") or data[:4] not in (b"\x00\x01\x00\x00", b"true", b"OTTO", b"wOFF", b"wOF2"):
            err = "فایل فونت معتبر نیست (ttf، otf، woff یا woff2)."
        else:
            for x in FONTDIR.glob("custom.*"):
                x.unlink()
            (FONTDIR / ("custom." + ext)).write_bytes(data)
            t["font"] = "custom"
    if t["font"] == "custom" and custom_font() is None:
        t["font"] = "vazir"
    fd, tmp = tempfile.mkstemp(dir=str(A.DATA), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(t, fh)
    os.replace(tmp, TYPO)
    if err:
        return typo_view(req, err=err)
    raise web.HTTPFound("/admin/typography?ok=1")


# ------------------------------------------------------------------ wiring
pages.home = home
_pi = pages.install


def install(app):
    _pi(app)
    app.router.add_get("/account", account)
    FONTDIR.mkdir(parents=True, exist_ok=True)
    app.router.add_static("/static/shopfonts/", str(FONTDIR))
    app.router.add_get("/admin/typography", typo_get)
    app.router.add_post("/admin/typography", typo_save)
    app.middlewares.append(mw)


pages.install = install
