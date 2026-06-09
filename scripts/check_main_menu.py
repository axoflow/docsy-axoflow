#!/usr/bin/env python3
"""Check (and optionally sync) the axoflow.com top navbar against the Hugo menu config.

Scrapes the main navigation menu from a page on axoflow.com 
(``<nav role="navigation" class="v3-navbar_menu w-nav-menu">``) and verifies
that every linked item also appears in the ``[[menus.main]]`` sections of
``themes/docsy-axoflow/config/_default/config.toml``.

Matching is done by normalized URL. Pure dropdown toggles 
(``url = "/"`` or ``#``) carry no destination and are ignored on both sides.

For every navbar link that is missing from the config the script also works out
*where* it belongs, so it can generate ready-to-use ``[[menus.main]]`` entries:

* ``parent``     -- the navbar mega-menu column heading (e.g. "Use Cases",
                    "Capabilities") is matched, by name, to an existing config
                    entry; that entry's ``identifier`` becomes the parent.
* ``weight``     -- the item's weight is interpolated between the weights of its
                    neighbours in the same column, so the menu keeps the same
                    order as the navbar. Columns with no existing entries get
                    evenly spaced weights (100, 200, ...).
* ``identifier`` -- a unique slug derived from the URL path, de-duplicated
                    against the identifiers already present in the config.

Output formats (``--format``):

    text   human-readable coverage report plus the planned additions (default)
    json   machine-readable report: counts, ``missing``, ``additions``,
           ``unresolved`` -- suitable for feeding into another script or prompt
    toml   just the generated ``[[menus.main]]`` blocks for the missing items

With ``--write`` the generated blocks are inserted into the config file (right
before the footer-menu section). TOML order does not affect the rendered menu --
Hugo resolves nesting by ``parent`` and orders siblings by ``weight`` -- so the
blocks are simply inserted as a group.

Exit status: 0 when every navbar link is covered, 1 when some are missing, 2 on
a runtime error -- suitable for CI gating.

Dependencies: BeautifulSoup (``beautifulsoup4``), already used by the sibling
``hugo_to_markdown.py`` script.

Usage:
    python3 themes/docsy-axoflow/scripts/check_main_menu.py
    python3 themes/docsy-axoflow/scripts/check_main_menu.py --format json
    python3 themes/docsy-axoflow/scripts/check_main_menu.py --format toml
    python3 themes/docsy-axoflow/scripts/check_main_menu.py --write
"""

import argparse
import json
import os
import sys
import tomllib
import urllib.request
from urllib.parse import urlparse

from bs4 import BeautifulSoup

DEFAULT_URL = "https://axoflow.com/"
# config.toml lives at ../config/_default/ relative to this script.
DEFAULT_CONFIG = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "config", "_default", "config.toml")
)
USER_AGENT = "axoflow-docs-menu-check/1.0 (+https://axoflow.com/docs/)"

# UTM suffix used by the existing axoflow.com menu entries in config.toml.
UTM_SUFFIX = "?utm_source=docs&utm_medium=menu"
# Weight spacing for generated entries when neighbours don't constrain it.
WEIGHT_STEP = 100
# Marker placed before the inserted block / used to find the insertion point.
FOOTER_MARKER = "# Hugo - Footer row-1 menu"


def normalize_url(url):
    """Reduce a menu URL to a stable comparison key, or None if it is not a real link.

    axoflow.com links collapse to their path (``/cost-reduction``); external
    links keep ``host + path`` (``kube-logging.dev/docs``). Query strings and
    trailing slashes are dropped. Placeholder/toggle targets ("/", "#", "")
    return None so dropdown labels are not treated as link destinations.
    """
    if not url:
        return None
    url = url.strip()
    if url in ("/", "#", ""):
        return None
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    path = parsed.path.rstrip("/") or "/"
    if host in ("axoflow.com", ""):
        return path
    return host + path


def normalize_name(name):
    """Case- and whitespace-insensitive key for matching menu names."""
    return " ".join((name or "").lower().split())


def clean_text(node):
    return " ".join(node.get_text(" ", strip=True).split())


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #

def fetch_html(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "replace")


