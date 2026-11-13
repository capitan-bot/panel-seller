from __future__ import annotations

import os
import time

import aiosqlite
from cryptography.fernet import Fernet

from . import config

_db: aiosqlite.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS buttons(
  key TEXT PRIMARY KEY, title TEXT NOT NULL, emoji_id TEXT NOT NULL DEFAULT '',
  style TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS users(
  tg_id INTEGER PRIMARY KEY, name TEXT, balance INTEGER NOT NULL DEFAULT 0,
  blocked INTEGER NOT NULL DEFAULT 0, test_used INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS plans(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, price INTEGER NOT NULL,
  days INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS panels(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, plan_id INTEGER,
  admin_username TEXT NOT NULL UNIQUE, expires INTEGER NOT NULL,
  status TEXT NOT NULL DEFAULT 'active', is_test INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS products(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, descr TEXT NOT NULL DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1, sort INTEGER NOT NULL DEFAULT 0,
  price_gb INTEGER NOT NULL DEFAULT 0, min_gb INTEGER NOT NULL DEFAULT 250, max_gb INTEGER NOT NULL DEFAULT 10240);
CREATE TABLE IF NOT EXISTS packages(
  id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER NOT NULL, gb INTEGER NOT NULL,
  price INTEGER NOT NULL, active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS ubtn(
  key TEXT PRIMARY KEY, title TEXT NOT NULL DEFAULT '', emoji_id TEXT NOT NULL DEFAULT '', style TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS sales(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, panel TEXT NOT NULL DEFAULT '', kind TEXT NOT NULL,
  gb REAL NOT NULL DEFAULT 0, price INTEGER NOT NULL DEFAULT 0, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS events(
  id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL, kind TEXT NOT NULL, user_id INTEGER NOT NULL DEFAULT 0,
  arg TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS staff(tg_id INTEGER PRIMARY KEY, role TEXT NOT NULL, added INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS codes(
  id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, value INTEGER NOT NULL,
  max_uses INTEGER NOT NULL DEFAULT 0, used INTEGER NOT NULL DEFAULT 0, expires INTEGER NOT NULL DEFAULT 0,
  min_price INTEGER NOT NULL DEFAULT 0, active INTEGER NOT NULL DEFAULT 1, created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS code_uses(code_id INTEGER NOT NULL, user_id INTEGER NOT NULL, ts INTEGER NOT NULL,
  PRIMARY KEY(code_id, user_id));
CREATE TABLE IF NOT EXISTS receipts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, amount INTEGER NOT NULL,
  file_id TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', created INTEGER NOT NULL);
"""

DEFAULT_BUTTONS = [
    ("buy", "خرید پنل", "success"),
    ("account", "حساب کاربری", ""),
    ("test", "تست پنل", ""),
    ("faq", "سوالات متداول", ""),
    ("panels", "پنل‌های من", ""),
    ("wallet", "کیف پول", "primary"),
    ("support", "پشتیبانی", ""),
]

DEFAULT_SETTINGS = {
    "shop": "فروشگاه پنل",
    "welcome": "🌟 {name} عزیز، به {shop} خوش آمدی!\nیکی از گزینه‌های زیر را انتخاب کن.",
    "faq": "هنوز متنی برای سوالات متداول ثبت نشده است.",
    "support": "هنوز آیدی پشتیبانی ثبت نشده است.",
    "card": "",
    "holder": "",
    "test_days": "0",
    "test_gb": "0",
    "warn_on": "1",
    "min_charge": "10000",
}


def now() -> int:
    return int(time.time())


async def init(path: str | None = None) -> None:
    global _db
    path = path or config.DB_PATH
    if path != ":memory:":
        os.makedirs(os.path.dirname(path), exist_ok=True)
    _db = await aiosqlite.connect(path)
    _db.row_factory = aiosqlite.Row
    await _db.execute("PRAGMA journal_mode=WAL")
    await _db.executescript(SCHEMA)
    have = {r["name"] for r in await rows("PRAGMA table_info(panels)")}
    if "product_id" not in have:
        await _db.execute("ALTER TABLE panels ADD COLUMN product_id INTEGER")
    if "gb" not in have:
        await _db.execute("ALTER TABLE panels ADD COLUMN gb REAL NOT NULL DEFAULT 0")
    uh = {r["name"] for r in await rows("PRAGMA table_info(users)")}
    if "username" not in uh:
        await _db.execute("ALTER TABLE users ADD COLUMN username TEXT NOT NULL DEFAULT ''")
    if "seen" not in uh:
        await _db.execute("ALTER TABLE users ADD COLUMN seen INTEGER NOT NULL DEFAULT 0")
    if "nick" not in have:
        await _db.execute("ALTER TABLE panels ADD COLUMN nick TEXT NOT NULL DEFAULT ''")
    if "note" not in have:
        await _db.execute("ALTER TABLE panels ADD COLUMN note TEXT NOT NULL DEFAULT ''")
    if "warn" not in have:
        await _db.execute("ALTER TABLE panels ADD COLUMN warn INTEGER NOT NULL DEFAULT 0")
    if "pw" not in have:
        await _db.execute("ALTER TABLE panels ADD COLUMN pw TEXT NOT NULL DEFAULT ''")
    await _db.execute("CREATE TABLE IF NOT EXISTS servers(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, "
                      "url TEXT NOT NULL, username TEXT NOT NULL, password TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 0)")
    if "server_id" not in have:
        await _db.execute("ALTER TABLE panels ADD COLUMN server_id INTEGER NOT NULL DEFAULT 1")
    if "server_id" not in {r["name"] for r in await rows("PRAGMA table_info(products)")}:
        await _db.execute("ALTER TABLE products ADD COLUMN server_id INTEGER NOT NULL DEFAULT 0")
    if not await row("SELECT 1 FROM servers"):
        pu, pn, pp = await get_setting("panel_url"), await get_setting("panel_user"), await get_setting("panel_pass")
        if pu and pn and pp:
            await _db.execute("INSERT INTO servers(id,name,url,username,password,is_default) VALUES(1,?,?,?,?,1)",
                              ("پنل اصلی", pu, pn, pp))
    if not await row("SELECT 1 FROM products"):
        await _db.execute("INSERT INTO products(name,descr) VALUES('سرویس تانل','سرویس تانل')")
    for i, (k, t, s) in enumerate(DEFAULT_BUTTONS):
        await _db.execute("INSERT OR IGNORE INTO buttons(key,title,style,sort) VALUES(?,?,?,?)", (k, t, s, i))
    for k, v in DEFAULT_SETTINGS.items():
        await _db.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)", (k, v))
    await _db.commit()
    await load_staff()
    if path != ":memory:":
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass


async def load_staff() -> None:
    """Owners (.env) + full admins -> config.ADMIN_IDS; operators -> config.OPERATOR_IDS (updated in place)."""
    rs = await rows("SELECT tg_id, role FROM staff")
    config.ADMIN_IDS.clear()
    config.ADMIN_IDS.update(config.OWNER_IDS)
    config.ADMIN_IDS.update(r["tg_id"] for r in rs if r["role"] == "admin")
    config.OPERATOR_IDS.clear()
    config.OPERATOR_IDS.update(r["tg_id"] for r in rs if r["role"] == "operator")


async def close() -> None:
    global _db
    if _db:
        await _db.close()
        _db = None


async def rows(sql: str, *a):
    cur = await _db.execute(sql, a)
    r = await cur.fetchall()
    await cur.close()
    return r


async def row(sql: str, *a):
    r = await rows(sql, *a)
    return r[0] if r else None


async def run(sql: str, *a) -> tuple[int, int]:
    """Execute + commit. Returns (lastrowid, rowcount)."""
    cur = await _db.execute(sql, a)
    await _db.commit()
    res = (cur.lastrowid, cur.rowcount)
    await cur.close()
    return res


# ---------- settings ----------
async def get_setting(key: str, default: str = "") -> str:
    r = await row("SELECT value FROM settings WHERE key=?", key)
    return r["value"] if r else default


async def set_setting(key: str, value: str) -> None:
    await run("INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", key, value)


# ---------- crypto ----------
def enc(s: str) -> str:
    return Fernet(config.ENCRYPTION_KEY.encode()).encrypt(s.encode()).decode()


def dec(s: str) -> str:
    return Fernet(config.ENCRYPTION_KEY.encode()).decrypt(s.encode()).decode()


# ---------- users / wallet ----------
async def touch_user(uid: int, name: str, username: str = "") -> None:
    await run(
        "INSERT INTO users(tg_id,name,username,seen,created) VALUES(?,?,?,?,?) "
        "ON CONFLICT(tg_id) DO UPDATE SET name=excluded.name, username=excluded.username, seen=excluded.seen "
        "WHERE name IS NOT excluded.name OR username IS NOT excluded.username OR seen < excluded.seen - 60",
        uid, name, username, now(), now())


async def sale(uid: int, panel: str, kind: str, gb: float, price: int) -> None:
    await run("INSERT INTO sales(user_id,panel,kind,gb,price,created) VALUES(?,?,?,?,?,?)", uid, panel, kind, gb, price, now())
    from . import report
    report.on_sale(uid, panel, kind, gb, price)


async def ev(kind: str, uid: int = 0, arg: str = "") -> None:
    await run("INSERT INTO events(ts,kind,user_id,arg) VALUES(?,?,?,?)", now(), kind, uid, arg)
    from . import report
    report.on_event(kind, uid, arg)


async def is_blocked(uid: int) -> bool:
    r = await row("SELECT blocked FROM users WHERE tg_id=?", uid)
    return bool(r and r["blocked"])


async def debit(uid: int, amount: int) -> bool:
    """Atomic: subtracts only if the balance is enough."""
    if amount <= 0:
        raise ValueError("amount must be positive")
    _, n = await run("UPDATE users SET balance=balance-? WHERE tg_id=? AND balance>=?", amount, uid, amount)
    return n == 1


async def credit(uid: int, amount: int) -> None:
    if amount <= 0:
        raise ValueError("amount must be positive")
    await run("UPDATE users SET balance=balance+? WHERE tg_id=?", amount, uid)


# ---------- discount / gift codes ----------
async def code_check(code: str, uid: int, kinds: tuple, price: int = 0):
    """-> (row, '') or (None, error text)."""
    c = (code or "").strip().upper()
    r = await row("SELECT * FROM codes WHERE code=?", c) if c else None
    if not r or not r["active"]:
        return None, "کد نامعتبر است."
    if r["kind"] not in kinds:
        return None, ("این یک کد هدیه است؛ از «کد هدیه» در منوی اصلی استفاده کن." if r["kind"] == "gift"
                      else "این یک کد تخفیف است؛ در مرحله‌ی تایید سفارش خرید وارد کن.")
    if r["expires"] and r["expires"] < now():
        return None, "این کد منقضی شده است."
    if r["max_uses"] and r["used"] >= r["max_uses"]:
        return None, "ظرفیت استفاده از این کد تمام شده است."
    if await row("SELECT 1 FROM code_uses WHERE code_id=? AND user_id=?", r["id"], uid):
        return None, "قبلاً از این کد استفاده کرده‌ای."
    if r["kind"] != "gift" and price and r["min_price"] and price < r["min_price"]:
        return None, f"این کد برای خرید حداقل {r['min_price']:,} تومان است."
    return r, ""


def code_discount(r, price: int) -> int:
    d = price * r["value"] // 100 if r["kind"] == "percent" else r["value"]
    return max(0, min(d, price - 1000))   # final price never drops under 1000 toman


async def code_use(code_id: int, uid: int) -> bool:
    """Atomically takes one use of the code for this user."""
    import sqlite3
    _, n = await run("UPDATE codes SET used=used+1 WHERE id=? AND active=1 AND (max_uses=0 OR used<max_uses) "
                     "AND (expires=0 OR expires>=?)", code_id, now())
    if n != 1:
        return False
    try:
        await run("INSERT INTO code_uses(code_id,user_id,ts) VALUES(?,?,?)", code_id, uid, now())
    except sqlite3.IntegrityError:
        await run("UPDATE codes SET used=MAX(used-1,0) WHERE id=?", code_id)
        return False
    return True


async def code_release(code_id, uid: int) -> None:
    if not code_id:
        return
    _, n = await run("DELETE FROM code_uses WHERE code_id=? AND user_id=?", code_id, uid)
    if n:
        await run("UPDATE codes SET used=MAX(used-1,0) WHERE id=?", code_id)


async def gift_redeem(code: str, uid: int):
    """-> (amount, '') or (0, error)."""
    r, err = await code_check(code, uid, ("gift",))
    if not r:
        return 0, err
    if not await code_use(r["id"], uid):
        return 0, "این کد دیگر قابل استفاده نیست."
    await credit(uid, r["value"])
    await ev("giftcode", uid, f"{r['code']} (+{r['value']:,})")
    return r["value"], ""
