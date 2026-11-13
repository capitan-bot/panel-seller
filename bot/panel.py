"""PasarGuard client: admin login + the admin (reseller) endpoints only.

The admin endpoints below follow the PasarGuard/Marzban layout but were NOT verified against a live
panel. Use the admin menu: "اتصال پنل" -> "تست اتصال و ساختار" to print the real endpoints/fields.
"""
from __future__ import annotations

import asyncio
import re
import secrets
import string

import httpx

from . import config, db

TIMEOUT = httpx.Timeout(20.0, connect=10.0)


class PanelError(Exception):
    pass


class PanelTaken(PanelError):
    pass


def gen_username() -> str:
    return "rs" + "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(7))


def gen_password(n: int = 16) -> str:
    """PasarGuard rules: >=2 digits (and usually >=2 upper/lower + a symbol). We always give 3 digits,
    3 upper, 3 lower and 2 safe symbols, the rest random."""
    sets = [(string.ascii_lowercase, 3), (string.ascii_uppercase, 3), (string.digits, 3), ("@#%+=-_", 2)]
    pw = [secrets.choice(s) for s, k in sets for _ in range(k)]
    pool = string.ascii_letters + string.digits
    pw += [secrets.choice(pool) for _ in range(max(0, n - len(pw)))]
    secrets.SystemRandom().shuffle(pw)
    return "".join(pw)


def _detail(r: httpx.Response) -> str:
    try:
        j = r.json()
        d = j.get("detail", j) if isinstance(j, dict) else j
        return (d if isinstance(d, str) else str(d))[:300]
    except Exception:
        return (r.text or f"HTTP {r.status_code}")[:300]


