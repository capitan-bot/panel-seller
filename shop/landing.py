from __future__ import annotations

import asyncio
import copy
import io
import json
import os
import re
import tempfile

from aiohttp import web
from PIL import Image

from web import app as A

from . import auth, pages, skin, theme
from .theme import bot_user, esc, fa, fg

CFG = A.DATA / "site.json"
SITE = A.DATA / "site"
HERO = SITE / "hero.jpg"
NF, NS, NQ = 6, 4, 6
LINK = re.compile(r"^(https?://[^\s\"'<>]+|/(?!/)[^\s\"'<>]*|#[\w-]*)$")

DEF = {
    "brand": "",
    "hero_title": "پنل نمایندگی خودت را در چند ثانیه بساز",
    "hero_sub": "خرید پنل، تحویل فوری، مدیریت ساده و ربات تلگرام؛ همه از یک‌جا.",
    "b1_text": "شروع و ورود", "b1_link": "/login",
    "b2_text": "ادامه ↓", "b2_link": "#more",
    "overlay": 60,
    "about_title": "چرا ما؟",
    "about_text": "همه‌چیز برای شروع کار نمایندگی در یک سایت و یک ربات جمع شده است: انتخاب پکیج، پرداخت از کیف پول، تحویل پنل و مدیریت سرویس.",
    "features": [
        {"i": "⚡", "t": "تحویل سریع", "d": "بعد از پرداخت از کیف پول، پنل در چند ثانیه ساخته می‌شود و اطلاعاتش برایت می‌آید."},
        {"i": "🔐", "t": "ورود امن", "d": "ورود فقط با کد یک‌بارمصرفی که به تلگرام خودت می‌آید؛ رمز اضافه‌ای لازم نیست."},
        {"i": "💳", "t": "کیف پول", "d": "کیف پول را شارژ کن و هر زمان خواستی حجم یا پنل جدید بخر."},
        {"i": "📊", "t": "مدیریت و مصرف", "d": "وضعیت، حجم و تاریخ هر پنل را در یک نگاه ببین."},
        {"i": "🤖", "t": "ربات تلگرام", "d": "همه‌ی کارها را هم از سایت و هم از ربات انجام بده."},
        {"i": "🎧", "t": "پشتیبانی", "d": "اگر مشکلی بود، از طریق تلگرام به ما خبر بده."},
    ],
    "steps_title": "چطور کار می‌کند؟",
    "steps": [
        {"t": "ورود با تلگرام", "d": "آیدی عددی‌ات را بزن و کد ورود را از ربات بگیر."},
        {"t": "شارژ کیف پول", "d": "با کارت‌به‌کارت و ارسال رسید، موجودی‌ات را شارژ کن."},
        {"t": "خرید و تحویل", "d": "پکیج را انتخاب کن؛ نام کاربری و رمز پنل همان لحظه تحویل می‌شود."},
    ],
    "show_prices": 1,
    "plans_title": "پکیج‌ها و قیمت‌ها",
    "faq": [
        {"q": "چطور وارد شوم؟", "a": "آیدی عددی تلگرامت را وارد کن؛ یک کد ۶ رقمی به ربات می‌آید. ربات باید قبلاً /start شده باشد."},
        {"q": "کیف پول چطور شارژ می‌شود؟", "a": "با کارت‌به‌کارت و ارسال عکس رسید. بعد از تأیید، موجودی اضافه می‌شود."},
        {"q": "بعد از خرید چه چیزی می‌گیرم؟", "a": "آدرس ورود به پنل، نام کاربری و رمز؛ هم در سایت و هم در تلگرام."},
        {"q": "اگر مشکلی پیش آمد؟", "a": "از طریق تلگرام به پشتیبانی پیام بده."},
    ],
    "cta_title": "آماده‌ای شروع کنیم؟",
    "cta_text": "همین حالا وارد شو و اولین پنلت را بساز.",
    "cta_btn": "ورود و خرید", "cta_link": "/login",
    "contact": "",
    "footer": "",
}


