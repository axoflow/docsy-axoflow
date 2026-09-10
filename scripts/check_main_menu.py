#!/usr/bin/env python3
"""Check (and optionally sync) axoflow.com's navigation against data/nav-menu.yaml.

The docs navbar is no longer built from ``[[menus.main]]`` in config.toml -- both
sites render it from ``themes/docsy-axoflow/data/nav-menu.yaml``:
``items`` for the bar (``_partials/navbar-menu.html``) and ``mobile.items`` for
the phone drawer (``_partials/navbar-drawer.html``). So this script reads that
data file, and it checks BOTH menus, because axoflow.com carries two
navigations in one document and they disagree with each other:

    bar     <nav class="v3-navbar_menu"> > .v3-navbar_desktop-contents
    phone   <nav class="v3-navbar_menu"> > .v3-navbar_mobile-contents

The scrape reproduces the whole nav-menu.yaml schema, not just a list of URLs:
group headings with their icon, description and (when the heading is a link) its
href, per-link descriptions, the three chevron glyphs and the Request Sandbox
CTA. Icons and glyphs are sliced out of the raw response so the brand's own
attribute casing survives -- ``viewBox`` stays ``viewBox``.

Links are compared by normalized URL and label, so a row that moved between
groups, got reworded, or got repointed is reported as that rather than as one
addition plus one removal. The UTM suffix the data file adds to every href
(``?utm_source=docs&utm_medium=menu``) is ignored when matching and re-applied
when generating.

Output formats (``--format``):

    text   human-readable drift report (default)
    json   the same report, machine-readable
    yaml   the scraped menu in nav-menu.yaml's schema, ready to diff or merge

With ``--write`` the data file is regenerated from the scrape. The merge is
additive: rows, groups and items that are in the data file but not on live are
carried over (live's order wins where both have a row), so the deliberate
non-live entries -- the ``Capabilities > Overview`` rows -- survive a refresh.
The comment block at the head of the file and the one in front of ``mobile:``
are preserved; comments INSIDE the item lists are not, so re-read the diff.

Some shapes live draws have no place in the schema and are mapped rather than
copied; each mapping is listed under "notes" in the report. Currently: the
sub-columns inside a mega group (``Pipeline`` / ``Storage`` under Products)
become groups of their own.

Exit status: 0 when both menus match live, 1 on drift, 2 on a runtime error --
suitable for CI gating.

Dependencies: BeautifulSoup (``beautifulsoup4``), PyYAML

Usage:
    python3 themes/docsy-axoflow/scripts/check_main_menu.py
    python3 themes/docsy-axoflow/scripts/check_main_menu.py --format json
    python3 themes/docsy-axoflow/scripts/check_main_menu.py --format yaml
    python3 themes/docsy-axoflow/scripts/check_main_menu.py --write
"""

import argparse
import json
import os
import sys
from urllib.parse import urlparse

import yaml
from bs4 import BeautifulSoup

from axoflow_site import (
    RawMarkup,
    clean_text,
    fetch_html,
    has_class,
    normalize_label,
    normalize_url,
    read_comment_blocks,
    site_host,
)

DEFAULT_URL = "https://axoflow.com/"
# nav-menu.yaml lives at ../data/ relative to this script.
DEFAULT_DATA = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "nav-menu.yaml")
)

# What the data file tags every menu click with. Added by this script, not by
# axoflow.com, and ignored when comparing.
UTM_SUFFIX = "?utm_source=docs&utm_medium=menu"

# Key order the generated YAML uses, per node type. Matches the hand-written
# file so a regeneration diffs against it readably. `column` and `sub` are the
# layout live states and the schema cannot infer -- see `mega_item`.
ITEM_KEYS = ("kind", "label", "href", "mega", "groups")
GROUP_KEYS = ("kind", "column", "sub", "links", "label", "description", "href",
              "icon")
LINK_KEYS = ("label", "href", "icon", "description")

# Fields compared as wording and layout rather than as links. A change here is
# marketing rewriting a blurb, renaming a heading, redrawing an icon or moving a
# group to another column -- none of which shows up in a list of URLs.
PROSE_ITEM_FIELDS = ("mega",)
PROSE_GROUP_FIELDS = ("label", "description", "href", "column", "sub", "icon")
PROSE_LINK_FIELDS = ("label", "description", "icon")


def ordered(node, keys):
    """Re-key a dict into `keys` order, dropping keys that are unset."""
    out = {k: node[k] for k in keys if node.get(k) is not None}
    out.update({k: v for k, v in node.items() if k not in keys})
    return out


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #

