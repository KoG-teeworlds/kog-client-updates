import re
import struct
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
PAGES = [SITE / "index.html", SITE / "404.html"] + sorted(SITE.glob("*/index.html"))
RESERVED = ["stable", "canary", "dev", "base", "releases"]
BUDGET_TOTAL = 100 * 1024
BUDGET_PAGE = 60 * 1024


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.stack = []
        self.errors = []
        self.text = []
        self.ids = set()
        self.refs = []
        self.headings = []
        self.metas = []
        self.title = ""
        self.lang = None
        self.scripts = []
        self.inline_script = False
        self.style_blocks = 0
        self.style_attrs = 0
        self.event_attrs = 0
        self.in_title = False
        self.in_script = False
        self.void = {"meta", "link", "img", "br", "hr", "input", "source", "wbr"}

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        self.tags.append(tag)
        if tag not in self.void:
            self.stack.append(tag)
        if tag == "html":
            self.lang = data.get("lang")
        if "id" in data:
            self.ids.add(data["id"])
        if any(name.startswith("on") for name in data):
            self.event_attrs += 1
        if "style" in data:
            self.style_attrs += 1
        if tag == "style":
            self.style_blocks += 1
        if tag == "script":
            self.in_script = True
            if "src" in data:
                self.scripts.append(data["src"])
            else:
                self.inline_script = True
        if tag == "title":
            self.in_title = True
        if tag in ("h1", "h2", "h3", "h4"):
            self.headings.append(int(tag[1]))
        if tag == "meta":
            self.metas.append(data)
        for name in ("href", "src"):
            if name in data:
                self.refs.append((tag, name, data[name], data))

    def handle_endtag(self, tag):
        if tag in self.void:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append("unexpected </%s> after %s" % (tag, self.stack[-3:]))
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
            return
        self.stack.pop()
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.in_script:
            self.text.append(data)


def parse(path):
    page = Page()
    page.feed(path.read_text())
    page.close()
    return page


def url_of(path):
    relative = path.relative_to(SITE).as_posix()
    if relative == "index.html":
        return "/"
    if relative == "404.html":
        return "/404.html"
    return "/" + relative[: -len("index.html")]


def resolve(page_url, href):
    base = "https://client.kog.tw" + page_url
    from urllib.parse import urljoin

    return urlparse(urljoin(base, href))


def target_file(path):
    if path.endswith("/"):
        return SITE / path.lstrip("/") / "index.html"
    return SITE / path.lstrip("/")


