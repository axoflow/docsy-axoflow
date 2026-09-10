#!/usr/bin/env python3
"""Check axoflow.com's chrome CSS against a recorded baseline.

The other three scripts answer "does the chrome say what live says". This one
answers "has marketing REDRAWN it" -- the question that was invisible until the
Products menu grew from three groups to seven and the panel's
`grid-template-columns: 1fr 1fr 25%` stopped describing anything real.

WHAT IT DOES NOT DO. It does not compare live's CSS with this site's. It cannot:
the two share no class names (`.v3-navbar_mega-dropdown-col` against
`.axo-nav-col`), the numbers live in different files, and whether two boxes look
alike is a question about rendered geometry, not about declarations. That
comparison needs a browser and a judgement call, so it is a review with eyes on
it -- the `chrome-parity` skill, in .claude/skills/ of this submodule -- and not
this script.

What this does is narrow and deterministic: fetch the stylesheets the page
links, keep every rule whose selector mentions one of the chrome's own class
prefixes, normalize it, and diff that against a baseline committed next to the
data files. A change here means live's own design moved, and names the rule that
moved, which is the cue to go and look.

    baselines/chrome-css.json    the baseline: selector -> declarations.
                                 Regenerate with --write when the change is
                                 understood and this site has caught up.

Normalizing means: declarations split, sorted and de-duplicated per rule, and
`@media` conditions kept as part of the rule's key. Webflow reorders and
re-hashes its output on every publish, so a raw text diff of the stylesheet is
noise; a diff of sorted declarations under a stable key is not.

Output formats (``--format``):

    text   human-readable report (default)
    json   the same report, machine-readable
    css    the scraped rules, as CSS, for eyeballing or for a manual diff

Exit status: 0 when the chrome CSS matches the baseline, 1 on drift, 2 on a
runtime error -- suitable for CI gating.

Dependencies: BeautifulSoup (``beautifulsoup4``)

Usage:
    python3 themes/docsy-axoflow/scripts/check_chrome_css.py
    python3 themes/docsy-axoflow/scripts/check_chrome_css.py --format css
    python3 themes/docsy-axoflow/scripts/check_chrome_css.py --write
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from axoflow_site import fetch_html

DEFAULT_URL = "https://axoflow.com/"
# `baselines/`, not `data/`: Hugo merges a theme's data directory into
# `site.Data` on every build, and 27KB of somebody else's stylesheet is not
# site data.
DEFAULT_BASELINE = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "baselines", "chrome-css.json")
)

# The chrome this site reproduces, and nothing else. A Webflow stylesheet is
# 140KB of the whole marketing site; without this filter every unrelated publish
# would read as chrome drift.
CHROME_PREFIXES = (
    "v3-navbar",     # the bar, both menus and the mega panels
    "v3-footer",     # the footer's three rows
    "v2-banner",     # the announcement strip
    "v2-button",     # the CTA beside the menu
    "v3-dropdown-chevron",  # the glyphs the partials inline
)

# Declarations that carry no design information and change on every publish.
IGNORED_PROPERTIES = ("-webkit-font-smoothing", "-moz-osx-font-smoothing")


# --------------------------------------------------------------------------- #
# Collecting the stylesheets
# --------------------------------------------------------------------------- #

def stylesheet_urls(html, page_url):
    """Every stylesheet the page links, absolute, in document order."""
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for link in soup.find_all("link"):
        rels = [r.lower() for r in (link.get("rel") or [])]
        href = (link.get("href") or "").strip()
        if "stylesheet" not in rels or not href:
            continue
        url = urljoin(page_url, href)
        if url not in urls:
            urls.append(url)
    return urls


def inline_styles(html):
    """The contents of the page's own <style> blocks."""
    soup = BeautifulSoup(html, "html.parser")
    return [tag.get_text() for tag in soup.find_all("style") if tag.get_text().strip()]


def fetch_stylesheets(html, page_url, skip_hosts=()):
    """Return (sources, notes): the CSS text of the page's own stylesheets.

    Third-party sheets are skipped -- the chrome is Webflow's own output and a
    slider library's stylesheet is not something this site reproduces.
    """
    sources, notes = [], []
    for url in stylesheet_urls(html, page_url):
        if any(host in url for host in skip_hosts):
            notes.append("skipped a third-party stylesheet: %s" % url)
            continue
        try:
            sources.append((url, fetch_html(url)))
        except Exception as error:  # noqa: BLE001 - reported, not fatal
            notes.append("could not fetch %s: %s" % (url, error))
    for index, text in enumerate(inline_styles(html)):
        sources.append(("inline <style> #%d" % (index + 1), text))
    return sources, notes


