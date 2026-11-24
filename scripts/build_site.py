#!/usr/bin/env python3
import html
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SITE = ROOT / "site"
ORIGIN = "https://client.kog.tw"
REPO = "https://github.com/KoG-teeworlds/kog-client"

WEBSITE = "https://kog.tw/"
CLIENTS = "https://kog.tw/clients"

NAV = [
    ("index", "Download", "#download"),
    ("verify", "Verify", "verify/"),
    ("install", "Install", "install/"),
    ("updates", "Updates", "updates/"),
    ("privacy", "Privacy", "privacy/"),
    ("faq", "FAQ", "faq/"),
    ("changelog", "Changelog", "changelog/"),
]

CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; img-src 'self' data:; "
    "connect-src 'self' https://kog-teeworlds.github.io; base-uri 'none'; form-action 'none'"
)


def read_page(path):
    meta, body = {}, []
    lines = path.read_text().split("\n")
    index = 0
    while index < len(lines) and lines[index].startswith("@"):
        key, _, value = lines[index][1:].partition(" ")
        meta[key] = value.strip()
        index += 1
    body = "\n".join(lines[index:]).strip("\n")
    return meta, body


def output_path(name):
    if name == "index":
        return SITE / "index.html"
    if name == "404":
        return SITE / "404.html"
    return SITE / name / "index.html"


def url_path(name):
    if name == "index":
        return "/"
    if name == "404":
        return "/404.html"
    return "/%s/" % name


def prefix(name):
    if name == "index":
        return ""
    if name == "404":
        return "/"
    return "../"


def render(name, meta, body):
    base = prefix(name)
    title = meta["title"]
    description = meta["description"]
    canonical = ORIGIN + url_path(name)
    nav = []
    for key, label, target in NAV:
        current = ' aria-current="page"' if key == name else ""
        nav.append('<li><a href="%s"%s>%s</a></li>' % (base + target, current, label))
    strip = ""
    if name != "index":
        strip = (
            '<div class="strip"><div class="wrap"><p><strong>Best effort only.</strong> Volunteer-maintained, '
            "no warranty or support guarantee. You do not need this client to play on KoG.</p></div></div>\n"
        )
    script = ""
    if name == "index":
        script = '<script src="assets/manifest.js"></script>\n<script src="assets/app.js"></script>\n'
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description, quote=True)}">
<link rel="canonical" href="{canonical}">
<link rel="icon" href="{base}favicon.svg" type="image/svg+xml">
<meta property="og:type" content="website">
<meta property="og:site_name" content="KoG Client">
<meta property="og:title" content="{html.escape(title, quote=True)}">
<meta property="og:description" content="{html.escape(description, quote=True)}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{ORIGIN}/assets/og.png">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta property="og:image:alt" content="KoG Client: an open-source Teeworlds client for King of Gores">
<meta name="twitter:card" content="summary_large_image">
<link rel="stylesheet" href="{base}assets/style.css">
</head>
<body>
<a class="skip" href="#main">Skip to content</a>
<header class="site">
<div class="wrap">
<a class="brand" href="{base or './'}"><img src="{base}assets/kog-logo.svg" alt="" width="36" height="36"><span>KoG Client</span></a>
<nav aria-label="Main"><ul>
{chr(10).join(nav)}
</ul></nav>
<a class="back" href="{WEBSITE}">kog.tw<span aria-hidden="true"> &#8599;</span><span class="visually-hidden"> (back to the KoG website)</span></a>
</div>
</header>
{strip}<main id="main">
<div class="wrap">
{body}
</div>
</main>
<footer class="site">
<div class="wrap">
<p><strong>Best effort only.</strong> The KoG client is maintained by volunteers, with no warranty and no support guarantee. Use at your own risk.</p>
<ul>
<li><a href="{WEBSITE}">kog.tw</a></li>
<li><a href="{CLIENTS}">Approved clients</a></li>
<li><a href="{REPO}">Source code</a></li>
<li><a href="{REPO}/issues">Issues</a></li>
<li><a href="{base}privacy/">Privacy</a></li>
<li><a href="{REPO}/blob/main/SECURITY.md">Security</a></li>
<li><a href="{REPO}/blob/main/license.txt">Licence</a></li>
<li><a href="{REPO}/blob/main/NOTICE_KOG.md">Credits and notice</a></li>
</ul>
<p>An independent fork of <a href="https://github.com/TaterClient/TClient">TClient</a>, itself a fork of <a href="https://ddnet.org">DDNet</a>. Not an official release of Teeworlds, DDNet or TClient, and not endorsed by their authors.</p>
</div>
</footer>
{script}</body>
</html>
"""


def sitemap(names):
    entries = "\n".join("  <url><loc>%s%s</loc></url>" % (ORIGIN, url_path(n)) for n in names if n != "404")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % entries


def build():
    outputs = {}
    names = []
    for path in sorted(CONTENT.glob("*.html")):
        name = path.stem
        meta, body = read_page(path)
        outputs[output_path(name)] = render(name, meta, body)
        names.append(name)
    names.sort(key=lambda n: (n != "index", n))
    outputs[SITE / "sitemap.xml"] = sitemap(names)
    return outputs


def main():
    check = "--check" in sys.argv
    stale = []
    for path, text in build().items():
        if check:
            if not path.exists() or path.read_text() != text:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text)
    if stale:
        print("out of date, run scripts/build_site.py: " + ", ".join(stale), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
