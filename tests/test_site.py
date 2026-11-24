import html as htmllib
import os
import re
import struct
import subprocess
import sys
import unittest
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urldefrag, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import build_site  # noqa: E402

SITE = ROOT / "site"
PAGES = [SITE / "index.html", SITE / "404.html"] + sorted(p for p in SITE.rglob("index.html") if p != SITE / "index.html")
DOC_PAGES = [SITE / name / "index.html" for name in build_site.DOCS_ORDER]
RESERVED = ["stable", "canary", "dev", "base", "releases"]
BUDGET_TOTAL = 400 * 1024
BUDGET_PAGE = 90 * 1024
BUDGET_DOC_PAGE = 200 * 1024
BUDGET_SCRIPT = 20 * 1024


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
        self.first_in_body = None
        self.in_body = False
        self.in_disclaimer = 0
        self.disclaimer_text = []
        self.disclaimer_links = []
        self.void = {"meta", "link", "img", "br", "hr", "input", "source", "wbr"}

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if self.in_body and self.first_in_body is None:
            self.first_in_body = (tag, data)
            if tag == "aside":
                self.in_disclaimer = 1
        elif self.in_disclaimer:
            if tag == "aside":
                self.in_disclaimer += 1
            if tag == "a":
                self.disclaimer_links.append(data.get("href"))
        if tag == "body":
            self.in_body = True
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
        if tag == "aside" and self.in_disclaimer:
            self.in_disclaimer -= 1
        if tag == "title":
            self.in_title = False
        if tag == "script":
            self.in_script = False

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        elif not self.in_script:
            self.text.append(data)
            if self.in_disclaimer:
                self.disclaimer_text.append(data)


def squash(text):
    return " ".join(text.split())


def redirect_target(page):
    for meta in page.metas:
        if meta.get("http-equiv") == "refresh":
            return meta["content"].split("url=", 1)[1]
    return None


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
        for name in ["robots.txt", "sitemap.xml", "CNAME", ".nojekyll", "favicon.svg", "404.html", "assets/style.css", "assets/app.js", "assets/manifest.js", "assets/kog-logo.svg", "assets/og.png", "assets/docs.js", "assets/search-index.json"]:
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
        expected = {"https://client.kog.tw" + url_of(page) for page in PAGES if page.name != "404.html" and not redirect_target(parse(page))}
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