# --------------------------------------------------------------------------- #
# Parsing
# --------------------------------------------------------------------------- #

def strip_comments(css):
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def split_rules(css, condition=""):
    """Yield (condition, selector, declarations) for every rule in `css`.

    A hand-rolled scanner rather than a CSS library: the only structure that
    matters here is at-rule nesting, the input is minified machine output, and a
    dependency that has to be installed before CI can check the design is a
    dependency that will not be installed.
    """
    index, length = 0, len(css)
    while index < length:
        brace = css.find("{", index)
        if brace == -1:
            return
        prelude = css[index:brace].strip()
        if prelude.startswith("@"):
            # Find the matching close for this at-rule.
            depth, scan = 1, brace + 1
            while scan < length and depth:
                if css[scan] == "{":
                    depth += 1
                elif css[scan] == "}":
                    depth -= 1
                scan += 1
            body = css[brace + 1:scan - 1]
            name = " ".join(prelude.split())
            if name.startswith(("@media", "@supports", "@layer")):
                nested = ("%s and %s" % (condition, name)) if condition else name
                for rule in split_rules(body, nested):
                    yield rule
            index = scan
            continue
        close = css.find("}", brace)
        if close == -1:
            return
        yield condition, prelude, css[brace + 1:close]
        index = close + 1


def normalize_declarations(text):
    """Declarations sorted, de-duplicated and whitespace-collapsed.

    Webflow emits the same property twice in one rule and reorders rules between
    publishes, so sorting is what makes a diff mean "this changed" rather than
    "this was regenerated".
    """
    out = set()
    for part in text.split(";"):
        if ":" not in part:
            continue
        prop, _, value = part.partition(":")
        prop = " ".join(prop.split()).lower()
        value = " ".join(value.split())
        if not prop or not value or prop in IGNORED_PROPERTIES:
            continue
        out.add("%s: %s" % (prop, value))
    return sorted(out)


def is_chrome(selector, prefixes):
    return any(prefix in selector for prefix in prefixes)


def collect(sources, prefixes=CHROME_PREFIXES):
    """Every chrome rule in the fetched CSS, keyed by condition + selector.

    A key can occur more than once across the sheets -- Webflow repeats a
    selector under different media queries and in its second, "optimized" file.
    Declarations accumulate into the key's set, so the baseline records what the
    page says about a box rather than which file happened to say it.
    """
    rules = {}
    for _, css in sources:
        for condition, selector, declarations in split_rules(strip_comments(css)):
            # One prelude can list several selectors; keep only the chrome ones,
            # so a rule shared with the rest of the site does not drag it in.
            wanted = [s.strip() for s in selector.split(",")
                      if is_chrome(s, prefixes)]
            if not wanted:
                continue
            body = normalize_declarations(declarations)
            if not body:
                continue
            for one in wanted:
                key = "%s | %s" % (condition, one) if condition else one
                rules.setdefault(key, set()).update(body)
    return {key: sorted(value) for key, value in sorted(rules.items())}


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #

