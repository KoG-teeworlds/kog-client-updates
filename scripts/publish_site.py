#!/usr/bin/env python3
"""Puts the built site into a checkout of the branch published and touches nothing else.

usage: publish_site.py STAGE PUBLISHED
STAGE is the built site, PUBLISHED a git checkout of the branch published. Files of the site are copied over,
site files that are gone from STAGE are removed, the result is staged with git add. The signed manifests and the
release data (canary/, dev/, stable/, releases.json and everything else publish_signed.sh of kog-client writes) are
not in the allowlist: a file outside it in STAGE, or a change outside it in the checkout, stops the script with exit 1.
"""
import shutil
import subprocess
import sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent.parent
ROOT_FILES = {"index.html", "404.html", "CNAME", ".nojekyll", "favicon.svg", "robots.txt", "sitemap.xml"}
RESERVED = {"stable", "canary", "dev", "base", "releases", "builds", "releases.json"}


def pages(content=ROOT / "content"):
    """Names of the pages with their own address: faq, technical, technical/login."""
    names = set()
    for path in content.rglob("*.html"):
        name = path.relative_to(content).with_suffix("").as_posix()
        names.add(name[: -len("/index")] if name.endswith("/index") else name)
    return {n for n in names if n not in ("index", "404") and n.split("/")[0] not in RESERVED}


def allowed(path, names):
    parts = PurePosixPath(path).parts
    if not parts or ".." in parts or PurePosixPath(path).is_absolute() or parts[0] in RESERVED or ".git" in parts:
        return False
    if len(parts) == 1:
        return parts[0] in ROOT_FILES
    if parts[0] == "assets":
        return True
    return len(parts) >= 2 and parts[-1] == "index.html" and "/".join(parts[:-1]) in names


def files(base):
    return sorted(p.relative_to(base).as_posix() for p in base.rglob("*") if p.is_file() and ".git" not in p.relative_to(base).parts)


def git(published, *args):
    return subprocess.run(["git", "-C", str(published), *args], check=True, capture_output=True, text=True).stdout


def publish(stage, published, names):
    stage, published = Path(stage), Path(published)
    staged = files(stage)
    refused = [f for f in staged if not allowed(f, names)]
    if refused:
        print("refused, not part of the site: " + ", ".join(refused), file=sys.stderr)
        return 1
    for f in files(published):
        if allowed(f, names) and f not in staged:
            (published / f).unlink()
    for f in staged:
        target = published / f
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(stage / f, target)
    git(published, "add", "-A")
    changed = [f for f in git(published, "diff", "--cached", "--name-only", "-z").split("\0") if f]
    outside = [f for f in changed if not allowed(f, names)]
    if outside:
        git(published, "reset", "--quiet")
        print("refused, would change files outside the site: " + ", ".join(outside), file=sys.stderr)
        return 1
    print("site files changed: %d" % len(changed))
    return 0


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    return publish(sys.argv[1], sys.argv[2], pages())


if __name__ == "__main__":
    sys.exit(main())
