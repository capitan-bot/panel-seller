from __future__ import annotations

import html
import json
import sqlite3
import sys
import time
import traceback
import urllib.error
import urllib.request

from . import app as A

D = 86400
STATE = A.DATA / "rate_state.json"
DDL = ("CREATE TABLE IF NOT EXISTS ratings(id INTEGER PRIMARY KEY AUTOINCREMENT, sale_id INTEGER NOT NULL UNIQUE, "
       "user_id INTEGER NOT NULL, stars INTEGER NOT NULL DEFAULT 0, comment TEXT NOT NULL DEFAULT '', "
       "rated INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL, rated_at INTEGER NOT NULL DEFAULT 0)")


def num(key, d):
    v = A.env(key)
    return int(v) if v.lstrip("-").isdigit() else d


def cfg():
    return {"delay": num("RATE_DELAY_MIN", 10) * 60, "cool": num("RATE_COOLDOWN_H", 24) * 3600,
            "minp": num("RATE_MIN_PRICE", 1), "kinds": {x.strip() for x in A.env("RATE_KINDS").split(",") if x.strip()}}


def load_state():
    try:
        return json.loads(STATE.read_text())
    except Exception:
        return {}


def save_state(s):
    STATE.write_text(json.dumps(s))


def con():
    c = sqlite3.connect(A.db_path(), timeout=15)
    c.execute(DDL)
    c.commit()
    return c


def tg(method, **p):
    req = urllib.request.Request("https://api.telegram.org/bot%s/%s" % (A.env("BOT_TOKEN"), method),
                                 data=json.dumps(p).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"ok": False, "error_code": e.code}
    except Exception as e:
        return {"ok": False, "description": repr(e)}


def text(panel):
    t = "⭐ <b>نظرت درباره‌ی خریدت چیه؟</b>\n\n"
    if panel:
        t += "🖥 پنل: <code>%s</code>\n\n" % html.escape(str(panel))
    return t + "راضی بودی؟ با یک ضربه امتیاز بده؛ نظرت کمک می‌کند بهتر شویم."


def keyboard(sid):
    st = ["danger", "danger", "primary", "success", "success"]
    return {"inline_keyboard": [[{"text": "%d⭐" % (i + 1), "callback_data": "rt:%d:%d" % (sid, i + 1), "style": st[i]}
                                 for i in range(5)]]}


def run_once(dry=False):
    k, now = cfg(), int(time.time())
    c = con()
    st = load_state()
    last = st.get("last")
    top = c.execute("SELECT COALESCE(MAX(id),0) FROM sales").fetchone()[0]
    if last is None:
        print("first run: starting after sale #%s (older customers get no survey)" % top)
        last = top
        if not dry:
            st["last"] = last
            save_state(st)
    rows = c.execute("SELECT id,created,user_id,kind,panel,price FROM sales WHERE id>? ORDER BY id LIMIT 50", (last,)).fetchall()
    sent = 0
    for sid, created, uid, kind, panel, price in rows:
        if created > now - k["delay"]:
            break
        skip = (price or 0) < k["minp"] or (k["kinds"] and kind not in k["kinds"]) or created < now - 3 * D
        if not skip:
            skip = bool(c.execute("SELECT 1 FROM ratings WHERE user_id=? AND sale_id>0 AND created>?",
                                  (uid, now - k["cool"])).fetchone())
        if not skip:
            if dry:
                print("would send: sale #%s | user %s | %s | %s toman" % (sid, uid, kind, price))
                sent += 1
            else:
                c.execute("INSERT OR IGNORE INTO ratings(sale_id,user_id,created) VALUES(?,?,?)", (sid, uid, now))
                c.commit()
                r = tg("sendMessage", chat_id=uid, text=text(panel), parse_mode="HTML", reply_markup=keyboard(sid))
                if r.get("ok"):
                    sent += 1
                else:
                    c.execute("DELETE FROM ratings WHERE sale_id=?", (sid,))
                    c.commit()
                    if r.get("error_code") not in (400, 403):
                        break
                time.sleep(0.3)
        last = sid
    if not dry:
        st["last"] = last
        save_state(st)
    return sent


def main():
    a = sys.argv[1:]
    if a[:1] == ["dry"]:
        c = con()
        print("settings:", cfg())
        print("kinds in sales:", c.execute("SELECT kind, COUNT(*), COALESCE(SUM(price),0) FROM sales GROUP BY kind").fetchall())
        print("total:", run_once(dry=True))
        return
    if a[:1] == ["test"]:
        c = con()
        uid, sid = sorted(A.admin_ids())[0], -int(time.time())
        c.execute("INSERT OR IGNORE INTO ratings(sale_id,user_id,created) VALUES(?,?,?)", (sid, uid, int(time.time())))
        c.commit()
        r = tg("sendMessage", chat_id=uid, text=text("sample_panel"), parse_mode="HTML", reply_markup=keyboard(sid))
        print("sent" if r.get("ok") else r)
        return
    print("rating survey sender running | settings:", cfg(), flush=True)
    while True:
        try:
            if A.env("RATE_ON") != "0":
                n = run_once()
                if n:
                    print("sent", n, flush=True)
        except Exception:
            traceback.print_exc()
        time.sleep(60)


if __name__ == "__main__":
    main()