def load_baseline(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except FileNotFoundError:
        return None
    return data.get("rules", data)


def write_baseline(path, rules, source_url):
    payload = {
        "_comment": (
            "axoflow.com's CSS for the chrome this site reproduces, normalized "
            "by scripts/check_chrome_css.py. Not a stylesheet: a baseline, so "
            "that a change to live's own design is visible as a diff. "
            "Regenerate with --write once the change is understood."
        ),
        "source": source_url,
        "prefixes": list(CHROME_PREFIXES),
        "rules": rules,
    }
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")


# --------------------------------------------------------------------------- #
# Comparison
# --------------------------------------------------------------------------- #

def build_report(rules, baseline, notes, source_url, baseline_path):
    if baseline is None:
        return {
            "source_url": source_url,
            "baseline_path": baseline_path,
            "baseline_missing": True,
            "rule_count": len(rules),
            "added": sorted(rules),
            "removed": [],
            "changed": [],
            "notes": notes,
            "drift_count": 0,
        }

    added = [key for key in rules if key not in baseline]
    removed = [key for key in baseline if key not in rules]
    changed = []
    for key, declarations in rules.items():
        if key not in baseline or baseline[key] == declarations:
            continue
        was, now = set(baseline[key]), set(declarations)
        changed.append({
            "selector": key,
            "added": sorted(now - was),
            "removed": sorted(was - now),
        })

    return {
        "source_url": source_url,
        "baseline_path": baseline_path,
        "baseline_missing": False,
        "rule_count": len(rules),
        "added": sorted(added),
        "removed": sorted(removed),
        "changed": sorted(changed, key=lambda c: c["selector"]),
        "notes": notes,
        "drift_count": len(added) + len(removed) + len(changed),
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #

def render_css(rules):
    out = []
    for key, declarations in rules.items():
        out.append("/* %s */" % key)
        selector = key.split(" | ")[-1]
        out.append("%s {" % selector)
        for declaration in declarations:
            out.append("    %s;" % declaration)
        out.append("}")
    return "\n".join(out)


def render_text(report):
    lines = ["Chrome CSS check",
             "  source   : %s" % report["source_url"],
             "  baseline : %s" % report["baseline_path"],
             "  chrome rules on live: %d" % report["rule_count"],
             ""]

    if report["baseline_missing"]:
        lines.append("  no baseline yet — run with --write to record one.")
        lines.append("")
        lines.append("OK: nothing to compare against.")
        return "\n".join(lines)

    for key in report["added"]:
        lines.append("    + %s" % key)
    for key in report["removed"]:
        lines.append("    - %s" % key)
    for entry in report["changed"]:
        lines.append("    ~ %s" % entry["selector"])
        for declaration in entry["removed"]:
            lines.append("        was: %s" % declaration)
        for declaration in entry["added"]:
            lines.append("        now: %s" % declaration)

    if report["notes"]:
        lines.append("")
        lines.append("Notes:")
        for note in report["notes"]:
            lines.append("    * %s" % note)

    lines.append("")
    if report["drift_count"]:
        lines.append("DRIFT: %d rule(s) changed. Look at the boxes these name "
                     "before accepting them: this reports that live's design "
                     "moved, not what to do about it. `--write` re-records the "
                     "baseline." % report["drift_count"])
    else:
        lines.append("OK: the chrome CSS matches the baseline.")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--url", default=DEFAULT_URL,
                        help="Page whose stylesheets to read (default: %(default)s)")
    parser.add_argument("--baseline", default=DEFAULT_BASELINE,
                        help="Path to the baseline JSON (default: the one in "
                             "this script's submodule)")
    parser.add_argument("--format", choices=("text", "json", "css"),
                        default="text", help="Output format (default: %(default)s)")
    parser.add_argument("--output", default=None,
                        help="Write the report to this file instead of stdout")
    parser.add_argument("--write", action="store_true",
                        help="Re-record the baseline from live")
    args = parser.parse_args(argv)

    try:
        html = fetch_html(args.url)
    except Exception as error:  # noqa: BLE001
        print("ERROR: failed to fetch %s: %s" % (args.url, error), file=sys.stderr)
        return 2

    sources, notes = fetch_stylesheets(html, args.url, skip_hosts=("cdn.jsdelivr.net",))
    if not sources:
        print("ERROR: found no stylesheets on %s." % args.url, file=sys.stderr)
        return 2

    rules = collect(sources)
    if not rules:
        print("ERROR: no rule on %s matched the chrome prefixes %s "
              "(the marketing markup may have been renamed)."
              % (args.url, ", ".join(CHROME_PREFIXES)), file=sys.stderr)
        return 2

    baseline = load_baseline(args.baseline)
    report = build_report(rules, baseline, notes, args.url, args.baseline)

    if args.write:
        write_baseline(args.baseline, rules, args.url)
        print("Recorded %d chrome rule(s) in %s from %s."
              % (len(rules), args.baseline, args.url), file=sys.stderr)
        if not report["baseline_missing"]:
            print("  %d added, %d removed, %d changed against the previous "
                  "baseline." % (len(report["added"]), len(report["removed"]),
                                 len(report["changed"])), file=sys.stderr)
        for note in notes:
            print("  note: %s" % note, file=sys.stderr)
        return 0

    if args.format == "json":
        rendered = json.dumps(report, indent=2, ensure_ascii=False)
    elif args.format == "css":
        rendered = render_css(rules)
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
