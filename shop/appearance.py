import asyncio
import base64
import colorsys
import copy
import io
import json
import os
import re
import tempfile

from aiohttp import web
from PIL import Image

from web import app as A

from . import auth, landing, theme

CFG = A.DATA / "theme.json"
LOGO = A.DATA / "site" / "logo.png"
HEXRE = re.compile(r"^#[0-9a-fA-F]{6}$")
DEF = {"pri": "#7c5cf0", "acc": "#22d3ee", "tint": 0, "bs": "grad", "nav": "app", "br": 14, "cr": 22,
       "order": ["about", "steps", "plans", "faq", "cta"], "hide": []}
SECS = {"about": "معرفی و قابلیت‌ها", "steps": "مراحل کار", "plans": "پکیج‌ها و قیمت‌ها",
        "faq": "سوالات متداول", "cta": "بنر پایین"}
PRESETS = [("بنفش", "#7c5cf0", "#22d3ee"), ("سبز", "#22c55e", "#14b8a6"), ("آبی", "#3b82f6", "#06b6d4"),
           ("نارنجی", "#f97316", "#facc15"), ("صورتی", "#ec4899", "#f59e0b"), ("قرمز", "#ef4444", "#f97316"),
           ("طلایی", "#eab308", "#f97316"), ("فیروزه‌ای", "#14b8a6", "#3b82f6")]
NEU = {"#07070c": 3.5, "#0a0a10": 4, "#0a0a12": 4.2, "#0b0b12": 4.6, "#0d0d13": 5.2, "#10101a": 6.5,
       "#11111a": 7, "#12121a": 7.5, "#161621": 8.8, "#171722": 9.2, "#1b1b2a": 10.5, "#1d1d2a": 11,
       "#1f1f2c": 11.5, "#232331": 13, "#23232f": 13, "#2c2c41": 16, "#2c2c36": 16}
SEC_RE = re.compile(r"<section\b.*?</section>", re.S)
LOGO1 = re.compile(r'(<div class="logo">).*?(</div>)', re.S)
LOGO2 = re.compile(r'(<span class="lg">).*?(</span>)', re.S)

_c = {"m": None, "t": None}
_lg = {"m": None, "u": ""}


# ---------- settings ----------
def load():
    try:
        m = CFG.stat().st_mtime
    except OSError:
        m = None
    if _c["t"] is not None and _c["m"] == m:
        return _c["t"]
    t = copy.deepcopy(DEF)
    if m is not None:
        try:
            s = json.loads(CFG.read_text(encoding="utf-8"))
            if isinstance(s, dict):
                for k in DEF:
                    if k in s and type(s[k]) is type(DEF[k]):
                        t[k] = s[k]
        except Exception:
            pass
    for k in ("pri", "acc"):
        if not HEXRE.match(t[k]):
            t[k] = DEF[k]
        t[k] = t[k].lower()
    if t["bs"] not in ("grad", "solid", "out"):
        t["bs"] = "grad"
    if t["nav"] not in ("app", "slim", "top"):
        t["nav"] = "app"
    order = [x for x in t["order"] if x in SECS]
    order += [x for x in SECS if x not in order]
    t["order"] = order
    t["hide"] = [x for x in t["hide"] if x in SECS]
    _c["m"], _c["t"] = m, t
    return t


def save(t):
    A.DATA.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(A.DATA), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(t, f, ensure_ascii=False)
    os.replace(tmp, CFG)


def logo_uri():
    try:
        m = LOGO.stat().st_mtime
    except OSError:
        return ""
    if _lg["m"] != m:
        _lg["u"] = "data:image/png;base64," + base64.b64encode(LOGO.read_bytes()).decode()
        _lg["m"] = m
    return _lg["u"]


def save_logo(data):
    Image.MAX_IMAGE_PIXELS = 30000000
    im = Image.open(io.BytesIO(data))
    im.load()
    im = im.convert("RGBA")
    im.thumbnail((128, 128))
    LOGO.parent.mkdir(parents=True, exist_ok=True)
    tmp = LOGO.with_suffix(".tmp")
    im.save(tmp, "PNG", optimize=True)
    os.replace(tmp, LOGO)


# ---------- colors ----------
def rgb(h):
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (1, 3, 5))


def hsl(h, s, l):
    r, g, b = colorsys.hls_to_rgb(h, max(0, min(1, l)), max(0, min(1, s)))
    return "#%02x%02x%02x" % (round(r * 255), round(g * 255), round(b * 255))


