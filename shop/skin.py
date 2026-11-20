from __future__ import annotations

import asyncio
import time

from web import app as A

from . import auth, pages, theme
from .theme import bot_user, esc, fa, fg

EXTRA = """
.lw{min-height:100vh;display:flex;flex-direction:column;align-items:center;justify-content:center;padding:28px 16px 40px;gap:20px}
.lh{text-align:center;max-width:420px}
.lg{width:84px;height:84px;margin:0 auto 14px;border-radius:26px;display:grid;place-items:center;font-size:38px;background:linear-gradient(135deg,#7c5cf0,#22d3ee);box-shadow:0 16px 40px #7c5cf055}
.lh h1{margin:0 0 8px;font-size:30px}.lh p{margin:0;color:var(--mu);font-size:14px;line-height:1.9}
.fts{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:14px}
.fts span{padding:6px 12px;border-radius:99px;background:#17172a;border:1px solid #2a2a45;font-size:12px;color:#c4b5fd}
.lc{width:min(94vw,420px);padding:24px 22px;animation:rv .5s cubic-bezier(.22,1,.36,1) both}
.lc label{display:block;margin:6px 4px 8px;color:var(--mu);font-size:13px}
.ip{position:relative}.ip span{position:absolute;right:14px;top:50%;transform:translateY(-50%);opacity:.8}.ip input{padding-right:44px}
.lst{display:flex;align-items:center;justify-content:center;gap:8px;margin:0 0 16px;font-size:13px;color:var(--mu)}
.lst span{display:flex;align-items:center;gap:6px}
.lst i{font-style:normal;width:24px;height:24px;border-radius:50%;display:grid;place-items:center;background:#1b1b2a;border:1px solid #2c2c41;font-size:12px}
.lst .on{color:#fff}.lst .on i{background:linear-gradient(135deg,#a78bfa,#22d3ee);border:0}
.lst u{width:24px;height:2px;border-radius:2px;background:#2c2c41}.lst u.on{background:#a78bfa}
.ots{display:flex;gap:8px;justify-content:center;margin:6px 0 14px}
.ob{width:100%;max-width:52px;height:60px;padding:0;text-align:center;font-size:24px;letter-spacing:0;border-radius:14px}
.tmr{text-align:center;color:var(--mu);font-size:13px}.tmr b{color:#c4b5fd}.tmr.ex b{color:var(--dn)}
.err.sk{animation:skk .5s}
@keyframes skk{20%,60%{transform:translateX(-7px)}40%,80%{transform:translateX(7px)}}
.go:disabled{opacity:.5}
.acts{display:flex;gap:10px;margin-top:16px}
.acts a{flex:1;text-align:center;padding:12px;border-radius:14px;font-weight:700;background:#ffffff1f;border:1px solid #ffffff2e}
.acts a.pr{background:linear-gradient(135deg,#a78bfa,#7c5cf0 55%,#22d3ee);border:0}
.qk{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin:16px 0}
.qt{display:flex;flex-direction:column;align-items:center;gap:8px;padding:16px 8px;border-radius:20px;background:#14141e;border:1px solid var(--bd);font-size:14px;transition:transform .2s,border-color .2s}
.qt:active,.qt:hover{transform:translateY(-3px);border-color:#7c5cf0}
.qt i{font-style:normal;font-size:26px;width:52px;height:52px;border-radius:16px;display:grid;place-items:center;background:#251f4a}
.bnr{display:block;margin-bottom:14px;padding:13px 16px;border-radius:16px;background:#2a2410;border:1px solid #6b5518;color:#fde68a;font-size:14px}
.ofr{display:flex;align-items:center;gap:14px;padding:18px;border-radius:22px;background:linear-gradient(135deg,#143a33,#0f2745);border:1px solid #1f6b5a;margin-bottom:6px}
.ofr .pe{background:#0f2e24}.ofr b{color:#6ee7b7}.ofr .cta{margin:0;padding:10px 16px;white-space:nowrap}
"""
theme.CSS += EXTRA
theme.TABS = (("home", "/", "🏠", "خانه"), ("buy", "/buy", "🛒", "خرید"), ("panels", "/panels", "🖥", "پنل‌ها"),
              ("wallet", "/wallet", "💳", "کیف پول"))
ICONS = ["🚀", "⚡", "🛰", "💎", "🔥", "🌐"]

