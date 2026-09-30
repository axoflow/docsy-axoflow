#!/usr/bin/env python3
"""Inventory a Hugo/Docsy content tree for an information-architecture audit.

Walks content/, reads front matter and body, resolves the internal link and
include graph, and reports structural problems plus per-page Diataxis signals.
The type signals are hints for the reader, not a classification: the audit
still reads the pages it flags.

Run from the project root:

    python3 themes/docsy-axoflow/.claude/skills/docs-ia/scripts/ia_inventory.py
    ... --section chapter-sources           # limit the report to one subtree
    ... --format json --out tmp/ia/inventory.json
    ... --format csv  --out tmp/ia/inventory.csv

Links are resolved across the whole site even with --section, so inbound
counts stay correct for the pages in scope.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import yaml
except ImportError:  # the fallback only reads flat `key: value` lines
    yaml = None

FRONT_MATTER = re.compile(r"\A﻿?---\s*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.S)
LINK_SHORTCODE = re.compile(r'\{\{[<%]\s*(?:relref|xref|ref)\s+"([^"]+)"\s*[>%]\}\}')
INCLUDE_SHORTCODE = re.compile(r'\{\{[<%]\s*(include-headless|readfile)\s+"?([^"\s}]+)"?')
MD_LINK = re.compile(r"\]\((/[^)\s#]*|[^):\s#]+\.md)(#[^)]*)?\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*(\{#[^}]*\})?\s*$")
FENCE = re.compile(r"^\s*(```|~~~)")
TABLE_RULE = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*\|")
ORDERED_ITEM =re.compile(r"^\s*\d+\.\s+\S")
OPTION_HEADING = re.compile(r"^[\w.-]+\(\)$")
TUTORIAL_WORDS = re.compile(r"\b(in this tutorial|you will learn|you'll learn|quickstart|let's|we will)\b", re.I)
PROCEDURE_INTRO = re.compile(r"\b(complete the following steps|do the following|follow these steps)\b", re.I)
EXPLAIN_WORDS = re.compile(r"\b(because|the reason|designed to|in contrast|trade-?off|how .{1,30} works|why)\b", re.I)


def parse_front_matter(text):
    m = FRONT_MATTER.match(text)
    if not m:
        return {}, text
    raw, body = m.group(1), text[m.end():]
    if yaml:
        try:
            data = yaml.safe_load(raw)
            if isinstance(data, dict):
                return data, body
        except yaml.YAMLError:
            pass
    data = {}
    for line in raw.splitlines():
        k, sep, v = line.partition(":")
        if sep and re.match(r"^[A-Za-z_]+$", k):
            data[k] = v.strip().strip('"')
    return data, body


def page_key(rel):
    """Hugo's page path: `a/b.md`, `a/b/_index.md` and `a/b/index.md` are all `a/b`."""
    key = re.sub(r"(^|/)_?index\.md$", "", rel.strip("/").rstrip("/"))
    return key[:-3] if key.endswith(".md") else key


def fm(meta, key):
    """Hugo front matter keys are case-insensitive (linkTitle vs linktitle)."""
    for k, v in meta.items():
        if str(k).lower() == key.lower():
            return v
    return None


CONCEPT_PATH = re.compile(r"concept|architecture|overview|how-it-works|intro", re.I)


def signals(body, path=""):
    """Count the markers that tend to separate the four Diataxis modes."""
    lines, in_code = [], False
    code_blocks = 0
    for line in body.splitlines():
        if FENCE.match(line):
            in_code = not in_code
            code_blocks += in_code
            continue
        if not in_code:
            lines.append(line)
    prose = "\n".join(lines)
    headings = [HEADING.match(l).group(2) for l in lines if HEADING.match(l)]
    option_headings = sum(1 for h in headings if OPTION_HEADING.match(h.strip("`")))
    steps = sum(1 for l in lines if ORDERED_ITEM.match(l))
    words = len(re.findall(r"\w+", re.sub(r"\{\{.*?\}\}", "", prose)))
    s = {
        "words": words,
        "headings": len(headings),
        "code_blocks": code_blocks,
        "steps": steps,
        "procedure_intros": len(PROCEDURE_INTRO.findall(prose)),
        "option_headings": option_headings,
        "tables": sum(1 for l in lines if TABLE_RULE.match(l)),
        "tutorial_words": len(TUTORIAL_WORDS.findall(prose)),
        "explain_words": len(EXPLAIN_WORDS.findall(prose)) + (4 if CONCEPT_PATH.search(path) else 0),
    }
    s["type_hint"], s["mixed_hint"] = type_hint(s)
    return s


