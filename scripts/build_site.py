#!/usr/bin/env python3
import html
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content"
SITE = ROOT / "site"
ORIGIN = "https://client.kog.tw"
REPO = "https://github.com/KoG-teeworlds/kog-client"

WEBSITE = "https://kog.tw/"
CLIENTS = "https://kog.tw/clients"

DISCLAIMER_LEAD = "The KoG client is a reference implementation."
DISCLAIMER = (
    DISCLAIMER_LEAD
    + " It exists to demonstrate and test new features that need client integration, such as new network messages and the KoG login."
    + " You do not need it to play on KoG: the normal DDNet and Teeworlds clients are fully supported."
    + " Builds are for testing and may change or break."
)
DISCLAIMER_LINK = "Just want to play?"

NAV = [
    ("index", "Download", ""),
    ("technical", "Docs", "technical/"),
    ("privacy", "Privacy", "privacy/"),
    (None, "Source", REPO),
    (None, "Approved clients", CLIENTS),
    (None, "kog.tw", WEBSITE),
]

SOURCE = "https://github.com/KoG-teeworlds/kog-client-updates"
DIAGRAMS = ROOT / "diagrams"

# The documentation under /technical/: groups of the sidebar, and with them the order of the Previous and Next links.
DOCS = [
    ("Start", ["technical", "technical/architecture"]),
    ("Updates and trust", ["technical/update-channel", "technical/release-signing", "technical/verify", "technical/security"]),
    ("Account and data", ["technical/login", "technical/privacy"]),
    ("Build", ["technical/build"]),
    ("Project", ["technical/roadmap", "technical/glossary"]),
]
DOCS_ORDER = [name for _, names in DOCS for name in names]
STATUS = {"built": "Built", "partial": "Partly built", "planned": "Planned"}
LONG_SECTION = 1200  # characters of prose from which a section is set in two columns on a wide screen
CHECKED = "24 November 2026"
CHECKED_COMMIT = "f93469fdd"

CSP = (
    "default-src 'none'; style-src 'self'; script-src 'self'; font-src 'self'; img-src 'self' data:; "
    "connect-src 'self' https://kog-teeworlds.github.io; base-uri 'none'; form-action 'none'"
)


def read_page(path):
    meta = {}
    lines = path.read_text().split("\n")
    index = 0
    while index < len(lines) and lines[index].startswith("@"):
        key, _, value = lines[index][1:].partition(" ")
        meta[key] = value.strip()
        index += 1
    body = "\n".join(lines[index:]).strip("\n")
    return meta, body


def page_name(path):
    rel = path.relative_to(CONTENT).with_suffix("").as_posix()
    return rel[: -len("/index")] if rel.endswith("/index") else rel


def source_file(name):
    nested = CONTENT / name / "index.html"
    return nested if nested.exists() else CONTENT / (name + ".html")


def is_doc(name):
    return name in DOCS_ORDER


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
    return "../" * (name.count("/") + 1)


def slug(text):
    text = re.sub(r"<[^>]+>", "", html.unescape(text)).lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "section"


def strip_tags(text):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", "", text)).split())


HEADING = re.compile(r"<h([23])((?:\s[^>]*)?)>(.*?)</h\1>", re.S)


def add_heading_anchors(body, links=True):
    """Gives every h2 and h3 an id and a link to itself. Returns the new body and the list of (level, id, text)."""
    used = set(re.findall(r'\bid="([^"]+)"', body))
    taken = set()
    found = []

    def one(match):
        level, attrs, inner = match.group(1), match.group(2), match.group(3)
        given = re.search(r'\bid="([^"]+)"', attrs)
        if given:
            ident = given.group(1)
        else:
            base = slug(inner)
            ident, number = base, 2
            while ident in used or ident in taken:
                ident = "%s-%d" % (base, number)
                number += 1
            attrs += ' id="%s"' % ident
        taken.add(ident)
        found.append((int(level), ident, strip_tags(inner)))
        link = '<a class="anchor" href="#%s" aria-label="Link to this section: %s">#</a>' % (ident, html.escape(strip_tags(inner), quote=True))
        if not links:
            return "<h%s%s>%s</h%s>" % (level, attrs, inner, level)
        return "<h%s%s>%s %s</h%s>" % (level, attrs, inner, link, level)

    return HEADING.sub(one, body), found