OTP_JS = r"""<script>(function(){
var bs=[].slice.call(document.querySelectorAll('.ob')),cv=document.getElementById('cv'),f=document.getElementById('cf2'),tm=document.getElementById('tm'),sb=document.getElementById('sb'),sent=false;
function norm(s){return String(s).replace(/[\u06F0-\u06F9]/g,function(c){return c.charCodeAt(0)-1776}).replace(/[\u0660-\u0669]/g,function(c){return c.charCodeAt(0)-1632}).replace(/\D/g,'')}
function val(){return bs.map(function(b){return b.value}).join('')}
function done(){var v=val();cv.value=v;if(v.length===6&&!sent){sent=true;f.submit()}}
function fill(i,s){s=norm(s);for(var k=0;k<s.length&&i+k<6;k++)bs[i+k].value=s[k];bs[Math.min(i+s.length,5)].focus();done()}
bs.forEach(function(b,i){
b.addEventListener('input',function(){var s=norm(b.value);if(!s){b.value='';return}if(s.length>1){fill(i,s);return}b.value=s;if(i<5)bs[i+1].focus();done()});
b.addEventListener('keydown',function(e){if(e.key==='Backspace'&&!b.value&&i>0){bs[i-1].focus();bs[i-1].value=''}});
b.addEventListener('paste',function(e){e.preventDefault();fill(0,(e.clipboardData||window.clipboardData).getData('text'))});
b.addEventListener('focus',function(){b.select()})});
f.addEventListener('submit',function(e){cv.value=val();if(cv.value.length<6)e.preventDefault()});
bs[0].focus();
var left=+tm.dataset.ttl,b=tm.querySelector('b'),P='\u06F0\u06F1\u06F2\u06F3\u06F4\u06F5\u06F6\u06F7\u06F8\u06F9';
function show(){var m=Math.floor(left/60),s=left%60;b.textContent=((m<10?'0':'')+m+':'+(s<10?'0':'')+s).replace(/\d/g,function(d){return P[d]})}
show();var iv=setInterval(function(){left--;if(left<=0){clearInterval(iv);tm.classList.add('ex');b.textContent='منقضی شد';sb.disabled=true;return}show()},1000);
})();</script>"""


def page_login(err="", status=200):
    feats = "<span>⚡ تحویل فوری</span><span>🔐 ورود با کد تلگرام</span><span>💳 کیف پول</span>"
    eb = '<div class="err sk">%s</div>' % esc(err) if err else '<div class="err"></div>'
    body = ('<div class="lw"><div class="lh"><div class="lg">🛡</div><h1>%s</h1>'
            "<p>خرید پنل، شارژ کیف پول و مدیریت سرویس‌ها؛ همه یک‌جا.</p><div class=\"fts\">%s</div></div>"
            '<form class="card lc" method="post" action="/login"><div class="lst"><span class="on"><i>۱</i>آیدی</span><u></u>'
            "<span><i>۲</i>کد</span></div><label>آیدی عددی تلگرام</label>"
            '<div class="ip"><span>🆔</span><input name="uid" inputmode="numeric" autocomplete="username" '
            'placeholder="مثلاً 123456789" required></div><button class="go">دریافت کد ورود</button>%s'
            '<div class="lk">آیدی عددی را از «👤 حساب کاربری» در ربات می‌بینی. ربات باید قبلاً /start شده باشد.</div></form></div>'
            % (esc(theme.TITLE), feats, eb))
    return theme.shell("ورود", body, nav=False, status=status)


def page_code(uid, err="", status=200):
    boxes = "".join('<input class="ob" inputmode="numeric" maxlength="1" autocomplete="%s" aria-label="رقم %d">'
                    % ("one-time-code" if i == 0 else "off", i + 1) for i in range(6))
    eb = '<div class="err sk">%s</div>' % esc(err) if err else '<div class="err"></div>'
    body = ('<div class="lw"><div class="lh"><div class="lg">📨</div><h1>کد ورود</h1>'
            "<p>اگر این آیدی در ربات ثبت باشد، یک کد ۶ رقمی به تلگرامش رفته است.</p></div>"
            '<form class="card lc" id="cf2" method="post" action="/login/code"><div class="lst"><span class="on"><i>✓</i>آیدی</span>'
            '<u class="on"></u><span class="on"><i>۲</i>کد</span></div>'
            '<input type="hidden" name="uid" value="%d"><input type="hidden" name="code" id="cv">'
            '<div class="ots" dir="ltr">%s</div><div class="tmr" id="tm" data-ttl="300">⏱ <b>۰۵:۰۰</b></div>'
            '<button class="go" id="sb">ورود</button>%s<a class="lk" href="/login">آیدی دیگر یا ارسال دوباره</a></form></div>'
            % (int(uid), boxes, eb)) + OTP_JS
    return theme.shell("کد ورود", body, nav=False, status=status)


