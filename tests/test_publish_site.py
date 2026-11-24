import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import publish_site  # noqa: E402

NAMES = publish_site.pages()


def run_git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


def write(base, files):
    for name, text in files.items():
        path = Path(base) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


class AllowlistTest(unittest.TestCase):
    def test_site_files_are_allowed(self):
        for path in ["index.html", "404.html", "CNAME", ".nojekyll", "favicon.svg", "robots.txt", "sitemap.xml",
                     "assets/style.css", "assets/sub/x.js", "faq/index.html", "verify/index.html"]:
            self.assertTrue(publish_site.allowed(path, NAMES), path)

    def test_release_data_is_not_allowed(self):
        for path in ["canary/update.json", "canary/update.json.sig", "canary/releases/0.1.0/update.json", "dev/update.json",
                     "stable/update.json.sigb", "builds/x.zip", "releases.json", "base/update.json", "releases/index.html",
                     "canary/index.html", "assets/../canary/update.json", "../index.html", "/index.html", ".git/config",
                     "unknown.txt", "faq/other.html", "faq/deeper/index.html", "unknown/index.html"]:
            self.assertFalse(publish_site.allowed(path, NAMES), path)

    def test_every_page_of_the_site_is_allowed(self):
        for name in NAMES:
            self.assertTrue(publish_site.allowed(name + "/index.html", NAMES))
        for path in (ROOT / "site").rglob("*"):
            if path.is_file():
                self.assertTrue(publish_site.allowed(path.relative_to(ROOT / "site").as_posix(), NAMES), path)


class PublishTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.stage = Path(self.tmp.name) / "stage"
        self.pub = Path(self.tmp.name) / "pub"
        self.stage.mkdir()
        self.pub.mkdir()
        run_git(self.pub, "init", "-q", "-b", "published")
        run_git(self.pub, "config", "user.name", "t")
        run_git(self.pub, "config", "user.email", "t@example.org")
        write(self.pub, {"index.html": "old", "assets/old.js": "old", "faq/index.html": "old",
                         "canary/update.json": "manifest", "canary/releases/1/update.json": "manifest",
                         "stable/update.json": "stable", "releases.json": "{}"})
        run_git(self.pub, "add", "-A")
        run_git(self.pub, "commit", "-q", "-m", "start")

    def changed(self):
        return sorted(run_git(self.pub, "diff", "--cached", "--name-only").split())

    def test_only_site_files_change(self):
        write(self.stage, {"index.html": "new", "assets/new.js": "new", "faq/index.html": "new", "CNAME": "client.kog.tw"})
        self.assertEqual(publish_site.publish(self.stage, self.pub, NAMES), 0)
        self.assertEqual(self.changed(), ["CNAME", "assets/new.js", "assets/old.js", "faq/index.html", "index.html"])
        self.assertEqual((self.pub / "canary/update.json").read_text(), "manifest")
        self.assertEqual((self.pub / "stable/update.json").read_text(), "stable")
        self.assertEqual((self.pub / "releases.json").read_text(), "{}")
        self.assertFalse((self.pub / "assets/old.js").exists())

    def test_a_changed_channel_file_is_refused(self):
        write(self.stage, {"index.html": "new", "canary/update.json": "forged"})
        self.assertEqual(publish_site.publish(self.stage, self.pub, NAMES), 1)
        self.assertEqual((self.pub / "canary/update.json").read_text(), "manifest")
        self.assertEqual((self.pub / "index.html").read_text(), "old")
        self.assertEqual(self.changed(), [])

    def test_new_channel_directories_and_data_files_are_refused(self):
        for path in ["dev/update.json", "builds/a.zip", "releases.json", "stable/releases/2/update.json", "other.txt"]:
            stage = Path(self.tmp.name) / ("stage-" + path.replace("/", "_"))
            write(stage, {"index.html": "new", path: "x"})
            self.assertEqual(publish_site.publish(stage, self.pub, NAMES), 1, path)
        self.assertEqual(self.changed(), [])

    def test_a_stray_change_outside_the_site_found_by_git_is_refused(self):
        write(self.stage, {"index.html": "new"})
        (self.pub / "releases.json").write_text("changed under our feet")
        self.assertEqual(publish_site.publish(self.stage, self.pub, NAMES), 1)
        self.assertEqual(self.changed(), [])

    def test_the_site_removes_its_own_old_files_only(self):
        write(self.stage, {"index.html": "new"})
        self.assertEqual(publish_site.publish(self.stage, self.pub, NAMES), 0)
        self.assertFalse((self.pub / "faq/index.html").exists())
        self.assertTrue((self.pub / "canary/releases/1/update.json").exists())


class MarkerTest(unittest.TestCase):
    def build(self, *args):
        with tempfile.TemporaryDirectory() as out:
            subprocess.run([sys.executable, "-B", str(ROOT / "scripts/build_site.py"), "--out", out, *args], check=True)
            return (Path(out) / "index.html").read_text(), (Path(out) / "faq/index.html").read_text()

    def test_marker_is_in_every_page_only_when_asked(self):
        for text in self.build("--marker", "abc123"):
            self.assertIn('<meta name="kog-site-build" content="abc123">', text)
        for text in self.build():
            self.assertNotIn("kog-site-build", text)

    def test_committed_site_has_no_marker(self):
        for path in (ROOT / "site").rglob("*.html"):
            self.assertNotIn("kog-site-build", path.read_text())


if __name__ == "__main__":
    unittest.main()
