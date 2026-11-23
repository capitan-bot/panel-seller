from __future__ import annotations

import asyncio
import logging
import time

from . import invoice
from . import config, db
from .tg import Callback, Message, Router
from .panel import PG, PanelError, gen_password, get_pg
from . import panel as panel_mod
from .ui import STYLE_NAME, STYLES, WAIT, btn, days_left, fgb, fmt, fnum, h, kb, num, panel_label, panel_text, show, waiting
from .user import extend_panel

def _guard(ev) -> bool:
    uid = ev.from_user.id
    if uid in config.ADMIN_IDS:
        return True
    if uid in config.OPERATOR_IDS:   # operators: only /admin, home and receipts
        d = getattr(ev, "data", None)
        if d is not None:
            return d in ("a:home", "a:rcpt") or d.startswith("a:rc:")
        t = (ev.text or "").split()
        return bool(t) and t[0].split("@")[0].lower() == "/admin"
    return False


router = Router(guard=_guard)
log = logging.getLogger(__name__)
_tasks: set = set()

SETTINGS = [
    ("shop", "🏪 نام فروشگاه"), ("welcome", "👋 متن خوش‌آمدگویی ({name} و {shop})"),
    ("faq", "❓ سوالات متداول"), ("support", "🎧 متن پشتیبانی"), ("card", "💳 شماره کارت"),
    ("holder", "👤 نام صاحب کارت"), ("test_gb", "🎁 حجم تست (گیگ؛ 0 = خاموش، مثلاً 1 یا 0.5)"),
    ("min_charge", "💰 حداقل شارژ (تومان)"), ("warn_on", "🔔 هشدار خودکار حجم (1 = روشن، 0 = خاموش)"),
]
NUMERIC = {"min_charge"}
HOME_BTN = [btn("🔙 مدیریت", "a:home")]

SRV_HELP = ("آدرس، نام‌کاربری و رمز ادمین (سودو) پنل و یک نام دلخواه را در <b>یک پیام</b> و با فاصله بفرست:\n"
            "<code>https://panel.example.com:8000 admin password نام‌دلخواه</code>\n\n"
            "نام دلخواه اختیاری است. پیامت بعد از خواندن پاک می‌شود و اتصال قبل از ذخیره تست می‌شود.")


def _g(v):
    if v is None:
        return "—"
    return f"{v / 1024:.2f} TB" if v >= 1024 else f"{v:.2f} GB"


def _num(d, *keys):
    for k in keys:
        if isinstance(d.get(k), (int, float)):
            return d[k]
    return None


NODE_ICON = {"connected": "🟢", "connecting": "🟡", "error": "🔴", "disabled": "⚫️", "limited": "🟠"}


async def _safe(coro, default):
    try:
        return await coro
    except Exception:
        return default


async def _since(sid, since):
    r = await db.row("SELECT COUNT(*) n, COALESCE(SUM(s.price),0) rev, COALESCE(SUM(s.gb),0) gb FROM sales s "
                     "JOIN panels p ON p.admin_username=s.panel WHERE p.server_id=? AND s.created>=?", sid, since)
    return r["n"], r["rev"], r["gb"]


async def server_dashboard(ev, r, k):
    sid, now_ = r["id"], int(time.time())
    t = f"🖥 <b>{h(r['name'])}</b>{' ⭐️' if r['is_default'] else ''}\n🌐 <code>{h(r['url'])}</code>\n"
    online, sysd, nodes, adms = False, {}, [], []
    t0 = time.monotonic()
    try:
        pg = await get_pg(sid)
        await pg.test()
        ms = int((time.monotonic() - t0) * 1000)
        online = True
    except PanelError as e:
        t += f"🔴 <b>آفلاین</b> — {h(str(e)[:160])}\n"
    if online:
        t += f"🟢 <b>آنلاین</b> • پاسخ {ms}ms\n"
        sysd = await _safe(pg.system_stats(), {})
        nodes = await _safe(pg.nodes(), [])
        adms = await _safe(pg.admins_full(), [])
        sl = []
        if sysd.get("version"):
            sl.append(f"🏷 نسخه: <code>{h(sysd['version'])}</code>")
        cpu, mu, mt = _num(sysd, "cpu_usage"), _num(sysd, "mem_used"), _num(sysd, "mem_total")
        if cpu is not None:
            cores = _num(sysd, "cpu_cores")
            sl.append(f"🧠 CPU: {cpu:g}%" + (f" ({int(cores)} هسته)" if cores else ""))
        if mu is not None and mt:
            sl.append(f"💾 RAM: {mu / 1024 ** 3:.1f} / {mt / 1024 ** 3:.1f} GB ({mu / mt * 100:.0f}%)")
        tin, tout = _num(sysd, "incoming_bandwidth"), _num(sysd, "outgoing_bandwidth")
        if tin is not None or tout is not None:
            sl.append(f"📶 ترافیک کل: ⬇️ {_g((tin or 0) / 1024 ** 3)} ⬆️ {_g((tout or 0) / 1024 ** 3)}")
        us = [("total_user", "کل"), ("online_users", "آنلاین"), ("users_active", "فعال"), ("users_expired", "منقضی"),
              ("users_limited", "حجم‌تمام"), ("users_disabled", "غیرفعال")]
        parts = [f"{lab}: {int(sysd[key])}" for key, lab in us if isinstance(sysd.get(key), (int, float))]
        if parts:
            sl.append("👥 کاربران پنل — " + " | ".join(parts))
        if sl:
            t += "\n<b>📊 وضعیت پنل</b>\n" + "\n".join(sl) + "\n"
        if nodes:
            cnt = {}
            for x in nodes:
                cnt[x.get("status")] = cnt.get(x.get("status"), 0) + 1
            t += f"\n<b>🌐 نودها:</b> {len(nodes)} (" + " ".join(f"{NODE_ICON.get(c, '⚪️')}{n}" for c, n in cnt.items()) + ")\n"
            for x in [x for x in nodes if x.get("status") != "connected"][:5]:
                t += f"   {NODE_ICON.get(x.get('status'), '⚪️')} {h(x.get('name', ''))}: {h(str(x.get('status')))}\n"
        res = [a for a in adms if not a["owner"]]
        if res:
            tl, tu = sum(a["limit"] or 0 for a in res), sum(a["used"] or 0 for a in res)
            near = [a for a in res if a["limit"] and a["used"] is not None and a["used"] / a["limit"] >= 0.8]
            dis = [a for a in res if a["disabled"]]
            t += (f"\n<b>👥 ادمین‌های نماینده:</b> {len(res)}\n   💎 مجموع حجم: {_g(tl)} | مصرف: {_g(tu)}\n"
                  f"   ⚠️ نزدیک اتمام: {len(near)} | ⛔️ غیرفعال: {len(dis)}\n")
    st = await db.rows("SELECT status, is_test, COUNT(*) n, COALESCE(SUM(gb),0) gb FROM panels WHERE server_id=? "
                       "GROUP BY status, is_test", sid)
    paid = sum(x["n"] for x in st if not x["is_test"])
    active = sum(x["n"] for x in st if not x["is_test"] and x["status"] == "active")
    tests = sum(x["n"] for x in st if x["is_test"])
    sold = sum(x["gb"] for x in st if not x["is_test"])
    d1, d30 = await _since(sid, now_ - 86400), await _since(sid, now_ - 30 * 86400)
    mon = await db.get_setting(f"mon_{sid}", "1") == "1"
    t += (f"\n<b>🤖 آمار ربات روی این پنل</b>\n📦 سرویس فروخته‌شده: {paid} (فعال {active}) | 🧪 تست: {tests}\n"
          f"💎 حجم فروخته‌شده: {_g(sold)}\n🛒 محصولات متصل: {k}\n"
          f"💵 فروش ۲۴ساعت: {fmt(d1[1])} تومان ({d1[0]}) | ۳۰ روز: {fmt(d30[1])} تومان ({d30[0]})\n"
          f"🔔 پایش خودکار: {'روشن' if mon else 'خاموش'}\n🕒 {time.strftime('%H:%M:%S')}")
    if len(t) > 4000:
        t = t[:t.rfind("\n", 0, 3990)]
    s_ = r["id"]
    rows = [[btn("🔄 بروزرسانی", f"a:srvm:{s_}", style="primary"), btn("🧪 تست و ساختار", f"a:srvt:{s_}")],
            [btn("👥 ادمین‌ها", f"a:srvu:{s_}"), btn("⚠️ نزدیک اتمام", f"a:srvlow:{s_}")],
            [btn("🌐 نودها", f"a:srvn:{s_}"), btn("📈 فروش", f"a:srvs:{s_}", style="success")],
            [btn("🔍 جستجوی ادمین", f"a:srvq:{s_}"), btn("🔁 همگام‌سازی", f"a:srvsy:{s_}")],
            [btn("🛒 محصولات", f"a:srvp:{s_}"), btn("🔔 پایش: ✅" if mon else "🔔 پایش: ❌", f"a:srvmon:{s_}",
                                                   style="success" if mon else "danger")],
            [btn("✏️ ویرایش", f"a:srve:{s_}")] + ([] if r["is_default"] else [btn("⭐️ پیش‌فرض", f"a:srvd:{s_}")]),
            [btn("🗑 حذف", f"a:srvx:{s_}", style="danger")], [btn("🔙 بازگشت", "a:panel")]]
    await show(ev, t, kb(rows))


