#!/usr/bin/env python3
"""Warn about canonical links that point at pages another doc set doesn't publish.

A page copied from another doc set can name that set's copy as canonical
(layouts/_partials/canonical-url.html, `canonical_site` in front matter). If the
other doc set later moves, renames, or hides the page, the canonical points at a
404, and search engines drop this site's copy without indexing the target.

This script reads the built site, collects every canonical link that points
outside the page's own URL, fetches the sitemap.xml of each target doc set, and
reports the canonical links whose target isn't listed there.

It only warns, and always exits 0: the target doc set is the published one,
so work in progress on either side would otherwise fail every build. On GitHub
Actions, each problem is also printed as a ::warning:: annotation.

Usage: themes/docsy-axoflow/scripts/check_canonicals.py [public/]
"""

import argparse
import os
import re
import sys
import urllib.request
from pathlib import Path
from xml.etree import ElementTree

CANONICAL_RE = re.compile(r'<link rel="?canonical"? href="?([^" >]+)')
OG_URL_RE = re.compile(r'<meta property="?og:url"? content="?([^" >]+)')
SITEMAP_NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"


def warn(message: str) -> None:
    print(f"WARNING: {message}")
    if os.environ.get("GITHUB_ACTIONS"):
        print(f"::warning title=Canonical link::{message}")


def foreign_canonicals(public: Path) -> dict[str, str]:
    """Map page URL -> canonical URL, for pages whose canonical is somewhere else."""
    found = {}
    for html in public.rglob("index.html"):
        text = html.read_text(encoding="utf-8", errors="ignore")
        canonical = CANONICAL_RE.search(text)
        own = OG_URL_RE.search(text)
        # Alias redirect pages have no og:url, and their canonical is the target page.
        if canonical and own and canonical.group(1) != own.group(1):
            found[own.group(1)] = canonical.group(1)
    return found


def site_base(url: str, bases: list[str]) -> str | None:
    return next((b for b in bases if url.startswith(b)), None)


def fetch_sitemap(base: str) -> set[str] | None:
    """The <loc> URLs of base/sitemap.xml, following one level of sitemap index."""
    try:
        with urllib.request.urlopen(base + "sitemap.xml", timeout=30) as resp:
            root = ElementTree.fromstring(resp.read())
    except Exception as exc:  # network, HTTP, or XML errors: report, don't fail
        warn(f"couldn't read {base}sitemap.xml ({exc}); canonical targets under it weren't checked")
        return None
    locs = {el.text.strip() for el in root.iter(f"{SITEMAP_NS}loc") if el.text}
    if root.tag == f"{SITEMAP_NS}sitemapindex":
        urls = set()
        for child in locs:
            try:
                with urllib.request.urlopen(child, timeout=30) as resp:
                    urls |= {el.text.strip() for el in ElementTree.fromstring(resp.read()).iter(f"{SITEMAP_NS}loc") if el.text}
            except Exception as exc:
                warn(f"couldn't read {child} ({exc})")
        return urls
    return locs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("public", nargs="?", default="public", help="built site directory (default: public)")
    args = parser.parse_args()

    public = Path(args.public)
    if not public.is_dir():
        warn(f"{public} is not a directory; build the site first")
        return 0

    pages = foreign_canonicals(public)
    if not pages:
        print("No page names another doc set's copy as canonical.")
        return 0

    # A target doc set is everything up to the first path segment after /docs/,
    # for example https://axoflow.com/docs/axoflow/.
    bases = sorted({m.group(0) for c in pages.values() if (m := re.match(r"https?://[^/]+/docs/[^/]+/", c))})
    sitemaps = {b: fetch_sitemap(b) for b in bases}

    missing = 0
    for page, canonical in sorted(pages.items()):
        base = site_base(canonical, bases)
        if base is None:
            warn(f"{page}: canonical {canonical} isn't under a /docs/<site>/ path")
            missing += 1
        elif sitemaps[base] is not None and canonical not in sitemaps[base]:
            warn(f"{page}: canonical {canonical} isn't in {base}sitemap.xml")
            missing += 1

    checked = sum(1 for c in pages.values() if sitemaps.get(site_base(c, bases) or "") is not None)
    print(f"{len(pages)} pages name another doc set's copy as canonical; {checked} checked, {missing} not found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