async def home(req):
    uid = req["uid"]

    def work():
        now = int(time.time())
        u = A.q("SELECT balance, name FROM users WHERE tg_id=?", (uid,))
        bal, name = (u[0][0], u[0][1]) if u else (0, "")
        pn = A.q("SELECT COUNT(*) FROM panels WHERE user_id=? AND is_test=0 AND status='active'", (uid,))[0][0]
        sp = A.q("SELECT COUNT(*), COALESCE(SUM(price),0) FROM sales WHERE user_id=?", (uid,))[0]
        ex = A.q("SELECT admin_username, expires FROM panels WHERE user_id=? AND is_test=0 AND status='active' "
                 "AND expires>? AND expires<? ORDER BY expires LIMIT 1", (uid, now, now + 7 * 86400))
        best = A.q("SELECT k.id, k.gb, k.price FROM packages k JOIN products p ON p.id=k.product_id "
                   "WHERE k.active=1 AND p.active=1 AND k.gb>0 ORDER BY k.price*1.0/k.gb LIMIT 1")
        prs = A.q("SELECT id,name,descr,price_gb,min_gb,max_gb FROM products WHERE active=1 ORDER BY sort,id")
        pks = A.q("SELECT product_id,gb,price FROM packages WHERE active=1 ORDER BY gb")
        rec = A.q("SELECT created,kind,panel,gb,price FROM sales WHERE user_id=? ORDER BY id DESC LIMIT 3", (uid,))
        return int(bal or 0), name, pn, sp, ex, best, prs, pks, rec, now
    bal, name, pn, sp, ex, best, prs, pks, rec, now = await asyncio.to_thread(work)
    bu = bot_user()
    banner = ""
    if ex:
        banner = ('<a class="bnr" href="/panels">⏰ پنل <b dir="ltr">%s</b> حدود %s روز دیگر منقضی می‌شود.</a>'
                  % (esc(ex[0][0]), fa(max(1, (ex[0][1] - now) // 86400))))
    hero = ('<div class="hero rv"><div class="mu" style="color:#cbd5e1;margin:0">موجودی کیف پول</div>'
            '<div class="big"><span class="n" data-n="%d">۰</span> <small>تومان</small></div>'
            '<div class="acts"><a class="pr" href="/buy">🛒 خرید پنل</a><a href="/wallet">➕ شارژ</a></div><div class="hs">'
            '<div><b class="n" data-n="%d">۰</b><span>پنل فعال</span></div>'
            '<div><b class="n" data-n="%d">۰</b><span>خرید</span></div>'
            '<div><b class="n" data-n="%d">۰</b><span>جمع خرید (تومان)</span></div></div></div>'
            % (bal, pn, sp[0], int(sp[1] or 0)))
    tiles = [("🛒", "خرید پنل", "/buy"), ("💳", "شارژ کیف پول", "/wallet"), ("📦", "پنل‌های من", "/panels")]
    qk = "".join('<a class="qt" href="%s"><i>%s</i>%s</a>' % (h, i, t) for i, t, h in tiles)
    if bu:
        qk += '<a class="qt" href="https://t.me/%s" target="_blank" rel="noopener"><i>🤖</i>ربات تلگرام</a>' % esc(bu)
    offer = ""
    if best:
        bid, bgb, bpr = best[0]
        offer = ('<div class="ofr rv"><div class="pe">💎</div><div style="flex:1"><b>به‌صرفه‌ترین پکیج</b>'
                 '<div class="mu" style="margin:3px 0 0">%s گیگ فقط %s تومان · هر گیگ %s تومان</div></div>'
                 '<a class="cta" href="/buy/p/%d">خرید</a></div>' % (fg(bgb), fa(bpr), fa(round(bpr / bgb)), bid))
    cards = ""
    for i, (pid, pname, descr, pgb, mn, mx) in enumerate(prs):
        mine = [(g, p) for q, g, p in pks if q == pid]
        chips = "".join('<span class="pl">%s گیگ <b>%s</b> تومان</span>' % (fg(g), fa(p)) for g, p in mine)
        start = min([p for g, p in mine] or [(pgb or 0) * (mn or 0)])
        extra = ('<div class="mu">حجم دلخواه: هر گیگ %s تومان</div>' % fa(pgb)) if pgb else ""
        cards += ('<div class="pc rv"><div class="pi"><div class="ph"><div class="pe">%s</div><div><h3>%s</h3>'
                  '<div class="mu" style="margin:0">شروع از <b>%s</b> تومان</div></div></div><div class="mu">%s</div>%s%s'
                  '<a class="cta" href="/buy">🛒 مشاهده و خرید</a></div></div>'
                  % (ICONS[i % len(ICONS)], esc(pname), fa(start), esc(descr), chips, extra))
    rc = "".join('<div class="tx"><div><div>%s</div><small>%s%s · <span class="tm" data-f="dt" data-t="%d"></span></small></div>'
                 "<b>%s تومان</b></div>" % (esc(k), esc(p or "—"), (" · %s گیگ" % fg(g)) if g else "", t or 0, fa(pr))
                 for t, k, p, g, pr in rec)
    body = (banner + hero + '<div class="qk">' + qk + "</div>" + offer + "<h2>محصولات</h2>" +
            ('<div class="grid">%s</div>' % cards if cards else '<div class="card">محصولی فعال نیست.</div>') +
            ("<h2>آخرین خریدها</h2><div class=\"card\">%s</div>" % rc if rc else ""))
    return theme.shell("فروشگاه", body, "home", sub="سلام <b>%s</b> 👋 خوش آمدی" % esc(name or "دوست من"))


auth.page_login = page_login
auth.page_code = page_code
pages.home = home
