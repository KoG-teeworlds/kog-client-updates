#!/usr/bin/env python3
"""Fetches the official KoG logo files, unmodified, into site/assets/brand/ and checks them.

usage: fetch_brand.py [--check]

The files come from the public repository KoG-teeworlds/brand_and_media at the commit pinned below, and each file is
checked against its SHA-256. --check only verifies the committed copies (no network); the tests run it. The artwork is
licensed CC BY-NC-ND 4.0: it is used as it is, never recoloured, cropped, redrawn or turned into another mark. If a
new commit of the brand repository should be used, change COMMIT and the hashes here in one reviewed pull request.
"""
import hashlib
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "assets" / "brand"
REPOSITORY = "KoG-teeworlds/brand_and_media"
COMMIT = "700f64d29bca1413a0c1fbab435852a5cc2e47c7"
FILES = {
    "logo_short_black.svg": "849e586394341c1fc2e839d7d6e14b43779129bda369d1c703b70638c298917d",
    "logo_short_white.svg": "18b5f06efb47f551c436924be055be31dc3e5a7a41641c2092c940654196ca9c",
    "logo_long_black.svg": "7be9ba9c82f82e1792c216010df5ee89e3711bd759c1b304bd7a290d8a294592",
    "logo_long_white.svg": "03663f5a63037d37a3bd1d69802a2d12d7236895fee96200005a8282b63f26de",
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check():
    bad = []
    for name, expected in FILES.items():
        path = OUT / name
        if not path.exists() or digest(path.read_bytes()) != expected:
            bad.append(name)
    return bad


def main():
    if "--check" in sys.argv:
        bad = check()
        if bad:
            print("brand files differ from the pinned commit: " + ", ".join(bad), file=sys.stderr)
            return 1
        return 0
    OUT.mkdir(parents=True, exist_ok=True)
    for name, expected in FILES.items():
        url = "https://raw.githubusercontent.com/%s/%s/brand/logo/%s" % (REPOSITORY, COMMIT, name)
        with urllib.request.urlopen(url, timeout=30) as response:
            data = response.read()
        if digest(data) != expected:
            print("%s does not match the pinned SHA-256" % name, file=sys.stderr)
            return 1
        (OUT / name).write_bytes(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
