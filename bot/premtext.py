from __future__ import annotations

import re

TAG = re.compile(r"(<tg-emoji[^>]*>.*?</tg-emoji>|<[^>]+>)", re.S)
OPEN = re.compile(r"^<(code|pre|a)\b", re.I)
CLOSE = re.compile(r"^</(code|pre|a)\s*>", re.I)
_c: dict = {"sig": None, "pat": None}


def premium_text(text):
    from . import ui
    pe = ui.PE
    if not pe or not isinstance(text, str):
        return text
    sig = tuple(pe)
    if _c["sig"] != sig:
        keys = sorted(pe, key=len, reverse=True)
        _c["pat"] = re.compile("|".join("".join(re.escape(ch) + "\ufe0f?" for ch in k) for k in keys))
        _c["sig"] = sig
    pat, depth, out = _c["pat"], 0, []
    for tok in TAG.split(text):
        if not tok or tok.startswith("<tg-emoji"):
            out.append(tok)
        elif tok.startswith("<") and tok.endswith(">"):
            if OPEN.match(tok):
                depth += 1
            elif CLOSE.match(tok):
                depth = max(0, depth - 1)
            out.append(tok)
        elif depth:
            out.append(tok)
        else:
            out.append(pat.sub(
                lambda m: '<tg-emoji emoji-id="%s">%s</tg-emoji>' % (pe[m.group(0).replace("\ufe0f", "")], m.group(0)),
                tok))
    return "".join(out)


def premium_params(method, params) -> None:
    if params.get("parse_mode") != "HTML":
        return
    for k in ("text", "caption"):
        if isinstance(params.get(k), str):
            params[k] = premium_text(params[k])