def scrape_nav(html):
    """Return (flat_items, columns) scraped from the main navbar.

    flat_items : {normalized_url: {"name", "url", "normalized"}} for every link
                 anywhere in the navbar (deduplicated by normalized URL; the
                 first non-empty link text wins). Drives the coverage check.

    columns    : ordered list of mega-menu columns, each
                 {"heading": str, "entries": [ {"name","url","normalized",
                 "is_heading"} ]} in navbar (visual) order. Drives placement of
                 missing items. The column heading is included as the first
                 entry when it is itself a link (is_heading=True).
    """
    nav = BeautifulSoup(html, "html.parser").find("nav", class_="v3-navbar_menu")
    if nav is None:
        return {}, []

    flat_items = {}

    def remember(name, href):
        key = normalize_url(href)
        if key is None:
            return key
        existing = flat_items.get(key)
        if existing is None or (not existing["name"] and name):
            flat_items[key] = {"name": name, "url": href, "normalized": key}
        return key

    for anchor in nav.find_all("a"):
        remember(clean_text(anchor), anchor.get("href"))

    columns = []
    seen_columns = set()
    for col in nav.select("div.v3-navbar_mega-dropdown-col"):
        heading_el = col.select_one(".v3-navbar_mega-link")
        heading_text = clean_text(heading_el) if heading_el else ""

        entries = []
        # The column heading is sometimes a link (e.g. "Case studies").
        top = col.select_one(".v3-navbar_mega-dropdown-item-top")
        heading_anchor = top.find("a") if top else None
        if heading_anchor is not None:
            key = normalize_url(heading_anchor.get("href"))
            if key is not None:
                entries.append({
                    "name": clean_text(heading_anchor) or heading_text,
                    "url": heading_anchor.get("href"),
                    "normalized": key,
                    "is_heading": True,
                })

        for anchor in col.select("a.v3-navbar_mega-dropdown_link"):
            key = normalize_url(anchor.get("href"))
            if key is None:
                continue
            entries.append({
                "name": clean_text(anchor),
                "url": anchor.get("href"),
                "normalized": key,
                "is_heading": False,
            })

        if not entries:
            continue
        # The page can render the same column more than once (desktop variants);
        # key on heading + member URLs and keep only the first occurrence.
        signature = (normalize_name(heading_text),
                     tuple(e["normalized"] for e in entries))
        if signature in seen_columns:
            continue
        seen_columns.add(signature)
        columns.append({"heading": heading_text, "entries": entries})

    return flat_items, columns


# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

def load_config(config_path):
    """Parse config.toml and index the [[menus.main]] entries.

    Returns a dict with:
        url_to_name      {normalized_url: name}
        url_to_weight    {normalized_url: weight}
        name_to_id       {normalized_name: identifier}
        identifiers      set of all identifiers in use
    """
    with open(config_path, "rb") as handle:
        config = tomllib.load(handle)

    url_to_name = {}
    url_to_weight = {}
    name_to_id = {}
    identifiers = set()

    for entry in config.get("menus", {}).get("main", []):
        identifier = entry.get("identifier")
        if identifier:
            identifiers.add(identifier)
            name_to_id.setdefault(normalize_name(entry.get("name")), identifier)
        key = normalize_url(entry.get("url"))
        if key is None:
            continue
        url_to_name.setdefault(key, entry.get("name", ""))
        if "weight" in entry:
            url_to_weight.setdefault(key, entry["weight"])

    return {
        "url_to_name": url_to_name,
        "url_to_weight": url_to_weight,
        "name_to_id": name_to_id,
        "identifiers": identifiers,
    }


# --------------------------------------------------------------------------- #
# Placement of missing items
# --------------------------------------------------------------------------- #

def make_identifier(normalized, is_heading, used):
    """Derive a unique menu identifier from a URL, de-duplicated against `used`."""
    if normalized.startswith("/"):
        base = normalized.strip("/").replace("/", "-")
    else:  # external link: slugify host + path
        base = "".join(c if (c.isalnum() or c == "-") else "-" for c in normalized)
        base = "-".join(filter(None, base.split("-")))
    base = base or "menu-item"

    candidate = base
    if candidate in used:
        candidate = base + ("-overview" if is_heading else "-link")
    suffix = 2
    while candidate in used:
        candidate = "%s-%d" % (base, suffix)
        suffix += 1
    used.add(candidate)
    return candidate


def interpolate_weights(known, missing_positions, count):
    """Assign weights to `missing_positions` so the column stays in navbar order.

    known            {index: weight} for entries already present in the config
    missing_positions ordered list of indices that need a weight
    count            total number of entries in the column

    Missing entries between two known neighbours are spread evenly between them;
    a trailing run extends past the last known weight; a leading run sits below
    the first known weight; a column with no known weights is numbered 100, 200,
    ... by position.
    """
    result = {}
    missing_set = set(missing_positions)

    def known_before(i):
        for j in range(i - 1, -1, -1):
            if j in known:
                return known[j]
        return None

    def known_after(i):
        for j in range(i + 1, count):
            if j in known:
                return known[j]
        return None

    # Group consecutive missing indices into runs.
    runs = []
    run = []
    for i in range(count):
        if i in missing_set:
            run.append(i)
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)

    for run in runs:
        before = known_before(run[0])
        after = known_after(run[-1])
        length = len(run)
        for pos, index in enumerate(run):
            if before is not None and after is not None:
                gap = (after - before) / (length + 1)
                weight = before + gap * (pos + 1)
            elif before is not None:
                weight = before + WEIGHT_STEP * (pos + 1)
            elif after is not None:
                weight = after - WEIGHT_STEP * (length - pos)
            else:
                weight = WEIGHT_STEP * (pos + 1)
            result[index] = int(round(weight))
    return result