class ShellTests(unittest.TestCase):
    def test_every_page_has_the_same_banner_header_container_and_footer(self):
        banners, headers = set(), set()
        for path in PAGES:
            with self.subTest(page=url_of(path)):
                text = path.read_text()
                banners.add(re.search(r'<aside class="disclaimer".*?</aside>', text, re.S).group(0))
                header = re.search(r'<header class="site">.*?</header>', text, re.S).group(0)
                header = re.sub(r'(href|src)="(?:\.{1,2}/)*/?', r'\1="', header)
                header = header.replace(' aria-current="page"', "")
                headers.add(header)
                order = [text.index(marker) for marker in ('<aside class="disclaimer"', '<a class="skip"', '<header class="site">', '<footer class="site">')]
                self.assertEqual(order, sorted(order))
                between = text[text.index("</header>") + len("</header>"): text.index('<footer class="site">')]
                self.assertTrue(between.strip().startswith('<div class="wrap">'), path)
                self.assertEqual(between.count('<main id="main"'), 1)
                self.assertGreaterEqual(text.count('class="wrap'), 4)
        self.assertEqual(len(banners), 1)
        self.assertEqual(len(headers), 1)


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
                self.assertEqual(canonical[0][2], redirect_target(page) or "https://client.kog.tw" + url_of(path))
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

    def test_the_disclaimer_is_the_first_block_of_every_page_before_main(self):
        expected = squash(build_site.DISCLAIMER)
        for path in sorted(SITE.rglob("*.html")):
            with self.subTest(page=path.relative_to(SITE).as_posix()):
                page = parse(path)
                self.assertEqual(page.first_in_body[0], "aside")
                self.assertEqual(page.first_in_body[1].get("class"), "disclaimer")
                self.assertLess(page.tags.index("aside"), page.tags.index("main"))
                text = squash("".join(page.disclaimer_text))
                self.assertTrue(text.startswith(expected), text)
                self.assertIn(build_site.DISCLAIMER_LINK, text)
                self.assertEqual(page.disclaimer_links, ["https://kog.tw/"])

    def test_every_html_page_of_the_site_is_covered_by_the_page_list(self):
        found = {p for p in SITE.rglob("*.html")}
        self.assertEqual(found, set(PAGES))

    def test_the_disclaimer_text_is_defined_once_in_the_generator(self):
        source = (ROOT / "scripts" / "build_site.py").read_text()
        self.assertEqual(source.count("It exists to demonstrate and test new features"), 1)
        self.assertEqual(source.count("The KoG client is a reference implementation."), 1)
        for path in (ROOT / "content").rglob("*.html"):
            self.assertNotIn("It exists to demonstrate", path.read_text(), path.name)
            self.assertNotIn("The KoG client is a reference implementation", path.read_text(), path.name)
        self.assertIn("reference implementation", build_site.DISCLAIMER)
        self.assertIn("fully supported", build_site.DISCLAIMER)
        self.assertIn("may change or break", build_site.DISCLAIMER)

    def test_best_effort_in_every_footer(self):
        for path in PAGES:
            with self.subTest(page=path.name):
                self.assertIn("Best effort only", " ".join(parse(path).text))

    def test_redirect_pages_show_the_banner_and_a_link(self):
        redirects = [p for p in PAGES if redirect_target(parse(p))]
        self.assertEqual(sorted(p.parent.name for p in redirects), ["changelog", "faq", "install", "updates", "verify"])
        for path in redirects:
            with self.subTest(page=path.parent.name):
                page = parse(path)
                target = redirect_target(page)
                self.assertTrue(target.startswith("https://client.kog.tw/"))
                local = target[len("https://client.kog.tw"):]
                self.assertIn(local, [r[2] for r in page.refs if r[0] == "a"])
                self.assertTrue([m for m in page.metas if m.get("name") == "robots" and m.get("content") == "noindex"])

    def test_navigation_has_the_five_entries_on_every_page(self):
        for path in PAGES:
            with self.subTest(page=path.name):
                hrefs = [r[2] for r in parse(path).refs if r[0] == "a"]
                for needed in ["https://github.com/KoG-teeworlds/kog-client", "https://kog.tw/", "https://kog.tw/clients"]:
                    self.assertIn(needed, hrefs)
                self.assertTrue(any(h.endswith("technical/") for h in hrefs))

    def test_home_page_sections(self):
        home = parse(SITE / "index.html")
        for fragment in ["download", "install", "install-windows", "install-macos", "install-linux", "safe", "faq", "faq-need", "faq-replace", "faq-login", "faq-data", "faq-update", "faq-problem", "faq-source"]:
            self.assertIn(fragment, home.ids)
        hrefs = [r[2] for r in home.refs if r[0] == "a"]
        for needed in [
            "https://kog.tw/",
            "https://kog.tw/clients",
            "https://github.com/KoG-teeworlds/kog-client",
            "technical/verify/",
            "technical/login/",
            "privacy/",
        ]:
            self.assertIn(needed, hrefs)

    def test_every_page_links_back_to_the_website(self):
        for path in PAGES:
            with self.subTest(page=path.name):
                hrefs = [r[2] for r in parse(path).refs if r[0] == "a"]
                self.assertIn("https://kog.tw/", hrefs)

    def test_external_links_go_to_known_hosts_only(self):
        known = {"kog.tw", "github.com", "ddnet.org", "cli.github.com", "docs.github.com"}
        for path in PAGES:
            with self.subTest(page=path.name):
                for tag, name, value, attrs in parse(path).refs:
                    if value.startswith("https://") and attrs.get("rel") != "canonical":
                        self.assertIn(urlparse(value).hostname, known, value)

    def test_the_404_page_leads_back(self):
        hrefs = [r[2] for r in parse(SITE / "404.html").refs if r[0] == "a"]
        self.assertIn("/", hrefs)
        self.assertIn("https://kog.tw/", hrefs)
        for tag, name, value, attrs in parse(SITE / "404.html").refs:
            if tag in ("link", "script", "img") and not value.startswith("https://"):
                self.assertTrue(value.startswith("/"), "the 404 page is served at any depth: " + value)

    def test_planned_things_are_marked_and_nothing_is_left_open(self):
        for path in PAGES:
            text = path.read_text()
            self.assertNotIn("TODO", text)
            self.assertNotIn("kog.tw/account", text)