def load():
    d = copy.deepcopy(DEF)
    try:
        s = json.loads(CFG.read_text(encoding="utf-8"))
        if isinstance(s, dict):
            for k, v in s.items():
                if k in d and type(v) is type(d[k]):
                    d[k] = v
    except Exception:
        pass
    return d


def save(d):
    A.DATA.mkdir(exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(A.DATA), suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False)
    os.replace(tmp, CFG)


def clip(s, n):
    return (s or "").strip()[:n]


def clean_link(v, default):
    v = clip(v, 300)
    return v if LINK.match(v) else default


LCSS = r"""
@font-face{font-family:V;src:url(/static/Vazirmatn-Regular.ttf)}
@font-face{font-family:V;font-weight:700;src:url(/static/Vazirmatn-Bold.ttf)}
:root{--bd:#232331;--tx:#eceef5;--mu:#9a9db0}
*{box-sizing:border-box}html{scroll-behavior:smooth;background:#07070c}
body{margin:0;color:var(--tx);font-family:V,Tahoma,sans-serif;background:#07070c}
a{color:inherit;text-decoration:none}
.nav{position:absolute;top:0;left:0;right:0;z-index:5;display:flex;align-items:center;gap:12px;padding:14px 18px}
.br{display:flex;align-items:center;gap:10px;font-weight:700}
.lg{width:36px;height:36px;border-radius:11px;display:grid;place-items:center;background:linear-gradient(135deg,#7c5cf0,#22d3ee)}
.nl{display:flex;gap:4px}.nl a{padding:8px 12px;border-radius:10px;color:#cfd2e3;font-size:14px}.sp{flex:1}
.nb{padding:9px 16px;border-radius:12px;background:#ffffff1f;border:1px solid #ffffff33;font-size:14px;white-space:nowrap}
@media(max-width:700px){.nl{display:none}}
.hero{position:relative;min-height:100vh;min-height:100svh;display:flex;align-items:center;justify-content:center;text-align:center;padding:90px 18px 70px;background-size:cover;background-position:center}
.noimg{background:radial-gradient(620px 420px at 85% 8%,#7c5cf055,transparent 62%),radial-gradient(520px 400px at 4% 92%,#22d3ee33,transparent 62%),#0a0a12}
.noimg:after{content:"";position:absolute;inset:0;pointer-events:none;background-image:linear-gradient(#ffffff08 1px,transparent 1px),linear-gradient(90deg,#ffffff08 1px,transparent 1px);background-size:44px 44px;-webkit-mask-image:radial-gradient(ellipse at 50% 40%,#000 10%,transparent 70%);mask-image:radial-gradient(ellipse at 50% 40%,#000 10%,transparent 70%)}
.hi{position:relative;z-index:2;max-width:760px}
.hero h1{margin:0 0 14px;font-size:clamp(28px,6vw,52px);line-height:1.45}
.hero p{margin:0 auto 26px;max-width:600px;color:#d5d8e8;font-size:clamp(15px,2.6vw,19px);line-height:2}
.bt{display:flex;gap:12px;justify-content:center;flex-wrap:wrap}
.b1,.b2{display:inline-block;padding:14px 28px;border-radius:16px;font-weight:700;font-size:16px}
.b1{background:linear-gradient(135deg,#a78bfa,#7c5cf0 55%,#22d3ee);color:#fff;box-shadow:0 12px 30px #7c5cf055}
.b2{background:#ffffff1c;border:1px solid #ffffff3a}.b1.sm{padding:10px 20px;font-size:14px;margin-top:14px}
.sc{position:absolute;bottom:16px;left:50%;transform:translateX(-50%);color:#ffffffaa;font-size:22px;animation:bn 1.8s infinite}
@keyframes bn{50%{transform:translate(-50%,7px)}}
.sec{max-width:1040px;margin:auto;padding:64px 18px 0}
.sec h2{margin:0 0 8px;font-size:clamp(22px,4vw,32px);text-align:center}
.lead{text-align:center;color:var(--mu);line-height:2;max-width:660px;margin:0 auto 28px}
.gr{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px}
.ft{padding:22px;border-radius:22px;background:linear-gradient(165deg,#161621,#10101a);border:1px solid var(--bd)}
.ft i{font-style:normal;font-size:28px;width:56px;height:56px;border-radius:18px;display:grid;place-items:center;background:#251f4a;margin-bottom:12px}
.ft h3{margin:0 0 6px}.ft p{margin:0;color:var(--mu);line-height:1.9;font-size:14px}
.chs{display:flex;flex-wrap:wrap;gap:6px;margin-top:12px}
.chp{padding:6px 12px;border-radius:99px;background:#1b1b2a;border:1px solid #2c2c41;font-size:13px}.chp b{color:#c4b5fd}
.fq{margin:0 auto 10px;max-width:760px;border-radius:16px;background:#12121a;border:1px solid var(--bd);padding:4px 16px}
.fq summary{cursor:pointer;padding:14px 0;font-weight:700}.fq p{margin:0 0 14px;color:var(--mu);line-height:1.9}
.cta{max-width:1040px;margin:64px auto 0;padding:36px 22px;border-radius:28px;text-align:center;background:linear-gradient(135deg,#2d2366,#153b55);border:1px solid #3b3573}
.cta h2{margin:0 0 8px}.cta p{margin:0 0 20px;color:#cbd5e1}
.fo{max-width:1040px;margin:34px auto 0;padding:24px 18px 40px;display:flex;flex-wrap:wrap;gap:14px;justify-content:space-between;color:var(--mu);font-size:13px}
.fo a{color:#c4b5fd}
.fab{position:fixed;bottom:16px;left:16px;z-index:9;padding:11px 16px;border-radius:14px;background:#251f4a;border:1px solid #3b3573;font-size:14px}
.js .rv{opacity:0;transform:translateY(18px);transition:opacity .6s,transform .6s}.js .rv.in{opacity:1;transform:none}
@media(prefers-reduced-motion:reduce){.js .rv{opacity:1;transform:none;transition:none}.sc{animation:none}}
"""