def build_url(normalized, original_href):
    """Reconstruct a config-style URL (full axoflow.com URL with UTM suffix)."""
    if normalized.startswith("/"):
        return "https://axoflow.com" + normalized + UTM_SUFFIX
    # External link: keep as authored.
    return original_href


def plan_additions(flat_items, columns, config_info):
    """Work out config entries for every missing navbar link.

    Returns (additions, unresolved):
        additions  : list of dicts {name, url, normalized, parent, weight,
                     identifier} ready to render as [[menus.main]] blocks,
                     sorted by (parent, weight).
        unresolved : list of {name, normalized, reason} for missing links whose
                     placement could not be determined automatically.
    """
    config_urls = set(config_info["url_to_name"])
    missing = {k for k in flat_items if k not in config_urls}

    used_identifiers = set(config_info["identifiers"])
    additions = []
    placed = set()

    for column in columns:
        entries = column["entries"]
        col_missing = [i for i, e in enumerate(entries) if e["normalized"] in missing]
        if not col_missing:
            continue

        parent = config_info["name_to_id"].get(normalize_name(column["heading"]))
        if not parent:
            # Fall back: borrow the parent of an existing sibling in this column.
            for entry in entries:
                sibling = entry["normalized"]
                if sibling not in missing:
                    # No direct parent lookup by URL; skip -- reported as unresolved.
                    pass
        if not parent:
            continue  # leave for the unresolved report below

        known = {
            i: config_info["url_to_weight"][e["normalized"]]
            for i, e in enumerate(entries)
            if e["normalized"] in config_info["url_to_weight"]
        }
        weights = interpolate_weights(known, col_missing, len(entries))

        for i in col_missing:
            entry = entries[i]
            if entry["normalized"] in placed:
                continue
            identifier = make_identifier(
                entry["normalized"], entry["is_heading"], used_identifiers
            )
            additions.append({
                "name": entry["name"],
                "url": build_url(entry["normalized"], entry["url"]),
                "normalized": entry["normalized"],
                "parent": parent,
                "weight": weights[i],
                "identifier": identifier,
            })
            placed.add(entry["normalized"])

    unresolved = [
        {
            "name": flat_items[k]["name"],
            "normalized": k,
            "reason": "no navbar column / matching parent identifier found",
        }
        for k in sorted(missing)
        if k not in placed
    ]

    additions.sort(key=lambda a: (a["parent"], a["weight"], a["normalized"]))
    return additions, unresolved


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def toml_escape(value):
    return value.replace("\\", "\\\\").replace('"', '\\"')


def render_entry_toml(addition):
    return (
        "  [[menus.main]]\n"
        '    name = "%s"\n'
        "    weight = %d\n"
        '    url = "%s"\n'
        '    identifier = "%s"\n'
        '    parent = "%s"\n'
        % (
            toml_escape(addition["name"]),
            addition["weight"],
            toml_escape(addition["url"]),
            toml_escape(addition["identifier"]),
            toml_escape(addition["parent"]),
        )
    )


def render_additions_toml(additions):
    """Render all additions, grouped by parent with a comment header per group."""
    if not additions:
        return ""
    blocks = []
    current_parent = None
    for addition in additions:
        if addition["parent"] != current_parent:
            current_parent = addition["parent"]
            blocks.append(
                "  # Added from axoflow.com navbar -- children of "
                '"%s"' % current_parent
            )
        blocks.append(render_entry_toml(addition).rstrip("\n"))
    return "\n".join(blocks) + "\n"


