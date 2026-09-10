#!/usr/bin/env python3
"""Check (and optionally sync) axoflow.com's footer against data/footer.yaml.

The documentation footer reproduces the marketing one box for box and renders
from ``themes/docsy-axoflow/data/footer.yaml`` (``_partials/footer.html`` and
its three row partials), so this is the footer counterpart of
``check_main_menu.py``: it scrapes ``footer.v3-footer_component`` and diffs
every part of it against that file.

    row-1   the five link columns          -> columns
    row-2   logo, tagline, badges          -> logo / tagline / badges
    row-3   copyright, privacy, social      -> copyright / privacy / social

Three things in the data file are NOT copies of live and are preserved rather
than overwritten -- they are why this cannot be a plain re-extraction:

    vendored art    `logo.light`, `logo.dark` and `badges[].file` point at
                    files under assets/img/footer/, while live serves CDN URLs
                    with a Webflow hash in the name. The paths are kept; the
                    script instead checks the artwork behind them (the logo by
                    its path data, a badge by its filename) and says when it
                    looks like it needs re-vendoring.
    social labels   live's social links have no text at all -- they are icons.
                    The label is what `footer/row-3.html` keys its inlined
                    glyph off, so labels are derived from the link's host and
                    checked against the glyphs that partial actually defines.
    corrections     the marketing footer spells it `Capablities`; this site
                    says `Capabilities`. The typo fix is applied on the way in
                    and reported, so `--write` never regresses it.

`copyright` is live's line with its `[auto-updating date]` placeholder -- the
year Webflow fills in client-side -- replaced by the current year.

Output formats (``--format``):

    text   human-readable drift report (default)
    json   the same report, machine-readable
    yaml   the scraped footer in footer.yaml's schema, ready to diff or merge

With ``--write`` the data file is regenerated. Links the data file has and live
does not are carried over, column title casing is kept (the stylesheet
uppercases the titles anyway), and the comment blocks are preserved -- the
header and the note above `social:`. Comments inside a list are not.

Exit status: 0 when the footer matches live, 1 on drift, 2 on a runtime error
-- suitable for CI gating.

Dependencies: BeautifulSoup (``beautifulsoup4``), PyYAML

Usage:
    python3 themes/docsy-axoflow/scripts/check_footer.py
    python3 themes/docsy-axoflow/scripts/check_footer.py --format json
    python3 themes/docsy-axoflow/scripts/check_footer.py --format yaml
    python3 themes/docsy-axoflow/scripts/check_footer.py --write
"""

import argparse
import datetime
import json
import os
import re
import sys
from urllib.parse import unquote, urlparse

import yaml
from bs4 import BeautifulSoup

from axoflow_site import (
    RawMarkup,
    clean_text,
    fetch_html,
    normalize_label,
    normalize_url,
    read_comment_blocks,
    site_host,
)

DEFAULT_URL = "https://axoflow.com/"
_HERE = os.path.dirname(__file__)
# footer.yaml lives at ../data/ relative to this script; the glyph keys the
# social strip is limited to are in the partial that renders it.
DEFAULT_DATA = os.path.normpath(os.path.join(_HERE, "..", "data", "footer.yaml"))
ROW_3_PARTIAL = os.path.normpath(
    os.path.join(_HERE, "..", "layouts", "_partials", "footer", "row-3.html")
)
ASSETS_DIR = os.path.normpath(os.path.join(_HERE, "..", "assets"))

# What the data file tags every outbound footer href with -- `menu` on the bar,
# `footer` here. Added by this script, not by axoflow.com, and ignored when
# comparing.
UTM_SUFFIX = "?utm_source=docs&utm_medium=footer"

# Live link text this site deliberately does not copy. Applied on the way in so
# a regeneration cannot quietly reintroduce the typo; every application is
# reported. Marketing's own copy still needs the fix.
LABEL_CORRECTIONS = {"Capablities": "Capabilities"}

# The social marks are icons with no text, so the label -- which is also the
# glyph key in footer/row-3.html and the anchor's accessible name -- comes from
# the host.
SOCIAL_LABELS = {
    "x.com": "X",
    "twitter.com": "X",
    "linkedin.com": "LinkedIn",
    "github.com": "GitHub",
    "discord.gg": "Discord",
    "discord.com": "Discord",
    "youtube.com": "YouTube",
    "mastodon.social": "Mastodon",
    "bsky.app": "Bluesky",
}