LJS = ("<script>(function(){var r=[].slice.call(document.querySelectorAll('.rv'));"
       "if(!window.IntersectionObserver){r.forEach(function(e){e.classList.add('in')});return}"
       "var o=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){e.target.classList.add('in');o.unobserve(e.target)}})},{threshold:.12});"
       "r.forEach(function(e){o.observe(e)})})();</script>")


def plans_html(d):
    if not d["show_prices"]:
        return ""
    prs = A.q("SELECT id,name,descr FROM products WHERE active=1 ORDER BY sort,id")
    pks = A.q("SELECT product_id,gb,price FROM packages WHERE active=1 ORDER BY gb")
    cards = ""
    for pid, name, descr in prs:
        mine = [(g, p) for q, g, p in pks if q == pid]
        if not mine:
            continue
        chips = "".join('<span class="chp">%s گیگ <b>%s</b> تومان</span>' % (fg(g), fa(p)) for g, p in mine[:5])
        cards += ('<div class="ft rv"><h3>%s</h3><p>%s</p><div class="chs">%s</div><a class="b1 sm" href="/buy">خرید</a></div>'
                  % (esc(name), esc(descr), chips))
    if not cards:
        return ""
    return '<section class="sec" id="plans"><h2>%s</h2><div class="gr">%s</div></section>' % (esc(d["plans_title"]), cards)