# Every command on the technical pages (the blocks marked class="sh"), in the order of the pages, and the files of
# kog-client they name. Checked in both directions.
COMMANDS = [
    "sha256sum KoG-Client-linux.tar.xz",
    "shasum -a 256 KoG-Client-macOS.dmg",
    "Get-FileHash .\\KoG-Client-windows.zip -Algorithm SHA256",
    "gh attestation verify KoG-Client-linux.tar.xz -R KoG-teeworlds/kog-client",
    "git clone --depth 1 https://github.com/KoG-teeworlds/kog-client",
    "cd kog-client",
    "cc -O2 -o kogsign scripts/kog/kogsign.c src/engine/external/monocypher/monocypher.c src/engine/external/monocypher/monocypher-ed25519.c -Isrc/engine/external/monocypher",
    "curl -fsSO https://client.kog.tw/canary/update.json",
    "curl -fsSO https://client.kog.tw/canary/update.json.sig",
    'for k in $(python3 scripts/kog/keys_from_header.py ci canary); do ./kogsign verify "$k" update.json update.json.sig; done',
    "scripts/kog/verify_published.sh canary",
    "git clone https://github.com/KoG-teeworlds/kog-client",
    "cd kog-client",
    "git submodule update --init --recursive",
    "sudo apt-get install -y cmake glslang-tools libavcodec-dev libavformat-dev libavutil-dev libcurl4-openssl-dev libfreetype6-dev libglew-dev libnotify-dev libogg-dev libopus-dev libopusfile-dev libpng-dev libsdl2-dev libsqlite3-dev libssl-dev libswresample-dev libswscale-dev libvulkan-dev libwavpack-dev libx264-dev ninja-build pkg-config spirv-tools zlib1g-dev",
    "mkdir build",
    "cd build",
    "cmake .. -DCLIENT=ON -DSERVER=OFF -DTOOLS=OFF -DCMAKE_BUILD_TYPE=Release",
    "cmake --build . --target game-client",
    "brew install ffmpeg molten-vk ninja pkg-config sdl2",
    "cmake .. -A x64 -DCLIENT=ON -DSERVER=OFF -DTOOLS=OFF",
    "cmake --build . --config Release --target game-client",
    "cmake .. -DDOWNLOAD_GTEST=ON",
    "cmake --build . --target run_tests",
]
KOG_CLIENT_FILES = [
    "scripts/kog/kogsign.c",
    "scripts/kog/keys_from_header.py",
    "scripts/kog/verify_published.sh",
    "scripts/kog/verify_release.sh",
    "scripts/kog/approve_release.sh",
    "scripts/kog/publish_signed.sh",
    "scripts/kog/smoke_test.sh",
    "src/engine/external/monocypher/monocypher.c",
    "src/engine/external/monocypher/monocypher-ed25519.c",
    "src/engine/client/kog_update_pubkey.h",
    "src/engine/client/kog_keystore.cpp",
    "src/engine/client/updater.cpp",
    "src/engine/client/updater.h",
    "src/engine/shared/kog_update.cpp",
    "src/engine/shared/kog_update.h",
    "src/engine/shared/kog_failsafe.cpp",
    "src/engine/shared/kog_login.cpp",
    "src/engine/shared/kog_protocol.h",
    "src/engine/shared/config_variables_kog.h",
    "src/engine/shared/http_curl.cpp",
    "src/engine/http.h",
    "src/game/client/components/kog/kog_login.cpp",
    "src/game/client/components/kog/kog_hello.cpp",
    "src/game/client/components/menus_settings_ddnet.cpp",
    "src/test/kog_update_test.cpp",
    "src/test/kog_login_test.cpp",
    "src/test/kog_failsafe_test.cpp",
    "datasrc/network.py",
    ".github/workflows/kog-build.yml",
    ".github/workflows/kog-package.yml",
    "docs/UPDATE_CHANNEL.md",
    "docs/LOGIN.md",
    "docs/PRIVACY.md",
    "docs/BUILDING.md",
    "SECURITY.md",
    "NOTICE_KOG.md",
    "license.txt",
]


def technical_commands():
    lines = []
    for path in DOC_PAGES:
        for block in re.findall(r'<pre class="sh"[^>]*><code>(.*?)</code></pre>', path.read_text(), re.S):
            lines.extend(line for line in htmllib.unescape(block).split("\n") if line.strip())
    return lines


def doc_text(path):
    return htmllib.unescape(path.read_text())


class TechnicalPageTests(unittest.TestCase):
    def test_commands_on_the_pages_are_exactly_the_fixture_list(self):
        self.assertEqual(technical_commands(), COMMANDS)

    def test_files_named_in_commands_and_text_are_in_the_fixture(self):
        named = set(re.findall(r"(?<![\w/.-])((?:scripts|src|docs)/[\w./-]+\.(?:c|py|sh|h|md|cpp))", " ".join(COMMANDS)))
        for path in DOC_PAGES:
            named |= set(re.findall(r"(?<![\w/.-])(scripts/kog/[\w.-]+)", doc_text(path)))
            named |= set(re.findall(r"<code>(src/[\w./-]+\.(?:c|cpp|h))</code>", doc_text(path)))
        self.assertTrue(named)
        for name in named:
            self.assertIn(name, KOG_CLIENT_FILES)

    def test_fixture_files_exist_in_a_checkout_of_kog_client(self):
        checkout = os.environ.get("KOG_CLIENT_DIR")
        if not checkout:
            self.skipTest("set KOG_CLIENT_DIR to a checkout of kog-client")
        for name in KOG_CLIENT_FILES:
            self.assertTrue((Path(checkout) / name).exists(), name)

    def test_package_names_in_commands_match_the_download_script(self):
        script = (SITE / "assets" / "manifest.js").read_text()
        for name in re.findall(r"KoG-Client-[\w.]+", " ".join(COMMANDS)):
            self.assertIn(name, script)

    def test_planned_things_are_labelled_planned(self):
        for page, things in {
            "technical/protocol": ["kog_hello", "kog_telemetry"],
            "technical/roadmap": ["builds/allowlist.json", "Join proof", "Federated login", "Code signing"],
            "technical/index": ["builds/allowlist.json", "kog_hello", "kog_telemetry"],
        }.items():
            path = SITE / (page + "/index.html" if page != "technical/index" else "technical/index.html")
            text = path.read_text()
            for thing in things:
                around = text[max(0, text.index(thing) - 400): text.index(thing) + 800].lower()
                self.assertTrue("planned" in around or "partly built" in around, "%s: %s" % (page, thing))
        self.assertIn("not reproducible yet", " ".join(parse(SITE / "technical" / "build" / "index.html").text))
        self.assertIn("No such statement proves that a client is unmodified", " ".join(parse(SITE / "technical" / "roadmap" / "index.html").text))

    def test_old_urls_still_exist(self):
        for name in ["verify", "install", "updates", "faq", "changelog", "privacy"]:
            self.assertTrue((SITE / name / "index.html").exists(), name)

    def test_old_redirects_point_into_the_new_pages(self):
        expected = {"verify": "/technical/verify/", "updates": "/technical/update-channel/", "changelog": "/technical/roadmap/#history"}
        for name, target in expected.items():
            self.assertEqual(redirect_target(parse(SITE / name / "index.html")), "https://client.kog.tw" + target)


