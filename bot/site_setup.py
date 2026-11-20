"""Site setup engine: DNS check, nginx config, SSL certificate, with progress reporting."""
import asyncio
import os
import re
import shutil
import socket
import urllib.request

DOMAIN_RE = re.compile(r"^(?=.{4,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")
CONF_DIR = "/etc/nginx/sites-available"
ENABLED_DIR = "/etc/nginx/sites-enabled"

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


async def run_setup(domain, port, email, progress, skip_dns=False):
    """progress: async function, await progress(text). Returns (ok, message)."""
    conf_name = "pgbot-" + domain
    avail = os.path.join(CONF_DIR, conf_name)
    enabled = os.path.join(ENABLED_DIR, conf_name)

    async def fail(step, msg, rollback=False):
        if rollback:
            await _sh("rm -f %s %s && nginx -t && systemctl reload nginx" % (enabled, avail))
        await progress(render(step * 10 + 10, step, step, msg))
        return False, msg

    await progress(render(10, 0, 0))
    ok, ip, got = await check_dns(domain)
    if not ok and not skip_dns:
        return await fail(0, "DNS با IP سرور نمی‌خونه.\nIP سرور: %s\nIP دامنه: %s" % (ip, ", ".join(got) or "پیدا نشد"))

    await progress(render(30, 1, 1))

    if (await _sh("fuser /var/lib/dpkg/lock-frontend"))[0] == 0:
        await progress(render(30, 1, 1) + "\n\n⏳ سیستم در حال آپدیت خودکاره؛ تا چند دقیقه صبر می‌کنم...")
    if not shutil.which("nginx"):
        busy = await _sh("ss -ltn | grep -E ':80 |:443 '")
        if busy[1]:
            return await fail(1, "پورت 80 یا 443 توسط برنامه‌ی دیگه‌ای اشغاله:\n" + busy[1])
        code, out = await _sh("apt-get update -qq; DEBIAN_FRONTEND=noninteractive apt-get install -y nginx", 400)
        if code:
            return await fail(1, out)
    conf = NGINX_TEMPLATE.format(domain=domain, port=port)
    tmp = "/tmp/" + conf_name
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(conf)
    code, out = await _sh("cp %s %s && ln -sf %s %s" % (tmp, avail, avail, enabled))
    if code:
        return await fail(1, out)

    await progress(render(50, 2, 2))
    code, out = await _sh("nginx -t")
    if code:
        return await fail(2, out, rollback=True)
    code, out = await _sh("systemctl reload nginx")
    if code:
        return await fail(2, out, rollback=True)

    await progress(render(70, 3, 3))

    if (await _sh("fuser /var/lib/dpkg/lock-frontend"))[0] == 0:
        await progress(render(70, 3, 3) + "\n\n⏳ سیستم در حال آپدیت خودکاره؛ تا چند دقیقه صبر می‌کنم...")
    code, out = await _sh("DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx", 400)
    if code:
        return await fail(3, out)
    code, out = await _sh(
        "certbot --nginx -d %s -m %s --agree-tos --non-interactive --redirect" % (domain, email), 240)
    if code:
        return await fail(3, out)

    await progress(render(90, 4, 4))

    def probe():
        try:
            with urllib.request.urlopen("https://" + domain, timeout=10) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except Exception as e:
            return str(e)

    status = await asyncio.get_running_loop().run_in_executor(None, probe)
    if not isinstance(status, int):
        return await fail(4, "سایت جواب نداد: %s" % status)

    await progress(render(100, 5, 5))
    return True, "https://" + domain
