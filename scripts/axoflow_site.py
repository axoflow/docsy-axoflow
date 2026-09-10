#!/usr/bin/env python3
"""Shared plumbing for the scripts that read axoflow.com's chrome.

`check_main_menu.py` (data/nav-menu.yaml) and `check_footer.py`
(data/footer.yaml) both scrape the marketing site and diff it against a data
file, so the fetch, the comparison keys, the raw-markup slicing and the
comment-preserving write live here rather than in each of them.

Not a package: the scripts are run by path, which puts this directory on
`sys.path`, so a plain `import axoflow_site` resolves.
"""

import http.client
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

# Every run of whitespace except U+00A0 -- see clean_text.
SPACE_RUN = re.compile("[^\\S\u00a0]+")

USER_AGENT = "axoflow-docs-chrome-check/1.0 (+https://axoflow.com/docs/)"

# axoflow.com truncates the response (IncompleteRead) on roughly every other
# request, so a single attempt fails often enough to break CI.
FETCH_ATTEMPTS = 4
FETCH_BACKOFF = 1.0  # seconds before the first retry; doubled after each failure
RETRYABLE_ERRORS = (
    http.client.IncompleteRead,
    http.client.RemoteDisconnected,
    urllib.error.URLError,  # connection reset/refused, DNS, socket timeout
    TimeoutError,
)
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #

def is_retryable(error):
    """True for transient network failures; 4xx (other than 429) are permanent."""
    if isinstance(error, urllib.error.HTTPError):
        return error.code in RETRYABLE_STATUS
    return isinstance(error, RETRYABLE_ERRORS)


def fetch_html(url, attempts=FETCH_ATTEMPTS):
    """Fetch `url`, retrying transient failures with exponential backoff.

    Re-raises the last error once `attempts` is exhausted, so the caller still
    sees a clean failure.
    """
    delay = FETCH_BACKOFF
    for attempt in range(1, attempts + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset, "replace")
        except Exception as error:  # noqa: BLE001 - re-raised unless retryable
            if attempt == attempts or not is_retryable(error):
                raise
            print(
                "WARNING: attempt %d/%d to fetch %s failed (%s); retrying in %.0fs"
                % (attempt, attempts, url, error, delay),
                file=sys.stderr,
            )
            time.sleep(delay)
            delay *= 2


def site_host(url, default="axoflow.com"):
    """The bare host of `url`, `www.` dropped, for comparing against a data file."""
    host = urlparse(url).netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host or default


# --------------------------------------------------------------------------- #
# Comparison keys
# --------------------------------------------------------------------------- #

def normalize_url(url, host="axoflow.com", keep_root=False):
    """Reduce a URL to a stable comparison key, or None if it is not a link.

    Live hrefs are mostly root-relative (``/cost-reduction``) while the data
    files store them absolute and UTM-tagged, so both collapse to a path for
    `host`; other hosts keep ``host + path``. Query strings and trailing
    slashes are dropped.

    ``/``, ``#`` and ``""`` return None -- they are how a dropdown toggle with
    no destination is written. `keep_root` exempts ``/``, which the footer's
    logo link really does point at.
    """
    if not url:
        return None
    url = url.strip()
    if url in ("#", ""):
        return None
    if url == "/" and not keep_root:
        return None
    parsed = urlparse(url)
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/") or "/"
    if netloc in (host, ""):
        return path
    return netloc + path


def normalize_label(label):
    """Case- and whitespace-insensitive key for matching link text."""
    return " ".join((label or "").lower().split())


def clean_text(node):
    """A node's visible text, whitespace collapsed but NON-BREAKING SPACE kept.

    `str.split()` treats U+00A0 as whitespace and would flatten it to a plain
    space, which is not what the brand wrote: the footer's `Privacy Policy`
    is deliberately unbreakable, and the data file records it that way.
    """
    if node is None:
        return ""
    return SPACE_RUN.sub(" ", node.get_text(" ", strip=True)).strip()


def has_class(node, name):
    return name in (node.get("class") or [])


# --------------------------------------------------------------------------- #
# Raw markup
# --------------------------------------------------------------------------- #

class RawMarkup:
    """Slices tags back out of the response by source position.

    Re-serializing from the parse tree would lowercase ``viewBox`` and reorder
    attributes; the data files carry the brand's SVGs verbatim, so the markup
    has to come from the bytes that arrived.
    """

    def __init__(self, html):
        self.html = html
        self.line_offsets = [0]
        for line in html.split("\n"):
            self.line_offsets.append(self.line_offsets[-1] + len(line) + 1)

    def of(self, tag):
        """The tag's markup as it arrived, whitespace collapsed, or None."""
        if tag is None or tag.sourceline is None:
            return None
        start = self.line_offsets[tag.sourceline - 1] + tag.sourcepos
        closing = "</%s>" % tag.name
        end = self.html.find(closing, start)
        if end == -1:
            return None
        return " ".join(self.html[start:end + len(closing)].split())

    def svg_in(self, container):
        """Inline SVG markup from an icon wrapper, or None."""
        return self.of(container.find("svg")) if container is not None else None


# --------------------------------------------------------------------------- #
# Comments, so a regenerated data file keeps its prose
# --------------------------------------------------------------------------- #

def read_comment_blocks(path):
    """Split a data file into its comment blocks: the header, and each key's.

    Returns ``(header, {dotted_key: block})`` -- ``"social"`` for a top-level
    key, ``"logo.light"`` for a nested one. A key's block is the run of comment
    and blank lines directly above it, indentation included, which is where
    both data files keep the notes that explain the value below.

    A comment above one ITEM of a list has no key of its own and is not
    returned, so a regenerating writer loses it. Say so when writing.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except FileNotFoundError:
        return "", {}

    def is_comment(line):
        stripped = line.strip()
        return not stripped or stripped.startswith("#")

    header = []
    for line in lines:
        if not is_comment(line):
            break
        header.append(line)

    blocks = {}
    stack = []  # (indent, key) for the mapping keys enclosing the current line
    for index, line in enumerate(lines):
        if index < len(header) or is_comment(line):
            continue
        stripped = line.lstrip()
        indent = len(line) - len(stripped)
        if stripped.startswith("-") or ":" not in stripped:
            continue
        key = stripped.split(":", 1)[0].strip()
        if not key:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path_key = ".".join([k for _, k in stack] + [key])
        stack.append((indent, key))

        start = index
        while start > len(header) and is_comment(lines[start - 1]):
            start -= 1
        # Only the prose, not the blank line in front of it: the writer spaces
        # the sections itself, and a blank-only run would double up.
        run = lines[start:index]
        while run and not run[0].strip():
            run.pop(0)
        if run and any(l.strip().startswith("#") for l in run) \
                and path_key not in blocks:
            blocks[path_key] = "".join(run)

    return "".join(header), blocks