async def srv_admins_page(ev, r, mode):
    sid = r["id"]
    back = kb([[btn("🔄 بروزرسانی", f"a:srv{'u' if mode == 'all' else 'low'}:{sid}"), btn("🔙 بازگشت", f"a:srvm:{sid}")]])
    try:
        adms = await (await get_pg(sid)).admins_full()
    except PanelError as e:
        return await show(ev, f"❌ {h(str(e)[:200])}", back)
    res = [a for a in adms if not a["owner"]]

    def pc(a):
        return (a["used"] or 0) / a["limit"] * 100 if a["limit"] else 0
    if mode == "low":
        lst = sorted([a for a in res if a["disabled"] or pc(a) >= 80], key=lambda a: -pc(a))
        title = "⚠️ <b>نزدیک اتمام حجم / غیرفعال</b>"
    else:
        lst = sorted(res, key=lambda a: -(a["used"] or 0))
        title = "👥 <b>ادمین‌های پنل (بر اساس مصرف)</b>"
    lines = []
    for a in lst[:25]:
        lim = _g(a["limit"]) if a["limit"] else "نامحدود"
        lines.append(f"{'⛔️' if a['disabled'] else ('⚠️' if pc(a) >= 80 else '🔹')} <code>{h(a['username'])}</code> — "
                     f"{_g(a['used'])} / {lim}" + (f" ({pc(a):.0f}%)" if a["limit"] else ""))
    more = f"\n… و {len(lst) - 25} مورد دیگر" if len(lst) > 25 else ""
    await show(ev, f"{title}\n{h(r['name'])} • تعداد: {len(lst)}\n\n" + ("\n".join(lines) or "موردی نیست ✅") + more, back)


async def srv_nodes_page(ev, r):
    sid = r["id"]
    back = kb([[btn("🔄 بروزرسانی", f"a:srvn:{sid}"), btn("🔙 بازگشت", f"a:srvm:{sid}")]])
    try:
        nodes = await (await get_pg(sid)).nodes()
    except PanelError as e:
        return await show(ev, f"❌ {h(str(e)[:200])}", back)
    if not nodes:
        return await show(ev, "🌐 نودی پیدا نشد (یا این نسخه‌ی پنل لیست نودها را نمی‌دهد).", back)
    lines = []
    for x in nodes[:25]:
        up, dn = x.get("uplink"), x.get("downlink")
        tr = ""
        if isinstance(up, (int, float)) or isinstance(dn, (int, float)):
            tr = f" • ⬇️ {_g((dn or 0) / 1024 ** 3)} ⬆️ {_g((up or 0) / 1024 ** 3)}"
        ver = x.get("xray_version") or x.get("core_version") or x.get("node_version")
        line = (f"{NODE_ICON.get(x.get('status'), '⚪️')} <b>{h(x.get('name', ''))}</b> <code>{h(x.get('address', ''))}</code>{tr}"
                + (f" • v{h(ver)}" if ver else ""))
        if x.get("message"):
            line += f"\n     ⚠️ {h(str(x['message'])[:80])}"
        lines.append(line)
    await show(ev, f"🌐 <b>نودهای {h(r['name'])}</b> ({len(nodes)})\n\n" + "\n".join(lines), back)


async def srv_sales_page(ev, r):
    sid, now_ = r["id"], int(time.time())
    back = kb([[btn("🔄 بروزرسانی", f"a:srvs:{sid}"), btn("🔙 بازگشت", f"a:srvm:{sid}")]])
    lines = []
    for lab, sec in (("۲۴ ساعت", 86400), ("۷ روز", 7 * 86400), ("۳۰ روز", 30 * 86400), ("کل", now_)):
        n_, rev, gb = await _since(sid, now_ - sec)
        lines.append(f"• {lab}: {n_} فروش | {_g(gb)} | {fmt(rev)} تومان")
    top = await db.rows("SELECT s.user_id uid, u.name name, COUNT(*) n, SUM(s.price) p FROM sales s "
                        "JOIN panels pn ON pn.admin_username=s.panel LEFT JOIN users u ON u.tg_id=s.user_id "
                        "WHERE pn.server_id=? AND s.price>0 GROUP BY s.user_id ORDER BY p DESC LIMIT 5", sid)
    t = f"📈 <b>فروش روی {h(r['name'])}</b>\n\n" + "\n".join(lines)
    if top:
        t += "\n\n🏆 <b>خریداران برتر</b>\n" + "\n".join(
            f"{i}. {h(x['name'] or '-')} (<code>{x['uid']}</code>) — {fmt(x['p'])} تومان ({x['n']}×)" for i, x in enumerate(top, 1))
    await show(ev, t, back)


async def srv_sync_page(ev, r):
    sid = r["id"]
    back = kb([[btn("🔄 بروزرسانی", f"a:srvsy:{sid}"), btn("🔙 بازگشت", f"a:srvm:{sid}")]])
    try:
        adms = await (await get_pg(sid)).admins_full()
    except PanelError as e:
        return await show(ev, f"❌ {h(str(e)[:200])}", back)
    on_panel = {a["username"] for a in adms if not a["owner"]}
    mine = {x["admin_username"] for x in await db.rows("SELECT admin_username FROM panels WHERE server_id=?", sid)}
    extra, missing = sorted(on_panel - mine), sorted(mine - on_panel)

    def fl(xs):
        return "\n".join(f"• <code>{h(x)}</code>" for x in xs[:20]) + (f"\n… و {len(xs) - 20} مورد دیگر" if len(xs) > 20 else "")
    t = (f"🔁 <b>همگام‌سازی {h(r['name'])}</b>\n\nروی پنل: {len(on_panel)} ادمین | در ربات: {len(mine)} سرویس\n\n"
         f"❓ روی پنل هست ولی در ربات ثبت نیست ({len(extra)}):\n{fl(extra) or '—'}\n\n"
         f"⚠️ در ربات ثبت است ولی روی پنل نیست ({len(missing)}):\n{fl(missing) or '—'}")
    await show(ev, t[:4000], back)


CODE_KIND = {"percent": "🎟 تخفیف درصدی", "amount": "🎟 تخفیف مبلغی", "gift": "🎁 هدیه شارژ"}
CODE_HELP = {
    "percent": "🎟 <b>کد تخفیف درصدی</b>\n\nدر یک پیام بفرست:\n<code>کد درصد سقف‌استفاده روز‌اعتبار حداقل‌خرید</code>\n\n"
               "مثال: <code>EID20 20 100 7 50000</code>\n= کد EID20، ۲۰٪ تخفیف، حداکثر ۱۰۰ بار، ۷ روز اعتبار، برای خرید حداقل ۵۰٬۰۰۰ تومان.\n\n"
               "• به‌جای کد بنویس <code>auto</code> تا خودکار ساخته شود.\n"
               "• سقف، روز و حداقل‌خرید اختیاری‌اند (۰ یا ننوشتن = نامحدود).\n• هر کاربر از هر کد فقط یک‌بار می‌تواند استفاده کند.",
    "amount": "🎟 <b>کد تخفیف مبلغی</b>\n\nدر یک پیام بفرست:\n<code>کد مبلغ سقف‌استفاده روز‌اعتبار حداقل‌خرید</code>\n\n"
              "مثال: <code>OFF10K 10000 50 30 30000</code>\n= ۱۰٬۰۰۰ تومان تخفیف، حداکثر ۵۰ بار، ۳۰ روز اعتبار، برای خرید حداقل ۳۰٬۰۰۰ تومان.\n\n"
              "• به‌جای کد بنویس <code>auto</code> تا خودکار ساخته شود.\n• سقف، روز و حداقل‌خرید اختیاری‌اند (۰ یا ننوشتن = نامحدود).",
    "gift": "🎁 <b>کد هدیه (شارژ کیف پول)</b>\n\nدر یک پیام بفرست:\n<code>کد مبلغ سقف‌استفاده روز‌اعتبار</code>\n\n"
            "مثال: <code>auto 50000 1 30</code>\n= کد خودکار، ۵۰٬۰۰۰ تومان هدیه، فقط ۱ نفر می‌تواند استفاده کند، ۳۰ روز اعتبار.\n\n"
            "⚠️ سقف ۰ یعنی بی‌نهایت نفر؛ برای کد هدیه حتماً سقف بگذار.\n"
            "کاربر آن را از «کد هدیه» در منوی اصلی وارد می‌کند.",
}


async def codes_page(ev):
    rs = await db.rows("SELECT * FROM codes ORDER BY id DESC LIMIT 20")
    now_ = int(time.time())
    allc = (await db.row("SELECT COUNT(*) c FROM codes"))["c"]
    rows, live = [], 0
    for r in rs:
        dead = (not r["active"]) or (r["expires"] and r["expires"] < now_) or (r["max_uses"] and r["used"] >= r["max_uses"])
        live += 0 if dead else 1
        val = f"{r['value']}٪" if r["kind"] == "percent" else fmt(r["value"])
        icon = "⛔️" if dead else ("🎁" if r["kind"] == "gift" else "🎟")
        rows.append([btn(f"{icon} {r['code']} • {val} • {r['used']}/{r['max_uses'] or '∞'}", f"a:cdv:{r['id']}")])
    rows += [[btn("➕ تخفیف درصدی", "a:cdn:percent", style="success"), btn("➕ تخفیف مبلغی", "a:cdn:amount", style="success")],
             [btn("🎁 کد هدیه (شارژ کیف پول)", "a:cdn:gift", style="primary")], HOME_BTN]
    t = (f"🎟 <b>کد تخفیف و هدیه</b>\n\nتعداد کل: {allc}" + (f" | فعال (در ۲۰ تای آخر): {live}" if rs else "") +
         "\n\n🎟 تخفیف: کاربر در مرحله‌ی تایید سفارش خرید وارد می‌کند.\n"
         "🎁 هدیه: کاربر از «کد هدیه» در منوی اصلی وارد می‌کند و مبلغ به کیف پولش اضافه می‌شود.")
    await show(ev, t, kb(rows))