def render(uid, d):
    brand = d["brand"] or theme.TITLE
    admin = uid is not None and uid in A.admin_ids()
    o = max(0, min(90, int(d["overlay"]))) / 100.0
    if HERO.exists():
        bg = (' style="background-image:linear-gradient(rgba(7,7,12,%.2f),rgba(7,7,12,%.2f)),url(/site/hero.jpg?v=%d)"'
              % (o, min(o + .3, .97), int(HERO.stat().st_mtime)))
        cls = "hero"
    else:
        bg, cls = "", "hero noimg"

    def lk(v):
        return "/buy" if uid is not None and v == "/login" else v
    feats = "".join('<div class="ft rv"><i>%s</i><h3>%s</h3><p>%s</p></div>' % (
        esc(x.get("i") or "✨"), esc(x.get("t", "")), esc(x.get("d", ""))) for x in d["features"] if isinstance(x, dict))
    steps = "".join('<div class="ft rv"><i>%s</i><h3>%s</h3><p>%s</p></div>' % (
        fa(i + 1), esc(x.get("t", "")), esc(x.get("d", ""))) for i, x in enumerate(d["steps"]) if isinstance(x, dict))
    faq = "".join('<details class="fq rv"><summary>%s</summary><p>%s</p></details>' % (
        esc(x.get("q", "")), esc(x.get("a", "")).replace("\n", "<br>")) for x in d["faq"] if isinstance(x, dict) and x.get("q"))
    plans = plans_html(d)
    links = '<a href="#more">درباره</a>' + ('<a href="#plans">قیمت‌ها</a>' if plans else "") + ('<a href="#faq">سوالات</a>' if faq else "")
    right = '<a class="nb" href="%s">%s</a>' % (("/", "🏠 فروشگاه") if uid is not None else ("/login", "ورود"))
    nav = ('<nav class="nav"><a class="br" href="/about"><span class="lg">🛡</span>%s</a><div class="nl">%s</div>'
           '<span class="sp"></span>%s</nav>' % (esc(brand), links, right))
    hero = ('<header class="%s"%s><div class="hi"><h1>%s</h1><p>%s</p><div class="bt"><a class="b1" href="%s">%s</a>'
            '<a class="b2" href="%s">%s</a></div></div><a class="sc" href="#more" aria-label="ادامه">⌄</a></header>'
            % (cls, bg, esc(d["hero_title"]), esc(d["hero_sub"]), esc(lk(d["b1_link"])), esc(d["b1_text"]),
               esc(d["b2_link"]), esc(d["b2_text"])))
    about = ('<section class="sec" id="more"><h2 class="rv">%s</h2><div class="lead rv">%s</div><div class="gr">%s</div></section>'
             % (esc(d["about_title"]), esc(d["about_text"]).replace("\n", "<br>"), feats))
    stp = ('<section class="sec"><h2 class="rv">%s</h2><div class="gr">%s</div></section>' % (esc(d["steps_title"]), steps)) if steps else ""
    fsec = ('<section class="sec" id="faq"><h2 class="rv">سوالات متداول</h2>%s</section>' % faq) if faq else ""
    cta = ('<section class="cta rv"><h2>%s</h2><p>%s</p><a class="b1" href="%s">%s</a></section>'
           % (esc(d["cta_title"]), esc(d["cta_text"]), esc(lk(d["cta_link"])), esc(d["cta_btn"])))
    bu = bot_user()
    ct = d["contact"].lstrip("@")
    fl = ""
    if bu:
        fl += '<a href="https://t.me/%s" target="_blank" rel="noopener">🤖 ربات تلگرام</a> ' % esc(bu)
    if ct:
        fl += '<a href="https://t.me/%s" target="_blank" rel="noopener">🎧 پشتیبانی</a>' % esc(ct)
    foot = '<footer class="fo"><div>%s</div><div>%s</div></footer>' % (esc(d["footer"] or brand), fl)
    fab = '<a class="fab" href="/admin/site">✏️ ویرایش سایت</a>' if admin else ""
    return ('<!doctype html><html lang="fa" dir="rtl"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#07070c">'
            '<meta name="description" content="%s"><title>%s | %s</title><script>document.documentElement.className="js"</script>'
            "<style>%s</style></head><body>%s%s%s%s%s%s%s%s%s%s</body></html>"
            % (esc(d["hero_sub"]), esc(d["hero_title"]), esc(brand), LCSS, nav, hero, about, stp, plans, fsec, cta, foot, fab, LJS))