class DocsTests(unittest.TestCase):
    def pager(self, path):
        text = path.read_text()
        prev = re.findall(r'<a class="pager-prev" rel="prev" href="([^"]+)"', text)
        following = re.findall(r'<a class="pager-next" rel="next" href="([^"]+)"', text)
        return prev, following

    def test_every_technical_page_is_in_the_documentation_order(self):
        on_disk = {p for p in SITE.rglob("index.html") if p.relative_to(SITE).parts[0] == "technical"}
        redirects = {p for p in on_disk if redirect_target(parse(p))}
        self.assertEqual(on_disk - redirects, set(DOC_PAGES))
        self.assertEqual(len(build_site.DOCS_ORDER), len(set(build_site.DOCS_ORDER)))

    def test_pagination_links_form_one_chain_through_all_pages(self):
        names = build_site.DOCS_ORDER
        by_url = {}
        for name in names:
            path = SITE / name / "index.html"
            prev, following = self.pager(path)
            by_url[url_of(path)] = (prev, following)
            self.assertLessEqual(len(prev), 1)
            self.assertLessEqual(len(following), 1)
            for href in prev + following:
                self.assertTrue(target_file(resolve(url_of(path), href).path).exists(), href)
        order = [url_of(SITE / name / "index.html") for name in names]
        self.assertEqual(by_url[order[0]][0], [])
        self.assertEqual(by_url[order[-1]][1], [])
        walked, current = [], order[0]
        while current:
            self.assertNotIn(current, walked, "cycle at " + current)
            walked.append(current)
            following = by_url[current][1]
            current = resolve(current, following[0]).path if following else None
        self.assertEqual(walked, order)
        for position, url in enumerate(order):
            prev = by_url[url][0]
            if position:
                self.assertEqual(resolve(url, prev[0]).path, order[position - 1])
                self.assertEqual(resolve(order[position - 1], by_url[order[position - 1]][1][0]).path, url)

    def test_pager_cards_carry_the_titles_of_the_neighbours(self):
        order = build_site.DOCS_ORDER
        for position, name in enumerate(order):
            text = (SITE / name / "index.html").read_text()
            nav = re.search(r'<nav class="docs-nav".*?</nav>', text, re.S).group(0)
            titles = {href: label for href, label in re.findall(r'<a href="[^"]*?(technical(?:/[\w-]+)?)/"[^>]*>([^<]*)</a>', nav)}
            for rel, step in (("prev", -1), ("next", 1)):
                card = re.search(r'rel="%s" href="[^"]+"><span class="pager-label">[^<]*</span><span class="pager-title">([^<]*)</span>' % rel, text)
                if 0 <= position + step < len(order):
                    self.assertEqual(htmllib.unescape(card.group(1)), htmllib.unescape(titles[order[position + step]]))
                else:
                    self.assertIsNone(card)

    def test_every_page_has_the_sidebar_with_every_page_and_marks_its_own(self):
        expected = {url_of(p) for p in DOC_PAGES}
        for path in DOC_PAGES:
            with self.subTest(page=url_of(path)):
                text = path.read_text()
                nav = re.search(r'<nav class="docs-nav".*?</nav>', text, re.S).group(0)
                hrefs = {resolve(url_of(path), h).path for h in re.findall(r'<a href="([^"]+)"', nav)}
                self.assertEqual(hrefs, expected)
                current = re.findall(r'<a href="([^"]+)" aria-current="page"', nav)
                self.assertEqual([resolve(url_of(path), h).path for h in current], [url_of(path)])
                self.assertIn('<summary>Contents</summary>', nav)

    REFERENCE = ["technical", "technical/glossary"]

    def test_status_badges_are_only_on_feature_pages(self):
        for name in build_site.DOCS_ORDER:
            text = (SITE / name / "index.html").read_text()
            nav = re.search(r'<nav class="docs-nav".*?</nav>', text, re.S).group(0)
            head = re.search(r'<header class="doc-head">.*?</header>', text, re.S).group(0)
            if name in self.REFERENCE:
                self.assertNotIn("Built", head.split('<aside')[0], name)
                self.assertNotRegex(head, r"<dt>Status</dt>", name)
                self.assertNotRegex(nav, r'<a href="[^"]*/%s/"[^>]*>[^<]*</a> <span class="state' % re.escape(name.split("/")[-1] if "/" in name else "technical"), name)
            else:
                self.assertRegex(head, r'<h1>[^<]*<span class="state', name)
                self.assertRegex(head, r"<dt>Status</dt>", name)
        for name in ["architecture", "update-channel", "release-signing", "verify", "login", "protocol", "privacy", "build", "security", "roadmap"]:
            self.assertIn("technical/" + name, build_site.DOCS_ORDER)
            self.assertNotIn("technical/" + name, self.REFERENCE)

    def test_only_the_first_diagram_of_a_page_loads_eagerly(self):
        for path in DOC_PAGES:
            imgs = re.findall(r"<img src=\"[^\"]*diagrams[^>]*>", path.read_text())
            for position, tag in enumerate(imgs):
                self.assertEqual('loading="lazy"' in tag, position > 0, tag)
                self.assertIn("width=", tag)
                self.assertIn("height=", tag)

    def test_breadcrumb_toc_edit_link_and_skip_target(self):
        for path in DOC_PAGES:
            with self.subTest(page=url_of(path)):
                text = path.read_text()
                self.assertIn('<nav class="crumbs" aria-label="Breadcrumb">', text)
                self.assertEqual(text.count('aria-current="page">'), text.count('<li aria-current="page">') + len(re.findall(r'<a href="[^"]+" aria-current="page"', text)))
                self.assertIn('<main id="main" class="doc">', text)
                edit = re.search(r'<a href="(https://github\.com/KoG-teeworlds/kog-client-updates/edit/main/([^"]+))">Edit this page on GitHub', text)
                self.assertIsNotNone(edit)
                self.assertTrue((ROOT / edit.group(2)).exists(), edit.group(2))
                page = parse(path)
                if "<h2" in text and len(re.findall(r"<h[23]", text)) >= 2:
                    toc = re.search(r'<aside class="docs-toc".*?</aside>', text, re.S).group(0)
                    for target in re.findall(r'href="#([^"]+)"', toc):
                        self.assertIn(target, page.ids)

    def test_headings_have_anchor_links_to_existing_ids(self):
        for path in DOC_PAGES:
            with self.subTest(page=url_of(path)):
                page = parse(path)
                text = path.read_text()
                for ident in re.findall(r'<h[23] [^>]*id="([^"]+)"[^>]*>.*?<a class="anchor" href="#([^"]+)"', text, re.S):
                    self.assertEqual(ident[0], ident[1])
                    self.assertIn(ident[0], page.ids)
                self.assertEqual(len(re.findall(r"<h[23]", text)), len(re.findall(r'class="anchor"', text)))

    def test_tables_are_in_scrolling_regions_and_code_blocks_are_focusable(self):
        for path in DOC_PAGES:
            text = path.read_text()
            self.assertEqual(text.count("<table"), text.count('<div class="table-scroll"'), path)
            for tag in re.findall(r"<pre[^>]*>", text):
                self.assertIn('tabindex="0"', tag)

    def test_diagram_figures_have_text_alternatives_and_sources(self):
        used = set()
        for path in DOC_PAGES:
            text = path.read_text()
            for figure in re.findall(r'<figure class="diagram[ "].*?</figure>', text, re.S):
                alt = re.search(r'<img src="([^"]+)" alt="([^"]+)" width="(\d+)" height="(\d+)"', figure)
                self.assertIsNotNone(alt, figure[:200])
                self.assertGreater(len(alt.group(2)), 40)
                self.assertIn("<figcaption>", figure)
                self.assertIn('<details class="diagram-src"><summary>', figure)
                self.assertIn('<pre class="mermaid-src" tabindex="0"><code>', figure)
                dark = re.search(r'<source media="\(prefers-color-scheme: dark\)" srcset="([^"]+)"', figure).group(1)
                for ref in (alt.group(1), dark):
                    file = target_file(resolve(url_of(path), ref).path)
                    self.assertTrue(file.exists(), ref)
                    used.add(file.name.rsplit("-", 1)[0])
        self.assertEqual(used, {p.stem for p in (ROOT / "diagrams").glob("*.mmd")})
        for name in used:
            self.assertGreaterEqual(len(used), 6)

    def test_the_six_wanted_diagrams_exist_on_their_pages(self):
        wanted = {
            "technical/architecture": "architecture",
            "technical/update-channel": "update-flow",
            "technical/login": "login",
            "technical/release-signing": "release-signing",
            "technical/protocol": None,
        }
        for page, diagram in wanted.items():
            if diagram:
                self.assertIn("figure-" + diagram, (SITE / page / "index.html").read_text())
        self.assertIn("figure-join-proof", (SITE / "technical/login/index.html").read_text())
        self.assertIn("figure-channel-keys", (SITE / "technical/update-channel/index.html").read_text())

    def test_diagram_files_are_safe_current_and_in_both_themes(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / "render_diagrams.py"), "--check"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for source in (ROOT / "diagrams").glob("*.mmd"):
            for theme in ("light", "dark"):
                text = (SITE / "assets" / "diagrams" / ("%s-%s.svg" % (source.stem, theme))).read_text()
                self.assertTrue(text.startswith("<svg"))
                self.assertNotIn("<script", text)
                self.assertNotIn("onload", text)
                self.assertIsNone(re.search(r"(href|src)=\"https?://", text))
                self.assertNotIn("foreignObject", text)
            self.assertNotEqual((SITE / "assets" / "diagrams" / (source.stem + "-light.svg")).read_text(), (SITE / "assets" / "diagrams" / (source.stem + "-dark.svg")).read_text())

    def test_search_index_covers_every_page_and_its_headings(self):
        import json

        index = json.loads((SITE / "assets" / "search-index.json").read_text())
        self.assertEqual([e["u"] for e in index], [url_of(p) for p in DOC_PAGES])
        for entry, path in zip(index, DOC_PAGES):
            ids = parse(path).ids
            self.assertTrue(entry["t"] and entry["d"])
            for ident, text in entry["h"]:
                self.assertIn(ident, ids)
                self.assertTrue(text)
        self.assertLess((SITE / "assets" / "search-index.json").stat().st_size, 16 * 1024)

    def test_the_overview_maps_every_page_with_a_status(self):
        text = (SITE / "technical" / "index.html").read_text()
        for name in build_site.DOCS_ORDER[1:]:
            self.assertIn('href="/%s/"' % name, text, name)
        for state in ("built", "partial", "planned"):
            self.assertIn('class="state %s"' % state, text)

    def test_old_single_page_anchors_are_mapped_by_the_script(self):
        script = (SITE / "assets" / "docs.js").read_text()
        for old in ["verify", "login", "privacy", "messages", "repro", "build", "signing", "security", "history", "manifest", "channels", "endpoints"]:
            self.assertRegex(script, r"\b%s:|\"%s\":" % (old, old))
        self.assertIn('data-overview=""', (SITE / "technical" / "index.html").read_text())