def render_text(report):
    lines = []
    lines.append("Main menu coverage check")
    lines.append("  source : %s" % report["source_url"])
    lines.append("  config : %s" % report["config_path"])
    lines.append(
        "  navbar links: %d unique  |  config menus.main links: %d"
        % (report["nav_unique_link_count"], report["config_link_count"])
    )

    if report["missing_count"] == 0:
        lines.append("")
        lines.append("OK: every navbar link is present in [[menus.main]].")
        return "\n".join(lines)

    lines.append("")
    lines.append(
        "MISSING: %d navbar link(s) not found in [[menus.main]]."
        % report["missing_count"]
    )

    if report["additions"]:
        lines.append("")
        lines.append("Planned additions (parent / weight / identifier):")
        for item in report["additions"]:
            lines.append(
                "  - %-38s parent=%-12s weight=%-5d id=%s"
                % (item["normalized"], item["parent"], item["weight"],
                   item["identifier"])
            )
    if report["unresolved"]:
        lines.append("")
        lines.append("Needs manual placement:")
        for item in report["unresolved"]:
            lines.append("  - %-38s (%s)" % (item["normalized"], item["reason"]))
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Writing into config.toml
# --------------------------------------------------------------------------- #

def insert_into_config(config_path, additions):
    """Insert the rendered blocks into config.toml before the footer-menu section."""
    with open(config_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    marker_index = None
    for i, line in enumerate(lines):
        if FOOTER_MARKER in line:
            marker_index = i
            break

    block = render_additions_toml(additions)
    snippet = "\n" + block + "\n"

    if marker_index is None:
        # No footer marker: append at end of file.
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        lines.append(snippet)
        insert_at = len(lines)
    else:
        # Back up over the rule line(s) immediately preceding the marker comment.
        insert_at = marker_index
        while insert_at > 0 and lines[insert_at - 1].lstrip().startswith("#"):
            insert_at -= 1
        lines.insert(insert_at, snippet)

    with open(config_path, "w", encoding="utf-8") as handle:
        handle.writelines(lines)
    return insert_at


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help="Page to scrape the navbar from (default: %(default)s)",
    )
    parser.add_argument(
        "--config", default=DEFAULT_CONFIG,
        help="Path to config.toml containing [[menus.main]] (default: the "
             "config.toml in this script's submodule)",
    )
    parser.add_argument(
        "--format", choices=("text", "json", "toml"), default="text",
        help="Output format (default: %(default)s)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Write the report to this file instead of stdout",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Insert the generated [[menus.main]] entries into the config file",
    )
    args = parser.parse_args(argv)

    try:
        html = fetch_html(args.url)
    except Exception as error:  # noqa: BLE001 - report any fetch failure cleanly
        print("ERROR: failed to fetch %s: %s" % (args.url, error), file=sys.stderr)
        return 2

    flat_items, columns = scrape_nav(html)
    if not flat_items:
        print(
            "ERROR: could not find any linked items in "
            "<nav class=\"v3-navbar_menu w-nav-menu\"> on %s "
            "(page markup may have changed)." % args.url,
            file=sys.stderr,
        )
        return 2

    try:
        config_info = load_config(args.config)
    except FileNotFoundError:
        print("ERROR: config file not found: %s" % args.config, file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001
        print("ERROR: failed to parse %s: %s" % (args.config, error), file=sys.stderr)
        return 2

    config_urls = set(config_info["url_to_name"])
    missing_keys = sorted(k for k in flat_items if k not in config_urls)
    additions, unresolved = plan_additions(flat_items, columns, config_info)

    report = {
        "source_url": args.url,
        "config_path": args.config,
        "nav_unique_link_count": len(flat_items),
        "config_link_count": len(config_urls),
        "missing_count": len(missing_keys),
        "missing": [flat_items[k] for k in missing_keys],
        "additions": additions,
        "unresolved": unresolved,
    }

    if args.write:
        if additions:
            insert_into_config(args.config, additions)
            print(
                "Added %d entr%s to %s."
                % (len(additions), "y" if len(additions) == 1 else "ies",
                   args.config),
                file=sys.stderr,
            )
            for item in additions:
                print(
                    "  + %s (parent=%s, weight=%d, identifier=%s)"
                    % (item["normalized"], item["parent"], item["weight"],
                       item["identifier"]),
                    file=sys.stderr,
                )
        else:
            print("Nothing to add: no resolvable missing entries.", file=sys.stderr)
        if unresolved:
            print(
                "Skipped %d item(s) needing manual placement:" % len(unresolved),
                file=sys.stderr,
            )
            for item in unresolved:
                print("  - %s" % item["normalized"], file=sys.stderr)
        return 1 if (missing_keys and not additions) or unresolved else 0

    if args.format == "json":
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
    elif args.format == "toml":
        rendered = render_additions_toml(additions).rstrip("\n")
    else:
        rendered = render_text(report)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    else:
        print(rendered)

    return 1 if report["missing_count"] else 0


if __name__ == "__main__":
    sys.exit(main())