# ---------------- admin editor ----------------
EDCSS = ("<style>.ed label{display:block;margin:12px 0 6px;color:var(--mu);font-size:13px}"
         ".ed input,.ed textarea{width:100%;padding:11px;border-radius:12px;border:1px solid #2c2c36;background:#0d0d13;color:#fff;"
         "font-family:inherit;font-size:15px;direction:rtl;text-align:right;letter-spacing:0}"
         ".ed input[type=checkbox]{width:auto}.ed input[type=range]{padding:0}"
         ".g2{display:grid;gap:10px;grid-template-columns:1fr 1fr}.g3{display:grid;gap:10px;grid-template-columns:70px 1fr}"
         ".ed h3{margin:0 0 6px}.ed .it{padding:10px 0;border-top:1px solid #1f1f2c}.nt{color:var(--mu);font-size:12px;margin-top:6px}"
         ".okb{background:#0f2e24;color:#34d399;padding:12px;border-radius:14px;margin-bottom:12px}"
         ".erb{background:#331818;color:#f87171;padding:12px;border-radius:14px;margin-bottom:12px}"
         ".rst{margin-top:14px;background:#331818;border:0;color:#f87171;border-radius:12px;padding:10px 16px;font-family:inherit;cursor:pointer}</style>")


def inp(name, val, label, ph="", rows=0):
    lab = "<label>%s</label>" % esc(label)
    if rows:
        return lab + '<textarea name="%s" rows="%d">%s</textarea>' % (name, rows, esc(val))
    return lab + '<input name="%s" value="%s" placeholder="%s">' % (name, esc(val), esc(ph))


def card(title, inner):
    return '<div class="card ed" style="margin-bottom:14px"><h3>%s</h3>%s</div>' % (esc(title), inner)


