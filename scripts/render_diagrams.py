#!/usr/bin/env python3
"""Renders diagrams/*.mmd to site/assets/diagrams/NAME-light.svg and NAME-dark.svg with Mermaid, at build time.

usage: render_diagrams.py [--check] [NAME ...]

The SVG files are committed, so the site build and its tests need neither Node nor a browser, and the page that goes
live is exactly what was reviewed. The text of each diagram stays in diagrams/NAME.mmd; the lock file
diagrams/render.lock.json records the hash of every source and configuration the committed SVGs were made from, and
--check (also run by the tests) fails when a source changed without a new render. Rendering itself needs Node and a
Chrome: CHROME_PATH names it (default: google-chrome). The SVGs hold no script and no external reference; the pages
show them as images, so the strict Content-Security-Policy of the site (no inline style) is not touched.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "diagrams"
OUT = ROOT / "site" / "assets" / "diagrams"
LOCK = SRC / "render.lock.json"
MERMAID_CLI = "@mermaid-js/mermaid-cli@11.12.0"
THEMES = ("light", "dark")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def current_lock():
    entries = {"mermaid-cli": MERMAID_CLI, "config": {t: digest(SRC / ("mermaid-%s.json" % t)) for t in THEMES}, "sources": {}}
    for path in sorted(SRC.glob("*.mmd")):
        entries["sources"][path.stem] = digest(path)
    return entries


def finish(svg):
    """Fixed size from the view box instead of a width of 100 percent, and no leftover style on the root element."""
    match = re.search(r'viewBox="-?[\d.]+ -?[\d.]+ ([\d.]+) ([\d.]+)"', svg)
    width, height = round(float(match.group(1))), round(float(match.group(2)))
    svg = svg.replace(' width="100%"', ' width="%d" height="%d"' % (width, height), 1)
    svg = re.sub(r' style="max-width: [\d.]+px;[^"]*"', "", svg, count=1)
    assert "<script" not in svg and "http://www.w3.org/1999/xlink" not in svg.replace('xmlns:xlink="http://www.w3.org/1999/xlink"', "")
    return svg


def render(names):
    chrome = os.environ.get("CHROME_PATH", "google-chrome")
    env = dict(os.environ, PUPPETEER_SKIP_DOWNLOAD="1")
    with tempfile.TemporaryDirectory() as tmp:
        browser = Path(tmp) / "puppeteer.json"
        browser.write_text(json.dumps({"executablePath": chrome, "args": ["--no-sandbox", "--disable-gpu"]}))
        OUT.mkdir(parents=True, exist_ok=True)
        for name in names:
            for theme in THEMES:
                target = Path(tmp) / ("%s-%s.svg" % (name, theme))
                subprocess.run(
                    ["npx", "--yes", MERMAID_CLI, "-i", str(SRC / (name + ".mmd")), "-o", str(target),
                     "-c", str(SRC / ("mermaid-%s.json" % theme)), "-p", str(browser), "-b", "transparent", "--quiet"],
                    check=True, env=env,
                )
                (OUT / target.name).write_text(finish(target.read_text()))


def main():
    args = sys.argv[1:]
    lock = current_lock()
    if "--check" in args:
        try:
            saved = json.loads(LOCK.read_text())
        except OSError:
            saved = None
        missing = [n for n in lock["sources"] for t in THEMES if not (OUT / ("%s-%s.svg" % (n, t))).exists()]
        if saved != lock or missing:
            print("diagrams out of date, run scripts/render_diagrams.py %s" % " ".join(missing), file=sys.stderr)
            return 1
        return 0
    names = [a for a in args if not a.startswith("-")] or list(lock["sources"])
    render(names)
    LOCK.write_text(json.dumps(lock, indent=1) + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