def hue(c):
    r, g, b = rgb(c)
    h, l, s = colorsys.rgb_to_hls(r, g, b)
    return h, s, l


def lum(c):
    r, g, b = rgb(c)
    return 0.299 * r + 0.587 * g + 0.114 * b


def palette(t):
    m = {}
    if t["pri"] != DEF["pri"]:
        h, s, _ = hue(t["pri"])
        sp = s if s < .12 else max(min(s, 1), .55)
        m["#7c5cf0"] = t["pri"]
        m["#a78bfa"] = hsl(h, sp, .76)
        m["#c4b5fd"] = hsl(h, sp, .85)
        m["#ddd6fe"] = hsl(h, sp, .91)
        m["#e0e7ff"] = hsl(h, sp, .93)
        m["#4338ca"] = hsl(h, sp, .50)
        m["#2d2366"] = hsl(h, sp * .55, .27)
        m["#251f4a"] = hsl(h, sp * .45, .20)
        m["#3b3573"] = hsl(h, sp * .35, .32)
        m["#1b1b3c"] = hsl(h, sp * .40, .17)
    if t["acc"] != DEF["acc"]:
        h, s, _ = hue(t["acc"])
        sp = s if s < .12 else max(min(s, 1), .55)
        m["#22d3ee"] = t["acc"]
        m["#67e8f9"] = hsl(h, sp, .72)
        m["#0e7490"] = hsl(h, sp, .30)
        m["#153b55"] = hsl(h, sp * .6, .22)
    if t["tint"]:
        h, s, _ = hue(t["pri"])
        sat = 0 if s < .12 else .28
        for k, l in NEU.items():
            m[k] = hsl(h, sat, l / 100.0)
    return m


def recolor(txt, m):
    if not m:
        return txt
    rx = re.compile("|".join(re.escape(k) for k in m), re.I)
    return rx.sub(lambda mo: m[mo.group(0).lower()], txt)


# ---------- page transforms ----------
def skey(s):
    h = s[:80]
    if 'id="more"' in h:
        return "about"
    if 'id="plans"' in h:
        return "plans"
    if 'id="faq"' in h:
        return "faq"
    if h.startswith('<section class="cta'):
        return "cta"
    if h.startswith('<section class="sec"'):
        return "steps"
    return None


def reorder(txt, t):
    if '<header class="hero' not in txt:
        return txt
    i = txt.find("</header>")
    j = txt.find("<section", i)
    k = txt.rfind("</section>")
    if i < 0 or j < 0 or k < j:
        return txt
    k += len("</section>")
    block = txt[j:k]
    parts = SEC_RE.findall(block)
    if "".join(parts) != block:
        return txt
    got = {}
    for p in parts:
        key = skey(p)
        if key is None or key in got:
            return txt
        got[key] = p
    out = "".join(got[x] for x in t["order"] if x in got and x not in t["hide"])
    txt = txt[:j] + out + txt[k:]
    for key, link in (("plans", '<a href="#plans">قیمت‌ها</a>'), ("faq", '<a href="#faq">سوالات</a>'),
                      ("about", '<a href="#more">درباره</a>')):
        if key in t["hide"]:
            txt = txt.replace(link, "")
    return txt