def type_hint(s):
    """A cheap first guess so the audit knows which pages to read closely."""
    score = {
        "reference": s["option_headings"] * 2 + s["tables"] * 2,
        "how-to": s["steps"] + s["procedure_intros"] * 3,
        "tutorial": s["tutorial_words"] * 4 + (s["steps"] if s["tutorial_words"] else 0),
        "explanation": s["explain_words"] if s["steps"] < 3 and s["option_headings"] == 0 else 0,
    }
    if s["words"] < 60:
        return "stub", ""
    ranked = sorted(score.items(), key=lambda kv: -kv[1])
    best, runner = ranked[0], ranked[1]
    if best[1] < 3:
        return "unclear", ""
    # Two strong modes on one page is what an audit most wants to see.
    mixed = runner[0] if runner[1] >= 6 and runner[1] >= best[1] * 0.5 else ""
    return best[0], mixed


def git_dates(root, content):
    """Last commit time per file, from one `git log` pass instead of 900."""
    try:
        out = subprocess.run(
            ["git", "log", "--format=%x00%cs", "--name-only", "--", str(content)],
            cwd=root, capture_output=True, text=True, check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return {}
    dates, current = {}, None
    for line in out.splitlines():
        if line.startswith("\x00"):
            current = line[1:]
        elif line and current:
            dates.setdefault(line, current)
    return dates


class Site:
    def __init__(self, root, content, headless):
        self.root, self.content, self.headless = root, content, headless
        self.pages = {}      # rel path -> record
        self.by_key = {}     # Hugo page path -> rel path
        self.by_name = defaultdict(list)

    def load(self):
        files = sorted(self.content.rglob("*.md"))
        # Markdown next to a leaf bundle's index.md is a page resource (the
        # glossary terms, for one), not a page of its own.
        leaf_dirs = {f.parent for f in files if f.name == "index.md"}
        for path in files:
            rel = path.relative_to(self.content).as_posix()
            resource = path.name != "index.md" and any(d == path.parent or d in path.parents for d in leaf_dirs)
            text = path.read_text(encoding="utf-8", errors="replace")
            meta, body = parse_front_matter(text)
            is_snippet = rel.startswith(self.headless + "/") or bool(fm(meta, "headless"))
            if resource and not is_snippet:
                continue
            rec = {
                "path": rel,
                "dir": os.path.dirname(rel),
                "is_index": path.name in ("_index.md", "index.md"),
                "snippet": is_snippet,
                "title": str(fm(meta, "title") or ""),
                "linkTitle": str(fm(meta, "linkTitle") or ""),
                "weight": fm(meta, "weight"),
                "description": bool(fm(meta, "description")),
                "short_description": bool(fm(meta, "short_description")),
                "draft": bool(fm(meta, "draft")),
                "hidden": any(fm(meta, k) for k in ("toc_hide", "manuallink", "manuallinkrelref")),
                "aliases": len(fm(meta, "aliases") or []),
                "body": body,
            }
            self.pages[rel] = rec
            self.by_key.setdefault(page_key(rel), rel)
            self.by_name[os.path.basename(page_key(rel))].append(rel)

    def resolve(self, target, source_dir, snippet=False):
        target = target.split("#")[0].split("?")[0].strip()
        if not target:
            return None
        base = self.headless if snippet else ""
        cands = []
        if target.startswith("/"):
            cands.append(target.lstrip("/"))
        else:
            cands += [os.path.normpath(os.path.join(source_dir, target)), target]
            if base:
                cands.append(os.path.join(base, target))
        for c in cands:
            if c in self.pages:
                return c
            hit = self.by_key.get(page_key(c))
            if hit:
                return hit
        # Hugo's ref lookup falls back to a unique basename anywhere in the site.
        hits = self.by_name.get(os.path.basename(page_key(target))) or []
        return hits[0] if len(hits) == 1 else None

    def link_graph(self):
        for rec in self.pages.values():
            body = rec["body"]
            rec["out"], rec["broken"], rec["includes"] = set(), [], set()
            # Shortcode targets and .md links name content files; a plain
            # "/some/url/" link names a URL, so a miss there isn't a break.
            targets = [(t, True) for t in LINK_SHORTCODE.findall(body)]
            targets += [(m[0], m[0].endswith(".md")) for m in MD_LINK.findall(body)]
            for t, is_file in targets:
                if t.startswith("#"):
                    continue
                hit = self.resolve(t, rec["dir"])
                if hit:
                    rec["out"].add(hit)
                elif is_file:
                    rec["broken"].append(t)
            for kind, t in INCLUDE_SHORTCODE.findall(body):
                hit = self.resolve(t, rec["dir"], snippet=(kind == "include-headless"))
                if hit:
                    rec["includes"].add(hit)
        for rec in self.pages.values():
            rec["own_out"] = set(rec["out"])
        # A snippet's links belong to every page that includes it.
        for rec in self.pages.values():
            seen, stack = set(), list(rec["includes"])
            while stack:
                s = stack.pop()
                if s in seen:
                    continue
                seen.add(s)
                rec["out"] |= self.pages[s]["out"]
                stack += list(self.pages[s]["includes"])
            rec["out"].discard(rec["path"])
            # Readers see the snippets inline, so type signals count them too.
            rec["expanded"] = rec["body"] + "\n".join(self.pages[x]["body"] for x in sorted(seen))
        # Snippets include snippets, so count every includer, not just pages.
        included_by = Counter()
        for rec in self.pages.values():
            for t in rec["includes"]:
                included_by[t] += 1
        # Count each file that writes a link once: a snippet included on 16
        # pages is still one link a writer maintains, not 16.
        inbound = Counter()
        for rec in self.pages.values():
            if rec["draft"] or (rec["snippet"] and not included_by[rec["path"]]):
                continue
            for t in rec["own_out"] - {rec["path"]}:
                inbound[t] += 1
        for rec in self.pages.values():
            rec["in"] = inbound[rec["path"]]
            rec["included_by"] = included_by[rec["path"]]


def section_of(rec):
    """The directory whose _index.md lists this page in the sidebar."""
    return os.path.dirname(rec["dir"]) if rec["is_index"] else rec["dir"]


def depth(rec):
    d = rec["dir"].count("/") + 1 if rec["dir"] else 0
    return d if rec["is_index"] else d + 1


def structural_issues(site, pages, args):
    issues = defaultdict(list)
    nav = [r for r in site.pages.values() if not r["snippet"] and not r["draft"]]
    children = defaultdict(list)
    for r in nav:
        if r["path"] != "_index.md":
            children[section_of(r)].append(r)
    in_scope = {r["path"] for r in pages}
    parents = {section_of(r) for r in nav}

    dirs_with_md = {r["dir"] for r in nav if r["dir"]}
    for d in sorted(dirs_with_md):
        if d + "/_index.md" not in site.pages and d + "/index.md" not in site.pages:
            if any(p.startswith(d + "/") for p in in_scope):
                issues["missing_index"].append(d)

    for sec, kids in sorted(children.items()):
        index = next((site.pages[p] for p in (sec + "/_index.md", "_index.md") if p in site.pages
                      and site.pages[p]["dir"] == sec), None)
        if index and index["path"] not in in_scope:
            continue
        if not index and not any(k["path"] in in_scope for k in kids):
            continue
        visible = [k for k in kids if not k["hidden"]]
        if len(visible) > args.max_children:
            issues["wide_section"].append(f"{sec or '(root)'}: {len(visible)} children")
        weights = Counter(k["weight"] for k in visible if k["weight"] is not None)
        dup = [f"{w}×{n}" for w, n in weights.items() if n > 1]
        if dup:
            issues["weight_collision"].append(f"{sec or '(root)'}: " + ", ".join(dup))
        titles = Counter((k["linkTitle"] or k["title"]).lower() for k in visible)
        same = [t for t, n in titles.items() if n > 1 and t]
        if same:
            issues["duplicate_sibling_title"].append(f"{sec or '(root)'}: " + "; ".join(same))

    # Snippets live outside any section, so check them site-wide every time.
    for r in site.pages.values():
        if r["snippet"] and r["included_by"] == 0 and not r["is_index"]:
            issues["unused_snippet"].append(r["path"])

    for r in pages:
        if r["snippet"]:
            continue
        if r["draft"]:
            continue
        if r["weight"] is None:
            issues["missing_weight"].append(r["path"])
        if not r["description"]:
            issues["missing_description"].append(
                r["path"] + (" (has short_description to copy)" if r["short_description"] else ""))
        if not r["title"]:
            issues["missing_title"].append(r["path"])
        if depth(r) > args.max_depth:
            issues["deep_page"].append(f"{r['path']} (depth {depth(r)})")
        if r["in"] == 0 and r["path"] != "_index.md" and not r["hidden"]:
            issues["no_inbound_links"].append(r["path"])
        if not r["out"] and r["words"] > 150:
            issues["dead_end"].append(r["path"])
        if r["words"] < 60 and not (r["is_index"] and r["dir"] in parents):
            issues["stub"].append(r["path"])
        if r["mixed_hint"]:
            issues["mixed_type_hint"].append(f"{r['path']} ({r['type_hint']} + {r['mixed_hint']})")
        for b in r["broken"]:
            issues["unresolved_link"].append(f"{r['path']} → {b}")

    titles = defaultdict(list)
    for r in nav:
        titles[r["title"].lower()].append(r["path"])
    for t, ps in sorted(titles.items()):
        if t and len(ps) > 1 and any(p in in_scope for p in ps):
            issues["duplicate_title_sitewide"].append(f'"{t}": ' + ", ".join(ps))
    return issues


ISSUE_HELP = {
    "unresolved_link": "internal link target not found (check before trusting: Hugo may still resolve it)",
    "missing_index": "directory has pages but no _index.md, so it has no section page",
    "missing_title": "no title in front matter",
    "weight_collision": "siblings share a weight, so sidebar order falls back to title",
    "duplicate_sibling_title": "siblings with the same sidebar label",
    "duplicate_title_sitewide": "same title on several pages (search results and llms.txt can't tell them apart)",
    "mixed_type_hint": "strong signals of two Diataxis modes on one page (read it)",
    "wide_section": "long sidebar list (consider grouping, but grouping reference by component is fine)",
    "deep_page": "deeper than --max-depth",
    "no_inbound_links": "no cross-link from any other page (reachable only through the sidebar)",
    "dead_end": "no outgoing internal links",
    "missing_weight": "no weight, so sidebar order is by title",
    "missing_description": "no description (used by llms.txt and section listings)",
    "stub": "under 60 words of prose",
    "unused_snippet": "headless snippet that no page or snippet includes (site-wide)",
}


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--content", default="content", help="content directory (default: content)")
    ap.add_argument("--headless", default="headless", help="snippet directory inside content (default: headless)")
    ap.add_argument("--section", default="", help="only report pages under this path, relative to content/")
    ap.add_argument("--format", choices=["summary", "json", "csv"], default="summary")
    ap.add_argument("--out", help="write to this file instead of stdout")
    ap.add_argument("--max-depth", type=int, default=4, help="flag pages deeper than this (default: 4)")
    ap.add_argument("--max-children", type=int, default=25, help="flag sections with more children (default: 25)")
    ap.add_argument("--no-git", action="store_true", help="skip last-modified dates")
    args = ap.parse_args()

    root = Path.cwd()
    content = root / args.content
    if not content.is_dir():
        sys.exit(f"error: {content} not found; run from the project root or pass --content")

    site = Site(root, content, args.headless)
    site.load()
    site.link_graph()
    dates = {} if args.no_git else git_dates(root, content)
    prefix = args.content.rstrip("/") + "/"
    for r in site.pages.values():
        r.update(signals(r["expanded"], r["path"]))
        r["depth"] = depth(r)
        r["updated"] = dates.get(prefix + r["path"], "")

    scope = args.section.strip("/")
    pages = [r for r in site.pages.values()
             if not scope or r["path"] == scope or r["path"].startswith(scope + "/")]
    if not pages:
        sys.exit(f"error: no pages under {scope}")
    issues = structural_issues(site, pages, args)

    cols = ["path", "title", "weight", "depth", "is_index", "snippet", "description", "words",
            "type_hint", "mixed_hint", "steps", "procedure_intros", "option_headings", "tables",
            "code_blocks", "in", "included_by", "updated"]
    rows = [{c: r[c] for c in cols} | {"out": len(r["out"])} for r in pages]

    out = open(args.out, "w", encoding="utf-8", newline="") if args.out else sys.stdout
    if args.format == "json":
        json.dump({"pages": rows, "issues": issues}, out, indent=1, default=str)
    elif args.format == "csv":
        w = csv.DictWriter(out, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    else:
        docs = [r for r in pages if not r["snippet"] and not r["draft"]]
        print(f"# IA inventory: {scope or args.content}\n", file=out)
        print(f"Pages: {len(docs)} (+{len(pages) - len(docs)} snippets/drafts)  "
              f"Max depth: {max((r['depth'] for r in docs), default=0)}", file=out)
        hints = Counter(r["type_hint"] for r in docs)
        print("Type hints: " + ", ".join(f"{k} {v}" for k, v in hints.most_common()), file=out)
        dated = sorted(r["updated"] for r in docs if r["updated"])
        if dated:
            print(f"Last edited: oldest {dated[0]}, median {dated[len(dated) // 2]}", file=out)
        for key, help_text in ISSUE_HELP.items():
            items = issues.get(key)
            if not items:
                continue
            print(f"\n## {key} ({len(items)}): {help_text}", file=out)
            for i in items[:40]:
                print(f"- {i}", file=out)
            if len(items) > 40:
                print(f"- … {len(items) - 40} more (use --format json)", file=out)
    if args.out:
        out.close()


if __name__ == "__main__":
    main()