# The order footer.yaml writes its top-level keys in.
TOP_LEVEL_KEYS = ("logo", "tagline", "copyright", "privacy", "columns",
                  "badges", "social")


# --------------------------------------------------------------------------- #
# Scraping
# --------------------------------------------------------------------------- #

class FooterExtractor:
    """Turns axoflow.com's footer into footer.yaml's own shape.

    `notes` collects everything the caller has to know that the values
    themselves do not say: corrections applied, artwork that needs
    re-vendoring, a social mark the partial has no glyph for.
    """

    def __init__(self, html, host="axoflow.com", data=None):
        self.host = host
        self.soup = BeautifulSoup(html, "html.parser")
        self.markup = RawMarkup(html)
        # The current data file, for the values that are this site's own and
        # not live's: vendored asset paths and the social labels.
        self.data = data or {}
        self.notes = []

    # -- helpers ----------------------------------------------------------- #

    def href(self, anchor):
        """A data-file style href: absolute, and UTM-tagged like its neighbours."""
        if anchor is None:
            return None
        raw = (anchor.get("href") or "").strip()
        if not raw or raw == "#":
            return None
        parsed = urlparse(raw)
        if not parsed.netloc:
            raw = "https://%s%s" % (self.host,
                                    raw if raw.startswith("/") else "/" + raw)
            parsed = urlparse(raw)
        if parsed.query:  # live already carries a query: leave it alone
            return raw
        return raw + UTM_SUFFIX

    def label(self, anchor):
        """Link text, with this site's corrections applied."""
        text = clean_text(anchor)
        fixed = LABEL_CORRECTIONS.get(text)
        if fixed:
            self.notes.append(
                "correction applied: live says %r, this site says %r" % (text, fixed)
            )
            return fixed
        return text

    # -- entry point ------------------------------------------------------- #

    def extract(self):
        footer = self.soup.select_one("footer.v3-footer_component") \
            or self.soup.select_one(".v3-footer_component")
        if footer is None:
            return None
        return {
            "logo": self.logo(footer),
            "tagline": self.tagline(footer),
            "copyright": self.copyright(footer),
            "privacy": self.privacy(footer),
            "columns": self.columns(footer),
            "badges": self.badges(footer),
            "social": self.social(footer),
        }

    # -- row 1 -------------------------------------------------------------- #

    def columns(self, footer):
        columns = []
        for column in footer.select(".v3-footer_row-1_column"):
            title = clean_text(column.select_one(".v3-footer_row-1_label"))
            links = []
            for anchor in column.select(".v3-footer_row-1_links a"):
                href = self.href(anchor)
                if href:
                    links.append({"label": self.label(anchor), "href": href})
            if title or links:
                columns.append({"title": title, "links": links})
        return columns

    # -- row 2 -------------------------------------------------------------- #

    def logo(self, footer):
        """The wordmark link. The art stays vendored; only the href is live's.

        The inline SVG is compared with the files under assets/ by its path
        data, which ignores the recolour that makes the dark variant a
        different file -- so a note here means the artwork itself changed.
        """
        anchor = footer.select_one(".v3-footer_row-2_logo-link")
        logo = dict(self.data.get("logo") or {})
        logo["href"] = self.href(anchor) or logo.get("href")

        live_paths = svg_path_set(str(footer.select_one(".v3-footer_row-2_logo svg")))
        for variant in ("light", "dark"):
            relative = logo.get(variant)
            if not relative or not live_paths:
                continue
            path = os.path.join(ASSETS_DIR, relative)
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    vendored = svg_path_set(handle.read())
            except OSError:
                self.notes.append("logo.%s: %s is missing" % (variant, relative))
                continue
            if vendored != live_paths:
                self.notes.append(
                    "logo.%s: %s no longer matches the wordmark live inlines; "
                    "re-vendor it" % (variant, relative)
                )
        return logo

    def tagline(self, footer):
        """Two lines: the lead, and the accent live wraps in a coloured span."""
        paragraph = footer.select_one(".v3-footer_row-2 p")
        if paragraph is None:
            return None
        accent = clean_text(paragraph.find("span"))
        lead = clean_text(paragraph)
        if accent and lead.endswith(accent):
            lead = lead[:-len(accent)].strip()
        return {"lead": lead, "accent": accent}

    def badges(self, footer):
        """The compliance badges: live's href and alt, this site's vendored file."""
        by_label = {normalize_label(b.get("label")): b
                    for b in self.data.get("badges") or []}
        badges = []
        for anchor in footer.select(".v3-footer_row-2_iso-link"):
            image = anchor.find("img")
            label = (image.get("alt") or "").strip() if image else ""
            href = self.href(anchor)
            if not href:
                continue
            known = by_label.get(normalize_label(label)) or {}
            badge = {"label": label, "href": href, "file": known.get("file")}
            source = (image.get("src") or "") if image else ""
            if badge["file"] and not same_image(source, badge["file"]):
                self.notes.append(
                    "badges: %r is vendored as %s but live now serves %s; "
                    "re-vendor it" % (label, badge["file"],
                                      os.path.basename(unquote(source)))
                )
            elif not badge["file"]:
                badge["file"] = "img/footer/%s" % os.path.basename(unquote(source))
                self.notes.append(
                    "badges: %r is new; %s has to be vendored under assets/%s"
                    % (label, source, badge["file"])
                )
            badges.append(badge)
        return badges

    # -- row 3 -------------------------------------------------------------- #

    def copyright(self, footer):
        """Live's line, with the year it fills in client-side filled in here."""
        row = footer.select_one(".v3-footer_row-3")
        if row is None:
            return None
        block = row.select_one("div.text-size-small")
        if block is None:
            return None
        block = BeautifulSoup(str(block), "html.parser")
        for span in block.find_all("span"):
            # `<span id="copyright-year">[auto-updating date]</span>`: a Webflow
            # placeholder, not text a reader ever sees.
            if span.get("id") == "copyright-year" or \
                    re.fullmatch(r"\[.*\]", clean_text(span)):
                span.string = str(datetime.date.today().year)
        return clean_text(block)

    def privacy(self, footer):
        for anchor in footer.select(".v3-footer_row-3 a"):
            if "privacy" in (anchor.get("href") or "").lower():
                return {"label": clean_text(anchor), "href": self.href(anchor)}
        return None

    def social(self, footer):
        """The marks, in live's order. Labels are keys into row-3.html's glyphs."""
        glyphs = known_glyphs()
        by_url = {normalize_url(entry.get("href"), self.host): entry.get("label")
                  for entry in self.data.get("social") or []}
        social = []
        for anchor in footer.select(".v3-footer_row-3_social-link"):
            raw = (anchor.get("href") or "").strip()
            if not raw:
                continue
            host = site_host(raw, default="")
            # No UTM on these: they leave axoflow.com entirely, and the live
            # footer does not tag them either.
            label = (by_url.get(normalize_url(raw, self.host))
                     or SOCIAL_LABELS.get(host)
                     or host.split(".")[0].capitalize())
            if glyphs and label not in glyphs:
                self.notes.append(
                    "social: %s has no glyph named %r in footer/row-3.html; add "
                    "one there or the mark renders empty" % (raw, label)
                )
            social.append({"label": label, "href": raw})
        return social