def wrap_tables(body):
    body = re.sub(r"<table(?![^>]*\bdata-wrapped)", '<div class="table-scroll" tabindex="0" role="region" aria-label="Table, scrolls sideways"><table', body)
    return body.replace("</table>", "</table></div>")


LANGUAGES = {"sh": "Shell", "json": "JSON", "text": "Text"}


def focusable_pre(body):
    def one(match):
        attrs = match.group(1)
        name = re.search(r'class="(\w+)"', attrs)
        lang = ' data-lang="%s"' % LANGUAGES[name.group(1)] if name and name.group(1) in LANGUAGES else ""
        return "<pre%s%s tabindex=\"0\">" % (attrs, lang)

    return re.sub(r"<pre(?![^>]*tabindex)([^>]*)>", one, body)


def sections(body):
    """The page text in one block per h2: the intro, then one section for each heading. Wide screens set them in columns."""
    parts = re.split(r"(?=<h2[ >])", body)
    out = []
    for part in parts:
        if not part.strip():
            continue
        prose = re.sub(r"<(table|pre|figure|dl)\b.*?</\1>", "", part, flags=re.S)
        long = len(strip_tags(prose)) > LONG_SECTION
        out.append('<section class="sec%s">\n%s\n</section>' % (" long" if long else "", part.strip()))
    return "\n".join(out)


def svg_size(path):
    match = re.search(r'viewBox="-?[\d.]+ -?[\d.]+ ([\d.]+) ([\d.]+)"', path.read_text())
    return round(float(match.group(1))), round(float(match.group(2)))


def diagram_meta(name):
    text = (DIAGRAMS / (name + ".mmd")).read_text()
    meta = {}
    for key in ("alt", "caption"):
        found = re.search("^%% " + key + ": (.*)$", text, re.M)
        if not found:
            raise SystemExit("diagrams/%s.mmd has no '%%%% %s: ...' line" % (name, key))
        meta[key] = found.group(1).strip()
    return text, meta


def diagram_figure(name, base, lazy=True):
    source, meta = diagram_meta(name)
    light = "assets/diagrams/%s-light.svg" % name
    dark = "assets/diagrams/%s-dark.svg" % name
    for rel in (light, dark):
        if not (SITE / rel).exists():
            raise SystemExit("%s is missing: run scripts/render_diagrams.py" % rel)
    width, height = svg_size(SITE / light)
    text = "\n".join(line for line in source.split("\n") if not line.startswith("%% "))
    return (
        '<figure class="diagram%s" id="figure-%s">\n'
        '<div class="diagram-scroll" tabindex="0" role="region" aria-label="Diagram, scrolls sideways">'
        '<picture><source media="(prefers-color-scheme: dark)" srcset="%s%s">'
        '<img src="%s%s" alt="%s" width="%d" height="%d"%s decoding="async"></picture></div>\n'
        "<figcaption>%s <a href=\"%s%s\">Open the diagram alone</a></figcaption>\n"
        '<details class="diagram-src"><summary>Diagram source as text (Mermaid)</summary>'
        '<pre class="mermaid-src" tabindex="0"><code>%s</code></pre></details>\n'
        "</figure>"
        % (
            " tall" if height > width * 0.9 else "", name, base, dark, base, light, html.escape(meta["alt"], quote=True), width, height, ' loading="lazy"' if lazy else "",
            html.escape(meta["caption"]), base, light, html.escape(text.strip("\n")),
        )
    )


def expand_diagrams(body, base):
    count = []

    def one(match):
        count.append(1)
        return diagram_figure(match.group(1), base, lazy=len(count) > 1)

    return re.sub(r"<!--\s*diagram\s+([\w-]+)\s*-->", one, body)


def nav_title(name, pages):
    return pages[name][0].get("nav") or pages[name][0]["title"]


SHORT = {"built": "Built", "partial": "Partly", "planned": "Planned"}