NAVBLK = re.compile(r'<nav class="tabs"[^>]*>(.*?)</nav>', re.S)
NAVA = re.compile(r'<a\b[^>]*class="tb[^"]*"[^>]*>.*?</a>', re.S)
TAGS = re.compile(r'<[^>]+>')
ICONS = {
    'home': '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    'store': '<path d="M3 9l1.5-5h15L21 9"/><path d="M4 9v11h16V9"/><path d="M9 20v-6h6v6"/>',
    'cart': '<circle cx="9" cy="20" r="1.3"/><circle cx="18" cy="20" r="1.3"/><path d="M2 3h3l2.5 12h11L21 7H6"/>',
    'panels': '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    'wallet': '<rect x="3" y="6" width="18" height="14" rx="2"/><path d="M3 10h18"/><circle cx="17" cy="15" r="1"/>',
    'dot': '<circle cx="12" cy="12" r="3"/>',
}
NAVKEYS = (('home', 'خانه'), ('store', 'فروشگاه'), ('cart', 'سبد'), ('panels', 'پنل'), ('wallet', 'کیف'))
SLIMCSS = '''.tabs{gap:0!important;padding:5px 4px calc(5px + env(safe-area-inset-bottom))!important;background:#0a0a10!important;border-top:1px solid var(--bd)!important}
.tb{background:none!important;border-radius:0!important;box-shadow:none!important;color:var(--mu)!important;font-size:11px!important;gap:3px!important;padding:7px 0!important;position:relative}
.tb svg{width:22px;height:22px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
.tb.on{color:var(--pri,#a78bfa)!important}
.tb.on:before{content:"";position:absolute;top:-6px;left:32%;right:32%;height:2px;border-radius:2px;background:var(--pri,#a78bfa)}
@media(min-width:900px){.tb{flex-direction:row!important;font-size:14px!important;padding:9px 16px!important}.tb.on:before{display:none}}'''
TOPCSS = '''.tabs{display:none!important}
body{padding-bottom:0!important}
.mb{background:var(--pri,#7c5cf0);color:#fff;border:0;border-radius:12px;padding:9px 14px;font-family:inherit;font-size:14px;font-weight:700;cursor:pointer}
.mm{display:none;position:fixed;top:62px;right:12px;left:12px;max-width:300px;z-index:60;background:#12121a;border:1px solid #232331;border-radius:16px;padding:6px;box-shadow:0 18px 40px #000a}
.mm.open{display:block}
.mm a{display:flex;align-items:center;gap:10px;padding:13px 14px;border-radius:10px;color:#eceef5}
.mm a.on{color:var(--pri,#a78bfa)}
.mm svg{width:20px;height:20px;fill:none;stroke:currentColor;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}'''
TOPJS = '''<script>(function(){var b=document.querySelector('.mb'),m=document.querySelector('.mm');if(b&&m)b.onclick=function(e){e.stopPropagation();m.classList.toggle('open')};document.addEventListener('click',function(){if(m)m.classList.remove('open')})})();</script>'''


def nav_items(blk):
    out = []
    for a in NAVA.findall(blk):
        mh = re.search(r'href="([^"]*)"', a)
        if not mh:
            continue
        mc = re.search(r'class="tb([^"]*)"', a)
        on = 'on' in (mc.group(1).split() if mc else [])
        lab = TAGS.sub('', re.sub(r'<i\b.*?</i>', '', a, flags=re.S)).strip()
        key = 'dot'
        for k, w in NAVKEYS:
            if w in lab:
                key = k
                break
        out.append((mh.group(1), lab, key, on))
    return out


def svg(key):
    return '<svg viewBox="0 0 24 24" aria-hidden="true">' + ICONS[key] + '</svg>'


def navfix(txt, t, pal):
    if t['nav'] == 'app':
        return txt
    mo = NAVBLK.search(txt)
    if not mo:
        return txt
    items = nav_items(mo.group(1))
    if not items or '</head>' not in txt:
        return txt
    mode = t['nav']
    if mode == 'top' and '<header class="top">' not in txt:
        mode = 'slim'
    css = SLIMCSS
    tail = ''
    if mode == 'slim':
        inner = ''.join('<a class="tb' + (' on' if on else '') + '" href="' + href + '">' + svg(k) + '<span>' + lab + '</span></a>'
                        for href, lab, k, on in items)
        txt = txt[:mo.start(1)] + inner + txt[mo.end(1):]
    else:
        css = TOPCSS
        menu = '<div class="mm">' + ''.join('<a' + (' class="on"' if on else '') + ' href="' + href + '">' + svg(k) + lab + '</a>'
                                           for href, lab, k, on in items) + '</div>'
        txt = txt.replace('<header class="top">', '<header class="top"><button type="button" class="mb" aria-label="منو">☰ منو</button>', 1)
        txt = txt.replace('</header>', '</header>' + menu, 1)
        tail = TOPJS
    txt = txt.replace('</head>', '<style>' + recolor(css, pal) + '</style></head>', 1)
    if tail and '</body>' in txt:
        txt = txt.replace('</body>', tail + '</body>', 1)
    return txt


