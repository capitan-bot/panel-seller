"""End-to-end smoke test: updates go through Dispatcher -> handlers with a fake Telegram and a fake panel."""
import asyncio

import httpx
from cryptography.fernet import Fernet

from bot import admin, config, db, main as botmain, user
from bot.panel import PG
from bot.tg import Bot, Dispatcher

config.ENCRYPTION_KEY = Fernet.generate_key().decode()
config.ADMIN_IDS.clear(); config.ADMIN_IDS.add(100)


class FakeBot(Bot):
    def __init__(self):
        self.calls = []
    async def api(self, method, **params):
        params = {k: v for k, v in params.items() if v is not None}
        self.calls.append((method, params))
        return {"message_id": len(self.calls), "chat": {"id": 1}, "date": 0}
    def texts(self):
        return [p.get("text") or p.get("caption") or "" for _, p in self.calls]


def panel_transport(log):
    def h(req):
        log.append((req.method, req.url.path))
        if req.url.path == "/api/admin/token":
            return httpx.Response(200, json={"access_token": "t"})
        return httpx.Response(200, json=[])
    return httpx.MockTransport(h)


def user_d(uid): return {"id": uid, "is_bot": False, "first_name": f"U{uid}"}
def msg(uid, text=None, photo=False):
    d = {"message_id": 5, "date": 0, "chat": {"id": uid}, "from": user_d(uid)}
    if text: d["text"] = text
    if photo: d["photo"] = [{"file_id": "F"}]
    return {"message": d}
def cb(uid, data):
    return {"callback_query": {"id": "1", "from": user_d(uid), "data": data,
                               "message": {"message_id": 9, "date": 0, "chat": {"id": uid}, "text": "x"}}}


def test_full_flow():
    async def go():
        await db.init(":memory:")
        bot = FakeBot()
        dp = Dispatcher(botmain.gate); dp.include(admin.router); dp.include(user.router)
        plog = []
        pg = PG("https://p.example.com", "root", "pw", transport=panel_transport(plog))
        async def fake_get_pg(): return pg
        user.get_pg = fake_get_pg; admin.get_pg = fake_get_pg
        n = 0
        async def send(u):
            nonlocal n; n += 1
            await dp.feed(bot, {"update_id": n, **u})

        await send(msg(7, "/start"))
        assert any("خوش آمدی" in t for t in bot.texts())
        menu = [p for m, p in bot.calls if m == "sendMessage"][-1]["reply_markup"]["inline_keyboard"]
        assert sum(len(r) for r in menu) == 7
        await send(cb(7, "u:buy"))
        assert any("پلنی" in t for t in bot.texts())

        await send(msg(100, "/admin")); await send(cb(100, "a:pla")); await send(msg(100, "نمایندگی ماهانه|500000|30"))
        assert (await db.row("SELECT * FROM plans"))["price"] == 500000
        await send(cb(100, "a:set")); await send(cb(100, "a:sv:test_days")); await send(msg(100, "2"))
        assert await db.get_setting("test_days") == "2"

        await send(cb(100, "a:bt:buy")); await send(cb(100, "a:bcl:buy"))
        assert (await db.row("SELECT style FROM buttons WHERE key='buy'"))["style"] == "danger"
        await send(cb(100, "a:bup:wallet"))
        assert (await db.row("SELECT sort FROM buttons WHERE key='wallet'"))["sort"] == 4
        # premium emoji: admin sends a custom emoji entity
        await send(cb(100, "a:bem:faq"))
        await send({"message": {**msg(100, "x")["message"], "entities": [{"type": "custom_emoji", "offset": 0, "length": 1, "custom_emoji_id": "5368324170671202286"}]}})
        assert (await db.row("SELECT emoji_id FROM buttons WHERE key='faq'"))["emoji_id"] == "5368324170671202286"
        bot.calls.clear(); await send(msg(7, "/start"))
        menu = bot.calls[-1][1]["reply_markup"]["inline_keyboard"]
        flat = [b for r in menu for b in r]
        assert any(b.get("icon_custom_emoji_id") == "5368324170671202286" for b in flat)   # shows up on the user's button
        assert any(b.get("style") == "danger" for b in flat)

        await send(cb(7, "u:buy2:1"))
        assert (await db.row("SELECT COUNT(*) c FROM panels"))["c"] == 0                  # no balance, nothing created

        await send(cb(7, "u:charge")); await send(msg(7, "۵۰۰۰۰۰"))                         # card not set yet
        await db.set_setting("card", "6037000000000000")
        await send(cb(7, "u:charge")); await send(msg(7, "500000")); await send(msg(7, photo=True))
        rid = (await db.row("SELECT id FROM receipts"))["id"]
        await send(cb(100, f"a:rc:ok:{rid}")); await send(cb(100, f"a:rc:ok:{rid}"))     # double approve
        assert (await db.row("SELECT balance FROM users WHERE tg_id=7"))["balance"] == 500000

        await send(cb(7, "u:buy2:1"))
        p = await db.row("SELECT * FROM panels")
        assert p and p["status"] == "active" and (await db.row("SELECT balance FROM users WHERE tg_id=7"))["balance"] == 0
        assert ("POST", "/api/admin") in plog
        assert any("رمز" in t and "dashboard" in t for t in bot.texts())

        await send(cb(7, "u:test")); await send(cb(7, "u:test"))
        assert (await db.row("SELECT COUNT(*) c FROM panels WHERE is_test=1"))["c"] == 1

        await send(cb(100, f"a:spt:{p['id']}"))
        assert (await db.row("SELECT status FROM panels WHERE id=?", p["id"]))["status"] == "suspended"
        await send(cb(100, f"a:spt:{p['id']}"))
        assert (await db.row("SELECT status FROM panels WHERE id=?", p["id"]))["status"] == "active"

        await send(cb(7, "a:home"))                                                       # non-admin can't open admin
        assert not any("پنل مدیریت" in t for t in bot.texts()[-2:])
        await db.run("UPDATE users SET blocked=1 WHERE tg_id=7")
        before = len(bot.calls); await send(msg(7, "/start")); assert len(bot.calls) == before
        await db.close()
    asyncio.run(go())