def form_html(d, err="", ok=False):
    msg = ('<div class="okb">✅ ذخیره شد. <a href="/about" target="_blank" style="text-decoration:underline">دیدن صفحه</a></div>' if ok else "")
    msg += '<div class="erb">%s</div>' % esc(err) if err else ""
    hint = '<div class="nt">لینک مجاز: /login ، /buy ، #more ، #plans ، #faq یا آدرس کامل https://…</div>'
    img = ""
    if HERO.exists():
        img = '<img src="/site/hero.jpg?v=%d" style="max-width:100%%;border-radius:14px;margin-top:10px">' % int(HERO.stat().st_mtime)
    top = (inp("brand", d["brand"], "نام برند (خالی = نام پیش‌فرض)") + inp("hero_title", d["hero_title"], "عنوان بزرگ", rows=2) +
           inp("hero_sub", d["hero_sub"], "توضیح زیر عنوان", rows=3) +
           '<div class="g2"><div>' + inp("b1_text", d["b1_text"], "دکمه‌ی اول: متن") + inp("b1_link", d["b1_link"], "دکمه‌ی اول: لینک") +
           "</div><div>" + inp("b2_text", d["b2_text"], "دکمه‌ی دوم: متن") + inp("b2_link", d["b2_link"], "دکمه‌ی دوم: لینک") +
           "</div></div>" + hint)
    pic = (img + '<label>تصویر بالای صفحه (JPG یا PNG؛ خودکار فشرده می‌شود)</label><input type="file" name="hero_file" accept="image/*">'
           '<label><input type="checkbox" name="hero_del" value="1"> حذف تصویر فعلی</label>'
           '<label>تیرگی روی تصویر: <b>%d</b></label><input type="range" name="overlay" min="0" max="90" value="%d">' % (d["overlay"], d["overlay"]))
    about = inp("about_title", d["about_title"], "عنوان بخش معرفی") + inp("about_text", d["about_text"], "متن معرفی", rows=4)
    fs = ""
    for i in range(NF):
        x = d["features"][i] if i < len(d["features"]) and isinstance(d["features"][i], dict) else {}
        fs += ('<div class="it"><div class="g3"><div>' + inp("fi%d" % i, x.get("i", ""), "آیکن") + "</div><div>" +
               inp("ft%d" % i, x.get("t", ""), "عنوان قابلیت %s" % fa(i + 1)) + "</div></div>" +
               inp("fd%d" % i, x.get("d", ""), "توضیح", rows=2) + "</div>")
    ss = inp("steps_title", d["steps_title"], "عنوان بخش مراحل")
    for i in range(NS):
        x = d["steps"][i] if i < len(d["steps"]) and isinstance(d["steps"][i], dict) else {}
        ss += '<div class="it">' + inp("st%d" % i, x.get("t", ""), "مرحله %s: عنوان" % fa(i + 1)) + inp("sd%d" % i, x.get("d", ""), "توضیح", rows=2) + "</div>"
    pl = ('<label><input type="checkbox" name="show_prices" value="1"%s> نمایش پکیج‌ها و قیمت‌ها (از فروشگاه)</label>' %
          (" checked" if d["show_prices"] else "")) + inp("plans_title", d["plans_title"], "عنوان بخش قیمت‌ها")
    qs = ""
    for i in range(NQ):
        x = d["faq"][i] if i < len(d["faq"]) and isinstance(d["faq"][i], dict) else {}
        qs += '<div class="it">' + inp("fq%d" % i, x.get("q", ""), "سوال %s" % fa(i + 1)) + inp("fa%d" % i, x.get("a", ""), "جواب", rows=2) + "</div>"
    cta = (inp("cta_title", d["cta_title"], "عنوان بنر پایین") + inp("cta_text", d["cta_text"], "متن بنر") +
           '<div class="g2"><div>' + inp("cta_btn", d["cta_btn"], "متن دکمه") + "</div><div>" + inp("cta_link", d["cta_link"], "لینک دکمه") + "</div></div>")
    ft = (inp("contact", d["contact"], "یوزرنیم تلگرام پشتیبانی (بدون @)", "support_id") + inp("footer", d["footer"], "متن فوتر (خالی = نام برند)"))
    return (EDCSS + msg + '<div class="sub">تغییرات بعد از ذخیره فوراً روی صفحه‌ی اصلی دیده می‌شود. بخشی که همه‌ی فیلدهایش خالی باشد نمایش داده نمی‌شود.</div>'
            '<form method="post" action="/admin/site" enctype="multipart/form-data">' + card("متن اصلی و دکمه‌ها", top) +
            card("تصویر بالای صفحه", pic) + card("معرفی", about) + card("قابلیت‌ها (تا ۶ مورد)", fs) + card("مراحل کار (تا ۴ مورد)", ss) +
            card("قیمت‌ها", pl) + card("سوالات متداول (تا ۶ مورد)", qs) + card("بنر پایین", cta) + card("تماس و فوتر", ft) +
            '<button class="go">💾 ذخیره‌ی تغییرات</button></form>'
            '<form method="post" action="/admin/site/reset" onsubmit="return confirm(\'همه‌ی متن‌ها به حالت پیش‌فرض برگردد؟\')">'
            '<button class="rst">↩️ بازگشت به متن‌های پیش‌فرض</button></form><a class="lk" href="/about" target="_blank">دیدن صفحه‌ی اصلی</a>')


def need_admin(req):
    uid = req.get("uid")
    if uid is None or uid not in A.admin_ids():
        raise web.HTTPFound("/")
    return uid


def save_hero(data):
    Image.MAX_IMAGE_PIXELS = 30_000_000
    im = Image.open(io.BytesIO(data))
    im.load()
    im = im.convert("RGB")
    im.thumbnail((1800, 1200))
    SITE.mkdir(parents=True, exist_ok=True)
    tmp = HERO.with_suffix(".tmp")
    im.save(tmp, "JPEG", quality=84, optimize=True, progressive=True)
    os.replace(tmp, HERO)


async def admin_get(req):
    need_admin(req)
    d = await asyncio.to_thread(load)
    return theme.shell("ویرایش سایت", form_html(d, ok=bool(req.query.get("ok"))), "home")