class Extractor:
    """Turns axoflow.com's navbar into nav-menu.yaml's own shape.

    `notes` collects the places where live's structure does not fit the schema
    and had to be mapped, so the report can say so instead of losing it
    silently.
    """

    def __init__(self, html, host="axoflow.com"):
        self.host = host
        self.soup = BeautifulSoup(html, "html.parser")
        self.markup = RawMarkup(html)
        self.notes = []

    # -- raw markup ------------------------------------------------------- #

    def raw(self, tag):
        return self.markup.of(tag)

    def icon(self, container):
        """Inline SVG markup from an icon wrapper, or None."""
        return self.markup.svg_in(container)

    # -- URLs -------------------------------------------------------------- #

    def href(self, anchor):
        """A data-file style href: absolute, and UTM-tagged like its neighbours."""
        raw = (anchor.get("href") or "").strip()
        if not raw or raw in ("/", "#"):
            return None
        parsed = urlparse(raw)
        if not parsed.netloc:
            raw = "https://%s%s" % (self.host, raw if raw.startswith("/") else "/" + raw)
            parsed = urlparse(raw)
        if parsed.query:  # live already carries a query: leave it alone
            return raw
        return raw + UTM_SUFFIX

    def link(self, anchor, label=None, description=None, icon=None):
        href = self.href(anchor)
        if href is None:
            return None
        return {
            "label": label if label is not None else clean_text(anchor),
            "href": href,
            "icon": icon,
            "description": description,
        }

    # -- entry point ------------------------------------------------------- #

    def extract(self):
        nav = self.soup.find("nav", class_="v3-navbar_menu")
        if nav is None:
            return None

        menu = {
            "host": self.host,
            "glyphs": self.glyphs(nav),
            "cta": self.cta(),
            "items": self.bar_items(nav),
            "mobile": {"items": self.mobile_items(nav)},
        }
        return menu

    def glyphs(self, nav):
        """The three chevrons the partials inline, by the class live marks them with."""
        return {
            "afterLink": self.icon(nav.select_one("div.is-after-link-sm")),
            "afterTitle": self.icon(nav.select_one("div.is-after-link-lg")),
            "toggle": self.icon(
                nav.select_one(
                    ".v3-navbar_mega-dropdown-toggle div.v3-dropdown-chevron-sm,"
                    ".v3-navbar_dropdown-toggle div.v3-dropdown-chevron-sm"
                )
            ),
        }

    def cta(self):
        """Request Sandbox, from the button block beside the menu (not inside it)."""
        buttons = self.soup.select_one("div.v3-navbar_menu-buttons")
        if buttons is None:
            return None
        for anchor in buttons.find_all("a"):
            # The other button in this block is the tablet/phone Login, which
            # the data file carries as a menu item rather than as the CTA.
            if anchor.find_parent(class_="show-tablet") is not None:
                continue
            href = self.href(anchor)
            if href:
                return {"label": clean_text(anchor), "href": href}
        return None

    def tablet_login(self):
        """The Login the phone gets: live's second button, not a row in its list."""
        buttons = self.soup.select_one("div.v3-navbar_menu-buttons .show-tablet")
        if buttons is None:
            return None
        anchor = buttons.find("a")
        if anchor is None:
            return None
        href = self.href(anchor)
        if href is None:
            return None
        return {"kind": "link", "label": clean_text(anchor), "href": href}

    # -- the bar ----------------------------------------------------------- #

    def bar_items(self, nav):
        contents = nav.select_one("div.v3-navbar_desktop-contents") or nav
        items = []
        for child in contents.find_all(recursive=False):
            if has_class(child, "v3-navbar_mega-menu-dropdown"):
                items.append(self.mega_item(child))
            elif has_class(child, "v3-navbar_menu-dropdown"):
                items.append(self.dropdown_item(child))
            elif child.name == "a" and has_class(child, "v3-navbar_link"):
                link = self.link(child)
                if link:
                    items.append({
                        "kind": "link",
                        "label": link["label"],
                        "href": link["href"],
                    })
        return [i for i in items if i]

    def mega_item(self, node):
        """Solutions / Products: a panel of columns, each column a stack of groups.

        `column` carries live's own column boundary onto every group, because
        the panel's layout is not derivable from the group list: live draws two
        white columns in a `3fr` block beside a dark `1fr` highlight
        (`.v3-navbar_mega-dropdown-content.is-solutions`), and Products puts
        four groups in the first column where Solutions puts one.
        """
        label = clean_text(node.select_one("div.v3-navbar_mega-dropdown-toggle"))
        groups = []
        index = 0
        for column in node.select("div.v3-navbar_mega-dropdown-col"):
            highlight = has_class(column, "is-solutions-highlight")
            # A string, not a count: Hugo's `where` drops entries whose field
            # type does not match the value compared against, so a menu holding
            # both `1` and `highlight` loses one of the two in the template.
            key = "highlight" if highlight else str(index + 1)
            if not highlight:
                index += 1
            for group in self.mega_column(label, column):
                group["column"] = key
                groups.append(group)
        return {"kind": "menu", "label": label, "mega": True, "groups": groups}

    def mega_column(self, item_label, column):
        """One mega column, in DOM (= visual) order.

        A column is a run of sections separated by `divider-horizontal`: a
        heading block (`item-top`) and the collection of links under it.
        Products puts three of those in its first column, one of which is a
        further pair of sub-columns -- see `mega_subcolumns`.
        """
        groups = []

        def current():
            if not groups:
                groups.append({"kind": "links", "links": []})
            return groups[-1]

        for child in column.find_all(recursive=False):
            if has_class(child, "v3-navbar_mega-dropdown-item-top"):
                groups.append(self.mega_heading(child))
            elif has_class(child, "v3-navbar_mega-dropdown_collection-wrapper"):
                current()["links"].extend(self.mega_links(child))
            elif has_class(child, "v3-navbar_mega-dropdown-item-wrapper"):
                groups.extend(self.mega_subcolumns(item_label, child))
        return groups

    def mega_heading(self, top):
        """The card at the top of a section: icon, title (sometimes a link), blurb."""
        icon = self.icon(top.select_one("div.v3-navbar_mega-icon-lg"))
        title = top.select_one(".v3-navbar_mega-link")
        description = clean_text(top.select_one("div.text-size-tiny")) or None
        group = {
            "kind": "links",
            "links": [],
            "label": clean_text(title),
            "description": description,
            "icon": icon,
        }
        if title is not None and title.name == "a":
            group["href"] = self.href(title)
        return group

    def mega_links(self, wrapper):
        links = []
        for anchor in wrapper.select("a.v3-navbar_mega-dropdown_link"):
            link = self.link(anchor)
            if link:
                links.append(link)
        return links

    def mega_subcolumns(self, item_label, wrapper):
        """Products' `Pipeline` / `Storage` sub-columns.

        One section of a column holding two narrow columns side by side, each a
        small heading over rows that carry their own one-line description
        (`.v3-navbar_mega-dropdown-item-wrapper`, gap 2.5rem, a vertical rule
        between). `sub: true` is what tells the partial to lay them out that
        way instead of stacking them like the column's other sections.
        """
        groups = []
        for column in wrapper.find_all("div", recursive=False):
            bottom = column.select_one("div.v3-navbar_mega-dropdown-item-bottom")
            if bottom is None:
                continue
            heading = column.select_one("div.v2-text-color-tertiary")
            links = []
            for row in bottom.select("div.v3-navbar_mega-dropdown-item_nested"):
                anchor = row.select_one("a.v3-navbar_mega-link")
                if anchor is None:
                    continue
                link = self.link(
                    anchor,
                    description=clean_text(row.select_one("div.text-size-tiny")) or None,
                )
                if link:
                    links.append(link)
            if not links:
                continue
            groups.append({
                "kind": "links",
                "links": links,
                "label": clean_text(heading) or None,
                "sub": True,
            })
        return groups

    def dropdown_item(self, node):
        """Resources / Open Source / About: plain rows plus nested flyouts."""
        label = clean_text(node.select_one("div.v3-navbar_dropdown-toggle"))
        listing = node.select_one("nav.v3-navbar_dropdown-list")
        groups = []

        def run():
            """The open run of plain rows, started on demand."""
            if not groups or groups[-1]["kind"] != "links" or groups[-1].get("label"):
                groups.append({"kind": "links", "links": []})
            return groups[-1]

        for child in (listing.find_all(recursive=False) if listing else []):
            if child.name == "a" and has_class(child, "v3-navbar_dropdown-link"):
                link = self.link(child)
                if link:
                    run()["links"].append(link)
            elif has_class(child, "v3-navbar_menu-dropdown_nested"):
                groups.append(self.submenu(child))
        return {
            "kind": "menu",
            "label": label,
            "mega": False,
            "groups": [g for g in groups if g["links"]],
        }

    def submenu(self, node):
        """A row that opens a flyout: live's `_nested` toggle plus its list.

        Both link classes, because the two menus disagree: the bar's flyouts
        hold `.v3-navbar_dropdown-link`, the phone's `..._nested`. Scoping to
        the list also drops the invisible `a.v3-navbar_dropdown-toggle_link`
        live lays over the row itself -- the partials render the row as a
        button, so that href has nowhere to go.
        """
        label = clean_text(node.select_one("div.v3-navbar_dropdown-toggle_nested"))
        links = []
        listing = node.select_one("nav.v3-navbar_dropdown-list_nested")
        selector = "a.v3-navbar_dropdown-link, a.v3-navbar_dropdown-link_nested"
        for anchor in (listing.select(selector) if listing else []):
            link = self.link(anchor)
            if link:
                links.append(link)
        return {"kind": "submenu", "label": label, "links": links}

    # -- the phone menu ---------------------------------------------------- #

    def mobile_items(self, nav):
        """`.v3-navbar_mobile-contents`: a flat run of headings, rows and flyouts."""
        contents = nav.select_one("div.v3-navbar_mobile-contents")
        if contents is None:
            return []

        items = []

        def item():
            if not items:
                items.append({"kind": "menu", "label": "", "groups": []})
            return items[-1]

        def run(kind):
            groups = item()["groups"]
            if not groups or groups[-1]["kind"] != kind or groups[-1].get("label"):
                groups.append({"kind": kind, "links": []})
            return groups[-1]

        for child in contents.find_all(recursive=False):
            if has_class(child, "v3-navbar_mobile-menu-label"):
                items.append({
                    "kind": "menu",
                    "label": clean_text(child),
                    "groups": [],
                })
            elif child.name == "a" and has_class(child, "v3-navbar_mobile-menu-link"):
                link = self.link(child)
                if link:
                    run("links")["links"].append(link)
            elif child.name == "a" and has_class(child, "v3-navbar_dropdown-link_nested"):
                # Live's second plain-row shape: the same rows a flyout holds,
                # one level in, used directly under the `Products` heading.
                link = self.link(child)
                if link:
                    run("nested")["links"].append(link)
            elif has_class(child, "v3-navbar_menu-dropdown"):
                group = self.submenu(child)
                if group["links"]:
                    item()["groups"].append(group)

        for entry in items:
            entry["groups"] = [g for g in entry["groups"] if g["links"]]

        login = self.tablet_login()
        if login:
            items.append(login)
            self.notes.append(
                "phone: `%s` is one of the two buttons beside live's list, not a row "
                "in it; kept as the trailing item the drawer renders" % login["label"]
            )
        return [i for i in items if i.get("kind") == "link" or i["groups"]]