def extra_css(t, logo):
    p, a = t["pri"], t["acc"]
    c = ":root{--pri:%s;--acc:%s}" % (p, a)
    if t["br"] != DEF["br"]:
        c += ".b1,.b2,a.cta,.go,.nb,.cp,.lo button,.fab{border-radius:%dpx!important}" % t["br"]
    if t["cr"] != DEF["cr"]:
        c += ".card,.ft{border-radius:%dpx!important}" % t["cr"]
    btn = ".b1,a.cta:not(.off),.go"
    changed = p != DEF["pri"] or a != DEF["acc"]
    if t["bs"] == "solid":
        c += btn + "{background:var(--pri)!important;box-shadow:none!important}"
    elif t["bs"] == "out":
        c += btn + "{background:transparent!important;border:2px solid var(--pri)!important;color:var(--pri)!important;box-shadow:none!important}"
    if t["bs"] == "solid" or (t["bs"] == "grad" and changed):
        L = lum(p) if t["bs"] == "solid" else (lum(p) + lum(a)) / 2
        c += btn + "{color:%s!important}" % ("#0b0b12" if L > .62 else "#fff")
    if logo:
        c += ".logo,.lg{background:transparent!important;overflow:hidden}.logo img,.lg img{width:100%;height:100%;object-fit:contain}"
        c += '.bx:before{content:""!important;background:url("%s") center/contain no-repeat!important}' % logo
    return "<style>" + c + "</style>"


def fab(req):
    uid = req.get("uid")
    if uid is None or uid not in A.admin_ids():
        return ""
    p = req.path
    if p == "/admin/appearance" or not (p.startswith("/admin") or p in ("/", "/about")):
        return ""
    return ('<a href="/admin/appearance" style="position:fixed;bottom:92px;left:16px;z-index:40;padding:10px 14px;'
            'border-radius:14px;background:var(--pri);color:#fff;font:14px V,Tahoma,sans-serif;'
            'box-shadow:0 8px 24px #0006">🎨 ظاهر سایت</a>')


@web.middleware
async def mw(req, handler):
    resp = await handler(req)
    try:
        if type(resp) is not web.Response or resp.content_type != "text/html" or resp.text is None:
            return resp
        t = load()
        txt = resp.text
        txt = recolor(txt, palette(t))
        txt = reorder(txt, t)
        txt = navfix(txt, t, palette(t))
        logo = logo_uri()
        if logo:
            img = '<img src="%s" alt="">' % logo
            txt = LOGO1.sub(lambda mo: mo.group(1) + img + mo.group(2), txt)
            txt = LOGO2.sub(lambda mo: mo.group(1) + img + mo.group(2), txt)
        head = extra_css(t, logo)
        if logo:
            head += '<link rel="icon" href="%s">' % logo
        if "</head>" in txt:
            txt = txt.replace("</head>", head + "</head>", 1)
        f = fab(req)
        if f and "</body>" in txt:
            txt = txt.replace("</body>", f + "</body>", 1)
        resp.text = txt
        resp.headers.pop("Content-Length", None)
    except Exception:
        pass
    return resp


# ---------- editor ----------
CSSX = """<style>
.ed input[type=color]{height:46px;padding:3px;cursor:pointer}
.ed input[type=radio]{width:auto}
.ps{display:inline-flex;align-items:center;gap:8px;margin:4px;padding:8px 14px;border-radius:12px;border:1px solid var(--bd);background:var(--card);color:var(--tx);font-family:inherit;cursor:pointer}
.ps i{width:18px;height:18px;border-radius:50%;display:inline-block}
.pv{margin-top:12px;padding:18px;border:1px solid var(--bd);border-radius:var(--cr,22px);background:var(--card)}
.pv .pb{display:inline-block;padding:11px 22px;font-weight:700;color:#fff;border-radius:var(--br,14px);background:linear-gradient(135deg,var(--pp),var(--pa))}
.pv.solid .pb{background:var(--pp)}
.pv.out .pb{background:transparent;border:2px solid var(--pp);color:var(--pp)}
.pv .pt{margin:0 0 12px;font-weight:700}
#ord{list-style:none;margin:0;padding:0}
#ord li{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:10px 0;border-top:1px solid var(--bd)}
#ord li button{background:var(--card);border:1px solid var(--bd);color:var(--tx);border-radius:10px;width:36px;height:34px;cursor:pointer;margin-right:4px}
.ed label.rw{display:flex;align-items:center;gap:8px;color:var(--tx)}
</style>"""