async def admin_post(req):
    auth.same_origin(req)
    need_admin(req)
    f = await req.post()
    d = await asyncio.to_thread(load)

    def g(k, n):
        v = f.get(k, "")
        return clip(v if isinstance(v, str) else "", n)
    d["brand"], d["hero_title"], d["hero_sub"] = g("brand", 40), g("hero_title", 140), g("hero_sub", 320)
    d["b1_text"], d["b2_text"] = g("b1_text", 40), g("b2_text", 40)
    d["b1_link"], d["b2_link"] = clean_link(g("b1_link", 300), "/login"), clean_link(g("b2_link", 300), "#more")
    d["about_title"], d["about_text"], d["steps_title"], d["plans_title"] = g("about_title", 80), g("about_text", 700), g("steps_title", 80), g("plans_title", 80)
    d["cta_title"], d["cta_text"], d["cta_btn"] = g("cta_title", 100), g("cta_text", 240), g("cta_btn", 40)
    d["cta_link"] = clean_link(g("cta_link", 300), "/login")
    d["contact"] = re.sub(r"[^A-Za-z0-9_]", "", g("contact", 40))
    d["footer"] = g("footer", 160)
    d["show_prices"] = 1 if f.get("show_prices") else 0
    try:
        d["overlay"] = max(0, min(90, int(g("overlay", 3))))
    except ValueError:
        d["overlay"] = 60
    d["features"] = [{"i": g("fi%d" % i, 4) or "✨", "t": g("ft%d" % i, 60), "d": g("fd%d" % i, 240)}
                     for i in range(NF) if g("ft%d" % i, 60) or g("fd%d" % i, 240)]
    d["steps"] = [{"t": g("st%d" % i, 60), "d": g("sd%d" % i, 240)} for i in range(NS) if g("st%d" % i, 60) or g("sd%d" % i, 240)]
    d["faq"] = [{"q": g("fq%d" % i, 140), "a": g("fa%d" % i, 500)} for i in range(NQ) if g("fq%d" % i, 140)]
    err = ""
    up = f.get("hero_file")
    if f.get("hero_del"):
        try:
            HERO.unlink()
        except FileNotFoundError:
            pass
    elif getattr(up, "filename", ""):
        data = up.file.read()
        if len(data) > 8 * 1024 * 1024:
            err = "حجم تصویر بیشتر از ۸ مگابایت است."
        else:
            try:
                await asyncio.to_thread(save_hero, data)
            except Exception:
                err = "تصویر معتبر نیست (JPG یا PNG بفرست)."
    await asyncio.to_thread(save, d)
    if err:
        return theme.shell("ویرایش سایت", form_html(d, err=err + " بقیه‌ی تغییرات ذخیره شد."), "home")
    raise web.HTTPFound("/admin/site?ok=1")


async def admin_reset(req):
    auth.same_origin(req)
    need_admin(req)
    try:
        CFG.unlink()
    except FileNotFoundError:
        pass
    raise web.HTTPFound("/admin/site?ok=1")


# ---------------- public routes and wiring ----------------
async def landing(req):
    d = await asyncio.to_thread(load)
    return web.Response(text=await asyncio.to_thread(render, req.get("uid"), d), content_type="text/html")


async def asset(req):
    if not HERO.exists():
        raise web.HTTPNotFound()
    return web.FileResponse(HERO)


async def home(req):
    if req.get("uid") is not None:
        return await skin.home(req)
    return await landing(req)


_orig_guard = auth.guard


@web.middleware
async def guard2(req, handler):
    p = req.path
    if p in ("/", "/about") or p.startswith("/site/"):
        uid = auth.read_cookie(req.cookies.get("pgshop", ""))
        if uid is not None:
            u = await asyncio.to_thread(auth.get_user, uid)
            if u and not u[1]:
                req["uid"] = uid
        resp = await handler(req)
        resp.headers.update(auth.SEC)
        if p.startswith("/site/"):
            resp.headers["Cache-Control"] = "public, max-age=86400"
        return resp
    return await _orig_guard(req, handler)


auth.guard = guard2
pages.home = home
_pages_install = pages.install


def install(app):
    _pages_install(app)
    app._client_max_size = max(getattr(app, "_client_max_size", 0), 9 * 1024 * 1024)
    r = app.router
    r.add_get("/about", landing)
    r.add_get("/site/hero.jpg", asset)
    r.add_get("/admin/site", admin_get)
    r.add_post("/admin/site", admin_post)
    r.add_post("/admin/site/reset", admin_reset)


pages.install = install