def svg_path_set(markup):
    """The `d` attributes in some SVG markup, as a set: artwork minus colour."""
    if not markup:
        return set()
    return {value.strip() for value in re.findall(r'\bd="([^"]+)"', markup)}


def same_image(source_url, vendored_path):
    """Whether a CDN URL and a vendored file look like the same image.

    Webflow serves ``<hash>_soc2 logo.webp``; the repo has ``soc2-logo.webp``.
    Comparing the alphanumerics of the two names catches a swapped image but
    not a re-upload of the same one under the same name -- which is why the
    report says "looks like", and why a badge is worth an eye now and then.
    """
    def key(name):
        name = os.path.basename(unquote(name or ""))
        name = re.sub(r"^[0-9a-f]{16,}_", "", name)
        name = os.path.splitext(name)[0]
        return re.sub(r"[^a-z0-9]", "", name.lower())

    return key(source_url) == key(vendored_path)


def known_glyphs(path=ROW_3_PARTIAL):
    """The glyph names footer/row-3.html defines, or an empty set if unreadable.

    The partial holds a `dict` of ``"Name" "M…"`` pairs and indexes it by each
    social entry's label, so a label that is not in here draws nothing.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            source = handle.read()
    except OSError:
        return set()
    return set(re.findall(r'"([^"]{1,24})"\s+"M', source))


def scrape(html, host="axoflow.com", data=None):
    extractor = FooterExtractor(html, host, data)
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


def walk_links(columns, host="axoflow.com"):
    """Every column link as a flat record, in footer order."""
    records = []
    for column in columns or []:
        title = column.get("title", "")
        for index, link in enumerate(column.get("links") or []):
            key = normalize_url(link.get("href"), host)
            if not key:
                continue
            records.append({
                "column": title,
                "label": link.get("label", ""),
                "href": link.get("href"),
                "url": key,
                "link_index": index,
            })
    return records


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #

def diff_columns(live_columns, data_columns, host="axoflow.com"):
    """Compare the five link columns, pass at a time.

    The passes are the ones check_main_menu.py uses, and for the same reason:
    a row that moved column, got reworded or got repointed should read as that
    and not as an addition plus a removal.
    """
    live = walk_links(live_columns, host)
    data = walk_links(data_columns, host)

    remaining_live = list(live)
    remaining_data = list(data)
    pairs = []

    def pass_over(predicate, bucket):
        for record in list(remaining_live):
            for candidate in remaining_data:
                if predicate(record, candidate):
                    remaining_live.remove(record)
                    remaining_data.remove(candidate)
                    pairs.append((record, candidate))
                    if bucket is not None:
                        bucket.append((record, candidate))
                    break

    same_label = lambda l, d: normalize_label(l["label"]) == normalize_label(d["label"])
    same_column = lambda l, d: normalize_label(l["column"]) == normalize_label(d["column"])

    relabelled_pairs, retargeted_pairs = [], []
    pass_over(lambda l, d: l["url"] == d["url"] and same_label(l, d)
              and same_column(l, d), None)
    pass_over(lambda l, d: l["url"] == d["url"] and same_label(l, d), None)
    pass_over(lambda l, d: l["url"] == d["url"] and same_column(l, d),
              relabelled_pairs)
    pass_over(lambda l, d: same_column(l, d) and same_label(l, d),
              retargeted_pairs)
    pass_over(lambda l, d: l["url"] == d["url"], relabelled_pairs)

    live_titles = [c.get("title", "") for c in live_columns or []]
    data_titles = [c.get("title", "") for c in data_columns or []]
    data_keys = [normalize_label(t) for t in data_titles]
    live_keys = [normalize_label(t) for t in live_titles]

    shared = {l["url"] for l, _ in pairs}

    return {
        "live_link_count": len(live),
        "data_link_count": len(data),
        "matched_count": len(pairs),
        "added": remaining_live,
        "removed": remaining_data,
        # Rewording the matcher cannot see: it pairs on a normalized label, so a
        # change of case or of whitespace -- `Privacy Policy` losing its
        # non-breaking space, say -- pairs cleanly and then differs.
        "wording": [{"url": l["url"], "column": l["column"],
                     "live": l["label"], "data": d["label"]}
                    for l, d in pairs if l["label"] != d["label"]
                    and normalize_label(l["label"]) == normalize_label(d["label"])],
        "relabelled": [{"url": l["url"], "column": l["column"],
                        "live": l["label"], "data": d["label"]}
                       for l, d in relabelled_pairs],
        "retargeted": [{"label": l["label"], "column": l["column"],
                        "live": l["href"], "data": d["href"]}
                       for l, d in retargeted_pairs],
        "moved": [{"label": l["label"], "url": l["url"],
                   "live": l["column"], "data": d["column"]}
                  for l, d in pairs
                  if normalize_label(l["column"]) != normalize_label(d["column"])],
        "columns_added": [t for t, k in zip(live_titles, live_keys)
                          if k not in data_keys],
        "columns_removed": [t for t, k in zip(data_titles, data_keys)
                            if k not in live_keys],
        "columns_reordered": ([k for k in live_keys if k in data_keys]
                              != [k for k in data_keys if k in live_keys]),
        "order_differs": ([l["url"] for l in live if l["url"] in shared]
                          != [d["url"] for d in data if d["url"] in shared]),
    }


def diff_list(live_entries, data_entries, host, key_field="href"):
    """Compare badges or social: matched on URL, so order and text drift show."""
    def key(entry):
        return normalize_url(entry.get(key_field), host, keep_root=True)

    live_keys = [key(e) for e in live_entries or []]
    data_keys = [key(e) for e in data_entries or []]
    by_key = {key(e): e for e in data_entries or []}

    return {
        "added": [e for e in live_entries or [] if key(e) not in data_keys],
        "removed": [e for e in data_entries or [] if key(e) not in live_keys],
        "relabelled": [
            {"href": e.get("href"), "live": e.get("label"),
             "data": by_key[key(e)].get("label")}
            for e in live_entries or []
            if key(e) in by_key
            and normalize_label(e.get("label")) != normalize_label(
                by_key[key(e)].get("label"))
        ],
        # As in diff_columns: a case- or whitespace-only rewrite of a label the
        # normalized comparison above treats as unchanged.
        "wording": [
            {"href": e.get("href"), "live": e.get("label"),
             "data": by_key[key(e)].get("label")}
            for e in live_entries or []
            if key(e) in by_key
            and e.get("label") != by_key[key(e)].get("label")
            and normalize_label(e.get("label")) == normalize_label(
                by_key[key(e)].get("label"))
        ],
        "reordered": ([k for k in live_keys if k in data_keys]
                      != [k for k in data_keys if k in live_keys]),
    }


def scalar_drift(live, data, host):
    """The single-value fields, compared field by field."""
    drift = []

    def check(field, live_value, data_value, url=False):
        if url:
            same = normalize_url(live_value, host, keep_root=True) == \
                normalize_url(data_value, host, keep_root=True)
        else:
            same = (live_value or "").strip() == (data_value or "").strip()
        if not same:
            drift.append({"field": field, "live": live_value, "data": data_value})

    check("logo.href", (live.get("logo") or {}).get("href"),
          (data.get("logo") or {}).get("href"), url=True)
    for field in ("lead", "accent"):
        check("tagline." + field, (live.get("tagline") or {}).get(field),
              (data.get("tagline") or {}).get(field))
    check("copyright", live.get("copyright"), data.get("copyright"))
    check("privacy.label", (live.get("privacy") or {}).get("label"),
          (data.get("privacy") or {}).get("label"))
    check("privacy.href", (live.get("privacy") or {}).get("href"),
          (data.get("privacy") or {}).get("href"), url=True)
    return drift


def drift_count(report):
    columns = report["columns"]
    total = sum(len(columns[k]) for k in
                ("added", "removed", "relabelled", "retargeted", "moved",
                 "wording", "columns_added", "columns_removed"))
    total += columns["columns_reordered"]
    for section in ("badges", "social"):
        part = report[section]
        total += sum(len(part[k]) for k in
                     ("added", "removed", "relabelled", "wording"))
        total += part["reordered"]
    return total + len(report["scalars"])


def build_report(live, data, notes, source_url, data_path, host):
    report = {
        "source_url": source_url,
        "data_path": data_path,
        "columns": diff_columns(live.get("columns"), data.get("columns"), host),
        "badges": diff_list(live.get("badges"), data.get("badges"), host),
        "social": diff_list(live.get("social"), data.get("social"), host),
        "scalars": scalar_drift(live, data, host),
        "notes": notes,
    }
    report["drift_count"] = drift_count(report)
    return report


# --------------------------------------------------------------------------- #
# Merging, for --write
# --------------------------------------------------------------------------- #

def merge(live, data, host):
    """The footer to write: live, plus what the data file has and live lacks.

    Column titles keep the data file's casing where the column is the same one
    -- the file writes them upper case, the stylesheet uppercases them anyway,
    and the title is also each column's `aria-label`.
    """
    kept = []
    live_urls = {r["url"] for r in walk_links(live.get("columns"), host)}
    by_title = {normalize_label(c.get("title")): c
                for c in data.get("columns") or []}

    columns = []
    for column in live.get("columns") or []:
        known = by_title.get(normalize_label(column.get("title"))) or {}
        links = list(column.get("links") or [])
        live_labels = {normalize_label(l.get("label")) for l in links}
        for index, link in enumerate(known.get("links") or []):
            if normalize_url(link.get("href"), host) in live_urls:
                continue
            if normalize_label(link.get("label")) in live_labels:
                continue  # same row, new destination: live's href wins
            links.insert(min(index, len(links)), link)
            kept.append("%s > %s (%s)" % (column.get("title"), link.get("label"),
                                          link.get("href")))
        columns.append({
            "title": known.get("title") or column.get("title"),
            "links": links,
        })

    for column in data.get("columns") or []:
        if normalize_label(column.get("title")) in {
                normalize_label(c.get("title")) for c in columns}:
            continue
        columns.append(column)
        kept.append("%s (whole column, %d link(s))"
                    % (column.get("title"), len(column.get("links") or [])))

    merged = {
        "logo": live.get("logo") or data.get("logo"),
        "tagline": live.get("tagline") or data.get("tagline"),
        "copyright": live.get("copyright") or data.get("copyright"),
        "privacy": live.get("privacy") or data.get("privacy"),
        "columns": columns,
        "badges": live.get("badges") or data.get("badges"),
        "social": live.get("social") or data.get("social"),
    }
    return merged, kept


# --------------------------------------------------------------------------- #
# Rendering the data file
# --------------------------------------------------------------------------- #

def quote(value):
    """A double-quoted YAML scalar, which is how footer.yaml writes every one."""
    text = "" if value is None else str(value)
    return '"%s"' % text.replace("\\", "\\\\").replace('"', '\\"')


def render_footer_yaml(footer, comments=None):
    """Write footer.yaml by hand, in the layout and quoting style it already has.

    Hand-written rather than `yaml.dump`, because that emits plain unquoted
    scalars and its own indentation, which would rewrite every line of a file
    whose values mostly have not changed.
    """
    comments = comments or {}
    out = []

    def block(key):
        """The prose that sat above this key in the file being replaced."""
        if comments.get(key):
            out.append(comments[key].rstrip("\n"))

    def mapping(key, node, fields):
        block(key)
        out.append("%s:" % key)
        for field in fields:
            if node and node.get(field) is not None:
                block("%s.%s" % (key, field))
                out.append("  %s: %s" % (field, quote(node[field])))
        out.append("")

    mapping("logo", footer.get("logo"), ("href", "light", "dark"))
    mapping("tagline", footer.get("tagline"), ("lead", "accent"))

    block("copyright")
    out.append("copyright: %s" % quote(footer.get("copyright")))
    out.append("")

    mapping("privacy", footer.get("privacy"), ("label", "href"))

    block("columns")
    out.append("columns:")
    for column in footer.get("columns") or []:
        out.append("  - title: %s" % quote(column.get("title")))
        out.append("    links:")
        for link in column.get("links") or []:
            out.append("      - label: %s" % quote(link.get("label")))
            out.append("        href: %s" % quote(link.get("href")))
    out.append("")

    block("badges")
    out.append("badges:")
    for badge in footer.get("badges") or []:
        out.append("  - label: %s" % quote(badge.get("label")))
        out.append("    href: %s" % quote(badge.get("href")))
        out.append("    file: %s" % quote(badge.get("file")))
    out.append("")

    block("social")
    out.append("social:")
    for entry in footer.get("social") or []:
        out.append("  - label: %s" % quote(entry.get("label")))
        out.append("    href: %s" % quote(entry.get("href")))

    return "\n".join(out) + "\n"


def write_data(path, footer):
    """Regenerate the data file, keeping its header and per-key comment blocks.

    A comment on one item of a list has no key to hang off and does not
    survive -- read the diff.
    """
    header, comments = read_comment_blocks(path)
    body = render_footer_yaml(footer, comments)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(header)
        handle.write(body)


# --------------------------------------------------------------------------- #
# Rendering the report
# --------------------------------------------------------------------------- #

def render_text(report):
    columns = report["columns"]
    lines = ["Footer check",
             "  source : %s" % report["source_url"],
             "  data   : %s" % report["data_path"],
             "",
             "  columns: %d link(s) on live, %d in the data file, %d matched"
             % (columns["live_link_count"], columns["data_link_count"],
                columns["matched_count"])]

    for record in columns["added"]:
        lines.append("    + %-44s %s  [%s]"
                     % (record["url"], record["label"], record["column"]))
    for record in columns["removed"]:
        lines.append("    - %-44s %s  [%s]"
                     % (record["url"], record["label"], record["column"]))
    for record in columns["relabelled"]:
        lines.append("    ~ %-44s %r -> %r"
                     % (record["url"], record["data"], record["live"]))
    for record in columns["retargeted"]:
        lines.append("    ~ %-44s %s -> %s"
                     % (record["label"], record["data"], record["live"]))
    for record in columns["moved"]:
        lines.append("    > %-44s %s -> %s"
                     % (record["label"], record["data"], record["live"]))
    for record in columns["wording"]:
        lines.append("    ~ %-44s %r -> %r  (whitespace/case)"
                     % (record["url"], record["data"], record["live"]))
    for title in columns["columns_added"]:
        lines.append("    + column  %s" % title)
    for title in columns["columns_removed"]:
        lines.append("    - column  %s" % title)
    if columns["columns_reordered"]:
        lines.append("    columns are in a different order than live")
    if columns["order_differs"]:
        lines.append("    links are in a different order than live")

    for section in ("badges", "social"):
        part = report[section]
        changes = []
        for entry in part["added"]:
            changes.append("    + %s  %s" % (entry.get("label"), entry.get("href")))
        for entry in part["removed"]:
            changes.append("    - %s  %s" % (entry.get("label"), entry.get("href")))
        for entry in part["relabelled"]:
            changes.append("    ~ %s  %r -> %r"
                           % (entry["href"], entry["data"], entry["live"]))
        for entry in part["wording"]:
            changes.append("    ~ %s  %r -> %r  (whitespace/case)"
                           % (entry["href"], entry["data"], entry["live"]))
        if part["reordered"]:
            changes.append("    order differs from live")
        lines.append("")
        lines.append("  %s: %s" % (section, "in sync" if not changes else ""))
        lines.extend(changes)

    lines.append("")
    if report["scalars"]:
        lines.append("  text and links outside the columns:")
        for entry in report["scalars"]:
            lines.append("    ~ %s" % entry["field"])
            lines.append("        live: %s" % entry["live"])
            lines.append("        data: %s" % entry["data"])
    else:
        lines.append("  text and links outside the columns: in sync")

    if report["notes"]:
        lines.append("")
        lines.append("Notes (what the data file keeps that live does not say):")
        for note in report["notes"]:
            lines.append("    * %s" % note)

    lines.append("")
    if report["drift_count"]:
        lines.append("DRIFT: %d difference(s). `--format yaml` prints the scraped "
                     "footer; `--write` merges it into the data file."
                     % report["drift_count"])
    else:
        lines.append("OK: the footer matches axoflow.com.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--url", default=DEFAULT_URL,
        help="Page to scrape the footer from (default: %(default)s)",
    )
    parser.add_argument(
        "--data", default=DEFAULT_DATA,
        help="Path to footer.yaml (default: the one in this script's submodule)",
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
        help="Merge the scraped footer into the data file (additive: nothing "
             "the data file has and live lacks is dropped)",
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
    live, notes = scrape(html, host, data)
    if live is None or not live["columns"]:
        print("ERROR: found no link columns in <footer "
              "class=\"v3-footer_component\"> on %s (page markup may have "
              "changed)." % args.url, file=sys.stderr)
        return 2

    report = build_report(live, data, notes, args.url, args.data, host)

    if args.write:
        merged, kept = merge(live, data, host)
        write_data(args.data, merged)
        columns = report["columns"]
        print("Wrote %s from %s." % (args.data, args.url), file=sys.stderr)
        print("  columns: +%d link(s), %d removed on live, %d reworded, %d moved"
              % (len(columns["added"]), len(columns["removed"]),
                 len(columns["relabelled"]), len(columns["moved"])),
              file=sys.stderr)
        if report["scalars"]:
            print("  updated: %s"
                  % ", ".join(e["field"] for e in report["scalars"]),
                  file=sys.stderr)
        if kept:
            print("  carried over (not on live):", file=sys.stderr)
            for entry in kept:
                print("    %s" % entry, file=sys.stderr)
        if notes:
            print("  notes:", file=sys.stderr)
            for note in notes:
                print("    %s" % note, file=sys.stderr)
        print("  comments inside the lists are not preserved -- "
              "check `git diff`.", file=sys.stderr)
        return 0

    if args.format == "json":
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
    elif args.format == "yaml":
        rendered = render_footer_yaml(live).rstrip("\n")
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
