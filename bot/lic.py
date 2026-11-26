import base64, json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

PUB = "KY2LJ8v8YHoAiC9HQooUEQI0ev6Sc5deR6SIc35hktw="

def _u(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))

def check(code, admin_id):
    try:
        pb, sb = code.strip().split(".")
        p, s = _u(pb), _u(sb)
        Ed25519PublicKey.from_public_bytes(base64.b64decode(PUB)).verify(s, p)
        d = json.loads(p)
        if d["a"] != int(admin_id):
            return None
        return d
    except Exception:
        return None
