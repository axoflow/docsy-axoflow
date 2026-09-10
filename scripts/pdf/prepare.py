#!/usr/bin/env python3
"""Turn Hugo's /_pdf/index.html into a document that renders correctly as a PDF.

Hugo can concatenate every page into one HTML file, but it cannot fix what
that concatenation breaks. Three things go wrong, and all three are silent —
the PDF looks fine and is quietly wrong:

1. Internal links stay web links. A link to /data-management/processing/ opens
   a browser instead of jumping to that chapter. There are ~2,800 of them.

2. Heading ids collide. 329 pages contribute ~1,100 heading ids of which only
   ~455 are unique: 57 pages have a "Prerequisites" heading, 118 have
   "Labels". Every #prerequisites link lands on the first one in the book.

3. Lazy images may never load, and srcset lets the browser pick a small
   variant for a print-sized layout.

This script fixes all three plus the smaller print-hostile details (tab panes
that are display:none, lightbox anchors, oversized tables), and reports what it
changed so a CI run can fail on regressions.

Usage:
    prepare.py public_pdf/_pdf/index.html \\
        --site-base https://axoflow.com/docs/axoflow/ \\
        --site-base http://127.0.0.1:8099/ \\
        --public-base https://axoflow.com/docs/axoflow/ \\
        --site-root public_pdf --strict

Requires: beautifulsoup4 (already a docs-build dependency).
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from urllib.parse import unquote, urljoin, urlsplit

from bs4 import BeautifulSoup

# Anything with one of these suffixes is a file, not a page: linking to it from
# the PDF has to stay a web link.
ASSET_SUFFIXES = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".pdf", ".zip", ".tar",
    ".gz", ".txt", ".yaml", ".yml", ".json", ".conf", ".sh", ".csv", ".xml",
)

# A table with at least this many columns gets shrunk rather than pushed off
# the page edge. Five is where the default 9pt body size starts to crowd on A4.
WIDE_TABLE_COLUMNS = 5

# Width in pixels an image should have to look sharp across the A4 text column
# (174 mm ≈ 233 dpi at this width). Screenshots on this site go up to 3840 px,
# which is four times more data than the page can show.
DEFAULT_IMAGE_WIDTH = 1600


def normalize_path(path: str) -> str:
    """Canonical map key for a site path: leading and trailing slash, no index.html."""
    path = unquote(path or "/")
    if path.endswith("index.html"):
        path = path[: -len("index.html")]
    if not path.startswith("/"):
        path = "/" + path
    if not path.endswith("/"):
        path += "/"
    return path


def site_path(href: str, site_bases: list[str]) -> str | None:
    """Return the site-relative path of an internal link, or None if external.

    Handles the two forms internal links actually take in the build: root-
    relative (`/foo/`, what Hugo emits) and absolute against one of the known
    site base URLs (`https://axoflow.com/docs/axoflow/foo/`, hand-written in
    content).
    """
    parts = urlsplit(href)

    if not parts.scheme and not parts.netloc:
        return normalize_path(parts.path) if parts.path.startswith("/") else None

    for base in site_bases:
        b = urlsplit(base)
        if parts.scheme in ("http", "https") and parts.netloc == b.netloc:
            prefix = b.path.rstrip("/")
            if prefix and not parts.path.startswith(prefix):
                continue
            return normalize_path(parts.path[len(prefix):])
    return None


def load_aliases(site_root: str, site_bases: list[str]) -> dict[str, str]:
    """Map alias path -> target path by reading Hugo's generated redirect stubs.

    Content still links to a few pre-move URLs. Those resolve on the web
    because Hugo writes a meta-refresh stub for every `aliases:` entry; in a
    single document they would be dead ends, so we follow the stubs here.
    """
    aliases: dict[str, str] = {}
    refresh = re.compile(
        rb'http-equiv=["\']?refresh["\']?[^>]*?url=([^"\'>\s]+)', re.IGNORECASE
    )
    for dirpath, _dirnames, filenames in os.walk(site_root):
        if "index.html" not in filenames:
            continue
        full = os.path.join(dirpath, "index.html")
        # Redirect stubs are tiny; skip real pages without reading them.
        if os.path.getsize(full) > 4096:
            continue
        with open(full, "rb") as fh:
            head = fh.read(4096)
        m = refresh.search(head)
        if not m:
            continue
        target = m.group(1).decode("utf-8", "replace").rstrip('"\'')
        src = normalize_path("/" + os.path.relpath(dirpath, site_root))
        dest = site_path(target, site_bases)
        if dest and dest != src:
            aliases[src] = dest
    return aliases


def build_page_index(soup: BeautifulSoup) -> tuple[dict[str, str], list]:
    """Map every site path to the uid of the section that holds that page."""
    index: dict[str, str] = {}
    sections = soup.select("section.pdf-page[data-uid][data-path]")
    for section in sections:
        index[normalize_path(section["data-path"])] = section["data-uid"]
    return index, sections


def namespace_ids(sections) -> dict[str, set[str]]:
    """Prefix every id inside a page with that page's uid.

    Returns uid -> set of original ids, so link rewriting can tell whether a
    fragment actually exists on the page it points at.
    """
    owned: dict[str, set[str]] = {}
    for section in sections:
        uid = section["data-uid"]
        ids = owned.setdefault(uid, set())

        # `<a name="x">` is this site's convention for hanging an anchor off a
        # list item. Give those an id so they can be namespaced like the rest.
        for anchor in section.select("a[name]"):
            if not anchor.get("id"):
                anchor["id"] = anchor["name"]
            del anchor["name"]

        for el in section.find_all(id=True):
            old = el["id"]
            # The page's own anchor is the one id that must stay global.
            if old == f"pg-{uid}":
                continue
            ids.add(old)
            el["id"] = f"p{uid}--{old}"
    return owned


def pick_variant(srcset: str, target_width: int) -> tuple[str, int] | None:
    """Choose the smallest srcset candidate that still covers the print column.

    Taking the largest candidate would be the obvious choice and the wrong one:
    the widest screenshots on this site are 3840 px, four times what an A4
    column can show, and embedding them at that size triples the PDF.
    """
    candidates = []
    for candidate in srcset.split(","):
        bits = candidate.strip().split()
        if not bits:
            continue
        width = -1
        if len(bits) > 1 and bits[1].endswith("w"):
            try:
                width = int(bits[1][:-1])
            except ValueError:
                width = -1
        candidates.append((width, bits[0]))
    if not candidates:
        return None
    big_enough = [c for c in candidates if c[0] >= target_width]
    width, url = min(big_enough) if big_enough else max(candidates)
    return url, width


def fix_images(soup: BeautifulSoup, target_width: int) -> Counter:
    """Make every image render at print resolution, on the first paint.

    `loading=lazy` is the classic cause of blank images in a headless print,
    and `srcset` + `sizes` lets Chrome pick a 400 px variant for a layout it
    measures before pagination. Both go, replaced by one deliberate choice.
    """
    stats = Counter()
    for img in soup.find_all("img"):
        srcset = img.get("srcset")
        if srcset:
            chosen = pick_variant(srcset, target_width)
            if chosen:
                url, width = chosen
                if img.get("src") != url:
                    stats["resized"] += 1
                img["src"] = url
                # Keep the intrinsic size honest so the layout doesn't have to
                # guess the aspect ratio from a decoded image.
                if width > 0 and img.get("height", "").isdigit() and img.get("width", "").isdigit():
                    ratio = int(img["height"]) / int(img["width"])
                    img["width"] = str(width)
                    img["height"] = str(round(width * ratio))
                stats["srcset_flattened"] += 1
            del img["srcset"]
        for attr in ("sizes", "loading", "decoding", "fetchpriority"):
            if attr in img.attrs:
                del img[attr]
                if attr == "loading":
                    stats["lazy_removed"] += 1

        # An image wrapped in a link to the image file (the lightbox pattern,
        # by hand or via GLightbox) is unusable on paper — and the link
        # decoration around a screenshot is noise. Keep the image, drop the
        # link.
        parent = img.parent
        if parent is not None and parent.name == "a":
            href = (parent.get("href") or "").split("?")[0].lower()
            is_lightbox = "glightbox" in (parent.get("class") or []) or parent.has_attr("data-glightbox")
            alone = [c for c in parent.contents if getattr(c, "name", None) or str(c).strip()] == [img]
            if alone and (is_lightbox or href.endswith(ASSET_SUFFIXES)):
                parent.replace_with(img)
                stats["image_links_unwrapped"] += 1
    return stats


def expand_tabs(soup: BeautifulSoup) -> Counter:
    """Print every tab pane in sequence, labelled, instead of just the active one.

    Bootstrap keeps inactive panes at display:none. CSS in pdf.scss reveals
    them; what CSS cannot do is carry the tab's label over, so the label is
    copied in here as a subheading. Panes with no content (the shortcode emits
    a disabled leading tab used as a caption) are dropped.
    """
    stats = Counter()
    for nav in soup.select("ul.nav-tabs"):
        for button in nav.select("[data-bs-target], [aria-controls]"):
            target = button.get("data-bs-target") or "#" + button.get("aria-controls", "")
            if not target.startswith("#"):
                continue
            pane = soup.find(id=target[1:])
            if pane is None:
                continue
            if not pane.get_text(strip=True) and not pane.find(["img", "table", "pre"]):
                pane.decompose()
                stats["empty_panes_dropped"] += 1
                continue
            label = button.get_text(strip=True)
            if label:
                heading = soup.new_tag("p")
                heading["class"] = ["pdf-tab-label"]
                heading.string = label.rstrip(":")
                pane.insert(0, heading)
                stats["tabs_labelled"] += 1
        nav.decompose()
    return stats


def open_disclosures(soup: BeautifulSoup) -> int:
    """Expand every <details> element.

    A closed disclosure widget renders as its <summary> and nothing else, so
    on paper its content is simply gone — and there is no way to open it. The
    message schema reference is built entirely from nested <details>, which is
    ~25,000 words of reference material that would silently not be in the PDF.
    CSS can't do this: the closed state is a DOM property, not a style.
    """
    count = 0
    for details in soup.find_all("details"):
        if not details.has_attr("open"):
            details["open"] = ""
            count += 1
    return count


def mark_wide_tables(soup: BeautifulSoup) -> int:
    count = 0
    for table in soup.select(".td-content table"):
        first_row = table.find("tr")
        if first_row is None:
            continue
        columns = len(first_row.find_all(["th", "td"]))
        if columns >= WIDE_TABLE_COLUMNS:
            table["class"] = (table.get("class") or []) + ["pdf-wide-table"]
            count += 1
    return count


def rewrite_links(
    soup: BeautifulSoup,
    sections,
    page_index: dict[str, str],
    owned: dict[str, set[str]],
    aliases: dict[str, str],
    site_bases: list[str],
    public_base: str,
) -> tuple[Counter, list[str]]:
    """Point every internal link at its place in this document.

    Order matters: same-document fragments are resolved against the section
    the link sits in, so this has to walk section by section rather than over
    the whole soup.
    """
    stats = Counter()
    unresolved: list[str] = []

    def anchor_for(path: str, fragment: str) -> str | None:
        uid = page_index.get(path)
        if uid is None and path in aliases:
            uid = page_index.get(aliases[path])
            if uid is not None:
                stats["via_alias"] += 1
        if uid is None:
            return None
        if fragment:
            if fragment in owned.get(uid, ()):  # heading exists on that page
                return f"#p{uid}--{fragment}"
            # A fragment we can't place (generated by a shortcode, or a typo)
            # still belongs on the right page — better than a dead link.
            stats["fragment_fell_back_to_page"] += 1
        return f"#pg-{uid}"

    for section in sections:
        uid = section["data-uid"]
        for a in section.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("mailto:", "tel:", "javascript:", "data:")):
                continue

            parts = urlsplit(href)

            # Same-document link: resolve against the page it appears on.
            if not parts.path and not parts.netloc and parts.fragment:
                if parts.fragment in owned.get(uid, ()):
                    a["href"] = f"#p{uid}--{parts.fragment}"
                    stats["same_page"] += 1
                else:
                    # Namespacing just moved every id on this page, so leaving
                    # the fragment alone would guarantee a dead link. The top
                    # of the page is the closest honest target.
                    a["href"] = f"#pg-{uid}"
                    stats["same_page_fell_back"] += 1
                continue

            path = site_path(href, site_bases)
            if path is None:
                stats["external"] += 1
                continue

            if path.rstrip("/").lower().endswith(ASSET_SUFFIXES):
                # A downloadable file: keep it reachable from the PDF.
                a["href"] = urljoin(public_base, path.lstrip("/").rstrip("/"))
                stats["asset_absolutized"] += 1
                continue

            anchor = anchor_for(path, parts.fragment)
            if anchor:
                a["href"] = anchor
                stats["internal_anchored"] += 1
            else:
                # Unknown page (draft, deleted, or a typo): make sure the link
                # at least works from a PDF rather than resolving to nothing.
                a["href"] = urljoin(public_base, path.lstrip("/"))
                stats["unresolved_absolutized"] += 1
                unresolved.append(href)

    return stats, unresolved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("html", help="path to the generated _pdf/index.html")
    parser.add_argument("--out", help="write here instead of rewriting in place")
    parser.add_argument(
        "--site-base", action="append", default=[], metavar="URL",
        help="a base URL that means 'this site' (repeatable)",
    )
    parser.add_argument(
        "--public-base", default="", metavar="URL",
        help="base URL used for links that can't become in-document anchors",
    )
    parser.add_argument(
        "--site-root", metavar="DIR",
        help="the Hugo output directory, read to follow aliases",
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="exit non-zero if any internal link could not be anchored",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="process a document that has already been prepared",
    )
    parser.add_argument(
        "--image-width", type=int, default=DEFAULT_IMAGE_WIDTH, metavar="PX",
        help=f"pixel width to select images for (default: {DEFAULT_IMAGE_WIDTH})",
    )
    args = parser.parse_args()

    public_base = args.public_base or (args.site_base[0] if args.site_base else "/")

    with open(args.html, encoding="utf-8") as fh:
        soup = BeautifulSoup(fh.read(), "html.parser")

    # Running twice would prefix every id a second time. The result stays
    # self-consistent, which is exactly why it needs to be caught here rather
    # than noticed later in a 500-page PDF.
    root = soup.find("html")
    if root is not None and root.get("data-pdf-prepared") and not args.force:
        print("prepare: this document is already prepared — nothing to do (use --force to redo)")
        return 0

    page_index, sections = build_page_index(soup)
    if not sections:
        print("prepare: no <section class=\"pdf-page\"> found — wrong input file?", file=sys.stderr)
        return 2

    aliases = load_aliases(args.site_root, args.site_base) if args.site_root else {}

    # Order matters: the tab expander looks panes up by their original id, so
    # it has to run before ids get namespaced.
    tab_stats = expand_tabs(soup)
    disclosures = open_disclosures(soup)
    wide_tables = mark_wide_tables(soup)
    image_stats = fix_images(soup, args.image_width)
    owned = namespace_ids(sections)
    link_stats, unresolved = rewrite_links(
        soup, sections, page_index, owned, aliases, args.site_base, public_base
    )

    # Anything injected into the body would only run after pagination starts.
    for script in soup.select("body script"):
        script.decompose()

    if root is not None:
        root["data-pdf-prepared"] = "1"

    out = args.out or args.html
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(str(soup))

    print(f"prepare: {len(sections)} pages, {sum(len(v) for v in owned.values())} ids namespaced")
    print(
        "prepare: links — {internal} anchored, {same} same-page, {ext} external, "
        "{asset} assets, {unres} unresolved".format(
            internal=link_stats["internal_anchored"],
            same=link_stats["same_page"],
            ext=link_stats["external"],
            asset=link_stats["asset_absolutized"],
            unres=link_stats["unresolved_absolutized"],
        )
    )
    if link_stats["via_alias"]:
        print(f"prepare: {link_stats['via_alias']} link(s) followed an alias")
    fell_back = link_stats["fragment_fell_back_to_page"] + link_stats["same_page_fell_back"]
    if fell_back:
        print(
            f"prepare: {fell_back} link(s) had an unknown #fragment and now "
            "point at the top of the target page"
        )
    print(
        "prepare: images — {lazy} de-lazied, {srcset} srcset flattened "
        "({resized} re-pointed at a {w}px variant), {lb} image links unwrapped".format(
            lazy=image_stats["lazy_removed"],
            srcset=image_stats["srcset_flattened"],
            resized=image_stats["resized"],
            w=args.image_width,
            lb=image_stats["image_links_unwrapped"],
        )
    )
    print(
        f"prepare: {tab_stats['tabs_labelled']} tab panes labelled, "
        f"{tab_stats['empty_panes_dropped']} empty dropped, "
        f"{disclosures} <details> opened, {wide_tables} wide tables marked"
    )
    print(f"prepare: wrote {out}")

    if unresolved:
        shown = sorted(set(unresolved))
        print(f"prepare: {len(shown)} internal target(s) not in this document:", file=sys.stderr)
        for href in shown[:20]:
            print(f"  {href}", file=sys.stderr)
        if len(shown) > 20:
            print(f"  … and {len(shown) - 20} more", file=sys.stderr)
        if args.strict:
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