def scrape(html, host="axoflow.com"):
    extractor = Extractor(html, host)
    return extractor.extract(), extractor.notes


# --------------------------------------------------------------------------- #
# The data file
# --------------------------------------------------------------------------- #

def load_data(path):
    with open(path, "r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError("%s does not parse to a mapping" % path)
    return data


def menu_items(menu, which):
    """`items` for the bar, `mobile.items` for the phone, either side of the diff."""
    if which == "bar":
        return (menu or {}).get("items") or []
    return ((menu or {}).get("mobile") or {}).get("items") or []


def walk_links(items, host="axoflow.com"):
    """Every link in a menu as a flat record, in menu order.

    Records carry where they sit (`path`) and what index they sat at inside
    their group, which is what the merge needs to put a data-only row back.
    """
    records = []
    for item_index, item in enumerate(items):
        label = item.get("label", "")
        if item.get("kind") == "link":
            key = normalize_url(item.get("href"), host)
            if key:
                records.append({
                    "menu_label": label,
                    "group_label": None,
                    "path": label,
                    "label": label,
                    "href": item.get("href"),
                    "url": key,
                    "item_index": item_index,
                    "group_index": None,
                    "link_index": None,
                })
            continue
        for group_index, group in enumerate(item.get("groups") or []):
            group_label = group.get("label")
            for link_index, link in enumerate(group.get("links") or []):
                key = normalize_url(link.get("href"), host)
                if not key:
                    continue
                records.append({
                    "menu_label": label,
                    "group_label": group_label,
                    "path": "%s > %s" % (label, group_label or "(unlabelled)"),
                    "label": link.get("label", ""),
                    "href": link.get("href"),
                    "url": key,
                    "item_index": item_index,
                    "group_index": group_index,
                    "link_index": link_index,
                })
    return records


def group_paths(items):
    """Ordered ``item > group`` labels, for reporting structural drift."""
    paths = []
    for item in items:
        if item.get("kind") == "link":
            continue
        for group in item.get("groups") or []:
            paths.append("%s > %s" % (item.get("label", ""),
                                      group.get("label") or "(unlabelled)"))
    return paths


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #

def diff_menu(live_items, data_items, host="axoflow.com"):
    """Compare one menu (bar or phone) against the data file.

    Matches on (url, label) first, then on url alone (`relabelled`), then on
    label alone within the same group (`retargeted`). What is left over on
    either side is a real addition or removal.
    """
    live = walk_links(live_items, host)
    data = walk_links(data_items, host)

    remaining_live = list(live)
    remaining_data = list(data)
    pairs = []

    def pass_over(predicate, bucket):
        """Pair off whatever this rule can, then hand the rest to the next one.

        A pass at a time, not a cascade per row: `/support` is two rows on live
        now, and matching the first of them on URL alone would eat the data row
        that the second one matches exactly.
        """
        for record in list(remaining_live):
            for candidate in remaining_data:
                if predicate(record, candidate):
                    remaining_live.remove(record)
                    remaining_data.remove(candidate)
                    pairs.append((record, candidate))
                    if bucket is not None:
                        bucket.append((record, candidate))
                    break

    relabelled_pairs, retargeted_pairs = [], []
    pass_over(lambda l, d: l["url"] == d["url"]
              and normalize_label(l["label"]) == normalize_label(d["label"])
              and l["path"] == d["path"], None)
    pass_over(lambda l, d: l["url"] == d["url"]
              and normalize_label(l["label"]) == normalize_label(d["label"]), None)
    pass_over(lambda l, d: l["url"] == d["url"] and l["path"] == d["path"],
              relabelled_pairs)
    pass_over(lambda l, d: l["path"] == d["path"]
              and normalize_label(l["label"]) == normalize_label(d["label"]),
              retargeted_pairs)
    pass_over(lambda l, d: l["url"] == d["url"], relabelled_pairs)

    matched = [live_record for live_record, _ in pairs]
    added = remaining_live
    relabelled = [{"url": l["url"], "path": l["path"],
                   "live": l["label"], "data": d["label"]}
                  for l, d in relabelled_pairs]
    retargeted = [{"label": l["label"], "path": l["path"],
                   "live": l["href"], "data": d["href"]}
                  for l, d in retargeted_pairs]
    moved = [{"label": l["label"], "url": l["url"],
              "live": l["path"], "data": d["path"]}
             for l, d in pairs if l["path"] != d["path"]]

    live_paths = group_paths(live_items)
    data_paths = group_paths(data_items)

    # Order is compared over the rows both sides have: with additions and
    # carried-over rows in the mix the raw sequences always differ, which would
    # make the flag mean nothing.
    shared = {l["url"] for l, _ in pairs}
    live_order = [r["url"] for r in live if r["url"] in shared]
    data_order = [r["url"] for r in data if r["url"] in shared]

    return {
        "live_link_count": len(live),
        "data_link_count": len(data),
        "matched_count": len(matched),
        "added": added,          # on live, missing from the data file
        "removed": remaining_data,  # in the data file, gone from live
        "relabelled": relabelled,
        "retargeted": retargeted,
        "moved": moved,
        "groups_added": [p for p in live_paths if p not in data_paths],
        "groups_removed": [p for p in data_paths if p not in live_paths],
        "prose": diff_prose(live_items, data_items, host),
        "order_differs": live_order != data_order,
    }


def field_value(node, field):
    """A comparable value for one prose field; absent and empty are the same."""
    value = (node or {}).get(field)
    if field == "icon":
        return normalize_svg(value)
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return ""
    return value


def show_value(node, field):
    """What to print for a prose field. Artwork is described, not dumped."""
    value = (node or {}).get(field)
    if field == "icon":
        return "(artwork)" if value else "(none)"
    if value is None or value == "":
        return "(none)"
    return value


def diff_prose(live_items, data_items, host):
    """Wording and layout drift on the nodes both sides have.

    The link diff answers "are the same destinations there"; this answers "does
    it read and sit the way live does" -- group headings and blurbs, the
    per-link one-liners under the product rows, the icons, and which column a
    group is in. Marketing rewrote four Products blurbs in September and not one
    of them showed up as a link difference.
    """
    drift = []

    def record(path, field, live_node, data_node):
        drift.append({
            "path": path,
            "field": field,
            "live": show_value(live_node, field),
            "data": show_value(data_node, field),
        })

    def compare(path, fields, live_node, data_node):
        for field in fields:
            if field == "href":
                same = (normalize_url(live_node.get(field), host)
                        == normalize_url(data_node.get(field), host))
            else:
                same = field_value(live_node, field) == field_value(data_node, field)
            if not same:
                record(path, field, live_node, data_node)

    used_items = set()
    for live_item in live_items:
        key = normalize_label(live_item.get("label"))
        data_item = None
        for index, candidate in enumerate(data_items):
            if index not in used_items \
                    and normalize_label(candidate.get("label")) == key:
                data_item, _ = candidate, used_items.add(index)
                break
        if data_item is None:
            continue
        item_path = live_item.get("label") or "(unlabelled)"
        compare(item_path, PROSE_ITEM_FIELDS, live_item, data_item)

        data_groups = data_item.get("groups") or []
        used_groups = set()
        for live_group in live_item.get("groups") or []:
            match = match_group(live_group, data_groups, used_groups)
            if match is None:
                continue
            used_groups.add(match)
            data_group = data_groups[match]
            group_path = "%s > %s" % (item_path,
                                      live_group.get("label") or "(unlabelled)")
            compare(group_path, PROSE_GROUP_FIELDS, live_group, data_group)

            # Consume matches rather than index by URL: `Services` holds
            # `Professional Services` and `Support`, both pointing at /support,
            # and a dict would pair live's second row with the data's first and
            # call it a rename.
            remaining = list(data_group.get("links") or [])

            def take(live_link, exact):
                for index, candidate in enumerate(remaining):
                    if normalize_url(candidate.get("href"), host) \
                            != normalize_url(live_link.get("href"), host):
                        continue
                    if exact and normalize_label(candidate.get("label")) \
                            != normalize_label(live_link.get("label")):
                        continue
                    return remaining.pop(index)
                return None

            live_links = live_group.get("links") or []
            pairs = []
            for live_link in live_links:
                data_link = take(live_link, exact=True)
                if data_link is not None:
                    pairs.append((live_link, data_link))
            for live_link in live_links:
                if any(live_link is l for l, _ in pairs):
                    continue
                data_link = take(live_link, exact=False)
                if data_link is not None:
                    pairs.append((live_link, data_link))

            for live_link, data_link in pairs:
                compare("%s > %s" % (group_path, live_link.get("label")),
                        PROSE_LINK_FIELDS, live_link, data_link)
    return drift


def drift_count(section):
    return sum(len(section[k]) for k in
               ("added", "removed", "relabelled", "retargeted", "moved",
                "groups_added", "groups_removed", "prose"))


def build_report(live, data, notes, source_url, data_path):
    menus = {which: diff_menu(menu_items(live, which), menu_items(data, which),
                              live.get("host", "axoflow.com"))
             for which in ("bar", "phone")}

    chrome = []
    for key in ("host",):
        if live.get(key) != data.get(key):
            chrome.append({"field": key, "live": live.get(key), "data": data.get(key)})
    for field, key in (("label", normalize_label), ("href", normalize_url)):
        live_value = (live.get("cta") or {}).get(field)
        data_value = (data.get("cta") or {}).get(field)
        if key(live_value) != key(data_value):
            chrome.append({"field": "cta." + field,
                           "live": live_value, "data": data_value})
    for name in ("afterLink", "afterTitle", "toggle"):
        live_value = (live.get("glyphs") or {}).get(name)
        data_value = (data.get("glyphs") or {}).get(name)
        if live_value and normalize_svg(live_value) != normalize_svg(data_value):
            chrome.append({"field": "glyphs." + name,
                           "live": "changed", "data": "changed"})

    return {
        "source_url": source_url,
        "data_path": data_path,
        "menus": menus,
        "chrome": chrome,
        "notes": notes,
        "drift_count": sum(drift_count(m) for m in menus.values()) + len(chrome),
    }


def normalize_svg(markup):
    """Compare artwork on its path data, not on how the markup was serialized."""
    if not markup:
        return ""
    return "".join(markup.split()).replace("></path>", "/>").replace("</path>", "")


# --------------------------------------------------------------------------- #
# Merging, for --write
# --------------------------------------------------------------------------- #

def link_key(link, host):
    return normalize_url(link.get("href"), host)


def merge_links(live_links, data_links, host, menu_urls):
    """Live's rows in live's order, with data-only rows put back where they were.

    `menu_urls` is every URL live has anywhere in this menu, not just in this
    group: a row live moved to another group -- AxoRouter, out of `Axoflow
    Platform` and into `Pipeline` -- must not be re-added here as well.
    """
    merged = list(live_links)
    live_labels = {normalize_label(l.get("label")) for l in live_links}
    kept = []
    for index, link in enumerate(data_links or []):
        if link_key(link, host) in menu_urls:
            continue
        if normalize_label(link.get("label")) in live_labels:
            continue  # same row, new destination: live's href wins
        merged.insert(min(index, len(merged)), link)
        kept.append(link)
    return merged, kept


def match_group(group, candidates, used):
    """Find `group`'s counterpart: by label if it has one, else by kind and order."""
    label = normalize_label(group.get("label"))
    for index, candidate in enumerate(candidates):
        if index in used:
            continue
        if label and normalize_label(candidate.get("label")) == label:
            return index
    if label:
        return None
    for index, candidate in enumerate(candidates):
        if index in used or candidate.get("label"):
            continue
        if candidate.get("kind") == group.get("kind"):
            return index
    return None


def keep_group(group, host, menu_urls):
    """A data-only group, minus rows live already draws elsewhere, or None.

    Without the filter, a group live has dissolved would re-add every row it
    held, and each of those rows would then appear twice in the menu.
    """
    links = [l for l in group.get("links") or []
             if link_key(l, host) not in menu_urls]
    if not links:
        return None
    group = dict(group)
    group["links"] = links
    return group


def merge_items(live_items, data_items, host, which, kept_log):
    """Live's items, with data-only links, groups and items carried over."""
    merged = []
    used_items = set()
    menu_urls = {record["url"] for record in walk_links(live_items, host)}

    for live_item in live_items:
        label = normalize_label(live_item.get("label"))
        data_item = None
        for index, candidate in enumerate(data_items):
            if index in used_items:
                continue
            if normalize_label(candidate.get("label")) == label:
                data_item, used_items = candidate, used_items | {index}
                break
        if data_item is None or live_item.get("kind") == "link":
            merged.append(live_item)
            continue

        groups = []
        used_groups = set()
        for live_group in live_item.get("groups") or []:
            match = match_group(live_group, data_item.get("groups") or [], used_groups)
            if match is None:
                groups.append(live_group)
                continue
            used_groups.add(match)
            data_group = (data_item.get("groups") or [])[match]
            live_group = dict(live_group)
            live_group["links"], kept = merge_links(
                live_group.get("links") or [], data_group.get("links"),
                host, menu_urls
            )
            for link in kept:
                kept_log.append("%s: %s > %s > %s (%s)" % (
                    which, live_item.get("label"),
                    live_group.get("label") or "(unlabelled)",
                    link.get("label"), link.get("href")))
            groups.append(live_group)

        for index, data_group in enumerate(data_item.get("groups") or []):
            if index in used_groups:
                continue
            data_group = keep_group(data_group, host, menu_urls)
            if data_group is None:
                continue
            groups.append(data_group)
            kept_log.append("%s: %s > %s (whole group, %d row(s))" % (
                which, live_item.get("label"),
                data_group.get("label") or "(unlabelled)",
                len(data_group.get("links") or [])))

        live_item = dict(live_item)
        live_item["groups"] = groups
        merged.append(live_item)

    for index, data_item in enumerate(data_items):
        if index in used_items or data_item.get("kind") == "link":
            continue
        groups = [g for g in (keep_group(g, host, menu_urls)
                              for g in data_item.get("groups") or []) if g]
        if not groups:
            continue
        data_item = dict(data_item)
        data_item["groups"] = groups
        merged.append(data_item)
        kept_log.append("%s: %s (whole item)" % (which, data_item.get("label")))

    return merged


def merge(live, data):
    """The menu to write: live, plus everything the data file has that live lacks."""
    host = live.get("host", "axoflow.com")
    kept = []
    return {
        "host": host,
        "glyphs": live.get("glyphs") or data.get("glyphs"),
        "cta": live.get("cta") or data.get("cta"),
        "items": merge_items(menu_items(live, "bar"), menu_items(data, "bar"),
                             host, "bar", kept),
        "mobile": {
            "items": merge_items(menu_items(live, "phone"),
                                 menu_items(data, "phone"), host, "phone", kept),
        },
    }, kept


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def order_menu(menu):
    """Re-key every node so the dump comes out in the data file's key order."""
    def order_item(item):
        item = dict(item)
        if item.get("groups") is not None:
            item["groups"] = [order_group(g) for g in item["groups"]]
        return ordered(item, ITEM_KEYS)

    def order_group(group):
        group = dict(group)
        group["links"] = [ordered(dict(l), LINK_KEYS) for l in group.get("links") or []]
        return ordered(group, GROUP_KEYS)

    out = {}
    for key in ("host", "glyphs", "cta"):
        if menu.get(key) is not None:
            out[key] = menu[key]
    out["items"] = [order_item(i) for i in menu.get("items") or []]
    out["mobile"] = {"items": [order_item(i)
                               for i in menu_items(menu, "phone")]}
    return out


def dump_yaml(node):
    """Dump in the data file's own style: block sequences, no wrapping, no sorting.

    `width` is effectively infinite because the icons are single-line SVG
    markup thousands of characters long, and PyYAML would otherwise fold them.
    """
    return yaml.dump(node, sort_keys=False, default_flow_style=False,
                     allow_unicode=True, width=10 ** 9)


def render_yaml(menu):
    return dump_yaml(order_menu(menu))


def render_section(name, section):
    lines = []
    lines.append("  %s: %d link(s) on live, %d in the data file, %d matched"
                 % (name, section["live_link_count"], section["data_link_count"],
                    section["matched_count"]))
    if not drift_count(section):
        lines.append("    in sync"
                     + (" (order differs)" if section["order_differs"] else ""))
        return lines
    for record in section["added"]:
        lines.append("    + %-44s %s  [%s]"
                     % (record["url"], record["label"], record["path"]))
    for record in section["removed"]:
        lines.append("    - %-44s %s  [%s]"
                     % (record["url"], record["label"], record["path"]))
    for record in section["relabelled"]:
        lines.append("    ~ %-44s %r -> %r" % (record["url"], record["data"],
                                               record["live"]))
    for record in section["retargeted"]:
        lines.append("    ~ %-44s %s -> %s" % (record["label"], record["data"],
                                               record["live"]))
    for record in section["moved"]:
        lines.append("    > %-44s %s -> %s" % (record["label"], record["data"],
                                               record["live"]))
    for path in section["groups_added"]:
        lines.append("    + group  %s" % path)
    for path in section["groups_removed"]:
        lines.append("    - group  %s" % path)
    for entry in section["prose"]:
        lines.append("    ~ %s [%s]" % (entry["path"], entry["field"]))
        lines.append("        live: %s" % entry["live"])
        lines.append("        data: %s" % entry["data"])
    if section["order_differs"]:
        lines.append("    order differs from live")
    return lines


def render_text(report):
    lines = ["Navigation menu check",
             "  source : %s" % report["source_url"],
             "  data   : %s" % report["data_path"],
             ""]
    lines.extend(render_section("bar  ", report["menus"]["bar"]))
    lines.append("")
    lines.extend(render_section("phone", report["menus"]["phone"]))

    if report["chrome"]:
        lines.append("")
        lines.append("Outside the item lists:")
        for entry in report["chrome"]:
            lines.append("    ~ %-16s live=%s  data=%s"
                         % (entry["field"], entry["live"], entry["data"]))

    if report["notes"]:
        lines.append("")
        lines.append("Notes (live shapes the schema cannot hold as-is):")
        for note in report["notes"]:
            lines.append("    * %s" % note)

    lines.append("")
    if report["drift_count"]:
        lines.append("DRIFT: %d difference(s). `--format yaml` prints the scraped "
                     "menu; `--write` merges it into the data file."
                     % report["drift_count"])
    else:
        lines.append("OK: both menus match axoflow.com.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Writing the data file
# --------------------------------------------------------------------------- #

def write_data(path, menu):
    """Regenerate the data file, keeping the header and the `mobile:` preamble.

    Everything else is regenerated, so a comment sitting on an individual item
    or link does not survive -- read the diff.
    """
    header, blocks = read_comment_blocks(path)
    mobile_header = blocks.get("mobile", "")
    ordered_menu = order_menu(menu)
    mobile = {"items": ordered_menu.pop("mobile")["items"]}

    body = dump_yaml(ordered_menu)
    tail = dump_yaml({"mobile": mobile})

    with open(path, "w", encoding="utf-8") as handle:
        handle.write(header)
        handle.write(body)
        if mobile_header:
            handle.write("\n" if not header.endswith("\n\n") else "")
            handle.write(mobile_header)
        else:
            handle.write("\n")
        handle.write(tail)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help="Page to scrape the navigation from (default: %(default)s)",
    )
    parser.add_argument(
        "--data", default=DEFAULT_DATA,
        help="Path to nav-menu.yaml (default: the one in this script's submodule)",
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
        help="Merge the scraped menu into the data file (additive: nothing the "
             "data file has and live lacks is dropped)",
    )
    args = parser.parse_args(argv)

    try:
        html = fetch_html(args.url)
    except Exception as error:  # noqa: BLE001 - report any fetch failure cleanly
        print("ERROR: failed to fetch %s: %s" % (args.url, error), file=sys.stderr)
        return 2

    live, notes = scrape(html, site_host(args.url))
    if live is None or not live["items"]:
        print("ERROR: found no menu items in <nav class=\"v3-navbar_menu\"> on %s "
              "(page markup may have changed)." % args.url, file=sys.stderr)
        return 2

    try:
        data = load_data(args.data)
    except FileNotFoundError:
        print("ERROR: data file not found: %s" % args.data, file=sys.stderr)
        return 2
    except Exception as error:  # noqa: BLE001
        print("ERROR: failed to parse %s: %s" % (args.data, error), file=sys.stderr)
        return 2

    report = build_report(live, data, notes, args.url, args.data)

    if args.write:
        merged, kept = merge(live, data)
        write_data(args.data, merged)
        print("Wrote %s from %s." % (args.data, args.url), file=sys.stderr)
        for section in ("bar", "phone"):
            counts = report["menus"][section]
            print("  %s: +%d row(s), %d removed on live, %d reworded, %d moved"
                  % (section, len(counts["added"]), len(counts["removed"]),
                     len(counts["relabelled"]), len(counts["moved"])),
                  file=sys.stderr)
        if kept:
            print("  carried over (not on live):", file=sys.stderr)
            for entry in kept:
                print("    %s" % entry, file=sys.stderr)
        if report["notes"]:
            print("  notes:", file=sys.stderr)
            for note in report["notes"]:
                print("    %s" % note, file=sys.stderr)
        print("  comments inside the item lists are not preserved -- "
              "check `git diff`.", file=sys.stderr)
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