def luminance(color):
    channels = []
    for index in (1, 3, 5):
        value = int(color[index : index + 2], 16) / 255
        channels.append(value / 12.92 if value <= 0.03928 else ((value + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def theme_variables():
    css = (SITE / "assets" / "style.css").read_text()
    blocks = re.findall(r":root\s*\{([^}]*)\}", css)
    themes = []
    for block in blocks:
        themes.append(dict(re.findall(r"--([a-z-]+):\s*(#[0-9a-fA-F]{6})", block)))
    return themes[0], {**themes[0], **themes[1]}


class BuildTests(unittest.TestCase):
    def test_generated_pages_are_up_to_date(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_site.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_expected_files_exist(self):
        for name in ["robots.txt", "sitemap.xml", "CNAME", ".nojekyll", "favicon.svg", "404.html", "assets/style.css", "assets/app.js", "assets/manifest.js", "assets/kog-logo.svg", "assets/og.png"]:
            self.assertTrue((SITE / name).exists(), name)

    def test_cname_and_robots(self):
        self.assertEqual((SITE / "CNAME").read_text().strip(), "client.kog.tw")
        robots = (SITE / "robots.txt").read_text()
        self.assertIn("Allow: /", robots)
        self.assertNotIn("Disallow: /\n", robots)
        self.assertIn("https://client.kog.tw/sitemap.xml", robots)

    def test_sitemap_lists_every_page_but_404(self):
        sitemap = (SITE / "sitemap.xml").read_text()
        locations = set(re.findall(r"<loc>([^<]+)</loc>", sitemap))
        expected = {"https://client.kog.tw" + url_of(page) for page in PAGES if page.name != "404.html"}
        self.assertEqual(locations, expected)

    def test_nothing_in_the_manifest_owners_territory(self):
        for name in RESERVED:
            self.assertFalse((SITE / name).exists(), name + " belongs to the manifest builder")
        for name in ["update.json", "update.json.sig"]:
            self.assertFalse((SITE / name).exists(), name)

    def test_og_image_is_1200_by_630_png(self):
        data = (SITE / "assets" / "og.png").read_bytes()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")
        width, height = struct.unpack(">II", data[16:24])
        self.assertEqual((width, height), (1200, 630))


class PageTests(unittest.TestCase):
    def test_every_page_is_well_formed_and_has_the_basics(self):
        for path in PAGES:
            with self.subTest(page=path.name, url=url_of(path)):
                page = parse(path)
                self.assertEqual(page.errors, [])
                self.assertEqual(page.stack, [])
                self.assertEqual(page.lang, "en")
                self.assertTrue(page.title.strip())
                description = [m for m in page.metas if m.get("name") == "description"]
                self.assertEqual(len(description), 1)
                self.assertTrue(description[0].get("content", "").strip())
                self.assertEqual(page.tags.count("h1"), 1)
                self.assertIn("main", page.tags)
                self.assertIn("main", page.ids)
                canonical = [r for r in page.refs if r[3].get("rel") == "canonical"]
                self.assertEqual(len(canonical), 1)
                self.assertEqual(canonical[0][2], "https://client.kog.tw" + url_of(path))
                self.assertTrue([m for m in page.metas if m.get("name") == "viewport"])
                self.assertTrue([m for m in page.metas if m.get("name") == "referrer" and m.get("content") == "no-referrer"])
                self.assertTrue([m for m in page.metas if m.get("property") == "og:image"])
                self.assertTrue([m for m in page.metas if m.get("name") == "twitter:card"])

    def test_headings_do_not_skip_levels(self):
        for path in PAGES:
            with self.subTest(page=path.name):
                levels = parse(path).headings
                self.assertEqual(levels[0], 1)
                for before, after in zip(levels, levels[1:]):
                    self.assertLessEqual(after, before + 1)

    def test_content_security_policy_meta(self):
        for path in PAGES:
            with self.subTest(page=path.name):
                metas = [m for m in parse(path).metas if m.get("http-equiv") == "Content-Security-Policy"]
                self.assertEqual(len(metas), 1)
                policy = metas[0]["content"]
                for directive in ["default-src 'none'", "style-src 'self'", "script-src 'self'", "base-uri 'none'", "form-action 'none'"]:
                    self.assertIn(directive, policy)
                self.assertNotIn("unsafe", policy)
                self.assertNotIn("*", policy)

    def test_no_inline_script_style_or_handlers(self):
        for path in PAGES:
            with self.subTest(page=path.name):
                page = parse(path)
                self.assertFalse(page.inline_script)
                self.assertEqual(page.style_blocks, 0)
                self.assertEqual(page.style_attrs, 0)
                self.assertEqual(page.event_attrs, 0)

    def test_no_third_party_scripts_styles_fonts_or_images(self):
        for path in PAGES:
            with self.subTest(page=path.name):
                for tag, name, value, attrs in parse(path).refs:
                    absolute = value.startswith("http://") or value.startswith("https://") or value.startswith("//")
                    if tag in ("script", "img") or (tag == "link" and attrs.get("rel") in ("stylesheet", "icon", "preload", "manifest")):
                        self.assertFalse(absolute, "%s %s" % (tag, value))
                    if tag == "a" and absolute:
                        self.assertTrue(value.startswith("https://"), value)

    def test_internal_links_and_fragments_resolve(self):
        pages = {url_of(p): parse(p) for p in PAGES}
        for path in PAGES:
            page_url = url_of(path)
            for tag, name, value, attrs in pages[page_url].refs:
                if value.startswith(("http://", "https://", "mailto:", "//")) or attrs.get("rel") == "canonical":
                    continue
                with self.subTest(page=page_url, ref=value):
                    clean, fragment = urldefrag(value)
                    target = resolve(page_url, clean) if clean else urlparse("https://client.kog.tw" + page_url)
                    self.assertTrue(target_file(target.path).exists(), "%s -> %s" % (value, target.path))
                    if fragment:
                        other = pages.get(target.path if target.path.endswith("/") or target.path.endswith(".html") else target.path + "/")
                        self.assertIsNotNone(other)
                        self.assertIn(fragment, other.ids)

    def test_best_effort_notice_on_the_home_page_and_every_footer(self):
        home = " ".join(" ".join(parse(SITE / "index.html").text).split())
        for sentence in [
            "The KoG client is maintained on a best-effort basis by volunteers.",
            "There is no warranty, no support guarantee and no release schedule.",
            "It can break, change or disappear without notice.",
            "Security fixes are made as time allows.",
            "You do not need this client to play on KoG:",
            "stock DDNet clients keep working.",
            "If you want guaranteed support or a stable experience, use the official DDNet client.",
            "Use at your own risk.",
        ]:
            self.assertIn(sentence, home)
        for path in PAGES:
            with self.subTest(page=path.name):
                self.assertIn("Best effort only", " ".join(parse(path).text))

    def test_planned_things_are_marked(self):
        home = (SITE / "index.html").read_text()
        self.assertGreaterEqual(home.count('class="planned"'), 2)
        self.assertNotIn("TODO", home)
        for path in PAGES:
            self.assertNotIn("kog.tw/account", path.read_text())


class WeightTests(unittest.TestCase):
    def test_total_weight_of_html_css_and_js_stays_under_budget(self):
        total = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file() and p.suffix in (".html", ".css", ".js"))
        self.assertLess(total, BUDGET_TOTAL)

    def test_one_page_load_stays_under_budget(self):
        shared = sum((SITE / "assets" / name).stat().st_size for name in ["style.css", "manifest.js", "app.js"]) + (SITE / "assets" / "kog-logo.svg").stat().st_size
        for path in PAGES:
            with self.subTest(page=path.name):
                self.assertLess(path.stat().st_size + shared, BUDGET_PAGE)


class ScriptTests(unittest.TestCase):
    FORBIDDEN = [r"\.innerHTML", r"\.outerHTML", r"insertAdjacentHTML", r"\beval\s*\(", r"new\s+Function", r"document\.write", r"setTimeout\s*\(\s*[\"']", r"setInterval\s*\(\s*[\"']", r"\.srcdoc", r"createContextualFragment", r"importScripts", r"XMLHttpRequest", r"localStorage", r"sessionStorage", r"document\.cookie"]

    def test_scripts_use_no_dangerous_apis(self):
        for name in ["app.js", "manifest.js"]:
            code = (SITE / "assets" / name).read_text()
            for pattern in self.FORBIDDEN:
                with self.subTest(file=name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, code))

    def test_scripts_make_no_third_party_requests(self):
        for name in ["app.js", "manifest.js"]:
            code = (SITE / "assets" / name).read_text()
            for url in re.findall(r"https?://[^\"'\s)]+", code):
                with self.subTest(file=name, url=url):
                    self.assertTrue(url == "https://github.com" or url.startswith("https://github.com/KoG-teeworlds/"), url)

    def test_home_page_loads_only_the_two_local_scripts(self):
        self.assertEqual(parse(SITE / "index.html").scripts, ["assets/manifest.js", "assets/app.js"])
        for path in PAGES:
            if path.name != "index.html" or path.parent != SITE:
                self.assertEqual(parse(path).scripts, [], path)


class StyleTests(unittest.TestCase):
    def test_text_contrast_meets_aa_in_both_themes(self):
        light, dark = theme_variables()
        pairs = [("fg", "bg"), ("fg", "surface"), ("muted", "bg"), ("muted", "surface"), ("link", "bg"), ("link", "surface"), ("link", "warn-bg"), ("fg", "warn-bg"), ("btn-fg", "btn-bg"), ("fg", "code-bg"), ("link", "code-bg"), ("muted", "code-bg")]
        for name, theme in (("light", light), ("dark", dark)):
            for foreground, background in pairs:
                with self.subTest(theme=name, pair=foreground + "/" + background):
                    self.assertGreaterEqual(contrast(theme[foreground], theme[background]), 4.5)

    def test_motion_and_focus_rules_exist(self):
        css = (SITE / "assets" / "style.css").read_text()
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(":focus-visible", css)
        self.assertIn("prefers-color-scheme: dark", css)

    def test_svg_files_reference_nothing_external(self):
        for name in ["favicon.svg", "assets/kog-logo.svg"]:
            text = (SITE / name).read_text()
            self.assertNotIn("<script", text)
            self.assertIsNone(re.search(r"(href|src)=\"https?://", text))
            self.assertNotIn("onload", text)


if __name__ == "__main__":
    unittest.main()