JSX = """<script>(function(){
var $=function(i){return document.getElementById(i)};
var pri=$("pri"),acc=$("acc");
pri.value="#"+pri.dataset.v;acc.value="#"+acc.dataset.v;
[].forEach.call(document.querySelectorAll("[data-g]"),function(e){var g=e.dataset.g.split(",");e.style.background="linear-gradient(135deg,#"+g[0]+",#"+g[1]+")"});
function upd(){
var pv=$("pv");pv.style.setProperty("--pp",pri.value);pv.style.setProperty("--pa",acc.value);
var bs=document.querySelector("input[name=bs]:checked").value;pv.className="pv "+bs;
pv.style.setProperty("--br",$("br").value+"px");pv.style.setProperty("--cr",$("cr").value+"px");
$("brv").textContent=$("br").value;$("crv").textContent=$("cr").value}
[].forEach.call(document.querySelectorAll("#f input"),function(e){e.addEventListener("input",upd);e.addEventListener("change",upd)});
[].forEach.call(document.querySelectorAll(".ps"),function(b){b.onclick=function(){pri.value="#"+b.dataset.p;acc.value="#"+b.dataset.a;upd()}});
[].forEach.call(document.querySelectorAll("#ord button"),function(b){b.onclick=function(){var li=b.closest("li"),d=+b.dataset.d;
if(d<0&&li.previousElementSibling)li.parentNode.insertBefore(li,li.previousElementSibling);
if(d>0&&li.nextElementSibling)li.parentNode.insertBefore(li.nextElementSibling,li)}});
$("f").onsubmit=function(){var o=[];[].forEach.call(document.querySelectorAll("#ord li"),function(l){o.push(l.dataset.k)});$("order").value=o.join(",")};
upd()})();</script>"""


def form(t, ok=False, err=""):
    esc = theme.esc
    msg = ""
    if ok:
        msg += '<div class="okb">✅ ذخیره شد. <a href="/about" target="_blank" style="text-decoration:underline">دیدن سایت</a></div>'
    if err:
        msg += '<div class="erb">%s</div>' % esc(err)
    ps = "".join('<button type="button" class="ps" data-p="%s" data-a="%s"><i data-g="%s,%s"></i>%s</button>'
                 % (p[1:], a[1:], p[1:], a[1:], esc(n)) for n, p, a in PRESETS)
    colors = ('<label>تم‌های آماده</label><div>' + ps + '</div>'
              '<label>رنگ اصلی</label><input type="color" name="pri" id="pri" data-v="%s">'
              '<label>رنگ دوم (انتهای گرادیان)</label><input type="color" name="acc" id="acc" data-v="%s">'
              '<label class="rw"><input type="checkbox" name="tint" value="1"%s> هماهنگ‌کردن پس‌زمینه‌ی تیره با رنگ اصلی</label>'
              % (t["pri"][1:], t["acc"][1:], " checked" if t["tint"] else ""))

    def rb(v, label):
        return '<label class="rw"><input type="radio" name="bs" value="%s"%s> %s</label>' % (v, " checked" if t["bs"] == v else "", label)
    btns = (rb("grad", "گرادیان (پیش‌فرض)") + rb("solid", "تک‌رنگ") + rb("out", "خطی (توخالی)") +
            '<label>گردی گوشه‌ی دکمه‌ها: <b id="brv">%d</b></label><input type="range" name="br" id="br" min="0" max="32" value="%d">'
            '<label>گردی گوشه‌ی کارت‌ها: <b id="crv">%d</b></label><input type="range" name="cr" id="cr" min="6" max="34" value="%d">'
            '<div class="pv" id="pv"><p class="pt">پیش‌نمایش</p><span class="pb">دکمه‌ی نمونه</span></div>'
            % (t["br"], t["br"], t["cr"], t["cr"]))
    lg = logo_uri()
    logo = ""
    if lg:
        logo += '<img src="%s" style="width:64px;height:64px;object-fit:contain;border-radius:12px;display:block;margin-bottom:8px" alt="">' % lg
    logo += ('<label>لوگو (PNG یا JPG، ترجیحاً مربع؛ جایگزین آیکن سپر و فاویکون می‌شود)</label>'
             '<input type="file" name="logo" accept="image/*">'
             '<label class="rw"><input type="checkbox" name="logo_del" value="1"> حذف لوگوی فعلی</label>')
    def nr(v, label):
        return '<label class="rw"><input type="radio" name="nav" value="' + v + '"' + (" checked" if t["nav"] == v else "") + "> " + label + "</label>"
    navc = (nr("app", "نوار پایین بزرگ (حالت فعلی)") + nr("slim", "نوار پایین ساده و باریک (آیکن خطی، بدون پس‌زمینه)") +
            nr("top", "منوی بالا با دکمه‌ی «منو» (بدون نوار پایین)"))
    lis = ""
    for k in t["order"]:
        lis += ('<li data-k="%s"><label class="rw"><input type="checkbox" name="show_%s" value="1"%s> %s</label>'
                '<span><button type="button" data-d="-1">↑</button><button type="button" data-d="1">↓</button></span></li>'
                % (k, k, "" if k in t["hide"] else " checked", esc(SECS[k])))
    lay = ('<div class="sub">با ↑ و ↓ جای بخش‌ها را عوض کن و با تیک، نمایش‌شان را روشن یا خاموش کن. '
           'بخش خالی (مثلاً قیمت‌ها بدون محصول) خودکار نمایش داده نمی‌شود.</div><ul id="ord">' + lis + '</ul>'
           '<input type="hidden" name="order" id="order">')
    return (landing.EDCSS + CSSX + msg +
            '<form method="post" action="/admin/appearance" enctype="multipart/form-data" id="f">' +
            landing.card("رنگ‌ها", colors) + landing.card("دکمه‌ها و کارت‌ها", btns) +
            landing.card("منوی ناوبری", navc) + landing.card("لوگو", logo) + landing.card("چیدمان صفحه‌ی اصلی", lay) +
            '<button class="go">💾 ذخیره‌ی تغییرات</button></form>'
            '<form method="post" action="/admin/appearance/reset" onsubmit="return confirm(\'همه‌ی تنظیمات ظاهر به حالت پیش‌فرض برگردد؟\')">'
            '<button class="rst">↩️ بازگشت به ظاهر پیش‌فرض</button></form>'
            '<a class="lk" href="/admin/site">✏️ ویرایش متن‌های صفحه‌ی اصلی</a>' + JSX)