def docs_sidebar(name, pages, base):
    groups = []
    for label, members in DOCS:
        items = []
        for member in members:
            current = ' aria-current="page"' if member == name else ""
            badge = pages[member][0].get("status")
            mark = ' <span class="state %s">%s</span>' % (badge, SHORT[badge]) if badge else ""
            inline = ""
            if member == name:
                _, own = add_heading_anchors(pages[member][1])
                tops = [h for h in own if h[0] == 2]
                if len(tops) > 1:
                    links = "".join('<li><a href="#%s">%s</a></li>' % (i, html.escape(t)) for _, i, t in tops)
                    inline = '\n<details class="inpage-d"><summary>On this page</summary><ul class="inpage">%s</ul></details>' % links
            items.append('<li><a href="%s%s/"%s>%s</a>%s%s</li>' % (base, member, current, html.escape(nav_title(member, pages)), mark, inline))
        opened = " open" if name in members else ""
        groups.append(
            '<li><details class="group"%s><summary>%s</summary><ul>\n%s\n</ul></details></li>' % (opened, html.escape(label), "\n".join(items))
        )
    index = base + "assets/search-index.json"
    return (
        '<nav class="docs-nav" aria-label="Documentation">\n'
        '<details class="nav-toggle"><summary><span class="dm">Docs menu</span><span class="cur">%s</span></summary>\n'
        '<button type="button" class="search-open side" data-index="%s" hidden><span>Search the documentation</span><kbd>/</kbd></button>\n'
        '<ul class="groups">\n%s\n</ul>\n</details>\n</nav>' % (html.escape(nav_title(name, pages)), index, "\n".join(groups))
    )


def docs_toc(headings):
    if len(headings) < 2:
        return ""
    out = []
    depth = 0
    for level, ident, text in headings:
        if level == 2:
            if depth == 3:
                out.append("</ul></li>")
            elif depth == 2:
                out.append("</li>")
            out.append('<li><a href="#%s">%s</a>' % (ident, html.escape(text)))
            depth = 2
        else:
            if depth == 2:
                out.append("<ul>")
            elif depth == 0:
                out.append("<li>")
            out.append('<li><a href="#%s">%s</a></li>' % (ident, html.escape(text)))
            depth = 3
    if depth == 3:
        out.append("</ul></li>")
    elif depth == 2:
        out.append("</li>")
    return (
        '<aside class="docs-toc" aria-label="On this page">\n<details class="toc-toggle" open><summary>On this page</summary>\n'
        '<ul>\n%s\n</ul>\n</details>\n</aside>' % "\n".join(out)
    )


def docs_pager(name, pages, base):
    position = DOCS_ORDER.index(name)
    cards = []
    for label, rel, target, css in (("Previous", "prev", position - 1, "pager-prev"), ("Next", "next", position + 1, "pager-next")):
        if 0 <= target < len(DOCS_ORDER):
            other = DOCS_ORDER[target]
            arrow = ("&#8592; " if rel == "prev" else "") + label + (" &#8594;" if rel == "next" else "")
            cards.append(
                '<a class="%s" rel="%s" href="%s%s/"><span class="pager-label">%s</span><span class="pager-title">%s</span></a>'
                % (css, rel, base, other, arrow, html.escape(nav_title(other, pages)))
            )
        else:
            cards.append('<span class="pager-none"></span>')
    source = source_file(name).relative_to(ROOT).as_posix()
    return (
        '<nav class="pager" aria-label="Pagination">\n%s\n</nav>\n'
        '<p class="edit"><a href="%s/edit/main/%s">Edit this page on GitHub</a></p>' % ("\n".join(cards), SOURCE, source)
    )


def docs_breadcrumb(name, pages, base):
    items = ['<li><a href="%s">KoG Client</a></li>' % (base or "./")]
    if name == "technical":
        items.append('<li aria-current="page">Docs</li>')
    else:
        items.append('<li><a href="%stechnical/">Docs</a></li>' % base)
        items.append('<li aria-current="page">%s</li>' % html.escape(nav_title(name, pages)))
    return '<nav class="crumbs" aria-label="Breadcrumb"><ol>%s</ol></nav>' % "".join(items)


def docs_group(name):
    for label, members in DOCS:
        if name in members:
            return label
    return ""