# Words that must not appear on a public page of this site: it documents the client only. An exception goes in
# ALLOWED below with the reason, never into the list or the page.
DENY = [
    "kog-2.0-server", "backend", "gateway", "edgeservice", "rabbitmq", "redis", "mariadb", "haproxy", "argo", "kubernetes",
    "hetzner", "protobuf", "message bus", "web2", "antibot", "teehistorian", "rcon", "infra-github", "opentofu", "master server",
    "temp_backend", "cloudflare",
]
ALLOWED = {
    # (path relative to site/, word): reason
}


class ClientOnlyTests(unittest.TestCase):
    def texts(self):
        for path in SITE.rglob("*"):
            if path.is_file() and path.suffix in (".html", ".js", ".json", ".svg", ".xml", ".txt", ".css"):
                yield path.relative_to(SITE).as_posix(), path.read_text()
        for path in (ROOT / "diagrams").glob("*.mmd"):
            yield "diagrams/" + path.name, path.read_text()

    def test_no_server_implementation_is_mentioned_on_any_page(self):
        for name, text in self.texts():
            for word in DENY:
                if (name, word) in ALLOWED:
                    continue
                with self.subTest(file=name, word=word):
                    self.assertIsNone(re.search(r"(?<![\w-])" + re.escape(word) + r"(?![\w])", text, re.I), "%s mentions %s" % (name, word))

    def test_no_private_repository_is_linked(self):
        for name, text in self.texts():
            for repo in re.findall(r"github\.com/KoG-teeworlds/([\w.-]+)", text):
                with self.subTest(file=name, repo=repo):
                    self.assertIn(repo, ("kog-client", "kog-client-updates"))
            self.assertNotRegex(text, r"/pull/\d+")

    def test_the_deny_list_itself_is_not_weakened(self):
        self.assertEqual(ALLOWED, {})


