from __future__ import annotations

import time

from aiohttp import web

from . import app as A
from . import pages as P
from . import stats as S

_DONE = [False]


def daily(n=30):
    now, D = int(time.time()), S.D
    b1 = (now + A.TZ) // D
    b0 = b1 - n + 1
    got = {r[0]: r[1] for r in S.rows(
        "SELECT CAST((rated_at+?)/? AS INTEGER) AS b, COUNT(*) FROM ratings WHERE sale_id>0 AND rated=1 AND rated_at>=? GROUP BY b",
        (A.TZ, D, b0 * D - A.TZ))}
    return [{"t": b * D - A.TZ, "v": got.get(b) or 0} for b in range(b0, b1 + 1)]


def payload():
    dist = {r[0]: r[1] for r in S.rows("SELECT stars, COUNT(*) FROM ratings WHERE sale_id>0 AND rated=1 GROUP BY stars")}
    sent = S.one("SELECT COUNT(*) FROM ratings WHERE sale_id>0")
    rated = sum(dist.values())
    ch = [S.donut("توزیع امتیازها", [("%d ستاره" % i, dist.get(i, 0)) for i in (5, 4, 3, 2, 1)], "امتیاز"),
          S.donut("رضایت کلی", [("راضی (۴ و ۵)", dist.get(4, 0) + dist.get(5, 0)), ("متوسط (۳)", dist.get(3, 0)),
                                ("ناراضی (۱ و ۲)", dist.get(1, 0) + dist.get(2, 0))], "امتیاز"),
          S.donut("نرخ پاسخ‌دهی", [("امتیاز داده", rated), ("پاسخ نداده", max(sent - rated, 0))], "نظرسنجی"),
          S.tbars("تعداد امتیاز روزانه (۳۰ روز اخیر)", daily(), S.D, "امتیاز")]
    last = S.rows("SELECT rated_at, user_id, stars, comment FROM ratings WHERE sale_id>0 AND rated=1 "
                  "ORDER BY rated_at DESC LIMIT 15")
    nm = S.names([r[1] for r in last])
    ch.append(S.table("آخرین نظرها", ["زمان", "کاربر", "امتیاز", "نظر"],
                      [[{"t": t}, S.who(nm, u), "⭐" * s, c or "—"] for t, u, s, c in last]))
    return {"charts": ch}


async def page_rt(req):
    r = S.rows("SELECT COUNT(*), AVG(stars) FROM ratings WHERE sale_id>0 AND rated=1")
    n, avg = r[0] if r else (0, None)
    sub = '<div class="sub">میانگین امتیاز: <b>%s</b> از ۵ · %s امتیاز ثبت‌شده</div>' % (
        ("%.2f" % avg) if avg else "—", n)
    return P.page("ratings", "رضایت مشتریان", sub + S.block("ratings"))


def install(app):
    if _DONE[0]:
        return
    _DONE[0] = True
    if not any(n[0] == "ratings" for n in P.NAV):
        P.NAV.insert(5, ("ratings", "/ratings", "رضایت مشتریان", "⭐"))
    S.PAYLOADS["ratings"] = payload
    app.router.add_get("/ratings", page_rt)