class PG:
    def __init__(self, url: str, username: str, password: str, verify: bool = True, transport=None):
        self.base = url.strip().rstrip("/")
        self.username, self.password = username, password
        self.verify, self.transport = verify, transport
        self.token: str | None = None
        self._spec: dict | None = None
        self._role = None

    async def _login(self, c: httpx.AsyncClient) -> None:
        try:
            r = await c.post(self.base + "/api/admin/token", data={
                "username": self.username, "password": self.password, "grant_type": "password"})
        except httpx.HTTPError as e:
            raise PanelError(f"اتصال به پنل ممکن نشد ({type(e).__name__})")
        if r.status_code >= 400:
            raise PanelError(f"ورود به پنل ناموفق بود: {_detail(r)}")
        try:
            self.token = r.json()["access_token"]
        except Exception:
            raise PanelError("پنل توکن ورود نداد؛ آدرس پنل را بررسی کن.")

    async def call(self, method: str, path: str, **kw) -> httpx.Response:
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=self.verify, transport=self.transport) as c:
            r = None
            for attempt in (0, 1):
                if not self.token:
                    await self._login(c)
                try:
                    r = await c.request(method, self.base + path, headers={
                        "Authorization": f"Bearer {self.token}", "Accept": "application/json"}, **kw)
                except httpx.HTTPError as e:
                    raise PanelError(f"اتصال به پنل ممکن نشد ({type(e).__name__})")
                if r.status_code == 401 and attempt == 0:
                    self.token = None
                    continue
                break
            return r

    @staticmethod
    def _ok(r: httpx.Response) -> None:
        if r.status_code >= 400:
            raise PanelError(f"HTTP {r.status_code}: {_detail(r)}")

    async def test(self) -> int:
        r = await self.call("GET", "/api/admins")
        self._ok(r)
        j = r.json()
        items = j.get("admins", []) if isinstance(j, dict) else j
        return len(items or [])

    # ---- live schema (openapi.json of the real panel) ----
    async def _openapi(self) -> dict:
        if self._spec is None:
            spec: dict = {}
            try:
                r = await self.call("GET", "/openapi.json")
                if r.status_code == 200 and isinstance(r.json(), dict):
                    spec = r.json()
            except (PanelError, ValueError):
                pass
            self._spec = spec
        return self._spec

    async def _schema(self, name: str) -> dict | None:
        s = (await self._openapi()).get("components", {}).get("schemas", {}).get(name)
        return s if isinstance(s, dict) else None

    async def _body(self, schema: str, data: dict) -> dict:
        """Drops `is_sudo` when this panel version no longer has it (roles replaced it)."""
        s = await self._schema(schema)
        if s is not None and "is_sudo" not in s.get("properties", {}):
            data = {k: v for k, v in data.items() if k != "is_sudo"}
        return data

    async def list_roles(self) -> list[dict]:
        """Roles as [{'id','name','n'}]. 1) roles endpoint (path from openapi.json, then guesses);
        2) fallback: the roles already used by existing non-owner admins (n = how many admins use it)."""
        spec = await self._openapi()
        found = [p for p, m in spec.get("paths", {}).items()
                 if "role" in p.lower() and "{" not in p and isinstance(m, dict) and "get" in m]
        for path in found + [c for c in ("/api/roles", "/api/role", "/api/admin/roles") if c not in found]:
            try:
                r = await self.call("GET", path)
                j = r.json() if r.status_code == 200 else None
            except (PanelError, ValueError):
                continue
            if isinstance(j, dict):
                j = next((v for v in j.values() if isinstance(v, list)), [])
            out = [{"id": it["id"], "name": str(it.get("name") or it.get("title") or ""), "n": 0}
                   for it in (j if isinstance(j, list) else []) if isinstance(it, dict) and it.get("id") is not None]
            if out:
                return out
        try:
            r = await self.call("GET", "/api/admins")
            j = r.json() if r.status_code == 200 else []
        except (PanelError, ValueError):
            return []
        items = j.get("admins", []) if isinstance(j, dict) else j
        seen: dict = {}
        for it in items or []:
            if not isinstance(it, dict) or it.get("is_owner") or it.get("is_sudo"):
                continue
            role = it.get("role")
            rid = it.get("role_id", role.get("id") if isinstance(role, dict) else None)
            if rid is None:
                continue
            name = role.get("name") if isinstance(role, dict) else (role if isinstance(role, str) else "")
            e = seen.setdefault(rid, {"id": rid, "name": "", "n": 0})
            e["n"] += 1
            if name:
                e["name"] = str(name)
        return sorted(seen.values(), key=lambda e: -e["n"])

    async def operator_role_id(self):
        """The id of the `operator` role (cached). Falls back to the role most used by existing admins."""
        if self._role is None:
            roles = await self.list_roles()
            hit = ([r for r in roles if r["name"].lower() == "operator"]
                   or [r for r in roles if "operator" in r["name"].lower()]
                   or [r for r in roles if r["n"]])
            if not hit:
                raise PanelError("نقش «operator» در پنل پیدا نشد؛ «🧪 تست اتصال و ساختار» را بزن و متنش را بفرست.")
            self._role = hit[0]["id"]
        return self._role

    async def create_admin(self, username: str, password: str, role_id=None, gb=None) -> None:
        data = {"username": username, "password": password, "is_sudo": False}
        s = await self._schema("AdminCreate")
        if gb:
            props = (s or {}).get("properties", {})
            field = next((k for k in ("data_limit", "traffic_limit") if k in props), None) or ("data_limit" if s is None else None)
            if not field:
                raise PanelError("پنل فیلد حجم ادمین (data_limit) ندارد؛ «🧪 تست اتصال و ساختار» را بزن و متنش را بفرست.")
            data[field] = int(float(gb) * 1024 ** 3)
        if role_id not in (None, ""):
            data["role_id"] = int(role_id) if str(role_id).isdigit() else role_id
        elif s is None:
            try:                                  # openapi unreadable: try, but old panels without roles still work
                data["role_id"] = await self.operator_role_id()
            except PanelError:
                pass
        elif "role_id" in s.get("properties", {}):
            data["role_id"] = await self.operator_role_id()
        r = await self.call("POST", "/api/admin", json=await self._body("AdminCreate", data))
        if r.status_code == 409 or (r.status_code in (400, 422) and re.search(
                r"already|exist|taken|duplicate", _detail(r), re.I)):
            raise PanelTaken(username)
        self._ok(r)

    async def set_disabled(self, username: str, disabled: bool) -> None:
        r = await self.call("PUT", f"/api/admin/{username}",
                            json=await self._body("AdminModify", {"is_disabled": disabled, "is_sudo": False}))
        self._ok(r)

    async def set_password(self, username: str, password: str) -> None:
        r = await self.call("PUT", f"/api/admin/{username}",
                            json=await self._body("AdminModify", {"password": password, "is_sudo": False}))
        self._ok(r)

    async def admin_info(self, username: str):
        """Live admin data: {disabled, limit, used, users} (GB / counts; None = unknown). None if the admin is missing."""
        r = await self.call("GET", f"/api/admin/{username}")
        j = r.json() if r.status_code == 200 else None
        if not isinstance(j, dict):
            if r.status_code == 404:
                return None
            lr = await self.call("GET", "/api/admins")
            lj = lr.json() if lr.status_code == 200 else []
            its = lj.get("admins", []) if isinstance(lj, dict) else lj
            j = next((i for i in its or [] if isinstance(i, dict) and i.get("username") == username), None)
            if j is None:
                return None
        def gbv(*keys):
            for k in keys:
                if isinstance(j.get(k), (int, float)):
                    return j[k] / 1024 ** 3
            return None
        users = next((j[k] for k in ("users_count", "total_users", "users_number") if isinstance(j.get(k), int)), None)
        if users is None:
            try:
                ur = await self.call("GET", "/api/users", params={"admin": username, "limit": 1})
                uj = ur.json() if ur.status_code == 200 else None
                if isinstance(uj, dict):
                    users = uj.get("total", uj.get("count"))
            except Exception:
                pass
        return {"disabled": bool(j.get("is_disabled")), "limit": gbv("data_limit", "traffic_limit"),
                "used": gbv("used_traffic"), "users": users}

    async def set_username(self, old: str, new: str, password: str) -> None:
        """Renames the admin login. PasarGuard has no rename on some versions: then it is only possible for an
        empty admin (no users, no usage) by recreating it with the same volume and password."""
        s = await self._schema("AdminModify")
        if s and "username" in s.get("properties", {}):
            r = await self.call("PUT", f"/api/admin/{old}", json=await self._body("AdminModify", {"username": new, "is_sudo": False}))
            self._ok(r)
            if await self.admin_info(new) is None:
                raise PanelError("پنل نام کاربری را عوض نکرد.")
            return
        i = await self.admin_info(old)
        if i is None:
            raise PanelError("این ادمین در پنل پیدا نشد.")
        if i["users"] != 0 or (i["used"] or 0) > 0.01:
            raise PanelError("این نسخهٔ پاسارگارد تغییر نام کاربری را پشتیبانی نمی‌کند و سرویس شما کاربر/مصرف دارد؛ "
                             "برای تغییر، به مدیر پیام بده.")
        await self.create_admin(new, password, gb=i["limit"] or None)
        await self.delete_admin(old)

    async def user_counts(self, username: str) -> dict:
        """Users inside this admin: total / active / limited (volume finished) / expired / disabled (None = unknown)."""
        keys = ("total", "active", "limited", "expired", "disabled")

        async def one(st):
            params = {"admin": username, "limit": 1}
            if st:
                params["status"] = st
            r = await self.call("GET", "/api/users", params=params)
            j = r.json() if r.status_code == 200 else None
            return j.get("total", j.get("count")) if isinstance(j, dict) else None
        res = await asyncio.gather(*[one(None if k == "total" else k) for k in keys], return_exceptions=True)
        return {k: (v if isinstance(v, int) else None) for k, v in zip(keys, res)}

    async def set_limit(self, username: str, gb: float) -> None:
        s = await self._schema("AdminModify")
        props = (s or {}).get("properties", {})
        field = next((k for k in ("data_limit", "traffic_limit") if k in props), None) or ("data_limit" if s is None else None)
        if not field:
            raise PanelError("پنل فیلد حجم ادمین (data_limit) ندارد.")
        r = await self.call("PUT", f"/api/admin/{username}",
                            json=await self._body("AdminModify", {field: int(float(gb) * 1024 ** 3), "is_sudo": False}))
        self._ok(r)

    async def admins_usage(self) -> dict:
        """{username: (limit_gb, used_gb)} from one /api/admins call (empty if the panel does not expose it)."""
        try:
            r = await self.call("GET", "/api/admins")
            j = r.json() if r.status_code == 200 else []
        except (PanelError, ValueError):
            return {}
        out = {}
        for it in (j.get("admins", []) if isinstance(j, dict) else j) or []:
            if isinstance(it, dict) and isinstance(it.get("used_traffic"), (int, float)):
                lim = it.get("data_limit") if isinstance(it.get("data_limit"), (int, float)) else it.get("traffic_limit")
                if isinstance(lim, (int, float)):
                    out[it.get("username")] = (lim / 1024 ** 3, it["used_traffic"] / 1024 ** 3)
        return out

    async def system_stats(self) -> dict:
        r = await self.call("GET", "/api/system")
        try:
            j = r.json() if r.status_code == 200 else {}
        except ValueError:
            j = {}
        return j if isinstance(j, dict) else {}

    async def nodes(self) -> list:
        r = await self.call("GET", "/api/nodes")
        try:
            j = r.json() if r.status_code == 200 else []
        except ValueError:
            j = []
        if isinstance(j, dict):
            j = next((v for v in j.values() if isinstance(v, list)), [])
        return [x for x in j if isinstance(x, dict)]

    async def admins_full(self) -> list:
        r = await self.call("GET", "/api/admins")
        self._ok(r)
        j = r.json()
        out = []
        for it in (j.get("admins", []) if isinstance(j, dict) else j) or []:
            if not isinstance(it, dict):
                continue
            lim = it.get("data_limit") if isinstance(it.get("data_limit"), (int, float)) else it.get("traffic_limit")
            used = it.get("used_traffic")
            out.append({"username": str(it.get("username", "")), "owner": bool(it.get("is_owner") or it.get("is_sudo")),
                        "limit": lim / 1024 ** 3 if isinstance(lim, (int, float)) and lim else None,
                        "used": used / 1024 ** 3 if isinstance(used, (int, float)) else None,
                        "disabled": bool(it.get("is_disabled"))})
        return out

    async def delete_admin(self, username: str) -> None:
        r = await self.call("DELETE", f"/api/admin/{username}")
        if r.status_code != 404:
            self._ok(r)

    async def schema_report(self) -> str:
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=self.verify, transport=self.transport) as c:
            try:
                r = await c.get(self.base + "/openapi.json")
            except httpx.HTTPError as e:
                return f"openapi.json در دسترس نیست ({type(e).__name__})."
        if r.status_code != 200:
            return f"openapi.json در دسترس نیست (HTTP {r.status_code})."
        try:
            d = r.json()
        except ValueError:
            return "openapi.json قابل خواندن نیست."
        lines = [f"{','.join(k.upper() for k in m)} {p}" for p, m in d.get("paths", {}).items() if "/admin" in p]
        sch = d.get("components", {}).get("schemas", {})
        for n in ("AdminCreate", "AdminModify"):
            if n in sch:
                lines.append(f"{n}: {', '.join(sch[n].get('properties', {}))}")
                if sch[n].get("required"):
                    lines.append(f"  required: {', '.join(sch[n]['required'])}")
        lines += [f"{','.join(k.upper() for k in m)} {p}" for p, m in d.get("paths", {}).items()
                  if "role" in p.lower() and "/admin" not in p]
        try:
            roles = await self.list_roles()
            lines.append("نقش‌ها: " + (", ".join(f"{r['id']}={r['name'] or '?'}" for r in roles) or "خوانده نشد"))
            rr = await self.call("GET", "/api/admins")
            jj = rr.json()
            its = jj.get("admins", []) if isinstance(jj, dict) else jj
            if its and isinstance(its[0], dict):
                lines.append("فیلدهای ادمین: " + ", ".join(its[0]))
        except Exception:
            pass
        return "\n".join(lines)[:3500] or "endpointهای ادمین پیدا نشد."


_cache: dict = {}


async def get_server(sid=None):
    """Server row by id; sid 0/None = the default server."""
    r = None
    if sid:
        r = await db.row("SELECT * FROM servers WHERE id=?", int(sid))
        if r is None:
            raise PanelError("پنلِ این سرویس از ربات حذف شده است.")
    else:
        r = await db.row("SELECT * FROM servers ORDER BY is_default DESC, id LIMIT 1")
    if r is None:
        raise PanelError("پنل پاسارگارد هنوز به ربات متصل نشده است.")
    return r


async def get_pg(sid=None) -> PG:
    r = await get_server(sid)
    key = (r["url"], r["username"], r["password"])
    hit = _cache.get(r["id"])
    if hit is None or hit[0] != key:
        pg = PG(r["url"], r["username"], db.dec(r["password"]), config.VERIFY_SSL)
        pg.sid = r["id"]
        _cache[r["id"]] = (key, pg)
        return pg
    return hit[1]