HOME_COMMANDS = {
    "windows": [
        "$m = Invoke-RestMethod https://client.kog.tw/canary/update.json",
        "$want = ($m.packages | Where-Object name -eq 'KoG-Client-windows.zip').sha256",
        "$have = (Get-FileHash .\\KoG-Client-windows.zip -Algorithm SHA256).Hash",
        "if ($have -eq $want) { 'OK: the file matches the list' } else { 'DIFFERENT: do not open the file' }",
    ],
    "macos": [
        "echo \"$(curl -fsSL https://client.kog.tw/canary/update.json | grep -A1 '\"KoG-Client-macOS.dmg\"' | grep -o '[0-9a-f]\\{64\\}')  KoG-Client-macOS.dmg\" | shasum -a 256 -c",
    ],
    "linux": [
        "echo \"$(curl -fsSL https://client.kog.tw/canary/update.json | grep -A1 '\"KoG-Client-linux.tar.xz\"' | grep -o '[0-9a-f]\\{64\\}')  KoG-Client-linux.tar.xz\" | sha256sum -c",
    ],
}


class HomeCheckTests(unittest.TestCase):
    def test_the_home_page_needs_no_github_cli_and_shows_one_command_per_system(self):
        home = (SITE / "index.html").read_text()
        self.assertNotRegex(home, r"\bgh (attestation|release|api)")
        found = {}
        for system, block in re.findall(r'<div class="vpanel" data-os="(\w+)">\s*<pre class="sh" tabindex="0"><code>(.*?)</code></pre>', home, re.S):
            found[system] = [line for line in htmllib.unescape(block).split("\n") if line.strip()]
        self.assertEqual(found, HOME_COMMANDS)
        packages = set(re.findall(r"KoG-Client-[\w.]+", (SITE / "assets" / "manifest.js").read_text()))
        for lines in HOME_COMMANDS.values():
            for name in re.findall(r"KoG-Client-[\w.]+", " ".join(lines)):
                self.assertIn(name, packages)

    def test_the_command_blocks_follow_the_system_switch_without_script(self):
        css = (SITE / "assets" / "style.css").read_text()
        for system in ("windows", "macos", "linux"):
            self.assertIn('#tab-%s:checked ~ #safe .vpanel[data-os="%s"]' % (system, system), css)
        home = (SITE / "index.html").read_text()
        self.assertEqual(len(re.findall(r'type="radio" name="os"', home)), 3)
        self.assertEqual(len(re.findall(r'type="radio" name="channel"', home)), 3)
        # the radios are siblings of the sections they switch, so no script is needed
        tabs = re.search(r'<div class="tabs">(.*?)<details class="good">', home, re.S).group(1)
        self.assertEqual(tabs.count('name="os"'), 3)

    def test_the_gh_command_stays_on_the_verify_page_as_an_optional_extra(self):
        text = (SITE / "technical" / "verify" / "index.html").read_text()
        self.assertIn("gh attestation verify", text)
        self.assertRegex(text, r"(?i)optional")

    def test_channel_choice_is_remembered_with_guarded_storage_and_a_stable_default(self):
        script = (SITE / "assets" / "app.js").read_text()
        for needle in ('"kog-channel"', "localStorage.getItem", "localStorage.setItem", 'load("stable", true)', "Nothing is published on the development channel yet.", "There is no stable version yet"):
            self.assertIn(needle, script)
        for match in re.finditer(r"localStorage", script):
            before = script[max(0, match.start() - 120): match.start()]
            self.assertIn("try {", before)


