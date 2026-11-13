import asyncio
import json
import re

import httpx
from cryptography.fernet import Fernet

from bot import config, db
from bot.panel import PG, PanelError, PanelTaken, gen_password, gen_username
from bot.ui import btn, main_menu, num

config.ENCRYPTION_KEY = Fernet.generate_key().decode()


def run(coro):
    return asyncio.run(coro)


def test_password_rules():
    for _ in range(200):
        pw = gen_password()
        assert len(pw) >= 12
        assert re.search(r"[a-z]", pw) and re.search(r"[A-Z]", pw) and re.search(r"\d", pw) and re.search(r"[@#%+=\-_]", pw)
    assert re.fullmatch(r"rs[a-z0-9]{7}", gen_username())


def test_num_persian_digits():
    assert num("۵۰٬۰۰۰".replace("٬", "")) == 50000
    assert num("1,000") == 1000
    assert num("abc") is None


def test_button_serialization():
    d = btn("x", "d", "5368324170671202286", "success")
    assert d == {"text": "x", "callback_data": "d", "icon_custom_emoji_id": "5368324170671202286", "style": "success"}
    assert "style" not in btn("x", "d") and "icon_custom_emoji_id" not in btn("x", "d")


def test_db_wallet_and_menu():
    async def go():
        await db.init(":memory:")
        await db.touch_user(1, "a")
        await db.credit(1, 1000)
        assert await db.debit(1, 600) is True
        assert await db.debit(1, 600) is False            # not enough: must not go negative
        assert (await db.row("SELECT balance FROM users WHERE tg_id=1"))["balance"] == 400
        res = await asyncio.gather(*[db.debit(1, 300) for _ in range(5)])
        assert sum(res) == 1                               # only one of five concurrent debits fits
        m = await main_menu()
        assert sum(len(r) for r in m["inline_keyboard"]) == 7
        await db.run("UPDATE buttons SET enabled=0 WHERE key='faq'")
        assert sum(len(r) for r in (await main_menu(True))["inline_keyboard"]) == 7  # 6 + admin button
        await db.set_setting("k", "v")
        assert await db.get_setting("k") == "v"
        assert db.dec(db.enc("secret")) == "secret"
        await db.close()
    run(go())


def make_transport(state):
    def handler(req: httpx.Request):
        state["calls"].append((req.method, req.url.path))
        if req.url.path == "/api/admin/token":
            state["logins"] += 1
            return httpx.Response(200, json={"access_token": f"t{state['logins']}"})
        if req.headers.get("authorization") == "Bearer t1" and state.get("expire_first"):
            state["expire_first"] = False
            return httpx.Response(401, json={"detail": "expired"})
        if req.url.path == "/api/admins":
            return httpx.Response(200, json=[{"username": "a"}])
        if req.method == "POST" and req.url.path == "/api/admin":
            body = json.loads(req.content)
            assert body["is_sudo"] is False
            if body["username"] == "taken":
                return httpx.Response(409, json={"detail": "Admin already exists"})
            return httpx.Response(200, json={})
        if req.method in ("PUT", "DELETE"):
            return httpx.Response(404 if "ghost" in req.url.path else 200, json={})
        return httpx.Response(404)
    return httpx.MockTransport(handler)


def test_panel_client():
    async def go():
        st = {"calls": [], "logins": 0}
        pg = PG("https://p.example.com:8000/", "root", "pw", transport=make_transport(st))
        assert pg.base == "https://p.example.com:8000"
        assert await pg.test() == 1
        await pg.create_admin("rsabc", "Pw1@xxxxxxxxxx")
        try:
            await pg.create_admin("taken", "x")
            raise AssertionError("should raise")
        except PanelTaken:
            pass
        await pg.set_disabled("rsabc", True)
        await pg.delete_admin("ghost")                      # 404 on delete is fine
        assert st["logins"] == 1                            # token reused
        st2 = {"calls": [], "logins": 0, "expire_first": True}
        pg2 = PG("https://p.example.com", "root", "pw", transport=make_transport(st2))
        assert await pg2.test() == 1 and st2["logins"] == 2  # re-login after 401
        bad = PG("https://p.example.com", "root", "pw", transport=httpx.MockTransport(lambda r: httpx.Response(401, json={"detail": "bad"})))
        try:
            await bad.test()
            raise AssertionError("should raise")
        except PanelError as e:
            assert "ورود" in str(e)
    run(go())
