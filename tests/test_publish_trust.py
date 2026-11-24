import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import publish_trust  # noqa: E402

# made by web2 (tests/Unit/TrustBundleTest.php), the same bytes as in the tests of the client
BUNDLE = '{"v":1,"payload":"eyJ2IjoxLCJlbnZpcm9ubWVudCI6InByb2R1Y3Rpb24iLCJzZXEiOjcsImlzc3VlZF9hdCI6MTgwMDAwMDAwMCwiZXhwaXJlc19hdCI6MTgwMDE3MjgwMCwiYW5jaG9ycyI6eyJ2MSI6IitXU3pLcWVSS1lpL0x4SExxV0JJTnJSKzROKzJ5Y2RlQlhTK2VBY2NWMWM9In0sInJldm9rZWQiOlt7InN1YmplY3RfaWQiOiJrb2ctcmV2b2tlZC0xIiwicHVia2V5X3NoYTI1NiI6IjJkNzExNjQyYjcyNmIwNDQwMTYyN2NhOWZiYWMzMmY1Yzg1MzBmYjE5MDNjYzRkYjAyMjU4NzE3OTIxYTQ4ODEiLCJzaW5jZSI6MTc5OTk5MDAwMH1dfQ==","sig":{"v1":"EsjzaL56aaTBaPPfcHS0kUgukp0Sfp2XvmmCEsnba0vSEo7YsCYS8pSGXHB8m4aK8EXv7IHRsAWf/PUgkS7aDw=="}}'
ANCHOR = "f964b32aa7912988bf2f11cba9604836b47ee0dfb6c9c75e0574be78071c5757"
OTHER = "2152f8d19b791d24453242e15f2eab6cb7cffa7b6a5ed30097960e069881db12"
NOW = 1800000100


def newer(text, seq):
    """The same list with another sequence number: the signature no longer fits, so only for the rollback test."""
    import base64
    served = json.loads(text)
    document = json.loads(base64.b64decode(served["payload"]))
    document["seq"] = seq
    served["payload"] = base64.b64encode(json.dumps(document).encode()).decode()
    return json.dumps(served)


class Check(unittest.TestCase):
    def test_a_signed_list_of_the_channel_is_accepted(self):
        ok, why, seq = publish_trust.check("stable", BUNDLE, {"production": [ANCHOR]}, 0, NOW)
        self.assertEqual((ok, why, seq), (True, "ok", 7))

    def test_every_refusal(self):
        anchors = {"production": [ANCHOR], "canary": [ANCHOR]}
        cases = [
            ("canary", BUNDLE, anchors, 0, NOW, "wrong environment"),
            ("beta", BUNDLE, anchors, 0, NOW, "unknown channel"),
            ("stable", BUNDLE, {"production": []}, 0, NOW, "no anchor"),
            ("stable", BUNDLE, {}, 0, NOW, "no anchor"),
            ("stable", BUNDLE, {"production": [OTHER]}, 0, NOW, "not signed"),
            ("stable", BUNDLE, anchors, 7, NOW, "not newer"),
            ("stable", BUNDLE, anchors, 0, 1800172801, "expired"),
            ("stable", "{}", anchors, 0, NOW, "not a trust list"),
            ("stable", "not json", anchors, 0, NOW, "not a trust list"),
            ("stable", BUNDLE + " " * (publish_trust.MAX_SIZE + 1), anchors, 0, NOW, "too big"),
            ("stable", newer(BUNDLE, 99), anchors, 0, NOW, "not signed"),
        ]
        for channel, text, keys, held, now, expected in cases:
            ok, why, _ = publish_trust.check(channel, text, keys, held, now)
            self.assertFalse(ok, expected)
            self.assertIn(expected, why)

    def test_the_committed_anchors_are_well_formed(self):
        anchors = json.loads((ROOT / "trust" / "anchors.json").read_text())
        self.assertEqual(sorted(anchors), ["canary", "dev", "production"])
        for keys in anchors.values():
            for key in keys:
                self.assertEqual(len(bytes.fromhex(key)), 32)

    def test_the_mirror_path_is_no_page_of_the_site(self):
        import publish_site
        for name in publish_site.pages():
            self.assertNotEqual(name.split("/")[0], "list")
        self.assertFalse(publish_site.allowed("list/stable/trust.json", publish_site.pages()), "the site job never writes the list")


class Publish(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.pub = Path(self.tmp.name) / "pub"
        self.pub.mkdir()
        for args in (["init", "-q", "-b", "published"], ["config", "user.name", "t"], ["config", "user.email", "t@example.org"]):
            subprocess.run(["git", "-C", str(self.pub), *args], check=True)
        (self.pub / "stable").mkdir()
        (self.pub / "stable" / "update.json").write_text("manifest")
        (self.pub / "index.html").write_text("site")
        subprocess.run(["git", "-C", str(self.pub), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(self.pub), "commit", "-q", "-m", "x"], check=True)
        self.file = Path(self.tmp.name) / "trust.json"
        self.file.write_text(BUNDLE)

    def staged(self):
        return subprocess.run(["git", "-C", str(self.pub), "diff", "--cached", "--name-only"], capture_output=True, text=True).stdout.split()

    def test_only_the_list_of_the_channel_changes(self):
        self.assertEqual(publish_trust.publish("stable", self.file, self.pub, {"production": [ANCHOR]}, NOW), 0)
        self.assertEqual(self.staged(), ["list/stable/trust.json"])
        self.assertEqual((self.pub / "stable" / "update.json").read_text(), "manifest")

    def test_an_older_list_does_not_replace_a_newer_one(self):
        anchors = {"production": [ANCHOR]}
        self.assertEqual(publish_trust.publish("stable", self.file, self.pub, anchors, NOW), 0)
        subprocess.run(["git", "-C", str(self.pub), "commit", "-q", "-m", "list"], check=True)
        self.assertEqual(publish_trust.publish("stable", self.file, self.pub, anchors, NOW), 1, "the same sequence number again")

    def test_without_an_anchor_nothing_is_written(self):
        self.assertEqual(publish_trust.publish("stable", self.file, self.pub, {"production": []}, NOW), 1)
        self.assertFalse((self.pub / "list").exists())


if __name__ == "__main__":
    unittest.main()