async def code_view(ev, cid: int):
    from .ui import fdate
    r = await db.row("SELECT * FROM codes WHERE id=?", cid)
    if not r:
        return await codes_page(ev)
    val = f"{r['value']}٪" if r["kind"] == "percent" else f"{fmt(r['value'])} تومان"
    now_ = int(time.time())
    if not r["active"]:
        status = "⛔️ غیرفعال"
    elif r["expires"] and r["expires"] < now_:
        status = "⌛️ منقضی"
    elif r["max_uses"] and r["used"] >= r["max_uses"]:
        status = "🈵 ظرفیت تمام"
    else:
        status = "🟢 فعال"
    t = (f"{CODE_KIND.get(r['kind'], r['kind'])}\n\n🔑 کد: <code>{h(r['code'])}</code>\n💎 مقدار: {val}\n"
         f"📊 استفاده: {r['used']} / {r['max_uses'] or '∞'}\n⏳ انقضا: {fdate(r['expires']) if r['expires'] else 'بدون انقضا'}\n"
         + (f"🛒 حداقل خرید: {fmt(r['min_price'])} تومان\n" if r["min_price"] else "") + f"وضعیت: {status}")
    us = await db.rows("SELECT cu.user_id, cu.ts, u.name FROM code_uses cu LEFT JOIN users u ON u.tg_id=cu.user_id "
                       "WHERE cu.code_id=? ORDER BY cu.ts DESC LIMIT 8", cid)
    if us:
        t += "\n\n👥 آخرین استفاده‌ها:\n" + "\n".join(f"• {h(x['name'] or '-')} (<code>{x['user_id']}</code>) {fdate(x['ts'])}" for x in us)
    rows = [[btn("⛔️ غیرفعال کن" if r["active"] else "✅ فعال کن", f"a:cdt:{cid}", style="primary"),
             btn("🗑 حذف", f"a:cdx:{cid}", style="danger")], [btn("🔙 بازگشت", "a:cd")]]
    await show(ev, t, kb(rows))


BAK_HOURS = (1, 2, 6, 12, 24)


