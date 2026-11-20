import os
import re

from . import site_setup as S

PORT = 8788
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)


def ask(p):
    return input(p).strip()


async def main():
    ip = await S.server_ip()
    print("\n=== Website setup ===\n")
    print("DNS guide:")
    print("  1) Open your domain panel (or Cloudflare)")
    print("  2) Create an A record: name '@' (or a subdomain like 'store')")
    print("  3) Value: %s  (this server's public IP)" % (ip or "unknown"))
    print("  4) If Cloudflare: turn the orange cloud OFF (grey)")
    print("  5) Wait a few minutes for DNS to propagate\n")

    while True:
        d = S.clean_domain(ask("Domain (empty = cancel): "))
        if d is None:
            if ask("Invalid or empty. Cancel? [y/N]: ").lower() == "y":
                return
            continue
        ok, ip, got = await S.check_dns(d)
        if ok:
            print("DNS OK.")
            break
        print("DNS does not point to this server.")
        print("  server IP : %s" % ip)
        print("  domain IP : %s" % (", ".join(got) or "not found"))
        if ask("Check again? [Y/n]: ").lower() == "n":
            return

    while True:
        email = ask("Email for SSL (optional, Enter to skip): ")
        if not email or EMAIL_RE.match(email):
            break
        print("Invalid email.")

    async def progress(t):
        os.system("clear")
        print(t)

    ok, msg = await S.run_setup(d, PORT, email, progress)
    print()
    if ok:
        data = os.path.join(os.getcwd(), "data")
        os.makedirs(data, exist_ok=True)
        open(os.path.join(data, "site_domain.txt"), "w", encoding="utf-8").write(d)
        print("Done: " + msg)
    else:
        print("Failed. Changes were rolled back.")
