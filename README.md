# kog-client-updates
Signed update manifest and download page of the KoG client

## The website

`content/` holds the pages (HTML fragments with a few `@key value` lines on top), `scripts/build_site.py` builds them into `site/`, and a merge to `main` publishes them. Run `python3 scripts/build_site.py` after a change and commit the result.

The documentation is `content/technical/`. The order of its pages (the sidebar and the Previous and Next links) is `DOCS` in `scripts/build_site.py`. Diagrams are Mermaid text in `diagrams/NAME.mmd`; `scripts/render_diagrams.py` renders them to `site/assets/diagrams/` (needs Node and Chrome, `CHROME_PATH`) and the SVGs are committed. Put `<!-- diagram NAME -->` in a page to show one. The pages describe the client only: a test fails on words that belong to server software.

## The trust list

`list/<channel>/trust.json` on client.kog.tw is a small signed file that the client reads to check the certificate of a KoG server (client side: `docs/SERVER-CERTIFICATES.md` in kog-client). It is put on the branch published by `.github/workflows/trust-mirror.yml` when it changes (an event, no timer). `scripts/publish_trust.py` publishes only a file that is signed by a key in `trust/anchors.json` for the channel, for the right environment, not expired and with a higher sequence number than the one there; a channel with no key committed publishes nothing. The keys are public; they are written here by the organisation's infrastructure repository, not by hand. No page of the site describes this file.