def docs_main(name, meta, body, pages, base):
    body, headings = add_heading_anchors(body)
    toc = docs_toc(headings)
    body = sections(expand_diagrams(wrap_tables(focusable_pre(body)), base))
    status = meta.get("status")
    badge = ' <span class="state %s">%s</span>' % (status, STATUS[status]) if status else ""
    lead = '<p class="lead">%s</p>\n' % meta["lead"] if meta.get("lead") else ""
    rows = []
    if status:
        rows.append("<dt>Status</dt><dd>%s</dd>" % STATUS[status])
    if name == "technical":
        features = body[body.index('id="status"'): body.index('id="map"')]
        counts = [len(re.findall(r'class="state %s"' % kind, features)) for kind in STATUS]
        rows.append("<dt>Features</dt><dd>%d built, %d partly built, %d planned</dd>" % tuple(counts))
        rows.append("<dt>It is</dt><dd>A reference implementation. You do not need it to play.</dd>")
    rows.append("<dt>Section</dt><dd>%s</dd>" % html.escape(docs_group(name)))
    rows.append(
        '<dt>Checked</dt><dd>%s, against <a href="%s/commit/%s">kog-client %s</a></dd>' % (CHECKED, REPO, CHECKED_COMMIT, CHECKED_COMMIT)
    )
    glance = '<aside class="glance" aria-label="At a glance"><p class="glance-title">At a glance</p><dl>%s</dl></aside>' % "".join(rows)
    return (
        '<div class="docs%s">\n%s\n%s\n<main id="main" class="doc">\n%s\n<header class="doc-head">\n<div>\n<p class="eyebrow">%s</p>\n'
        "<h1>%s%s</h1>\n%s</div>\n%s\n</header>\n%s\n%s\n</main>\n</div>"
        % (
            "" if toc else " no-toc", docs_sidebar(name, pages, base), toc, docs_breadcrumb(name, pages, base), html.escape(docs_group(name)),
            html.escape(meta.get("heading") or nav_title(name, pages)), badge, lead, glance, body, docs_pager(name, pages, base),
        )
    )


def search_index(pages):
    entries = []
    order = ["index"] + DOCS_ORDER + sorted(n for n in pages if n not in DOCS_ORDER and n not in ("index", "404") and "redirect" not in pages[n][0])
    for name in order:
        meta, body = pages[name]
        _, headings = add_heading_anchors(body)
        entries.append(
            {
                "u": url_path(name),
                "t": "Download" if name == "index" else (nav_title(name, pages) if name in DOCS_ORDER else meta["title"].split(" | ")[0].split(":")[0]),
                "d": meta["description"],
                "h": [[ident, text] for level, ident, text in headings if level == 2],
            }
        )
    return json.dumps(entries, ensure_ascii=False, separators=(",", ":")) + "\n"


