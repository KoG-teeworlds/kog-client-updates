# kog-client-updates
Signed update manifest and download page of the KoG client

## The website

`content/` holds the pages (HTML fragments with a few `@key value` lines on top), `scripts/build_site.py` builds them into `site/`, and a merge to `main` publishes them. Run `python3 scripts/build_site.py` after a change and commit the result.

The documentation is `content/technical/`. The order of its pages (the sidebar and the Previous and Next links) is `DOCS` in `scripts/build_site.py`. Diagrams are Mermaid text in `diagrams/NAME.mmd`; `scripts/render_diagrams.py` renders them to `site/assets/diagrams/` (needs Node and Chrome, `CHROME_PATH`) and the SVGs are committed. Put `<!-- diagram NAME -->` in a page to show one. The pages describe the client only: a test fails on words that belong to server software.