async def backup_page(ev):
    from . import report
    on = await db.get_setting("backup_on", "1") == "1"
    hrs = int(await db.get_setting("backup_hours", "2") or 2)
    last = int(await db.get_setting("backup_last", "0") or 0)
    if last:
        ago = int(time.time()) - last
        last_t = f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(last))} ({ago // 3600} ساعت و {ago % 3600 // 60} دقیقه پیش)"
    else:
        last_t = "هنوز بکاپی گرفته نشده"
    dest = "تاپیک «💾 بکاپ» در گروه گزارش" if await report.chat_id() else "پیام خصوصی مالک‌ها (گروه گزارش تنظیم نشده)"
    t = ("💾 <b>بکاپ دیتابیس</b>\n\n"
         f"🔁 بکاپ خودکار: {'✅ روشن' if on else '❌ خاموش'} — هر {hrs} ساعت\n"
         f"🕒 آخرین بکاپ: {last_t}\n📍 مقصد: {dest}\n\n"
         "ℹ️ فایل شامل کاربران، موجودی‌ها، سرویس‌ها و رمزهای رمزنگاری‌شده است؛ گروه گزارش باید خصوصی و فقط ادمین‌ها عضو باشند. "
         "کلید رمزنگاری (ENCRYPTION_KEY داخل .env) در بکاپ نیست؛ جدا و امن نگهش دار.")
    hb = [btn(("✅ " if x == hrs else "") + f"{x} ساعت", f"a:bakh:{x}") for x in BAK_HOURS]
    rows = [[btn("➕ افزودن بکاپ (همین حالا)", "a:bakn", style="success")],
            [btn("🔁 بکاپ خودکار: ✅" if on else "🔁 بکاپ خودکار: ❌", "a:bakt", style="success" if on else "danger")],
            hb[:3], hb[3:], HOME_BTN]
    await show(ev, t, kb(rows))


def report_help() -> str:
    from . import report
    names = " | ".join(v[0] for v in report.TOPICS.values())
    return ("📖 <b>آموزش راه‌اندازی گروه گزارش</b>\n\n"
            "۱) در تلگرام یک <b>گروه جدید</b> بساز (مثلاً «گزارش ربات»).\n"
            "۲) وارد تنظیمات گروه (Edit) شو و گزینه‌ی <b>Topics</b> را روشن کن؛ گروه خودکار «سوپرگروه» می‌شود.\n"
            "۳) ربات را به گروه اضافه کن (Add member ← یوزرنیم ربات).\n"
            "۴) ربات را <b>ادمین</b> کن و دسترسی <b>Manage Topics</b> (مدیریت تاپیک‌ها) را به آن بده.\n"
            "۵) داخل همان گروه، با اکانت خودت (نه به‌صورت ناشناس) این دستور را بفرست:\n<code>/setreport</code>\n\n"
            "ربات گروه را شناسایی می‌کند و خودش تاپیک‌ها را می‌سازد:\n" + names + "\n\n"
            "💡 راه دوم: ID گروه (عددی مثل <code>-1001234567890</code>) را با دکمه‌ی «🔗 ثبت با ID گروه» بفرست.\n"
            "⚠️ گروه را خصوصی نگه دار و فقط افراد مورد اعتماد را اضافه کن؛ بکاپ و اطلاعات کاربران داخلش می‌آید.")


async def report_page(ev):
    from . import report
    cid = await report.chat_id()
    lines = []
    for k, (name, _c) in report.TOPICS.items():
        ok = (await db.get_setting(f"rt_{k}")).isdigit()
        lines.append(f"{'✅' if ok and cid else '➖'} {name}")
    t = ("📣 <b>گروه گزارش</b>\n\n" +
         (f"وضعیت: ✅ متصل — <code>{cid}</code>" if cid else "وضعیت: ⚠️ هنوز متصل نشده؛ «📖 آموزش اتصال» را بزن.") +
         "\n\n🗂 تاپیک‌ها:\n" + "\n".join(lines))
    rows = [[btn("📖 آموزش اتصال", "a:rpth", style="primary")]]
    if cid:
        rows.append([btn("🧩 ساخت تاپیک‌ها", "a:rptm", style="success"), btn("🧪 تست ارسال", "a:rptt")])
    rows.append([btn("🔗 ثبت با ID گروه", "a:rptid")] + ([btn("❌ قطع اتصال", "a:rptx", style="danger")] if cid else []))
    rows.append(HOME_BTN)
    await show(ev, t, kb(rows))


@router.command("setreport")
async def setreport_cmd(m: Message):
    if m.from_user.id not in config.OWNER_IDS:
        return
    if m.chat_id > 0:
        return await m.answer("📣 این دستور را باید <b>داخل گروه گزارش</b> بفرستی، نه اینجا.\n\nراهنما: /admin ← «📣 گزارش» ← «📖 آموزش اتصال»")
    from . import report
    ok, text = await report.setup_chat(m.bot, m.chat_id)
    await m.answer(text)


async def servers_page(ev):
    rs = await db.rows("SELECT * FROM servers ORDER BY is_default DESC, id")
    lines = []
    for r in rs:
        n = (await db.row("SELECT COUNT(*) c FROM panels WHERE server_id=?", r["id"]))["c"]
        lines.append(f"{'⭐️' if r['is_default'] else '🖥'} <b>{h(r['name'])}</b> • {n} سرویس فروخته‌شده")
    t = ("🛰 <b>پنل‌های پاسارگارد</b>\n\n" + ("\n".join(lines) if lines else "هنوز پنلی متصل نشده است.") +
         "\n\n⭐️ = پنل پیش‌فرض (تست رایگان و محصولات بدون پنل روی آن ساخته می‌شوند)")
    bs = [btn(f"{'⭐️' if r['is_default'] else '🖥'} {r['name']}", f"a:srvm:{r['id']}") for r in rs]
    rows = [bs[i:i + 2] for i in range(0, len(bs), 2)]
    rows += [[btn("➕ افزودن پنل", "a:srva", style="success")], HOME_BTN]
    await show(ev, t, kb(rows))


async def srv_products_page(ev, sid: int):
    ps = await db.rows("SELECT * FROM products ORDER BY sort, id")
    names = {x["id"]: x["name"] for x in await db.rows("SELECT id, name FROM servers")}
    d = await db.row("SELECT id FROM servers WHERE is_default=1")
    rows = []
    for x in ps:
        sv = x["server_id"] or (d["id"] if d else 0)
        on = sv == sid
        label = ("✅ " if on else "⬜ ") + x["name"] + ("" if on else f" ({names.get(sv, '?')})")
        rows.append([btn(label, f"a:srvpa:{sid}:{x['id']}", style="success" if on else "")])
    rows.append([btn("🔙 بازگشت", f"a:srvm:{sid}")])
    await show(ev, "🛒 <b>محصولات این پنل</b>\n\nمحصولاتِ ✅ روی این پنل ساخته می‌شوند. "
                   "روی هر محصول بزن تا به این پنل منتقل شود.", kb(rows))

LABELS = {
    "shop": "🏪 نام فروشگاه", "welcome": "👋 متن خوش‌آمدگویی", "faq": "❓ سوالات متداول",
    "support": "🎧 متن پشتیبانی", "card": "💳 شماره کارت", "holder": "👤 نام صاحب کارت",
    "test_gb": "🎁 حجم تست رایگان", "min_charge": "💰 حداقل شارژ", "warn_on": "🔔 هشدار حجم",
}
HINTS = {
    "shop": "نام فروشگاه؛ در متن خوش‌آمدگویی جای {shop} می‌نشیند.",
    "welcome": "از {name} (نام کاربر) و {shop} (نام فروشگاه) می‌توانی استفاده کنی.",
    "faq": "متنی که کاربر در «سوالات متداول» می‌بیند.",
    "support": "متن یا آیدی پشتیبانی که کاربر می‌بیند.",
    "card": "شماره کارت برای شارژ کارت‌به‌کارت.",
    "holder": "نام صاحب کارت که کنار شماره کارت نمایش داده می‌شود.",
    "test_gb": "حجم تست رایگان به گیگابایت؛ مثلاً 1 یا 0.5. عدد 0 یعنی تست خاموش.",
    "min_charge": "حداقل مبلغ شارژ کیف پول به تومان.",
}


async def _f(key: str) -> float:
    try:
        return float(await db.get_setting(key) or 0)
    except ValueError:
        return 0.0


ROLE_NAME = {"admin": "👑 ادمین کامل", "operator": "🧾 اپراتور"}


async def staff_page(ev):
    rs = await db.rows("SELECT * FROM staff ORDER BY added")
    lines = [f"👑 مالک: <code>{x}</code>" for x in sorted(config.OWNER_IDS)]
    lines += [f"{ROLE_NAME.get(r['role'], r['role'])}: <code>{r['tg_id']}</code>" for r in rs]
    rows = [[btn(f"{ROLE_NAME.get(r['role'], r['role'])} • {r['tg_id']}", f"a:stfm:{r['tg_id']}")] for r in rs]
    rows += [[btn("➕ افزودن مدیر", "a:stfa", style="success")], HOME_BTN]
    await show(ev, "👮 <b>مدیران ربات</b>\n\n" + "\n".join(lines) +
               "\n\n👑 ادمین کامل: دسترسی به همه‌ی بخش‌ها\n🧾 اپراتور: فقط رسیدها (تایید/رد)", kb(rows))


async def settings_page(ev):
    shop = await db.get_setting("shop")
    holder = await db.get_setting("holder")
    card = "".join(ch for ch in await db.get_setting("card") if ch.isdigit())
    tgb, minc = await _f("test_gb"), int(await _f("min_charge"))
    warn = (await db.get_setting("warn_on")) == "1"
    card_txt = ("•••• " + card[-4:]) if card else "ثبت نشده"
    holder_txt = (" — " + h(holder)) if holder else ""
    test_txt = (f"{tgb:g} گیگ") if tgb > 0 else "خاموش"
    t = ("⚙️ <b>تنظیمات ربات</b>\n\n"
         f"🏪 فروشگاه: <b>{h(shop) or '—'}</b>\n"
         f"💳 کارت: <code>{card_txt}</code>{holder_txt}\n"
         f"💰 حداقل شارژ: {fmt(minc)} تومان\n"
         f"🎁 تست رایگان: {test_txt}\n"
         f"🔔 هشدار حجم: {'روشن' if warn else 'خاموش'}\n\n"
         "یکی از موارد زیر را برای ویرایش انتخاب کن 👇")
    rows = [
        [btn("🏪 نام فروشگاه", "a:sv:shop", style="primary"), btn("👋 متن خوش‌آمد", "a:sv:welcome", style="primary")],
        [btn("❓ سوالات متداول", "a:sv:faq"), btn("🎧 پشتیبانی", "a:sv:support")],
        [btn("💳 شماره کارت", "a:sv:card", style="success"), btn("👤 صاحب کارت", "a:sv:holder", style="success")],
        [btn("💰 حداقل شارژ", "a:sv:min_charge"), btn("🎁 حجم تست", "a:sv:test_gb")],
        [btn("🔔 هشدار حجم: ✅ روشن" if warn else "🔔 هشدار حجم: ❌ خاموش", "a:tg:warn_on",
             style="success" if warn else "danger")],
        [btn("🤖 پاسخگوی هوشمند", "ai:adm", style="primary")],
        [btn("🔙 مدیریت", "a:home", style="danger")],
    ]
    await show(ev, t, kb(rows))


async def home(ev):
    users = (await db.row("SELECT COUNT(*) c FROM users"))["c"]
    act = (await db.row("SELECT COUNT(*) c FROM panels WHERE status='active'"))["c"]
    pend = (await db.row("SELECT COUNT(*) c FROM receipts WHERE status='pending'"))["c"]
    if ev.from_user.id not in config.ADMIN_IDS:   # operator view
        return await show(ev, f"🧾 <b>پنل اپراتور</b>\n\n🧾 رسید در انتظار: {pend}",
                          kb([[btn("🧾 رسیدها", "a:rcpt", style="primary")], [btn("🏠 منوی کاربر", "u:home")]]))
    rows = [
        [btn("📊 آمار ربات", "s:m", style="primary")],
        [btn("👥 کاربران", "x:m"), btn("🧾 رسیدها", "a:rcpt")],
        [btn("🗂 فروخته‌شده", "a:sold"), btn("📦 محصولات", "a:prs")],
        [btn("🛠 مدیریت تغییرات ظاهری", "ux:m"), btn("🛰 اتصال پنل", "a:panel")],
        [btn("📢 پیام همگانی", "a:bc"), btn("⚙️ تنظیمات", "a:set")],
        [btn("🌐 ساخت وب‌سایت", "sw:m", style="success")],
    ]
    codes_btn = btn("🎟 کد تخفیف/هدیه", "a:cd", style="success")
    if ev.from_user.id in config.OWNER_IDS:
        rows.append([btn("👮 مدیران", "a:stf", style="primary"), codes_btn])
        from . import report as _rp
        rep_on = bool(await _rp.chat_id())
        rows.append([btn("💾 بکاپ", "a:bak", style="primary"),
                     btn("📣 گزارش ✅" if rep_on else "📣 گزارش ⚠️", "a:rpt", style="success" if rep_on else "danger")])
        rows.append([btn("🏠 منوی کاربر", "u:home")])
    else:
        rows.append([codes_btn, btn("🏠 منوی کاربر", "u:home")])
    await show(ev, f"🛠 <b>پنل مدیریت</b>\n\n👥 کاربران: {users}\n📦 پنل فعال: {act}\n🧾 رسید در انتظار: {pend}", kb(rows))


@router.command("admin")
async def admin_cmd(m: Message):
    WAIT.pop(m.from_user.id, None)
    await home(m)


async def btn_card(c, key: str):
    b = await db.row("SELECT * FROM buttons WHERE key=?", key)
    text = (f"🎛 <b>{h(b['title'])}</b>\n\nوضعیت: {'✅ روشن' if b['enabled'] else '⛔ خاموش'}\n"
            f"رنگ: {STYLE_NAME[b['style']]}\nایموجی پریمیوم: {'<code>' + h(b['emoji_id']) + '</code>' if b['emoji_id'] else 'ندارد'}")
    rows = [
        [btn("⛔ خاموش" if b["enabled"] else "✅ روشن", f"a:btg:{key}"), btn("🎨 رنگ بعدی", f"a:bcl:{key}")],
        [btn("✏️ تغییر نام", f"a:bnm:{key}"), btn("✨ ایموجی پریمیوم", f"a:bem:{key}")],
        [btn("⬆️", f"a:bup:{key}"), btn("⬇️", f"a:bdn:{key}")],
        [btn("🔙 بازگشت", "a:btn")],
    ]
    await show(c, text, kb(rows))


async def move_button(key: str, delta: int):
    keys = [r["key"] for r in await db.rows("SELECT key FROM buttons ORDER BY sort")]
    i = keys.index(key)
    j = i + delta
    if 0 <= j < len(keys):
        keys[i], keys[j] = keys[j], keys[i]
        for n, k in enumerate(keys):
            await db.run("UPDATE buttons SET sort=? WHERE key=?", n, k)


async def sold_card(c, pid: int):
    from . import paneladm
    return await paneladm.card(c, pid)
    x = await db.row("SELECT * FROM panels WHERE id=?", pid)
    if not x:
        return await c.answer("پیدا نشد.", show_alert=True)
    rows = [
        [btn("⛔ تعلیق" if x["status"] != "suspended" else "✅ فعال‌سازی", f"a:spt:{pid}"), btn("➕ تمدید", f"a:spe:{pid}")],
        [btn("🔑 رمز جدید", f"a:spw:{pid}"), btn("🗑 حذف", f"a:spd:{pid}", style="danger")],
        [btn("🔙 بازگشت", "a:sold")],
    ]
    await show(c, panel_text(x) + f"\n👤 مالک: <code>{x['user_id']}</code>", kb(rows))


@router.callback("a:")
async def acb(c: Callback):
    p = c.data.split(":")
    a, uid = p[1], c.from_user.id
    WAIT.pop(uid, None)
    back = kb([HOME_BTN])

    if a == "home":
        return await home(c)

    # ---- buttons ----
    if a == "btn":
        rows = await db.rows("SELECT * FROM buttons ORDER BY sort")
        lay = [[btn(("✅ " if r["enabled"] else "⛔ ") + r["title"], f"a:bt:{r['key']}", r["emoji_id"], r["style"])] for r in rows]
        return await show(c, "🎛 <b>دکمه‌های منوی اصلی</b>\nروی هر دکمه بزن تا تنظیمش کنی (پیش‌نمایش رنگ و ایموجی همین‌جاست).",
                          kb(lay + [HOME_BTN]))
    if a in ("bt", "btg", "bcl", "bnm", "bem", "bup", "bdn"):
        key = p[2]
        b = await db.row("SELECT * FROM buttons WHERE key=?", key)
        if not b:
            return await c.answer("پیدا نشد.", show_alert=True)
        if a == "btg":
            await db.run("UPDATE buttons SET enabled=1-enabled WHERE key=?", key)
        elif a == "bcl":
            await db.run("UPDATE buttons SET style=? WHERE key=?", STYLES[(STYLES.index(b["style"]) + 1) % len(STYLES)], key)
        elif a in ("bup", "bdn"):
            await move_button(key, -1 if a == "bup" else 1)
        elif a == "bnm":
            WAIT[uid] = ("a_btn_title", key)
            return await show(c, "اسم جدید دکمه را بفرست:", kb([[btn("🔙 بازگشت", f"a:bt:{key}")]]))
        elif a == "bem":
            WAIT[uid] = ("a_btn_emoji", key)
            return await show(c, "یک <b>ایموجی پریمیوم</b> را همین‌جا بفرست (یا عدد 0 برای حذف).",
                              kb([[btn("🔙 بازگشت", f"a:bt:{key}")]]))
        return await btn_card(c, key)

    # ---- products & packages ----
    if a == "prs":
        ps = await db.rows("SELECT * FROM products ORDER BY sort, id")
        lay = [[btn(("✅ " if x["active"] else "⛔ ") + x["name"], f"a:pr:{x['id']}")] for x in ps]
        lay.append([btn("➕ افزودن محصول", "a:pra", style="success")])
        return await show(c, "📦 <b>محصولات</b>\nهر محصول یک سرویس/پنل قابل فروش است و پکیج‌های حجم خودش را دارد.",
                          kb(lay + [HOME_BTN]))
    if a == "pra":
        WAIT[uid] = ("a_prod_add", None)
        return await show(c, "نام محصول را بفرست. مثال: <code>سرویس تانل</code>", kb([[btn("🔙 بازگشت", "a:prs")]]))
    if a in ("pr", "prt", "prx", "prxx"):
        pid = int(p[2])
        x = await db.row("SELECT * FROM products WHERE id=?", pid)
        if not x:
            return await c.answer("پیدا نشد.", show_alert=True)
        if a == "prt":
            await db.run("UPDATE products SET active=1-active WHERE id=?", pid)
        if a == "prx":
            return await show(c, f"⚠️ محصول «{h(x['name'])}» و همه‌ی پکیج‌هایش حذف شود؟ (پنل‌های فروخته‌شده می‌مانند)",
                              kb([[btn("🗑 بله، حذف", f"a:prxx:{pid}", style="danger"), btn("🔙 نه", f"a:pr:{pid}")]]))
        if a == "prxx":
            await db.run("DELETE FROM packages WHERE product_id=?", pid)
            await db.run("DELETE FROM products WHERE id=?", pid)
            return await show(c, "🗑 حذف شد.", kb([[btn("🔙 بازگشت", "a:prs")]]))
        x = await db.row("SELECT * FROM products WHERE id=?", pid)
        n = (await db.row("SELECT COUNT(*) c FROM packages WHERE product_id=?", pid))["c"]
        custom = f"{fmt(x['price_gb'])} تومان" if x["price_gb"] > 0 else "خاموش"
        text = (f"📦 <b>{h(x['name'])}</b>\nوضعیت: {'✅ فعال' if x['active'] else '⛔ غیرفعال'}\n"
                f"📝 توضیحات: {h(x['descr']) or '—'}\n💵 قیمت هر گیگ (حجم دلخواه): {custom}\n"
                f"📏 بازه‌ی حجم دلخواه: {fgb(x['min_gb'])} تا {fgb(x['max_gb'])}\n📦 تعداد پکیج: {n}")
        rows = [[btn("📦 پکیج‌ها", f"a:pks:{pid}", style="primary")],
                [btn("⛔ غیرفعال" if x["active"] else "✅ فعال", f"a:prt:{pid}"), btn("✏️ نام", f"a:prn:{pid}")],
                [btn("📝 توضیحات", f"a:prd:{pid}"), btn("💵 قیمت هر گیگ", f"a:prg:{pid}")],
                [btn("🗑 حذف", f"a:prx:{pid}", style="danger")], [btn("🔙 بازگشت", "a:prs")]]
        return await show(c, text, kb(rows))
    if a in ("prn", "prd", "prg"):
        pid = int(p[2])
        WAIT[uid] = ({"prn": "a_prod_name", "prd": "a_prod_desc", "prg": "a_prod_pgb"}[a], pid)
        ask = {"prn": "نام جدید محصول را بفرست:",
               "prd": "توضیحات محصول را بفرست (در صفحه‌ی جزئیات پکیج نمایش داده می‌شود؛ 0 = حذف):",
               "prg": "قیمت هر گیگابایت را به تومان بفرست (برای گزینه‌ی «حجم دلخواه»؛ 0 = خاموش):"}[a]
        return await show(c, ask, kb([[btn("🔙 بازگشت", f"a:pr:{pid}")]]))
    if a == "pks":
        pid = int(p[2])
        ks = await db.rows("SELECT * FROM packages WHERE product_id=? ORDER BY gb", pid)
        lay = [[btn(("✅ " if k["active"] else "⛔ ") + f"{fgb(k['gb'])} • {fmt(k['price'])} ت", f"a:pk:{k['id']}")] for k in ks]
        lay.append([btn("➕ افزودن پکیج", f"a:pka:{pid}", style="success")])
        lay.append([btn("🔙 بازگشت", f"a:pr:{pid}")])
        return await show(c, "📦 <b>پکیج‌های حجم</b>", kb(lay))
    if a == "pka":
        pid = int(p[2])
        WAIT[uid] = ("a_pkg_add", pid)
        return await show(c, "هر پکیج را در یک خط بفرست: <code>حجم(گیگ)|قیمت(تومان)</code>\nمی‌توانی چند خط را یک‌جا بفرستی:\n"
                             "<code>250|300000\n500|550000\n1000|1000000</code>", kb([[btn("🔙 بازگشت", f"a:pks:{pid}")]]))
    if a in ("pk", "pkt", "pkd"):
        k = await db.row("SELECT * FROM packages WHERE id=?", int(p[2]))
        if not k:
            return await c.answer("پیدا نشد.", show_alert=True)
        if a == "pkd":
            await db.run("DELETE FROM packages WHERE id=?", k["id"])
            return await show(c, "🗑 حذف شد.", kb([[btn("🔙 بازگشت", f"a:pks:{k['product_id']}")]]))
        if a == "pkt":
            await db.run("UPDATE packages SET active=1-active WHERE id=?", k["id"])
        k = await db.row("SELECT * FROM packages WHERE id=?", k["id"])
        rows = [[btn("⛔ غیرفعال" if k["active"] else "✅ فعال", f"a:pkt:{k['id']}"),
                 btn("🗑 حذف", f"a:pkd:{k['id']}", style="danger")], [btn("🔙 بازگشت", f"a:pks:{k['product_id']}")]]
        return await show(c, f"💎 <b>{fgb(k['gb'])}</b>\nقیمت: {fmt(k['price'])} تومان", kb(rows))

    # ---- servers (multi panel) ----
    if a == "panel":
        return await servers_page(c)
    if a == "srva":
        WAIT[uid] = ("a_srv", None)
        return await show(c, "➕ <b>افزودن پنل</b>\n\n" + SRV_HELP, kb([[btn("🔙 بازگشت", "a:panel", style="danger")]]))
    if a in ("srvm", "srvt", "srve", "srvd", "srvx", "srvxx", "srvp", "srvpa", "srvu", "srvlow", "srvn", "srvs",
             "srvsy", "srvq", "srvmon"):
        sid = int(p[2])
        r = await db.row("SELECT * FROM servers WHERE id=?", sid)
        if not r:
            return await servers_page(c)
        back_s = kb([[btn("🔙 بازگشت", f"a:srvm:{sid}")]])
        n = (await db.row("SELECT COUNT(*) c FROM panels WHERE server_id=?", sid))["c"]
        k = (await db.row("SELECT COUNT(*) c FROM products WHERE server_id=? OR (server_id=0 AND ?=1)", sid, r["is_default"]))["c"]
        if a == "srvm":
            return await server_dashboard(c, r, k)
        if a == "srvu":
            return await srv_admins_page(c, r, "all")
        if a == "srvlow":
            return await srv_admins_page(c, r, "low")
        if a == "srvn":
            return await srv_nodes_page(c, r)
        if a == "srvs":
            return await srv_sales_page(c, r)
        if a == "srvsy":
            return await srv_sync_page(c, r)
        if a == "srvq":
            WAIT[uid] = ("a_srvq", sid)
            return await show(c, "🔍 نام‌کاربری ادمین را بفرست:", back_s)
        if a == "srvmon":
            cur = await db.get_setting(f"mon_{sid}", "1")
            await db.set_setting(f"mon_{sid}", "0" if cur == "1" else "1")
            return await server_dashboard(c, r, k)
        if a == "srvt":
            try:
                pg = await get_pg(sid)
                cnt = await pg.test()
                rep = await pg.schema_report()
            except PanelError as e:
                return await show(c, f"❌ {h(e)}", back_s)
            return await show(c, f"✅ اتصال برقرار است ({cnt} ادمین روی پنل).\n\n<pre>{h(rep)}</pre>", back_s)
        if a == "srve":
            WAIT[uid] = ("a_srved", sid)
            return await show(c, "✏️ <b>ویرایش پنل</b>\n\n" + SRV_HELP, back_s)
        if a == "srvd":
            await db.run("UPDATE servers SET is_default=CASE WHEN id=? THEN 1 ELSE 0 END", sid)
            return await servers_page(c)
        if a in ("srvx", "srvxx"):
            if n or k:
                return await c.answer(f"این پنل {n} سرویس فروخته‌شده و {k} محصول متصل دارد؛ اول آن‌ها را منتقل کن.", show_alert=True)
            if a == "srvx":
                return await show(c, f"🗑 پنل «{h(r['name'])}» حذف شود؟",
                                  kb([[btn("✅ بله، حذف", f"a:srvxx:{sid}", style="danger"), btn("🔙 نه", f"a:srvm:{sid}")]]))
            await db.run("DELETE FROM servers WHERE id=?", sid)
            if r["is_default"]:
                await db.run("UPDATE servers SET is_default=1 WHERE id=(SELECT id FROM servers ORDER BY id LIMIT 1)")
            return await servers_page(c)
        if a == "srvp":
            return await srv_products_page(c, sid)
        if a == "srvpa":
            await db.run("UPDATE products SET server_id=? WHERE id=?", sid, int(p[3]))
            return await srv_products_page(c, sid)

    # ---- panel connection ----
    if a == "panel":
        url, user = await db.get_setting("panel_url"), await db.get_setting("panel_user")
        st = (f"🌐 <code>{h(url)}</code>\n👤 <code>{h(user)}</code>\n🎭 نقش پنل‌های نماینده: operator (خودکار)"
              if url else "هنوز پنلی متصل نشده است.")
        rows = [[btn("🔌 اتصال / تغییر پنل", "a:pnset", style="primary")], [btn("🧪 تست اتصال و ساختار", "a:pntest")], HOME_BTN]
        return await show(c, f"🛰 <b>پنل پاسارگارد</b>\n\n{st}", kb(rows))
    if a == "pnset":
        WAIT[uid] = ("a_panel", None)
        return await show(c, "آدرس، نام‌کاربری و رمز ادمین (سودو) پنل را در <b>یک پیام</b> و با فاصله بفرست:\n"
                             "<code>https://panel.example.com:8000 admin password</code>\n\nپیامت بعد از خواندن پاک می‌شود.",
                          kb([[btn("🔙 بازگشت", "a:panel")]]))
    if a == "pntest":
        try:
            pg = await get_pg()
            n = await pg.test()
            rep = await pg.schema_report()
        except PanelError as e:
            return await show(c, f"❌ {h(e)}", kb([[btn("🔙 بازگشت", "a:panel")]]))
        return await show(c, f"✅ اتصال برقرار است ({n} ادمین روی پنل).\n\nساختار واقعی ادمین در پنل تو:\n<pre>{h(rep)}</pre>\n"
                             "اگر مسیرها/فیلدها با ربات نمی‌خواند، همین متن را بفرست تا اصلاح شود.",
                          kb([[btn("🔙 بازگشت", "a:panel")]]))

    # ---- sold panels ----
    if a == "sold":
        ps = await db.rows("SELECT * FROM panels ORDER BY id DESC LIMIT 20")
        lay = [[btn(f"{panel_label(x)} • {x['status']}", f"a:sp:{x['id']}")] for x in ps]
        return await show(c, "🗂 <b>پنل‌های فروخته‌شده</b> (۲۰ تای آخر)", kb(lay + [HOME_BTN]))
    if a == "sp":
        return await sold_card(c, int(p[2]))
    if a in ("spt", "spe", "spw", "spd", "spdd"):
        pid = int(p[2])
        x = await db.row("SELECT * FROM panels WHERE id=?", pid)
        if not x:
            return await c.answer("پیدا نشد.", show_alert=True)
        try:
            if a == "spt":
                if x["status"] == "suspended":
                    if 0 < x["expires"] <= time.time():
                        return await c.answer("منقضی شده؛ اول تمدیدش کن.", show_alert=True)
                    await (await get_pg(x["server_id"])).set_disabled(x["admin_username"], False)
                    await db.run("UPDATE panels SET status='active' WHERE id=?", pid)
                else:
                    await (await get_pg(x["server_id"])).set_disabled(x["admin_username"], True)
                    await db.run("UPDATE panels SET status='suspended' WHERE id=?", pid)
            elif a == "spe":
                WAIT[uid] = ("a_ext", pid)
                return await show(c, "چند روز تمدید شود؟ (عدد بفرست)", kb([[btn("🔙 بازگشت", f"a:sp:{pid}")]]))
            elif a == "spw":
                pw = gen_password()
                await (await get_pg(x["server_id"])).set_password(x["admin_username"], pw)
                return await show(c, f"🔑 رمز جدید <code>{h(x['admin_username'])}</code>:\n<code>{h(pw)}</code>",
                                  kb([[btn("🔙 بازگشت", f"a:sp:{pid}")]]))
            elif a == "spd":
                return await show(c, f"⚠️ ادمین <code>{h(x['admin_username'])}</code> از پنل پاک شود؟",
                                  kb([[btn("🗑 بله، حذف", f"a:spdd:{pid}", style="danger"), btn("🔙 نه", f"a:sp:{pid}")]]))
            elif a == "spdd":
                await (await get_pg(x["server_id"])).delete_admin(x["admin_username"])
                await db.run("DELETE FROM panels WHERE id=?", pid)
                await db.ev("delete", x["user_id"], x["admin_username"])
                return await show(c, "🗑 حذف شد.", kb([[btn("🔙 بازگشت", "a:sold")]]))
        except PanelError as e:
            return await c.answer(f"خطای پنل: {e}"[:190], show_alert=True)
        return await sold_card(c, pid)

    # ---- receipts ----
    if a == "rc":
        rid = int(p[3])
        _, n = await db.run("UPDATE receipts SET status=? WHERE id=? AND status='pending'", "ok" if p[2] == "ok" else "no", rid)
        if n != 1:
            return await c.answer("این رسید قبلاً بررسی شده است.", show_alert=True)
        r = await db.row("SELECT * FROM receipts WHERE id=?", rid)
        if p[2] == "ok":
            await db.credit(r["user_id"], r["amount"])
            msg, note = f"✅ شارژ {fmt(r['amount'])} تومان تایید شد.", "✅ تایید شد"
        else:
            msg, note = "❌ رسید شارژ تو رد شد. اگر اشتباه است به پشتیبانی پیام بده.", "❌ رد شد"
        try:
            await invoice.settle(c.bot, rid, p[2] == "ok", r)
            await c.bot.send_message(r["user_id"], msg, effect="5046509860389126442" if p[2] == "ok" else None)
        except Exception:
            log.warning("cannot notify user %s", r["user_id"])
        try:
            await c.message.edit_caption(f"{c.message.caption}\n\n{note}")
        except Exception:
            pass
        return await c.answer(note)
    if a == "rcpt":
        rs = await db.rows("SELECT * FROM receipts WHERE status='pending' ORDER BY id LIMIT 10")
        if not rs:
            return await show(c, "🧾 رسید در انتظاری نیست.", back)
        for r in rs:
            mk = kb([[btn("✅ تایید", f"a:rc:ok:{r['id']}", style="success"), btn("❌ رد", f"a:rc:no:{r['id']}", style="danger")]])
            await c.bot.send_photo(uid, r["file_id"], caption=f"🧾 رسید #{r['id']}\nکاربر: <code>{r['user_id']}</code>\nمبلغ: {fmt(r['amount'])} تومان", reply_markup=mk)
        return await c.answer()

    # ---- users ----
    if a == "user":
        rows = [[btn("💰 تغییر موجودی", "a:ubal")], [btn("🚫 مسدود / آزاد", "a:ublk")], HOME_BTN]
        return await show(c, "👥 <b>کاربران</b>", kb(rows))
    if a == "ubal":
        WAIT[uid] = ("a_bal", None)
        return await show(c, "آیدی عددی و مبلغ را بفرست. مثال: <code>123456 50000</code> (برای کم کردن مبلغ منفی بزن)",
                          kb([[btn("🔙 بازگشت", "a:user")]]))
    if a == "ublk":
        WAIT[uid] = ("a_blk", None)
        return await show(c, "آیدی عددی کاربر را بفرست:", kb([[btn("🔙 بازگشت", "a:user")]]))

    # ---- backup (owners only) ----
    if a.startswith("bak"):
        if uid not in config.OWNER_IDS:
            return await c.answer("فقط مالک اصلی به این بخش دسترسی دارد.", show_alert=True)
        if a == "bakn":
            await c.answer("⏳ در حال ساخت بکاپ…")
            from .backup import run_backup
            err = await run_backup(c.bot, "manual")
            await c.message.answer(f"❌ بکاپ ناموفق بود:\n<code>{h(err)}</code>" if err else "✅ بکاپ ساخته و ارسال شد.")
        elif a == "bakt":
            cur = await db.get_setting("backup_on", "1")
            await db.set_setting("backup_on", "0" if cur == "1" else "1")
        elif a == "bakh" and int(p[2]) in BAK_HOURS:
            await db.set_setting("backup_hours", p[2])
        return await backup_page(c)

    # ---- report group (owners only) ----
    if a == "rpt":
        if uid not in config.OWNER_IDS:
            return await c.answer("فقط مالک اصلی به این بخش دسترسی دارد.", show_alert=True)
        return await report_page(c)
    if a.startswith("rpt"):
        if uid not in config.OWNER_IDS:
            return await c.answer("فقط مالک اصلی به این بخش دسترسی دارد.", show_alert=True)
        from . import report
        if a == "rpth":
            return await show(c, report_help(), kb([[btn("🔙 بازگشت", "a:rpt")]]))
        if a == "rptid":
            WAIT[uid] = ("a_rptid", None)
            return await show(c, "🔗 ID گروه را بفرست (عددی مثل <code>-1001234567890</code>).\n\n"
                                 "ربات باید قبلاً در گروه ادمین با دسترسی Manage Topics شده باشد.",
                              kb([[btn("🔙 بازگشت", "a:rpt", style="danger")]]))
        if a == "rptx":
            await db.set_setting("report_chat", "0")
        elif a == "rptm":
            await c.answer("⏳ در حال ساخت تاپیک‌ها…")
            created, failed = await report.ensure_topics(c.bot)
            msg = f"🧩 {len(created)} تاپیک ساخته شد." if created else "🧩 همه‌ی تاپیک‌ها از قبل ساخته شده‌اند."
            if failed:
                msg += "\n⚠️ ساخته نشد: " + "، ".join(failed) + "\nدسترسی Manage Topics ربات را چک کن."
            await c.message.answer(msg)
        elif a == "rptt":
            await c.answer("⏳ در حال ارسال تست…")
            n = await report.test_all(c.bot)
            await c.message.answer(f"🧪 تست در {n} تاپیک ارسال شد." if n else "❌ ارسال نشد؛ اتصال گروه و دسترسی ربات را چک کن.")
        return await report_page(c)

    # ---- discount / gift codes ----
    if a == "cd":
        return await codes_page(c)
    if a == "cdn":
        if p[2] not in CODE_HELP:
            return await c.answer()
        WAIT[uid] = ("a_cd", p[2])
        return await show(c, CODE_HELP[p[2]], kb([[btn("🔙 بازگشت", "a:cd", style="danger")]]))
    if a in ("cdv", "cdt", "cdx", "cdxx"):
        cid = int(p[2])
        r = await db.row("SELECT * FROM codes WHERE id=?", cid)
        if not r:
            return await codes_page(c)
        if a == "cdt":
            await db.run("UPDATE codes SET active=1-active WHERE id=?", cid)
        elif a == "cdx":
            return await show(c, f"🗑 کد <code>{h(r['code'])}</code> حذف شود؟",
                              kb([[btn("✅ بله، حذف", f"a:cdxx:{cid}", style="danger"), btn("🔙 نه", f"a:cdv:{cid}")]]))
        elif a == "cdxx":
            await db.run("DELETE FROM code_uses WHERE code_id=?", cid)
            await db.run("DELETE FROM codes WHERE id=?", cid)
            return await codes_page(c)
        return await code_view(c, cid)

    # ---- staff (owners only) ----
    if a.startswith("stf"):
        if uid not in config.OWNER_IDS:
            return await c.answer("فقط مالک اصلی به این بخش دسترسی دارد.", show_alert=True)
        if a == "stf":
            return await staff_page(c)
        if a == "stfa":
            WAIT[uid] = ("a_stf", None)
            return await show(c, "👮 <b>افزودن مدیر</b>\n\nآیدی عددی تلگرام فرد را بفرست.\n"
                                 "(فرد باید قبلاً ربات را استارت کرده باشد؛ آیدی را از ربات‌هایی مثل @userinfobot بگیر.)",
                              kb([[btn("🔙 بازگشت", "a:stf", style="danger")]]))
        if a == "stfm":
            r = await db.row("SELECT * FROM staff WHERE tg_id=?", int(p[2]))
            if not r:
                return await staff_page(c)
            other = "operator" if r["role"] == "admin" else "admin"
            rows = [[btn(f"تبدیل به {ROLE_NAME[other]}", f"a:stfs:{r['tg_id']}:{other}", style="primary")],
                    [btn("🗑 حذف", f"a:stfd:{r['tg_id']}", style="danger")], [btn("🔙 بازگشت", "a:stf")]]
            return await show(c, f"{ROLE_NAME[r['role']]}\n<code>{r['tg_id']}</code>", kb(rows))
        if a == "stfs":
            tid, role = int(p[2]), p[3]
            if role not in ROLE_NAME or tid in config.OWNER_IDS:
                return await c.answer("نامعتبر.", show_alert=True)
            await db.run("INSERT INTO staff(tg_id,role,added) VALUES(?,?,?) "
                         "ON CONFLICT(tg_id) DO UPDATE SET role=excluded.role", tid, role, int(time.time()))
            await db.load_staff()
            try:
                await c.bot.send_message(tid, f"👮 شما به‌عنوان {ROLE_NAME[role]} به ربات اضافه شدید.\nبرای ورود به پنل /admin را بفرستید.")
            except Exception:
                log.warning("cannot notify new staff %s", tid)
            return await staff_page(c)
        if a == "stfd":
            await db.run("DELETE FROM staff WHERE tg_id=?", int(p[2]))
            await db.load_staff()
            return await staff_page(c)

    # ---- settings ----
    if a == "set":
        return await settings_page(c)
    if a == "tg":
        if p[2] == "warn_on":
            cur = await db.get_setting("warn_on")
            await db.set_setting("warn_on", "0" if cur == "1" else "1")
        return await settings_page(c)
    if a == "sv":
        key = p[2]
        WAIT[uid] = ("a_set", key)
        cur = await db.get_setting(key)
        return await show(c, f"✏️ <b>{LABELS.get(key, key)}</b>\n\n📌 مقدار فعلی:\n<code>{h(cur) or '—'}</code>\n\n"
                             f"ℹ️ {HINTS.get(key, '')}\n\nمقدار جدید را بفرست:",
                          kb([[btn("🔙 بازگشت به تنظیمات", "a:set", style="danger")]]))

    # ---- broadcast ----
    if a == "bc":
        WAIT[uid] = ("a_bc", None)
        return await show(c, "متن پیام همگانی را بفرست:", back)

    await c.answer()


async def broadcast(bot, text: str, admin_id: int):
    ids = [r["tg_id"] for r in await db.rows("SELECT tg_id FROM users WHERE blocked=0")]
    ok = fail = 0
    for i in ids:
        try:
            await bot.send_message(i, text)
            ok += 1
        except Exception:
            fail += 1
        await asyncio.sleep(0.05)
    await bot.send_message(admin_id, f"📢 ارسال تمام شد: {ok} موفق، {fail} ناموفق")


@router.message(waiting("a_"))
async def await_admin(m: Message):
    uid = m.from_user.id
    kind, arg = WAIT[uid]
    text = (m.text or "").strip()

    if kind == "a_btn_title":
        if not text or len(text) > 40:
            return await m.answer("اسم باید بین ۱ تا ۴۰ حرف باشد.")
        await db.run("UPDATE buttons SET title=? WHERE key=?", text, arg)
    elif kind == "a_btn_emoji":
        ids = [e["custom_emoji_id"] for e in m.entities if e.get("type") == "custom_emoji"]
        if ids:
            eid = ids[0]
        elif text == "0":
            eid = ""
        elif text.isdigit() and len(text) > 10:
            eid = text
        else:
            return await m.answer("ایموجی پریمیوم دریافت نشد. یک ایموجی پریمیوم بفرست یا 0 برای حذف.")
        await db.run("UPDATE buttons SET emoji_id=? WHERE key=?", eid, arg)
    elif kind in ("a_prod_add", "a_prod_name"):
        if not text or len(text) > 40:
            return await m.answer("اسم باید بین ۱ تا ۴۰ حرف باشد.")
        if kind == "a_prod_add":
            await db.run("INSERT INTO products(name) VALUES(?)", text)
        else:
            await db.run("UPDATE products SET name=? WHERE id=?", text, arg)
    elif kind == "a_prod_desc":
        if len(text) > 500:
            return await m.answer("حداکثر ۵۰۰ حرف.")
        await db.run("UPDATE products SET descr=? WHERE id=?", "" if text == "0" else text, arg)
    elif kind == "a_prod_pgb":
        v = num(text)
        if v is None or v < 0:
            return await m.answer("یک عدد بفرست (0 = حجم دلخواه خاموش).")
        await db.run("UPDATE products SET price_gb=? WHERE id=?", v, arg)
    elif kind == "a_pkg_add":
        items = []
        for line in text.splitlines():
            if not line.strip():
                continue
            parts = [t.strip() for t in line.split("|")]
            gb, price = (num(parts[0]), num(parts[1])) if len(parts) == 2 else (None, None)
            if not gb or not price or gb <= 0 or price <= 0:
                return await m.answer(f"خط «{h(line)}» درست نیست. فرمت: <code>250|300000</code>")
            items.append((gb, price))
        if not items:
            return await m.answer("حداقل یک خط بفرست. مثال: <code>250|300000</code>")
        for gb, price in items:
            await db.run("INSERT INTO packages(product_id,gb,price) VALUES(?,?,?)", arg, gb, price)
    elif kind == "a_panel":
        try:
            await m.delete()
        except Exception:
            pass
        parts = text.split()
        if len(parts) != 3 or not parts[0].startswith("http"):
            return await m.answer("فرمت درست نیست: <code>https://panel.example.com:8000 admin password</code>")
        try:
            n = await PG(parts[0], parts[1], parts[2], config.VERIFY_SSL).test()
        except PanelError as e:
            return await m.answer(f"❌ {h(e)}\nدوباره بفرست یا /admin بزن.")
        await db.set_setting("panel_url", parts[0].rstrip("/"))
        await db.set_setting("panel_user", parts[1])
        await db.set_setting("panel_pass", db.enc(parts[2]))
        panel_mod._cache = None
        WAIT.pop(uid, None)
        return await m.answer(f"✅ پنل متصل شد ({n} ادمین روی پنل). حالا «تست اتصال و ساختار» را بزن.", reply_markup=kb([[btn("🛰 پنل", "a:panel")]]))
    elif kind == "a_ext":
        days = num(text)
        x = await db.row("SELECT * FROM panels WHERE id=?", arg)
        if not days or days <= 0 or not x:
            return await m.answer("یک عدد مثبت بفرست.")
        try:
            await extend_panel(x, days)
        except PanelError as e:
            return await m.answer(f"❌ {h(e)}")
    elif kind == "a_bal":
        parts = text.split()
        target, amount = (num(parts[0]), num(parts[1])) if len(parts) == 2 else (None, None)
        if not target or not amount:
            return await m.answer("فرمت: <code>123456 50000</code>")
        if not await db.row("SELECT 1 FROM users WHERE tg_id=?", target):
            return await m.answer("این کاربر هنوز ربات را استارت نکرده است.")
        if amount > 0:
            await db.credit(target, amount)
        elif not await db.debit(target, -amount):
            return await m.answer("موجودی کاربر کمتر از این مبلغ است.")
    elif kind == "a_blk":
        target = num(text)
        r = await db.row("SELECT blocked FROM users WHERE tg_id=?", target) if target else None
        if not r:
            return await m.answer("کاربر پیدا نشد.")
        await db.run("UPDATE users SET blocked=1-blocked WHERE tg_id=?", target)
        WAIT.pop(uid, None)
        return await m.answer("🚫 مسدود شد." if not r["blocked"] else "✅ آزاد شد.", reply_markup=kb([HOME_BTN]))
    elif kind == "a_set":
        if arg == "test_gb":
            v = fnum(text)
            if v is None:
                return await m.answer("یک عدد بفرست (مثلاً 1 یا 0.5؛ 0 = خاموش).")
            await db.set_setting(arg, f"{v:g}")
        else:
            if arg in NUMERIC and num(text) is None:
                return await m.answer("یک عدد بفرست.")
            await db.set_setting(arg, str(num(text)) if arg in NUMERIC else text)
        WAIT.pop(uid, None)
        await m.answer("✅ ذخیره شد.")
        return await settings_page(m)
    elif kind == "a_stf":
        tid = num(text)
        if tid is None or tid <= 0:
            return await m.answer("آیدی عددی معتبر بفرست.")
        if tid in config.OWNER_IDS:
            return await m.answer("این فرد مالک اصلی است.")
        WAIT.pop(uid, None)
        return await m.answer(f"نقش <code>{tid}</code> را انتخاب کن:", reply_markup=kb([
            [btn("👑 ادمین کامل", f"a:stfs:{tid}:admin", style="primary"),
             btn("🧾 اپراتور (فقط رسیدها)", f"a:stfs:{tid}:operator", style="success")],
            [btn("🔙 بازگشت", "a:stf", style="danger")]]))
    elif kind == "a_srvq":
        from .ui import fdate
        uname = text.strip().lstrip("@")
        WAIT.pop(uid, None)
        back_q = [btn("🔙 بازگشت", f"a:srvm:{arg}")]
        try:
            i = await (await get_pg(arg)).admin_info(uname)
        except PanelError as e:
            return await m.answer(f"❌ {h(str(e)[:200])}", reply_markup=kb([back_q]))
        mine = await db.row("SELECT * FROM panels WHERE admin_username=? AND server_id=?", uname, arg)
        if i is None:
            t = f"❌ ادمین <code>{h(uname)}</code> روی این پنل پیدا نشد."
        else:
            t = (f"👤 <b>{h(uname)}</b>\n{'⛔️ غیرفعال' if i['disabled'] else '🟢 فعال'}\n"
                 f"💎 حجم: {_g(i['limit'])} | مصرف: {_g(i['used'])}\n👥 کاربران: {i['users'] if i['users'] is not None else '—'}")
        rows = []
        if mine:
            t += (f"\n\n🤖 در ربات: خریدار <code>{mine['user_id']}</code> • {fdate(mine['created'])}"
                  f"{' • تست' if mine['is_test'] else ''}")
            rows.append([btn("🗂 مدیریت سرویس", f"a:sp:{mine['id']}", style="primary")])
        return await m.answer(t, reply_markup=kb(rows + [back_q]))
    elif kind in ("a_srv", "a_srved"):
        try:
            await m.delete()
        except Exception:
            pass
        parts = text.split(None, 3)
        if len(parts) < 3 or not parts[0].lower().startswith("http"):
            return await m.answer("فرمت درست نیست. این‌طور بفرست:\n<code>https://panel.example.com:8000 admin password نام‌دلخواه</code>")
        url, user, pw = parts[0].rstrip("/"), parts[1], parts[2]
        name = parts[3].strip() if len(parts) > 3 else url.split("//", 1)[-1]
        try:
            cnt = await PG(url, user, pw, config.VERIFY_SSL).test()
        except PanelError as e:
            return await m.answer(f"❌ اتصال ناموفق: {h(e)}\nدوباره بفرست، یا برای خروج /admin بزن.")
        if kind == "a_srv":
            first = not await db.row("SELECT 1 FROM servers")
            await db.run("INSERT INTO servers(name,url,username,password,is_default) VALUES(?,?,?,?,?)",
                         name, url, user, db.enc(pw), int(first))
        else:
            await db.run("UPDATE servers SET name=?, url=?, username=?, password=? WHERE id=?",
                         name, url, user, db.enc(pw), arg)
        WAIT.pop(uid, None)
        await m.answer(f"✅ پنل «{h(name)}» ذخیره شد ({cnt} ادمین روی پنل).")
        return await servers_page(m)
    elif kind == "a_cd":
        import re, secrets
        parts = text.split()
        if len(parts) < 2:
            return await m.answer("فرمت درست نیست. مثال: <code>EID20 20 100 7</code>")
        code = parts[0].upper()
        if code == "AUTO":
            code = "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(8))
        if not re.fullmatch(r"[A-Z0-9_-]{3,24}", code):
            return await m.answer("کد فقط حروف انگلیسی، عدد، _ و - باشد (۳ تا ۲۴ کاراکتر).")
        nums = [num(x) for x in parts[1:5]]
        if any(n is None or n < 0 for n in nums):
            return await m.answer("مقدارها باید عدد باشند.")
        nums += [0] * (4 - len(nums))
        value, mx, days, minp = nums[:4]
        if value <= 0 or (arg == "percent" and value > 100):
            return await m.answer("مقدار نامعتبر است (درصد باید بین ۱ تا ۱۰۰ باشد).")
        exp = int(time.time()) + days * 86400 if days else 0
        try:
            await db.run("INSERT INTO codes(code,kind,value,max_uses,expires,min_price,created) VALUES(?,?,?,?,?,?,?)",
                         code, arg, value, mx, exp, 0 if arg == "gift" else minp, int(time.time()))
        except Exception:
            return await m.answer("این کد قبلاً ساخته شده است؛ کد دیگری انتخاب کن.")
        WAIT.pop(uid, None)
        await m.answer(f"✅ ساخته شد:\n<code>{code}</code>")
        return await codes_page(m)
    elif kind == "a_rptid":
        from . import report
        n = num(text)
        if n is None or n >= 0:
            return await m.answer("ID گروه باید با - شروع شود، مثل <code>-1001234567890</code>.")
        ok, msg = await report.setup_chat(m.bot, n)
        if ok:
            WAIT.pop(uid, None)
        await m.answer(msg)
        if ok:
            return await report_page(m)
        return
    elif kind == "a_bc":
        WAIT.pop(uid, None)
        t = asyncio.create_task(broadcast(m.bot, text, uid))
        _tasks.add(t)
        t.add_done_callback(_tasks.discard)
        return await m.answer("📢 ارسال شروع شد؛ بعد از پایان گزارش می‌دهم.")
    WAIT.pop(uid, None)
    await m.answer("✅ انجام شد.", reply_markup=kb([HOME_BTN]))
