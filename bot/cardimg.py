from __future__ import annotations

import io
import re
import time
from pathlib import Path

import arabic_reshaper
from bidi.algorithm import get_display
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ASSETS = Path(__file__).parent / "assets"
BRAND = "CAPITAN PANEL"
EMO = re.compile("[\U0001F000-\U0001FFFF\u2600-\u27BF\u2B00-\u2BFF\ufe0f\u200d]")
S = 2


def rtl(s) -> str:
    return get_display(arabic_reshaper.reshape(EMO.sub("", str(s)).strip()))


def fnt(bold: bool, size: int):
    name = "Vazirmatn-Bold.ttf" if bold else "Vazirmatn-Regular.ttf"
    try:
        return ImageFont.truetype(str(ASSETS / name), size * S, layout_engine=ImageFont.Layout.BASIC)
    except Exception:
        return ImageFont.load_default()


def render(d: dict) -> bytes:
    W, H = 1080 * S, 640 * S
    bg = Image.new("RGB", (W, H))
    p = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / H
        p.line([(0, y), (W, y)], fill=(int(12 + 22 * t), int(16 + 10 * t), int(40 + 52 * t)))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([-200 * S, -200 * S, 380 * S, 380 * S], fill=(59, 130, 246, 120))
    gd.ellipse([760 * S, 360 * S, 1300 * S, 900 * S], fill=(168, 85, 247, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(110 * S))
    img = Image.alpha_composite(bg.convert("RGBA"), glow).convert("RGB")
    dr = ImageDraw.Draw(img, "RGBA")

    dr.rounded_rectangle([40 * S, 40 * S, 1040 * S, 600 * S], radius=40 * S,
                         fill=(255, 255, 255, 20), outline=(255, 255, 255, 50), width=2 * S)

    cx, cy, r, wd = 270 * S, 315 * S, 150 * S, 30 * S
    box = [cx - r, cy - r, cx + r, cy + r]
    dr.arc(box, 0, 360, fill=(255, 255, 255, 38), width=wd)
    pct = d.get("pct")
    col = (52, 211, 153) if pct is None or pct < 70 else (251, 191, 36) if pct < 90 else (248, 113, 113)
    if pct is None:
        dr.arc(box, 0, 360, fill=col + (255,), width=wd)
        dr.text((cx, cy), rtl("نامحدود"), font=fnt(True, 46), fill=(255, 255, 255), anchor="mm")
    else:
        if pct > 0:
            dr.arc(box, -90, -90 + 360 * pct / 100, fill=col + (255,), width=wd)
        dr.text((cx, cy - 12 * S), f"{pct:.0f}%", font=fnt(True, 72), fill=(255, 255, 255), anchor="mm")
        dr.text((cx, cy + 52 * S), rtl("مصرف"), font=fnt(False, 28), fill=(203, 213, 225), anchor="mm")

    dr.text((1000 * S, 90 * S), rtl(str(d.get("nick", ""))[:24]), font=fnt(True, 54),
            fill=(255, 255, 255), anchor="ra")

    st = str(d.get("state") or "—")
    pc = (52, 211, 153) if "فعال" in st else (248, 113, 113)
    f = fnt(True, 28)
    text = rtl(st)
    w = int(dr.textlength(text, font=f))
    x2, y1 = 1000 * S, 170 * S
    dr.rounded_rectangle([x2 - w - 80 * S, y1, x2, y1 + 54 * S], radius=27 * S,
                         fill=pc + (45,), outline=pc + (160,), width=2 * S)
    dr.ellipse([x2 - 31 * S, y1 + 20 * S, x2 - 17 * S, y1 + 34 * S], fill=pc + (255,))
    dr.text((x2 - 46 * S, y1 + 27 * S), text, font=f, fill=(255, 255, 255), anchor="rm")

    rows = [("حجم کل", d.get("limit")), ("مصرف‌شده", d.get("used")), ("باقی‌مانده", d.get("remain")),
            ("کاربران ساخته‌شده", d.get("users")), ("تاریخ ساخت", d.get("created"))]
    for i, (lab, val) in enumerate(rows):
        yy = (262 + i * 62) * S
        dr.text((1000 * S, yy), rtl(lab), font=fnt(False, 30), fill=(203, 213, 225), anchor="rm")
        dr.text((520 * S, yy), rtl(val if val not in (None, "") else "—"), font=fnt(True, 32),
                fill=(255, 255, 255), anchor="lm")
        if i < len(rows) - 1:
            dr.line([(520 * S, yy + 31 * S), (1000 * S, yy + 31 * S)], fill=(255, 255, 255, 28), width=S)

    dr.text((540 * S, 578 * S), f"{BRAND}   |   {time.strftime('%Y-%m-%d %H:%M')}", font=fnt(False, 22),
            fill=(148, 163, 184), anchor="mm")

    buf = io.BytesIO()
    img.resize((1080, 640), Image.LANCZOS).save(buf, "PNG", optimize=True)
    return buf.getvalue()
