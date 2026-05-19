#!/usr/bin/env python3
"""
find-unused-assets.py — locate images and headless markdown snippets that no
page or template references, so they wouldn't end up in the built site.

What counts as "used":
  Images:
    - Referenced by basename or full path inside any .md, .html, .scss, .css,
      .js, .yaml, .yml, or .toml file under content/, layouts/, themes/, data/.
      Catches markdown ![alt](src), HTML <img src=…>, `featured_image:` front
      matter values, `resources.Get "img/…"` calls, and CSS url(…) refs.
  Headless snippets (content/headless/*.md):
    - Referenced by an {{< include-headless "<filename>" >}} or
      {{< readfile "<path>" >}} shortcode anywhere under content/ or layouts/.

Known limitations (false negatives — i.e. things flagged as "unused" that
might actually be used):
  - Dynamic paths constructed by templates at build time (e.g.
    `<img src="{{ printf "img/%s.png" $name }}">`) won't be detected. Verify
    flagged images manually before deleting.
  - Glob patterns inside include-headless (e.g. "step-*.md") are recognized
    only when the literal pattern string also matches the snippet's basename.
    Files referenced exclusively via a wildcard may show up here.
  - Basename matching is loose. Two files with the same name in different
    bundles are conflated: a reference to `screenshot.png` in folder A will
    keep `screenshot.png` in folder B alive too. This means the script is
    biased toward false NEGATIVES (missing some unused files) rather than
    false POSITIVES (incorrectly flagging a used file), which is the safer
    direction when deletions are on the line.

Usage:
    python3 scripts/find-unused-assets.py             # run from repo root
    python3 scripts/find-unused-assets.py --quiet     # only print findings
    python3 scripts/find-unused-assets.py --root /path/to/repo

Exit code: 0 if nothing unused, 1 if any unused images or snippets found.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

IMAGE_EXTS = {'.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.avif'}
TEXT_EXTS = {'.md', '.html', '.htm', '.scss', '.css', '.js',
             '.yaml', '.yml', '.toml'}

# Directories that hold images on disk:
IMAGE_DIRS = (
    'assets/img',
    'static/img',
    'themes/docsy-axoflow/static/img',
    'content',  # page-bundle resources alongside markdown
)

# Directories whose text files might reference images or snippets:
SCAN_DIRS = (
    'content',
    'layouts',
    'data',
    'themes/docsy-axoflow/layouts',
    'themes/docsy-axoflow/assets',
)

# Where headless snippets live. Files directly under this dir are candidates.
HEADLESS_DIR = 'content/headless'

# Always skip these subtrees, even if encountered under a scan dir:
SKIP_DIRS = {'.git', 'node_modules', '_gen', 'public', '.unlighthouse',
             'resources'}

# Captures every image-extension path-like token in text. Anchors at a
# non-word boundary, then a path of [\w./\-] up to the extension. Catches
# all common reference forms: markdown ![](…), HTML src="…", template
# "img/…", front-matter "image: foo.png", CSS url(foo.png).
IMG_REF_RE = re.compile(
    r'([\w./\-]+\.(?:png|jpe?g|gif|svg|webp|avif))\b',
    re.IGNORECASE,
)

# Captures include-headless / readfile / include shortcode invocations with
# a quoted first argument. Hugo allows {{< … >}} and {{% … %}}, single or
# double-quoted args, and trailing space before the closing delimiter.
INCLUDE_RE = re.compile(
    r'\{\{[%<]\s*(?:include-headless|readfile|include)\s+["\']([^"\']+)["\']',
)


def iter_files(root: Path, dir_rel: str, exts: set[str]):
    """Yield every file under root/dir_rel whose suffix is in exts, skipping
    SKIP_DIRS subtrees and hidden directories."""
    base = root / dir_rel
    if not base.exists():
        return
    for dirpath, dirnames, filenames in os.walk(base):
        # Prune unwanted descents in-place so os.walk respects them.
        dirnames[:] = [d for d in dirnames
                       if d not in SKIP_DIRS and not d.startswith('.')]
        for name in filenames:
            if Path(name).suffix.lower() in exts:
                yield Path(dirpath) / name


def collect_text(root: Path) -> list[tuple[Path, str]]:
    """Read every scannable text file once. Returned tuples are (path, text)."""
    out = []
    seen = set()
    for d in SCAN_DIRS:
        for f in iter_files(root, d, TEXT_EXTS):
            if f in seen:
                continue
            seen.add(f)
            try:
                out.append((f, f.read_text(encoding='utf-8', errors='replace')))
            except OSError as e:
                print(f'WARN: could not read {f}: {e}', file=sys.stderr)
    return out


def find_unused_images(root: Path, texts: list[tuple[Path, str]]):
    """Return (unused, total) for image files on disk."""
    # All image candidates on disk.
    image_files: set[Path] = set()
    for d in IMAGE_DIRS:
        for f in iter_files(root, d, IMAGE_EXTS):
            image_files.add(f)

    # Pull every img-shaped token out of every text file. Bucket into:
    #   - exact paths (with their original separators, lowercased)
    #   - bare basenames (lowercased)
    referenced_paths: set[str] = set()
    referenced_basenames: set[str] = set()
    for _, blob in texts:
        for m in IMG_REF_RE.finditer(blob):
            ref = m.group(1).lower().lstrip('/')
            referenced_paths.add(ref)
            referenced_basenames.add(os.path.basename(ref))

    unused: list[Path] = []
    for img in sorted(image_files):
        rel = img.relative_to(root)
        name = img.name.lower()
        parts = [p.lower() for p in rel.parts]

        if name in referenced_basenames:
            continue

        # Build path-form candidates that templates / markdown might use to
        # refer to this file. Examples for assets/img/foo/bar.png:
        #     img/foo/bar.png        (typical template usage)
        #     foo/bar.png            (relative inside the bundle)
        #     bar.png                (basename only — already checked above)
        candidates = {'/'.join(parts), '/'.join(parts[1:]) if len(parts) > 1 else ''}
        for prefix in ('assets', 'static', 'themes/docsy-axoflow/static',
                       'content'):
            pp = prefix.split('/')
            if parts[: len(pp)] == pp:
                tail = parts[len(pp):]
                if tail:
                    candidates.add('/'.join(tail))
        if any(c and c in referenced_paths for c in candidates):
            continue

        unused.append(img)
    return unused, len(image_files)


def find_unused_snippets(root: Path, texts: list[tuple[Path, str]]):
    """Return (unused, total) for headless markdown snippets."""
    snippet_dir = root / HEADLESS_DIR
    snippets = sorted(p for p in iter_files(root, HEADLESS_DIR, {'.md'})
                      if p.name not in ('_index.md', 'index.md', 'README.md'))

    referenced: set[str] = set()
    referenced_basenames: set[str] = set()
    for _, blob in texts:
        for m in INCLUDE_RE.finditer(blob):
            ref = m.group(1).strip()
            referenced.add(ref)
            referenced_basenames.add(os.path.basename(ref))

    unused: list[Path] = []
    for snip in snippets:
        rel = snip.relative_to(snippet_dir)
        # include-headless typically takes the basename ("foo.md") relative
        # to content/headless/, but tolerate full paths too.
        candidates = {
            str(rel),                       # "subdir/foo.md"
            str(rel.with_suffix('')),       # "subdir/foo"
            snip.name,                      # "foo.md"
            snip.stem,                      # "foo"
        }
        if any(c in referenced or c in referenced_basenames for c in candidates):
            continue
        unused.append(snip)
    return unused, len(snippets)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0])
    ap.add_argument('--root', default='.', help='Repository root (default: cwd)')
    ap.add_argument('--quiet', action='store_true',
                    help='Suppress the header line; only print findings')
    args = ap.parse_args()
    root = Path(args.root).resolve()

    texts = collect_text(root)
    unused_imgs, total_imgs = find_unused_images(root, texts)
    unused_snips, total_snips = find_unused_snippets(root, texts)

    if not args.quiet:
        print(f'Scanned {total_imgs} image files and '
              f'{total_snips} headless snippets.\n')

    if unused_imgs:
        print(f'=== {len(unused_imgs)} unused image(s) ===')
        for f in unused_imgs:
            print(f'  {f.relative_to(root)}')
        print()

    if unused_snips:
        print(f'=== {len(unused_snips)} unused snippet(s) ===')
        for f in unused_snips:
            print(f'  {f.relative_to(root)}')
        print()

    if not unused_imgs and not unused_snips:
        if not args.quiet:
            print('Nothing unused.')
        return 0
    return 1


if __name__ == '__main__':
    sys.exit(main())
