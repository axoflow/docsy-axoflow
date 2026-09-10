#!/usr/bin/env python3
"""Write document properties into the rendered PDF.

Chrome fills in /Title from the page's <title> and nothing else — /Author is
empty and /Subject is empty, which is what a reader sees in Get Info, in a
document management system, or in a search index. The values come from the
prepared HTML (see baseof.pdf.html), so the PDF and the HTML edition can never
disagree about which build they came from.

The rewrite is incremental: pypdf appends the new /Info dictionary and a new
trailer rather than re-serialising the document, so an 80 MB PDF takes a few
seconds and the page tree, outline and named destinations are untouched.

Metadata is a nice-to-have on an artefact that has already been rendered, so
every failure here is a warning, not an error.

Usage:
    metadata.py out.pdf --html public_pdf/_pdf/index.html
"""

from __future__ import annotations

import argparse
import html
import re
import sys
from datetime import datetime, timezone


META_TAG_RE = re.compile(r"<meta\s+([^>]*?)/?>", re.IGNORECASE)
NAME_RE = re.compile(r'\bname\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
CONTENT_RE = re.compile(r'\bcontent\s*=\s*["\']([^"\']*)["\']', re.IGNORECASE)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def read_meta(html_path: str) -> dict[str, str]:
    """Pull the <meta name=... content=...> tags out of the prepared document.

    Regex rather than a parser on purpose: this runs after a PDF has already
    been rendered, so it should not be able to fail for want of an import, and
    the input is our own template output — a handful of tags in the first few
    kilobytes, not arbitrary HTML.
    """
    with open(html_path, encoding="utf-8") as fh:
        head = fh.read(16384).split("</head>")[0]

    # Attribute order varies: Hugo writes name before content, and the
    # BeautifulSoup pass in prepare.py re-serialises them alphabetically, so
    # each attribute is matched on its own rather than as a fixed sequence.
    meta = {}
    for attrs in META_TAG_RE.findall(head):
        name, content = NAME_RE.search(attrs), CONTENT_RE.search(attrs)
        if name and content and content.group(1).strip():
            meta[name.group(1).strip()] = html.unescape(content.group(1)).strip()
    title = TITLE_RE.search(head)
    if title:
        meta["title"] = html.unescape(title.group(1)).strip()
    return meta


def build_subject(meta: dict[str, str]) -> str:
    """One short line for /Subject: the version, and the commit that built it.

    Viewers show /Subject in a single-line field — Preview's inspector and
    Chrome's document properties both cut it off well before 100 characters —
    so this is deliberately the shortest thing that still identifies the
    build. The full provenance goes to the custom keys below, where nothing
    truncates it.

    Locally none of the docs-build-* values are set (Hugo can't work them out
    for itself; CI passes them in), so this degrades to the version alone.
    """
    # version_tag ("0.86.0") ahead of the CI version id ("0.86"), so the
    # Subject agrees with the Title a reader sees right above it.
    version = meta.get("docs-version") or meta.get("docs-build-version")
    commit = meta.get("docs-build-commit")

    if version and commit:
        return f"Version {version} ({commit[:8]})"
    if version:
        return f"Version {version}"
    if commit:
        return f"Build {commit[:8]}"
    return ""


def build_keywords(meta: dict[str, str]) -> str:
    """Terms worth having in a search index or a document management system."""
    terms = [
        meta.get("author"),
        "documentation",
        meta.get("docs-version") or meta.get("docs-build-version"),
        meta.get("docs-build-ref"),
    ]
    seen, out = set(), []
    for term in terms:
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return ", ".join(out)


def build_provenance(meta: dict[str, str]) -> dict[str, str]:
    """Full build provenance, as custom /Info keys.

    Custom keys are the right home for this: no viewer renders them in a
    truncating one-line field, Acrobat lists them under Custom properties, and
    anything scripted can read them exactly — full commit hashes, not the
    8-character prefixes a human wants to read.
    """
    return {
        f"/{key}": meta[tag]
        for key, tag in (
            ("BuildVersion", "docs-build-version"),
            ("BuildRef", "docs-build-ref"),
            ("BuildCommit", "docs-build-commit"),
            ("BuildTime", "docs-build-time"),
            ("ThemeDocsy", "docs-build-theme-docsy"),
            ("ThemeDocsyAxoflow", "docs-build-theme-docsy-axoflow"),
        )
        if meta.get(tag)
    }


def report_images(pdf_path: str) -> None:
    """Print how the images ended up encoded inside the PDF.

    This is the feedback loop for the print image pipeline. The whole reason
    the PDF build renders JPEGs (see render-image.html) is that Skia embeds
    JPEG source data as-is — /DCTDecode — while anything else is decoded to
    raw pixels and stored /FlateDecode at several times the size. That
    difference is invisible in the finished document and worth ~25 MB, so
    every build says which one it got.

    This step already has the PDF open with pypdf, which is why the check
    lives here rather than in a script of its own.
    """
    from collections import Counter

    from pypdf import PdfReader

    count: Counter = Counter()
    size: Counter = Counter()
    seen = set()
    for page in PdfReader(pdf_path).pages:
        resources = page.get("/Resources")
        if resources is None:
            continue
        xobjects = resources.get_object().get("/XObject")
        if xobjects is None:
            continue
        for ref in xobjects.get_object().values():
            idnum = getattr(ref, "idnum", None)
            if idnum in seen:
                continue
            seen.add(idnum)
            obj = ref.get_object()
            if obj.get("/Subtype") != "/Image":
                continue
            raw = obj.get("/Filter")
            name = "+".join(str(f) for f in raw) if isinstance(raw, list) else str(raw)
            count[name] += 1
            # The stream as stored, not decoded — get_data() would inflate
            # every screenshot back to raw pixels to measure it.
            size[name] += len(getattr(obj, "_data", b""))

    if not count:
        return
    parts = [f"{count[f]}× {f.lstrip('/')} {size[f] / 1e6:.1f} MB" for f, _ in count.most_common()]
    print("metadata: images — " + ", ".join(parts))
    if count.get("/FlateDecode", 0) > count.get("/DCTDecode", 0):
        print(
            "metadata: most images are stored losslessly — check that the PDF build "
            "is emitting JPEG (params.pdf.image_format)",
            file=sys.stderr,
        )


def pdf_date(iso: str | None) -> str | None:
    """Format a timestamp the way a PDF date string wants it (D:YYYYMMDDHHmmSSZ)."""
    if not iso:
        return None
    try:
        when = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return when.astimezone(timezone.utc).strftime("D:%Y%m%d%H%M%SZ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("pdf", help="the rendered PDF, updated in place")
    parser.add_argument("--html", required=True, help="the prepared _pdf/index.html it came from")
    parser.add_argument("--author", help="override the author from the HTML")
    args = parser.parse_args()

    try:
        from pypdf import PdfWriter
    except ImportError:
        print("metadata: pypdf is not installed — leaving the PDF's properties as Chrome wrote them", file=sys.stderr)
        return 0

    try:
        meta = read_meta(args.html)
    except Exception as err:  # noqa: BLE001 — never fail a finished render
        print(f"metadata: can't read {args.html} ({err}) — skipping", file=sys.stderr)
        return 0

    info = {}
    author = args.author or meta.get("author")
    if author:
        info["/Author"] = author
    if meta.get("title"):
        info["/Title"] = meta["title"]
    subject = build_subject(meta)
    if subject:
        info["/Subject"] = subject
    keywords = build_keywords(meta)
    if keywords:
        info["/Keywords"] = keywords
    info.update(build_provenance(meta))
    stamped = pdf_date(meta.get("docs-build-time"))
    if stamped:
        # The build's own timestamp, so two runs of the same commit agree.
        info["/CreationDate"] = stamped
        info["/ModDate"] = stamped

    if not info:
        print("metadata: nothing to write", file=sys.stderr)
        return 0

    try:
        writer = PdfWriter(args.pdf, incremental=True)
        writer.add_metadata(info)
        with open(args.pdf, "wb") as fh:
            writer.write(fh)
    except Exception as err:  # noqa: BLE001
        print(f"metadata: could not update {args.pdf} ({err}) — the PDF itself is fine", file=sys.stderr)
        return 0

    for key, value in info.items():
        print(f"metadata: {key[1:]:<13} {value}")

    try:
        report_images(args.pdf)
    except Exception as err:  # noqa: BLE001 — a report must not fail a build
        print(f"metadata: could not summarise the images ({err})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