def clampint(v, lo, hi, d):
    try:
        return max(lo, min(hi, int(v)))
    except Exception:
        return d


async def page(req):
    landing.need_admin(req)
    return theme.shell("ظاهر سایت", form(load(), ok=bool(req.query.get("ok"))), "home")


async def save_post(req):
    auth.same_origin(req)
    landing.need_admin(req)
    t = copy.deepcopy(load())
    try:
        f = await req.post()
    except web.HTTPRequestEntityTooLarge:
        return theme.shell("ظاهر سایت", form(t, err="فایل خیلی بزرگ است؛ لوگوی کوچک‌تری انتخاب کن."), "home")

    def hexv(k):
        v = f.get(k, "")
        return v.lower() if isinstance(v, str) and HEXRE.match(v) else t[k]
    t["pri"], t["acc"] = hexv("pri"), hexv("acc")
    t["tint"] = 1 if f.get("tint") else 0
    nv = f.get("nav")
    t["nav"] = nv if nv in ("app", "slim", "top") else "app"
    bs = f.get("bs")
    t["bs"] = bs if bs in ("grad", "solid", "out") else "grad"
    t["br"] = clampint(f.get("br"), 0, 32, 14)
    t["cr"] = clampint(f.get("cr"), 6, 34, 22)
    od = [x for x in str(f.get("order", "")).split(",") if x in SECS]
    od += [x for x in SECS if x not in od]
    t["order"] = od
    t["hide"] = [k for k in SECS if not f.get("show_" + k)]
    err = ""
    if f.get("logo_del"):
        try:
            LOGO.unlink()
        except OSError:
            pass
    fl = f.get("logo")
    if fl is not None and not isinstance(fl, str) and getattr(fl, "filename", ""):
        data = fl.file.read()
        if len(data) > 3000000:
            err = "لوگو بزرگ‌تر از ۳ مگابایت است."
        else:
            try:
                await asyncio.to_thread(save_logo, data)
            except Exception:
                err = "فایل لوگو معتبر نیست."
    await asyncio.to_thread(save, t)
    if err:
        return theme.shell("ظاهر سایت", form(load(), ok=True, err=err), "home")
    raise web.HTTPFound("/admin/appearance?ok=1")


async def reset(req):
    auth.same_origin(req)
    landing.need_admin(req)
    for p in (CFG, LOGO):
        try:
            p.unlink()
        except OSError:
            pass
    raise web.HTTPFound("/admin/appearance?ok=1")


def setup(app):
    app.middlewares.append(mw)
    app.router.add_get("/admin/appearance", page)
    app.router.add_post("/admin/appearance", save_post)
    app.router.add_post("/admin/appearance/reset", reset)
