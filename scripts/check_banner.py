#!/usr/bin/env python3
"""Check (and optionally sync) axoflow.com's top banner against data/chrome.yaml.

The strip above the bar -- live's ``.v2-banner_component``, an announcement with
one link -- is the third piece of marketing chrome this site reproduces, after
the navigation (``check_main_menu.py``) and the footer (``check_footer.py``).
``_partials/announcement-strip.html`` renders it from the ``announcement`` key
of ``themes/docsy-axoflow/data/chrome.yaml``:

    announcement.label   the banner's text, verbatim
    announcement.href    where it points

Unlike the menu and the footer, the href is stored EXACTLY as live writes it,
with no ``?utm_source=docs`` suffix -- that is what the data file has always
held, so nothing is appended here either.

The banner is the one piece of chrome that is meant to change often, and it can
also go away: marketing takes the strip down between events. The partial renders
nothing when ``label`` is empty, so that is how an absent banner is recorded,
and ``--write`` empties the label rather than deleting the key.

Output formats (``--format``):

    text   human-readable report (default)
    json   the same report, machine-readable
    yaml   the scraped announcement, as the two lines the data file holds

``--write`` edits ``chrome.yaml`` in place, replacing just the ``href`` and
``label`` lines of the ``announcement`` block. The rest of the file -- its
comments, and any other key it grows -- is left exactly as it was, and a file
that already matches is not rewritten at all.

Exit status: 0 when the banner matches live, 1 on drift, 2 on a runtime error --
suitable for CI gating.

Dependencies: BeautifulSoup (``beautifulsoup4``), PyYAML

Usage:
    python3 themes/docsy-axoflow/scripts/check_banner.py
    python3 themes/docsy-axoflow/scripts/check_banner.py --format json
    python3 themes/docsy-axoflow/scripts/check_banner.py --format yaml
    python3 themes/docsy-axoflow/scripts/check_banner.py --write
"""

import argparse
import json
import os
import re
import sys

import yaml
from bs4 import BeautifulSoup

from axoflow_site import (
    clean_text,
    fetch_html,
    normalize_url,
    site_host,
)

DEFAULT_URL = "https://axoflow.com/"
# chrome.yaml lives at ../data/ relative to this script.
DEFAULT_DATA = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "chrome.yaml")
)

BANNER_SELECTOR = ".v2-banner_component"
# The key in chrome.yaml this script owns. Everything else in the file is left
# untouched by --write.
KEY = "announcement"


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #

def scrape(html, host="axoflow.com"):
    """Return ``({"label", "href"}, notes)`` for the live banner.

    An empty label means live is not carrying a banner at all -- either the
    component is absent or it is on the page with nothing in it, which is how
    Webflow leaves it between announcements.
    """
    soup = BeautifulSoup(html, "html.parser")
    notes = []

    banners = []
    for component in soup.select(BANNER_SELECTOR):
        text = clean_text(component.select_one(".v2-banner_text")) \
            or clean_text(component)
        anchor = component.find("a", href=True)
        href = (anchor.get("href") or "").strip() if anchor else ""
        if not text:
            continue
        banners.append({"label": text, "href": href})

    if not banners:
        notes.append(
            "live is carrying no banner: no %s with any text. An empty label is "
            "how the data file records that, and the strip then renders nothing."
            % BANNER_SELECTOR
        )
        return {"label": "", "href": ""}, notes

    banner = banners[0]
    # Webflow renders the component once, but a page that carries two different
    # ones is worth saying out loud rather than silently taking the first.
    others = [b for b in banners[1:]
              if b["label"] != banner["label"] or b["href"] != banner["href"]]
    for other in others:
        notes.append("a second, different banner is on the page: %r -> %s"
                     % (other["label"], other["href"] or "(no link)"))

    if not banner["href"]:
        notes.append(
            "the banner has no link; the strip renders an empty href, so give "
            "`announcement.href` a destination by hand or drop the anchor from "
            "announcement-strip.html"
        )
    elif not normalize_url(banner["href"], host, keep_root=True):
        notes.append("the banner's link is a placeholder (%r)" % banner["href"])

    return banner, notes


# --------------------------------------------------------------------------- #
# The data file
# --------------------------------------------------------------------------- #

