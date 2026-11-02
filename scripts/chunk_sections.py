#!/usr/bin/env python3
"""Show how a Markdown page splits into chunks for agent retrieval.

Retrieval pipelines usually cut a page at its h2 and h3 headings, and an
agent often sees only one of those chunks. This script splits the page the
same way and prints the word count of each section, so /review-page can flag
sections that are too long to fit in one chunk (default: 300 words).

It also lists two things that chunk badly: h4-h6 headings, which a chunker
can cut away from their parent heading, and bold lines used as headings,
which become plain text after conversion.

Works on source pages (included snippets aren't expanded) and on the
Markdown that hugo_to_markdown.py writes into public/.

Background: https://idratherbewriting.com/blog/chunking-content-for-mcp-ingestion-agent-readability

Usage: themes/docsy-axoflow/scripts/chunk_sections.py <file.md> [--limit WORDS]
"""

import argparse
import re
import sys
from pathlib import Path

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
PSEUDO_HEADING_RE = re.compile(r"^\*\*[^*]+\*\*:?\s*$")
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def strip_front_matter(lines):
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                return lines[i + 1:], i + 1
    return lines, 0


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", type=Path)
    parser.add_argument("--limit", type=int, default=300,
                        help="flag sections longer than this many words")
    args = parser.parse_args()

    lines, offset = strip_front_matter(args.file.read_text().splitlines())

    # Each section: [line number, heading level, heading text, word count]
    sections = [[offset + 1, 0, "(before the first heading)", 0]]
    deep, pseudo = [], []
    in_fence = False

    for i, line in enumerate(lines, start=offset + 1):
        if FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence:
            m = HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                if level in (2, 3):
                    sections.append([i, level, m.group(2), 0])
                    continue
                if level >= 4:
                    deep.append((i, line.strip()))
            elif PSEUDO_HEADING_RE.match(line.strip()):
                pseudo.append((i, line.strip()))
        # Code and tables count too: they fill the chunk like prose does.
        sections[-1][3] += len(line.split())

    print(f"{'line':>5}  {'words':>5}  section")
    for lineno, level, title, words in sections:
        if level == 0 and words == 0:
            continue
        mark = "  <-- over limit" if words > args.limit else ""
        indent = "  " if level == 3 else ""
        print(f"{lineno:>5}  {words:>5}  {indent}{title}{mark}")

    for label, items in (("h4-h6 headings", deep),
                         ("Bold lines used as headings", pseudo)):
        if items:
            print(f"\n{label}:")
            for lineno, text in items:
                print(f"{lineno:>5}  {text}")

    over = sum(1 for s in sections if s[3] > args.limit)
    return 1 if over or deep or pseudo else 0


if __name__ == "__main__":
    sys.exit(main())