class WeightTests(unittest.TestCase):
    def test_total_weight_of_html_css_and_js_stays_under_budget(self):
        total = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file() and p.suffix in (".html", ".css", ".js"))
        self.assertLess(total, BUDGET_TOTAL)

    def test_one_page_load_stays_under_budget(self):
        base = sum((SITE / "assets" / name).stat().st_size for name in ["style.css", "kog-logo.svg"])
        for path in PAGES:
            with self.subTest(page=url_of(path)):
                scripts = sum((path.parent / ref).resolve().stat().st_size for ref in parse(path).scripts)
                if path in DOC_PAGES:
                    text = path.read_text()
                    pictures = sum(
                        max((SITE / ("assets/diagrams/%s-%s.svg" % (name, theme))).stat().st_size for theme in ("light", "dark"))
                        for name in re.findall(r'id="figure-([\w-]+)"', text)
                    )
                    self.assertLess(path.stat().st_size + base + scripts + pictures, BUDGET_DOC_PAGE)
                else:
                    self.assertLess(path.stat().st_size + base + scripts, BUDGET_PAGE)

    def test_no_script_is_a_library(self):
        for name in ["app.js", "manifest.js", "docs.js"]:
            self.assertLess((SITE / "assets" / name).stat().st_size, BUDGET_SCRIPT, name)


