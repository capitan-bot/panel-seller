from __future__ import annotations

import asyncio
import hashlib
import hmac
import ipaddress
import json
import os
import re
import sys
import time
from pathlib import Path

import aiohttp
from aiohttp import web

ROOT = Path(__file__).resolve().parent
DB = ROOT / "gw.json"
BRAND = os.environ.get("GW_BRAND", "capitan")
DOMAIN = os.environ.get("GW_DOMAIN", "web.aligater.ir")
INVITE = os.environ.get("GW_INVITE", "")
MAX = int(os.environ.get("GW_MAX", "300"))
USER_RE = re.compile(r"^[a-z0-9_]{5,32}$")
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailers", "transfer-encoding",
       "upgrade", "content-length", "content-encoding", "host", "accept-encoding", "x-gw-token", "x-forwarded-for",
       "x-forwarded-proto", "x-forwarded-host", "x-real-ip", "forwarded"}
LOCK = asyncio.Lock()
HITS: dict = {}
SESS: aiohttp.ClientSession | None = None


def load() -> dict:
    try:
        return json.loads(DB.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save(d: dict) -> None:
    tmp = DB.with_suffix(".tmp")
    tmp.write_text(json.dumps(d), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, DB)


def real_ip(req) -> str:
    if req.remote in ("127.0.0.1", "::1"):
        xf = req.headers.get("X-Forwarded-For", "").split(",")[-1].strip()
        if xf:
            return xf
    return req.remote or ""


def err(status: int, msg: str):
    return web.json_response({"ok": False, "error": msg}, status=status)


def hp(ip: str, port) -> str:
    return f"[{ip}]:{port}" if ":" in ip else f"{ip}:{port}"


def pin(fp: str):
    return aiohttp.Fingerprint(bytes.fromhex(fp))


async def ping(ip: str, port: int, fp: str, tok: str) -> bool:
    try:
        async with SESS.get(f"https://{hp(ip, port)}/__gw/ping", headers={"X-GW-Token": tok}, ssl=pin(fp),
                            timeout=aiohttp.ClientTimeout(total=12)) as r:
            j = await r.json(content_type=None)
            return r.status == 200 and j.get("id") == hashlib.sha256(tok.encode()).hexdigest()
    except Exception:
        return False


async def register(req):
    ip, now = real_ip(req), time.time()
    HITS[ip] = [t for t in HITS.get(ip, []) if now - t < 3600]
    if len(HITS[ip]) >= 8:
        return err(429, "too many attempts, try later")
    HITS[ip].append(now)
    try:
        d = await req.json()
        u = str(d.get("username", "")).lower().lstrip("@")
        port, tok = int(d.get("port", 0)), str(d.get("token", ""))
        fp = str(d.get("fp", "")).lower().replace(":", "")
    except Exception:
        return err(400, "bad request")
    if INVITE and not hmac.compare_digest(str(d.get("invite", "")), INVITE):
        return err(403, "invite code required")
    if not USER_RE.match(u) or not (1024 <= port <= 65535) or len(tok) < 24 or not re.fullmatch(r"[0-9a-f]{64}", fp):
        return err(400, "invalid fields")
    try:
        if not ipaddress.ip_address(ip).is_global:
            return err(400, "address not allowed")
    except ValueError:
        return err(400, "bad address")
    th = hashlib.sha256(tok.encode()).hexdigest()
    cur = load().get(u)
    if cur and cur["th"] != th:
        return err(409, "username already registered by another server")
    if not cur and len(load()) >= MAX:
        return err(503, "registry is full")
    if not await ping(ip, port, fp, tok):
        return err(400, "could not reach your panel on %s; open that port to this gateway and retry" % hp(ip, port))
    async with LOCK:
        db = load()
        db[u] = {"ip": ip, "port": port, "fp": fp, "th": th, "tok": tok, "created": int(now)}
        save(db)
    return web.json_response({"ok": True, "url": f"https://{DOMAIN}/{BRAND}/{u}/panel/"})


async def proxy(req):
    u = req.match_info["user"].lower()
    e = load().get(u)
    if not e:
        return web.Response(status=404, text="پنل پیدا نشد.", content_type="text/plain", charset="utf-8")
    h = {k: v for k, v in req.headers.items() if k.lower() not in HOP}
    h.update({"Host": req.host, "X-GW-Token": e["tok"], "X-Forwarded-For": real_ip(req), "X-Forwarded-Proto": "https"})
    return await relay(req, e, h)


async def relay(req, e, h):
    body = await req.read()
    try:
        async with SESS.request(req.method, f"https://{hp(e['ip'], e['port'])}{req.raw_path}", headers=h, data=body or None,
                                allow_redirects=False, ssl=pin(e["fp"])) as r:
            data = await r.read()
            resp = web.Response(status=r.status, body=data)
            for k, v in r.headers.items():
                if k.lower() not in HOP and k.lower() not in ("set-cookie", "server", "date"):
                    resp.headers[k] = v
            for c in r.headers.getall("Set-Cookie", []):
                resp.headers.add("Set-Cookie", c)
            return resp
    except Exception:
        return web.Response(status=502, text="پنل در دسترس نیست (سرور کاربر خاموش است یا پورت بسته است).",
                            content_type="text/plain", charset="utf-8")


async def health(req):
    return web.json_response({"ok": True, "panels": len(load())})


async def on_start(app):
    global SESS
    SESS = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=60))


async def on_stop(app):
    await SESS.close()


def cli() -> bool:
    a = sys.argv[1:]
    if a[:1] == ["list"]:
        for k, v in load().items():
            print(k, v["ip"], v["port"], time.strftime("%F", time.localtime(v["created"])))
        return True
    if a[:1] == ["del"] and len(a) > 1:
        d = load()
        print("deleted" if d.pop(a[1].lower().lstrip("@"), None) else "not found")
        save(d)
        return True
    return False


def main():
    if cli():
        return
    app = web.Application(client_max_size=8 * 1024 * 1024)
    app.router.add_post("/gw/register", register)
    app.router.add_get("/gw/health", health)
    app.router.add_route("*", "/%s/{user:[A-Za-z0-9_]+}/panel" % BRAND, proxy)
    app.router.add_route("*", "/%s/{user:[A-Za-z0-9_]+}/panel/{tail:.*}" % BRAND, proxy)
    app.on_startup.append(on_start)
    app.on_cleanup.append(on_stop)
    web.run_app(app, host="127.0.0.1", port=8790, access_log=None, print=None)


if __name__ == "__main__":
    main()