def render(name, meta, body, marker=None, pages=None):
    base = prefix(name)
    title = meta["title"]
    description = meta["description"]
    canonical = ORIGIN + url_path(name)
    nav = []
    for key, label, target in NAV:
        external = target.startswith("https://")
        here = key is not None and (key == name or name.startswith(key + "/"))
        current = ' aria-current="page"' if here else ""
        arrow = '<span aria-hidden="true"> &#8599;</span>' if external else ""
        nav.append('<li><a href="%s"%s>%s%s</a></li>' % (target if external else base + target, current, label, arrow))
    disclaimer = (
        '<aside class="disclaimer" aria-label="Disclaimer"><div class="wrap"><p><strong>%s</strong>%s '
        '<a href="%s">%s<span aria-hidden="true"> &#8594;</span></a></p></div></aside>\n'
        % (html.escape(DISCLAIMER_LEAD), html.escape(DISCLAIMER[len(DISCLAIMER_LEAD):]), WEBSITE, DISCLAIMER_LINK)
    )
    redirect = meta.get("redirect")
    refresh = ""
    if redirect:
        target = ORIGIN + redirect
        refresh = '<meta http-equiv="refresh" content="0; url=%s">\n<meta name="robots" content="noindex">\n' % html.escape(target, quote=True)
        canonical = target
    script = '<script src="%sassets/nav.js" defer></script>\n' % base
    if name == "index":
        script = '<script src="assets/manifest.js"></script>\n<script src="assets/app.js"></script>\n' + script
    docs = is_doc(name)
    if docs:
        script = '<script src="%sassets/docs.js" defer></script>\n' % base + script
        main = docs_main(name, meta, body, pages, base)
        main = '<div class="wrap">\n%s\n</div>' % main
    else:
        crumbs = ""
        if name != "404" and not redirect:
            body = add_heading_anchors(body, links=False)[0]
        if name not in ("index", "404") and not redirect:
            crumbs = '<nav class="crumbs" aria-label="Breadcrumb"><ol><li><a href="%s">KoG Client</a></li><li aria-current="page">%s</li></ol></nav>\n' % (base or "./", html.escape(meta.get("nav") or meta["title"].split(" | ")[0]))
        main = '<div class="wrap">\n<main id="main" class="page %s">\n%s%s\n</main>\n</div>' % ("home" if name == "index" else "prose", crumbs, body)
    body_class = (' class="docs-page"' + (' data-overview=""' if name == "technical" else "")) if docs else ""
    build_meta = '<meta name="kog-site-build" content="%s">\n' % html.escape(marker, quote=True) if marker else ""
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="{CSP}">
<meta name="referrer" content="no-referrer">
{build_meta}{refresh}<title>{html.escape(title)}</title>
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
<link rel="preload" href="{base}assets/fonts/saira-cond-700-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{base}assets/style.css">
</head>
<body{body_class}>
{disclaimer}<a class="skip" href="#main">Skip to content</a>
<header class="site">
<div class="wrap bar">
<a class="brand" href="{base or './'}"><img src="{base}assets/kog-logo.svg" alt="" width="36" height="36"><span>KoG Client</span></a>
<nav class="main" aria-label="Main"><details class="menu"><summary>Menu</summary><ul>
{chr(10).join(nav)}
</ul></details></nav>
<button type="button" class="search-open" data-index="{base}assets/search-index.json" hidden><span>Search</span><kbd>/</kbd></button>
</div>
</header>
{main}
<footer class="site">
<div class="wrap">
<p><strong>Best effort only.</strong> The KoG client is maintained by volunteers, with no warranty and no support guarantee. Use at your own risk.</p>
<ul>
<li><a href="{WEBSITE}">kog.tw</a></li>
<li><a href="{CLIENTS}">Approved clients</a></li>
<li><a href="{REPO}">Source code</a></li>
<li><a href="{REPO}/issues">Issues</a></li>
<li><a href="{base}privacy/">Privacy</a></li>
<li><a href="{base}technical/">Docs</a></li>
<li><a href="{REPO}/blob/main/SECURITY.md">Security</a></li>
<li><a href="{REPO}/blob/main/license.txt">Licence</a></li>
<li><a href="{REPO}/blob/main/NOTICE_KOG.md">Credits and notice</a></li>
</ul>
<p>This page is published automatically when a change is merged.</p>
<p>An independent fork of <a href="https://github.com/TaterClient/TClient">TClient</a>, itself a fork of <a href="https://ddnet.org">DDNet</a>. Not an official release of Teeworlds, DDNet or TClient, and not endorsed by their authors.</p>
</div>
</footer>
{script}</body>
</html>
"""


def sitemap(names):
    entries = "\n".join("  <url><loc>%s%s</loc></url>" % (ORIGIN, url_path(n)) for n in names if n != "404")
    return '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n%s\n</urlset>\n' % entries


def build(marker=None):
    outputs = {}
    names = []
    pages = {}
    for path in sorted(CONTENT.rglob("*.html")):
        pages[page_name(path)] = read_page(path)
    missing = [n for n in DOCS_ORDER if n not in pages]
    extra = sorted(n for n in pages if n.startswith("technical") and n not in DOCS_ORDER and "redirect" not in pages[n][0])
    if missing or extra:
        raise SystemExit("DOCS and content/technical differ: missing %s, not in DOCS %s" % (missing, extra))
    for name, (meta, body) in pages.items():
        outputs[output_path(name)] = render(name, meta, body, marker, pages)
        if "redirect" not in meta:
            names.append(name)
    names.sort(key=lambda n: (n != "index", n))
    outputs[SITE / "sitemap.xml"] = sitemap(names)
    outputs[SITE / "assets" / "search-index.json"] = search_index(pages)
    return outputs


def main():
    args = sys.argv[1:]
    check = "--check" in args
    marker = args[args.index("--marker") + 1] if "--marker" in args else None
    out = Path(args[args.index("--out") + 1]).resolve() if "--out" in args else None
    stale = []
    for path, text in build(marker).items():
        if out:
            path = out / path.relative_to(SITE)
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