def load_data(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("%s does not parse to a mapping" % path)
    return data


def stored_announcement(data):
    node = data.get(KEY)
    if not isinstance(node, dict):
        return {"label": "", "href": ""}
    return {"label": node.get("label") or "", "href": node.get("href") or ""}


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #

def build_report(live, data, notes, source_url, data_path, host):
    stored = stored_announcement(data)

    label_differs = live["label"].strip() != stored["label"].strip()
    # With no banner on live the href is not drift: the strip is off, and the
    # stored one is only the record of where the last banner pointed. Counting
    # it would leave CI red for as long as marketing has the strip down.
    href_differs = bool(live["label"]) and (
        normalize_url(live["href"], host, keep_root=True)
        != normalize_url(stored["href"], host, keep_root=True)
    )

    if live["label"] and not stored["label"]:
        state = "new"        # live put a banner up; this site shows none
    elif stored["label"] and not live["label"]:
        state = "withdrawn"  # live took the banner down; this site still shows it
    elif label_differs or href_differs:
        state = "changed"
    else:
        state = "in_sync"

    return {
        "source_url": source_url,
        "data_path": data_path,
        "state": state,
        "live": live,
        "data": stored,
        "label_differs": label_differs,
        "href_differs": href_differs,
        "notes": notes,
        "drift_count": int(label_differs) + int(href_differs),
    }


def merge(live, data):
    """What to store: live's banner, with the href kept when live has none.

    When the banner is withdrawn only the label is emptied -- that is what
    silences the strip -- and the last href is left in place as the record of
    what it pointed at.
    """
    stored = stored_announcement(data)
    if not live["label"]:
        return {"label": "", "href": stored["href"]}
    return {"label": live["label"], "href": live["href"] or stored["href"]}


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def quote(value):
    """A double-quoted YAML scalar, which is how chrome.yaml writes both values."""
    text = "" if value is None else str(value)
    return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')


def render_yaml(announcement):
    return "%s:\n  href: %s\n  label: %s\n" % (
        KEY, quote(announcement.get("href")), quote(announcement.get("label"))
    )


def render_text(report):
    live, data = report["live"], report["data"]
    lines = ["Banner check",
             "  source : %s" % report["source_url"],
             "  data   : %s" % report["data_path"],
             ""]

    headline = {
        "in_sync": "the banner matches axoflow.com",
        "changed": "the banner has changed",
        "new": "axoflow.com has put a banner up; this site shows none",
        "withdrawn": "axoflow.com has taken its banner down; this site still "
                     "shows one",
    }[report["state"]]
    lines.append("  %s" % headline)
    lines.append("")

    for field in ("label", "href"):
        if report["%s_differs" % field]:
            lines.append("    ~ %s" % field)
            lines.append("        live: %s" % (live[field] or "(none)"))
            lines.append("        data: %s" % (data[field] or "(none)"))
        elif field == "href" and report["state"] == "withdrawn":
            lines.append("    . href   %s (kept: where the last banner pointed)"
                         % (data[field] or "(none)"))
        else:
            lines.append("    = %-6s %s" % (field, live[field] or "(none)"))

    if report["notes"]:
        lines.append("")
        lines.append("Notes:")
        for note in report["notes"]:
            lines.append("    * %s" % note)

    lines.append("")
    if report["drift_count"]:
        lines.append("DRIFT: %d difference(s). `--write` updates the "
                     "`announcement` block in the data file."
                     % report["drift_count"])
    else:
        lines.append("OK: no change.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Writing the data file
# --------------------------------------------------------------------------- #

def write_data(path, announcement):
    """Replace the `href` and `label` lines of the `announcement` block in place.

    A surgical edit rather than a regeneration: chrome.yaml is shared chrome and
    may grow keys this script knows nothing about, so everything outside those
    two lines -- comments included -- is copied through untouched. A missing key
    or a missing block is appended.
    """
    with open(path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    start = next((i for i, line in enumerate(lines)
                  if re.match(r"^%s\s*:" % re.escape(KEY), line)), None)

    if start is None:
        block = "\n" if lines and lines[-1].strip() else ""
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(block + render_yaml(announcement))
        return

    # The block runs to the next line that starts a top-level key.
    end = len(lines)
    for index in range(start + 1, len(lines)):
        line = lines[index]
        if line.strip() and not line[0].isspace():
            end = index
            break

    body = lines[start + 1:end]
    indent = next((line[:len(line) - len(line.lstrip())]
                   for line in body if line.strip()), "  ")

    written = set()
    updated = []
    for line in body:
        match = re.match(r"^(\s*)(href|label)\s*:", line)
        if match:
            field = match.group(2)
            updated.append("%s%s: %s\n"
                           % (match.group(1), field, quote(announcement[field])))
            written.add(field)
        else:
            updated.append(line)

    # A field the block did not have yet goes after the last one it did.
    missing = [f for f in ("href", "label") if f not in written]
    if missing:
        insert_at = len(updated)
        while insert_at > 0 and not updated[insert_at - 1].strip():
            insert_at -= 1
        for field in reversed(missing):
            updated.insert(insert_at,
                           "%s%s: %s\n" % (indent, field, quote(announcement[field])))

    lines[start + 1:end] = updated
    with open(path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help="Page to scrape the banner from (default: %(default)s)",
    )
    parser.add_argument(
        "--data", default=DEFAULT_DATA,
        help="Path to chrome.yaml (default: the one in this script's submodule)",
    )
    parser.add_argument(
        "--format", choices=("text", "json", "yaml"), default="text",
        help="Output format (default: %(default)s)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Write the report to this file instead of stdout",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Update the `announcement` block in the data file",
    )
    args = parser.parse_args(argv)

    try:
        data = load_data(args.data)
    except FileNotFoundError:
        print("ERROR: data file not found: %s" % args.data, file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001
        print("ERROR: failed to parse %s: %s" % (args.data, error), file=sys.stderr)
        return 2

    try:
        html = fetch_html(args.url)
    except Exception as error:  # noqa: BLE001 - report any fetch failure cleanly
        print("ERROR: failed to fetch %s: %s" % (args.url, error), file=sys.stderr)
        return 2

    host = site_host(args.url)
    live, notes = scrape(html, host)
    report = build_report(live, data, notes, args.url, args.data, host)

    if args.write:
        if report["state"] == "in_sync":
            print("No change: %s already matches %s." % (args.data, args.url),
                  file=sys.stderr)
        else:
            merged = merge(live, data)
            write_data(args.data, merged)
            print("Wrote the %s block in %s from %s."
                  % (KEY, args.data, args.url), file=sys.stderr)
            print("  label: %s" % (merged["label"] or "(emptied: no banner on "
                                                      "live, so the strip is "
                                                      "hidden)"),
                  file=sys.stderr)
            print("  href : %s" % (merged["href"] or "(none)"), file=sys.stderr)
        for note in notes:
            print("  note: %s" % note, file=sys.stderr)
        return 0

    if args.format == "json":
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
    elif args.format == "yaml":
        rendered = render_yaml(live).rstrip("\n")
    else:
        rendered = render_text(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    else:
        print(rendered)

    return 1 if report["drift_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
