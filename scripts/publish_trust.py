#!/usr/bin/env python3
"""Puts the signed trust list of one channel into a checkout of the branch published, as list/CHANNEL/trust.json, and touches nothing else.

usage: publish_trust.py CHANNEL FILE PUBLISHED
CHANNEL is stable, canary or dev. FILE is the list as the website built it. It is published only if it is signed by a key in
trust/anchors.json for the environment of the channel (a channel without a key publishes nothing), is for that environment,
is not expired, and its sequence number is higher than the one already on the branch (a replay cannot roll the list back).
Everything else in the checkout stays as it is: exit 1 for a change outside list/CHANNEL/trust.json.
"""
import base64
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENVIRONMENT = {"stable": "production", "canary": "canary", "dev": "dev"}
MAX_SIZE = 64 * 1024
DOMAIN = b"kog-trust-bundle-v1\x00"
P = 2**255 - 19
D = -121665 * pow(121666, P - 2, P) % P
Q = 2**252 + 27742317777372353535851937790883648493


def _add(a, b):
    x1, y1, z1, t1 = a
    x2, y2, z2, t2 = b
    aa, bb = (y1 - x1) * (y2 - x2) % P, (y1 + x1) * (y2 + x2) % P
    c, d = 2 * t1 * t2 * D % P, 2 * z1 * z2 % P
    e, f, g, h = bb - aa, d - c, d + c, bb + aa
    return e * f % P, g * h % P, f * g % P, e * h % P


def _mul(scalar, point):
    result = (0, 1, 1, 0)
    while scalar:
        if scalar & 1:
            result = _add(result, point)
        point = _add(point, point)
        scalar >>= 1
    return result


def _decode(raw):
    y = int.from_bytes(raw, "little")
    sign, y = y >> 255, y & ((1 << 255) - 1)
    if y >= P:
        return None
    x2 = (y * y - 1) * pow(D * y * y + 1, P - 2, P) % P
    x = pow(x2, (P + 3) // 8, P)
    if (x * x - x2) % P:
        x = x * pow(2, (P - 1) // 4, P) % P
    if (x * x - x2) % P or (x == 0 and sign):
        return None
    if x & 1 != sign:
        x = P - x
    return x, y, 1, x * y % P


def verify(public: bytes, message: bytes, signature: bytes) -> bool:
    """RFC 8032 verification (the same as scripts/trust_anchor.py of infra-github; no dependency on the runner)."""
    if len(signature) != 64 or len(public) != 32:
        return False
    a, r = _decode(public), _decode(signature[:32])
    s = int.from_bytes(signature[32:], "little")
    if a is None or r is None or s >= Q:
        return False
    k = int.from_bytes(hashlib.sha512(signature[:32] + public + message).digest(), "little") % Q
    left = _mul(s, _decode((4 * pow(5, P - 2, P) % P).to_bytes(32, "little")))
    right = _add(r, _mul(k, a))
    return (left[0] * right[2] - right[0] * left[2]) % P == 0 and (left[1] * right[2] - right[1] * left[2]) % P == 0


def check(channel, text, anchors, held_seq, now):
    """Returns (ok, why, seq)."""
    if channel not in ENVIRONMENT:
        return False, "unknown channel", 0
    if len(text) > MAX_SIZE:
        return False, "file too big", 0
    try:
        served = json.loads(text)
        payload = base64.b64decode(served["payload"], validate=True)
        document = json.loads(payload)
        signatures = {label: base64.b64decode(value, validate=True) for label, value in served["sig"].items()}
        environment, seq, expires = document["environment"], int(document["seq"]), int(document["expires_at"])
    except (ValueError, KeyError, TypeError, AttributeError):
        return False, "not a trust list", 0
    if served.get("v") != 1 or environment != ENVIRONMENT[channel]:
        return False, "wrong environment for this channel", 0
    keys = [bytes.fromhex(k) for k in anchors.get(environment, [])]
    if not keys:
        return False, "no anchor committed for " + environment, 0
    if not any(verify(k, DOMAIN + payload, s) for k in keys for s in signatures.values()):
        return False, "not signed by a committed anchor", 0
    if now > expires:
        return False, "expired", 0
    if seq <= held_seq:
        return False, "not newer than the published one", seq
    return True, "ok", seq


def git(published, *args):
    return subprocess.run(["git", "-C", str(published), *args], check=True, capture_output=True, text=True).stdout


def publish(channel, file, published, anchors, now):
    published = Path(published)
    target = published / "list" / channel / "trust.json"
    held = 0
    if target.exists():
        try:
            held = int(json.loads(base64.b64decode(json.loads(target.read_text())["payload"]))["seq"])
        except (ValueError, KeyError, TypeError):
            held = 0
    text = Path(file).read_text()
    ok, why, _ = check(channel, text, anchors, held, now)
    if not ok:
        print("refused: " + why, file=sys.stderr)
        return 1
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text if text.endswith("\n") else text + "\n")
    git(published, "add", "-A")
    changed = [f for f in git(published, "diff", "--cached", "--name-only", "-z").split("\0") if f]
    outside = [f for f in changed if f != f"list/{channel}/trust.json"]
    if outside:
        git(published, "reset", "--quiet")
        print("refused, would change files outside the list: " + ", ".join(outside), file=sys.stderr)
        return 1
    print("changed: %d" % len(changed))
    return 0


def main():
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2
    anchors = json.loads((ROOT / "trust" / "anchors.json").read_text())
    return publish(sys.argv[1], sys.argv[2], sys.argv[3], anchors, int(time.time()))


if __name__ == "__main__":
    sys.exit(main())