class ScriptTests(unittest.TestCase):
    FORBIDDEN = [r"\.innerHTML", r"\.outerHTML", r"insertAdjacentHTML", r"\beval\s*\(", r"new\s+Function", r"document\.write", r"setTimeout\s*\(\s*[\"']", r"setInterval\s*\(\s*[\"']", r"\.srcdoc", r"createContextualFragment", r"importScripts", r"XMLHttpRequest", r"localStorage", r"sessionStorage", r"document\.cookie"]

    def test_scripts_use_no_dangerous_apis(self):
        for name in ["app.js", "manifest.js", "docs.js"]:
            code = (SITE / "assets" / name).read_text()
            for pattern in self.FORBIDDEN:
                if pattern == r"localStorage" and name == "app.js":
                    continue  # the channel choice; every access is inside try, see HomeCheckTests
                with self.subTest(file=name, pattern=pattern):
                    self.assertIsNone(re.search(pattern, code))

    def test_scripts_make_no_third_party_requests(self):
        for name in ["app.js", "manifest.js", "docs.js"]:
            code = (SITE / "assets" / name).read_text()
            for url in re.findall(r"https?://[^\"'\s)]+", code):
                with self.subTest(file=name, url=url):
                    self.assertTrue(url == "https://github.com" or url.startswith("https://github.com/KoG-teeworlds/"), url)

    def test_home_page_loads_only_the_two_local_scripts(self):
        self.assertEqual(parse(SITE / "index.html").scripts, ["assets/manifest.js", "assets/app.js"])
        for path in PAGES:
            if path in DOC_PAGES:
                self.assertEqual(parse(path).scripts, [("../" * (len(path.relative_to(SITE).parts) - 1)) + "assets/docs.js"], path)
            elif path.name != "index.html" or path.parent != SITE:
                self.assertEqual(parse(path).scripts, [], path)


class StyleTests(unittest.TestCase):
    def test_text_contrast_meets_aa_in_both_themes(self):
        light, dark = theme_variables()
        pairs = [("fg", "bg"), ("fg", "surface"), ("muted", "bg"), ("muted", "surface"), ("link", "bg"), ("link", "surface"), ("link", "warn-bg"), ("fg", "warn-bg"), ("btn-fg", "btn-bg"), ("fg", "code-bg"), ("link", "code-bg"), ("muted", "code-bg"), ("head-fg", "head-bg"), ("head-link", "head-bg"), ("badge-fg", "badge-bg"), ("muted", "warn-bg"), ("link", "surface"), ("partial-fg", "partial-bg"), ("fg", "note-bg"), ("link", "note-bg"), ("muted", "note-bg"), ("fg", "code-bg")]
        for name, theme in (("light", light), ("dark", dark)):
            for foreground, background in pairs:
                with self.subTest(theme=name, pair=foreground + "/" + background):
                    self.assertGreaterEqual(contrast(theme[foreground], theme[background]), 4.5)

    def test_the_documentation_area_is_fluid_up_to_at_least_1800_px(self):
        css = (SITE / "assets" / "style.css").read_text()
        checked = 0
        for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css):
            names = [n.strip() for n in selector.split(",")]
            if not any(n in (".docs", ".doc", ".wrap", ".docs.no-toc") for n in names):
                continue
            for value in re.findall(r"(?<![-\w])max-width:\s*([^;]+)", body):
                checked += 1
                value = value.strip()
                if value == "none":
                    continue
                match = re.fullmatch(r"([\d.]+)(rem|px)", value)
                self.assertIsNotNone(match, "%s max-width %s" % (selector, value))
                pixels = float(match.group(1)) * (16 if match.group(2) == "rem" else 1)
                self.assertGreaterEqual(pixels, 1800, "%s caps the article at %s" % (selector.strip(), value))
        self.assertGreaterEqual(checked, 1)
        self.assertIn("grid-template-columns: 16rem minmax(0, 1fr) 13.5rem", css)

    def test_one_container_rule_for_every_page(self):
        css = (SITE / "assets" / "style.css").read_text()
        rules = [(sel.strip(), body) for sel, body in re.findall(r"([^{}]+)\{([^{}]*)\}", css) if ".wrap" in sel]
        self.assertEqual([sel for sel, _ in rules], [".wrap"], "only one rule may style the container: " + str(rules))
        self.assertIn("max-width: 120rem", rules[0][1])
        self.assertIn("padding-left: clamp(1rem, 2.5vw, 3rem)", rules[0][1])
        self.assertIn("scrollbar-gutter: stable", css)

    def test_secondary_text_has_high_contrast_in_both_themes(self):
        light, dark = theme_variables()
        for name, theme in (("light", light), ("dark", dark)):
            for foreground, background in [("fg", "bg"), ("fg", "surface"), ("muted", "bg"), ("muted", "surface"), ("muted", "code-bg")]:
                with self.subTest(theme=name, pair=foreground + "/" + background):
                    self.assertGreaterEqual(contrast(theme[foreground], theme[background]), 7.0)
            for foreground, background in [("link", "bg"), ("link", "surface")]:
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
