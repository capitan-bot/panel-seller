"""Site setup engine: DNS check, nginx config, SSL certificate, with progress reporting."""
import asyncio
import os
import re
import shutil
import socket
import urllib.error
import urllib.request

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
CONF_DIR = "/etc/nginx/sites-available"
ENABLED_DIR = "/etc/nginx/sites-enabled"
APT = "DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout=600 -y"

NGINX_TEMPLATE = """server {{
    listen 80;
    listen [::]:80;
    server_name {domain};

    client_max_body_size 50m;

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""

STEPS = [
    "بررسی DNS دامنه",
    "ساخت کانفیگ nginx",
    "تست و ریلود nginx",
    "گرفتن گواهی SSL",
    "بررسی نهایی سایت",
]


def clean_domain(text):
    d = (text or "").strip().lower()
    d = re.sub(r"^https?://", "", d).split("/")[0].strip(".")
    return d if DOMAIN_RE.match(d) else None


def _fetch_ip():
    for url in ("https://api.ipify.org", "https://ifconfig.me/ip", "https://icanhazip.com"):
        try:
            with urllib.request.urlopen(url, timeout=6) as r:
                ip = r.read().decode().strip()
                if re.match(r"^\d+\.\d+\.\d+\.\d+$", ip):
                    return ip
        except Exception:
            continue
    return None


async def server_ip():
    return await asyncio.get_running_loop().run_in_executor(None, _fetch_ip)


def _resolve(domain):
    try:
        infos = socket.getaddrinfo(domain, None, socket.AF_INET)
        return sorted({i[4][0] for i in infos})
    except Exception:
        return []


async def resolve(domain):
    return await asyncio.get_running_loop().run_in_executor(None, _resolve, domain)


async def check_dns(domain):
    """Returns (ok, server_ip, resolved_ips)."""
    ip = await server_ip()
    got = await resolve(domain)
    return (ip is not None and ip in got), ip, got


async def _sh(cmd, timeout=180):
    if os.geteuid() != 0:
        cmd = "sudo -n " + cmd
    p = await asyncio.create_subprocess_shell(
        cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    try:
        out, _ = await asyncio.wait_for(p.communicate(), timeout)
    except asyncio.TimeoutError:
        p.kill()
        return 124, "timeout"
    return p.returncode, out.decode(errors="replace").strip()


def render(pct, done, current, error=None):
    filled = pct // 10
    bar = "█" * filled + "░" * (10 - filled)
    lines = ["🌐 در حال ساخت وب‌سایت", "", "%s %d%%" % (bar, pct), ""]
    for i, name in enumerate(STEPS):
        if i < done:
            lines.append("✅ " + name)
        elif i == current and error:
            lines.append("❌ " + name)
        elif i == current:
            lines.append("⏳ " + name)
        else:
            lines.append("▫️ " + name)
    if error:
        lines += ["", "خطا:", error[-600:]]
    return "\n".join(lines)


async def apt_busy():
    code, _ = await _sh("fuser /var/lib/dpkg/lock-frontend /var/lib/dpkg/lock", 15)
    return code == 0


async def wait_apt(progress, pct, done, cur, limit=900):
    """Stops the automatic system update and waits until apt is free."""
    if not await apt_busy():
        return True
    await _sh("systemctl stop --no-block apt-daily-upgrade.service apt-daily.service unattended-upgrades.service", 30)
    waited = 0
    while waited < limit:
        if not await apt_busy():
            return True
        await progress(render(pct, done, cur) +
                       "\n\n⏳ سیستم در حال آپدیت خودکاره؛ صبر می‌کنم... (%d ثانیه)" % waited)
        await asyncio.sleep(10)
        waited += 10
    return not await apt_busy()


async def run_setup(domain, port, email, progress, skip_dns=False):
    try:
        return await _run(domain, port, email, progress, skip_dns)
    finally:
        await _sh("systemctl start unattended-upgrades.service", 30)


async def _run(domain, port, email, progress, skip_dns):
    conf_name = "pgbot-" + domain
    avail = os.path.join(CONF_DIR, conf_name)
    enabled = os.path.join(ENABLED_DIR, conf_name)

    async def fail(step, msg, rollback=False):
        if rollback:
            await _sh("rm -f %s %s && nginx -t && systemctl reload nginx" % (enabled, avail))
        await progress(render(step * 10 + 10, step, step, msg))
        return False, msg

    # 1) DNS
    await progress(render(10, 0, 0))
    ok, ip, got = await check_dns(domain)
    if not ok and not skip_dns:
        return await fail(0, "DNS با IP سرور نمی‌خونه.\nIP سرور: %s\nIP دامنه: %s" % (ip, ", ".join(got) or "پیدا نشد"))

    # 2) nginx config (installs nginx if needed)
    await progress(render(30, 1, 1))
    if not shutil.which("nginx"):
        code, busy = await _sh("ss -ltn | grep -E ':80 |:443 '")
        if busy:
            return await fail(1, "پورت 80 یا 443 توسط برنامه‌ی دیگه‌ای اشغاله:\n" + busy)
        if not await wait_apt(progress, 30, 1, 1):
            return await fail(1, "قفل apt آزاد نشد (آپدیت خودکار سیستم هنوز در حاله). چند دقیقه بعد دوباره امتحان کن.")
        await _sh(APT + " update -qq", 300)
        code, out = await _sh(APT + " install nginx", 800)
        if code:
            return await fail(1, out)
    conf = NGINX_TEMPLATE.format(domain=domain, port=port)
    tmp = "/tmp/" + conf_name
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(conf)
    code, out = await _sh("mkdir -p %s %s && cp %s %s && ln -sf %s %s" % (CONF_DIR, ENABLED_DIR, tmp, avail, avail, enabled))
    if code:
        return await fail(1, out)

    # 3) test and reload
    await progress(render(50, 2, 2))
    code, out = await _sh("nginx -t")
    if code:
        return await fail(2, out, rollback=True)
    code, out = await _sh("systemctl enable nginx; systemctl reload nginx || systemctl restart nginx")
    if code:
        return await fail(2, out, rollback=True)

    # 4) SSL
    await progress(render(70, 3, 3))
    code, _ = await _sh("which certbot >/dev/null && dpkg -s python3-certbot-nginx >/dev/null 2>&1")
    if code:
        if not await wait_apt(progress, 70, 3, 3):
            return await fail(3, "قفل apt آزاد نشد (آپدیت خودکار سیستم هنوز در حاله). چند دقیقه بعد دوباره امتحان کن.", rollback=True)
        code, out = await _sh(APT + " install certbot python3-certbot-nginx", 800)
        if code:
            return await fail(3, out, rollback=True)
    mail = ("-m " + email) if email else "--register-unsafely-without-email"
    code, out = await _sh(
        "certbot --nginx -d %s %s --agree-tos --no-eff-email --non-interactive --redirect" % (domain, mail), 300)
    if code:
        return await fail(3, out, rollback=True)

    # 5) final check
    await progress(render(90, 4, 4))

    def probe():
        try:
            with urllib.request.urlopen("https://" + domain, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception as e:
            return str(e)

    status = None
    for _ in range(4):
        status = await asyncio.get_running_loop().run_in_executor(None, probe)
        if isinstance(status, int):
            break
        await asyncio.sleep(3)
    if not isinstance(status, int):
        return await fail(4, "سایت جواب نداد: %s" % status)

    await progress(render(100, 5, 5))
    return True, "https://" + domain
