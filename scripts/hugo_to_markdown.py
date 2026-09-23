#!/usr/bin/env python3
"""
Convert Hugo rendered HTML pages to Markdown, extracting only the
main content from <div class="td-content">.

Every page gets a small YAML header (title, canonical URL, description,
last modified date), and every link and image points to an absolute URL,
so a page still works when an agent copies it out of context. Internal
page links point to the Markdown copy of the target (`.../index.md`).

Usage:
    # Single file (prints to stdout)
    python hugo_to_markdown.py --input public/docs/my-page/index.html

    # Entire Hugo output directory (batch)
    python hugo_to_markdown.py --input public/ --output public/

Dependencies:
    pip install -r requirements-markdown.txt
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from markdownify import MarkdownConverter

# Taxonomy listings are link lists without content of their own.
SKIP_BODY_CLASSES = {"td-taxonomy", "td-term"}

# First line of every Markdown page; the llms.txt URL follows it.
LLMS_DIRECTIVE = "> For the complete documentation index, see [llms.txt]"


class DocsConverter(MarkdownConverter):
    def convert_a(self, el, text, parent_tags):
        # Glossary tooltips carry the definition in `title`; in Markdown it is noise.
        if "glossary-tooltip" in (el.get("class") or []):
            el.attrs.pop("title", None)
        return super().convert_a(el, text, parent_tags)


def code_language(pre):
    """Chroma puts the language on <pre data-language> and <code data-lang>."""
    if pre.get("data-language"):
        return pre["data-language"]
    code = pre.find("code")
    if code is None:
        return None
    if code.get("data-lang"):
        return code["data-lang"]
    for cls in code.get("class") or []:
        if cls.startswith("language-"):
            return cls[len("language-"):]
    return None


def meta(soup, *selectors):
    for sel in selectors:
        tag = soup.select_one(sel)
        if tag and tag.get("content", "").strip():
            return tag["content"].strip()
    return None


def md_url(url, site_prefix, aliases=None):
    """Point internal page links at their Markdown copy."""
    if not url.startswith(site_prefix):
        return url
    base, _, anchor = url.partition("#")
    # Alias pages are redirects and have no Markdown copy, so link the target.
    base = (aliases or {}).get(base, base)
    if base.endswith("/"):
        base += "index.md"
    elif base.endswith("/index.html"):
        base = base[: -len("index.html")] + "index.md"
    return base + (f"#{anchor}" if anchor else "")


def flatten_tabs(content, soup):
    """Tab panes render one after another, each labelled with its tab title."""
    for nav in content.select("ul.nav-tabs"):
        labels = {}
        for btn in nav.select("[data-bs-target]"):
            labels[btn["data-bs-target"].lstrip("#")] = btn.get_text(" ", strip=True)
        nav.decompose()
        for pane_id, label in labels.items():
            pane = content.find(id=pane_id)
            if pane is None:
                continue
            if not pane.get_text(strip=True):
                # Docsy uses empty, disabled tabs as row labels ("Package:").
                pane.decompose()
                continue
            heading = soup.new_tag("p")
            strong = soup.new_tag("strong")
            strong.string = label
            heading.append(strong)
            pane.insert(0, heading)


def convert_alerts(content, soup):
    for alert in content.select("div.alert"):
        heading = alert.select_one(".alert-heading")
        if heading:
            strong = soup.new_tag("strong")
            strong.string = heading.get_text(" ", strip=True).rstrip(":") + ":"
            heading.replace_with(strong)
        alert.name = "blockquote"
        alert.attrs = {}


def absolutize(content, page_url, site_prefix, aliases):
    for a in content.select("a[href]"):
        href = a["href"].strip()
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        if href.startswith("#"):
            a["href"] = md_url(page_url, site_prefix) + href
            continue
        a["href"] = md_url(urljoin(page_url, href), site_prefix, aliases)
    for img in content.select("img[src]"):
        img["src"] = urljoin(page_url, img["src"].strip())
        img.attrs.pop("srcset", None)


def html_file_to_markdown(
    html_path: Path,
    page_url: str | None = None,
    site_prefix: str | None = None,
    content_selector: str = "div.td-content",
    aliases: dict[str, str] | None = None,
) -> str | None:
    """
    Convert one rendered page to Markdown.

    Args:
        html_path: Path to the HTML file.
        page_url: Absolute URL of the page. Read from og:url when omitted.
        site_prefix: URL prefix of the site; links under it are internal.
        content_selector: CSS selector for the content element.
        aliases: Map of alias URLs to the URLs they redirect to.

    Returns:
        Markdown string, or None if the page has no content to convert.
    """
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")

    body = soup.body
    if body and SKIP_BODY_CLASSES & set(body.get("class") or []):
        return None

    content = soup.select_one(content_selector)
    if content is None:
        return None

    page_url = page_url or meta(soup, 'meta[property="og:url"]')
    if page_url and site_prefix is None:
        site_prefix = page_url

    description = meta(soup, 'meta[name="description"]', 'meta[property="og:description"]')
    if description:
        description = " ".join(description.split())
        # Without a front matter description, Hugo falls back to the page summary,
        # which only repeats the opening of the body. Compared without whitespace,
        # because plainify glues a heading to the next paragraph.
        # Docsy prints a front matter description as the lead paragraph under
        # the title, so the lead is left out too, or every real one would match.
        skip = [t for t in (content.find("h1"), content.select_one(".lead")) if t]
        body_text = "".join(
            "".join(t.split())
            for t in content.find_all(string=True)
            if not any(s in t.parents for s in skip)
        )
        # An empty page falls back further, to the site description.
        if description == meta(soup, 'meta[property="og:site_name"]') or body_text.startswith(
            "".join(description.split())[:60]
        ):
            description = None

    # Before the cleanup below: tab titles live in <button>s.
    flatten_tabs(content, soup)
    for tag in content.select(
        "script, style, nav, button, .td-page-meta, .td-heading-self-link, .visually-hidden"
    ):
        tag.decompose()
    convert_alerts(content, soup)
    if page_url:
        absolutize(content, page_url, site_prefix, aliases)

    md = DocsConverter(
        heading_style="ATX",
        bullets="-",
        code_language_callback=code_language,
        strip=["figure", "figcaption"],
        # An underscore inside a word never starts emphasis in CommonMark, and
        # agents read the raw text: `disk\_queue\_capacity` is not the metric name.
        escape_underscores=False,
    ).convert_soup(content)
    md = re.sub(r"[ \t]+\n", "\n", md)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"

    header = {
        "title": meta(soup, 'meta[property="og:title"]')
        or (soup.title.get_text(strip=True) if soup.title else None),
        "url": page_url,
        "description": description,
        "last_modified": meta(soup, 'meta[itemprop="dateModified"]'),
    }
    # json.dumps output is a valid YAML scalar, so no YAML dependency is needed.
    lines = [f"{k}: {json.dumps(v, ensure_ascii=False)}" for k, v in header.items() if v]
    # Agents that land on one page find the rest through llms.txt.
    if site_prefix:
        md = f"{LLMS_DIRECTIVE}({site_prefix}llms.txt).\n\n" + md
    return "---\n" + "\n".join(lines) + "\n---\n\n" + md


def site_prefix_for(html_path: Path, input_dir: Path) -> str | None:
    """
    The site's URL prefix, from a page's og:url minus its path under input_dir.
    Works for versioned sub-sites too, since each is built with its own baseURL.
    """
    soup = BeautifulSoup(html_path.read_text(encoding="utf-8"), "html.parser")
    page_url = meta(soup, 'meta[property="og:url"]')
    if not page_url:
        return None
    rel = html_path.relative_to(input_dir).parent.as_posix()
    rel = "" if rel == "." else rel + "/"
    if not page_url.endswith("/" + rel) and rel:
        return None
    return page_url[: len(page_url) - len(rel)]


REFRESH_RE = re.compile(r'<meta http-equiv="?refresh"? content="?\d+;\s*url=([^">]+)', re.I)


def collect_aliases(html_files, input_dir: Path, site_prefix: str) -> dict[str, str]:
    """Hugo writes each alias as a tiny page that only redirects."""
    aliases = {}
    for html_path in html_files:
        with html_path.open(encoding="utf-8") as f:
            head = f.read(2048)
        m = REFRESH_RE.search(head)
        if m:
            rel = html_path.relative_to(input_dir).parent.as_posix()
            aliases[site_prefix + ("" if rel == "." else rel + "/")] = urljoin(site_prefix, m.group(1))
    return aliases


LLMS_LINK_RE = re.compile(r"\]\((\S+?/index\.md)\)")


LLMS_SECTION_RE = re.compile(r"^- \[([^\]]+)\]\((\S+?/llms\.txt)\)")


def parse_llms_index(path: Path, input_dir: Path, site_prefix: str):
    """
    Title, summary, and (section title, [page .md URLs]) pairs, in llms.txt order.
    A root entry that links a section's own llms.txt is followed, so this reads
    both a single index and one split into section files.
    """
    title = summary = None
    sections = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# ") and title is None:
            title = line[2:].strip()
        elif line.startswith("> ") and summary is None:
            summary = line[2:].strip()
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif (m := LLMS_SECTION_RE.match(line)) and m.group(2).startswith(site_prefix):
            section_index = input_dir / m.group(2)[len(site_prefix) :]
            if section_index.exists():
                _, _, parts = parse_llms_index(section_index, input_dir, site_prefix)
                sections.append((m.group(1), [url for _, urls in parts for url in urls]))
            else:
                print(f"[WARN] llms.txt lists {m.group(2)}, which does not exist", file=sys.stderr)
        elif sections and line.lstrip().startswith("- "):
            m = LLMS_LINK_RE.search(line)
            if m:
                sections[-1][1].append(m.group(1))
    # The root's "## Sections" heading holds no pages of its own.
    return title, summary, [s for s in sections if s[1]]


def page_block(md: str, html_url: str) -> str:
    """A page inside a full-text file: its YAML header becomes one Source line."""
    if md.startswith("---\n"):
        end = md.find("\n---\n", 4)
        if end != -1:
            md = md[end + 5 :]
    # The index pointer is said once, in the full text's own header.
    lines = [line for line in md.strip().split("\n") if not line.startswith(LLMS_DIRECTIVE)]
    while lines and not lines[0].strip():
        lines.pop(0)
    for i, line in enumerate(lines):
        if line.startswith("# "):
            lines.insert(i + 1, f"Source: {html_url}")
            break
    else:
        lines.insert(0, f"Source: {html_url}")
    return "\n".join(lines)


def write_full_texts(input_dir: Path, output_dir: Path, site_prefix: str) -> None:
    """
    llms-full.txt for the whole site, and one per top-level section, with the
    pages in llms.txt order. Sites without the `LLMS` output format get neither.
    """
    index = input_dir / "llms.txt"
    if not index.exists():
        return
    title, summary, sections = parse_llms_index(index, input_dir, site_prefix)
    index_url = site_prefix + "llms.txt"

    def write(path: Path, header: str, blocks: list[str]) -> None:
        text = header + "\n\n" + "\n\n".join(blocks) + "\n"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        size = len(text.encode("utf-8"))
        # About four bytes a token for English prose.
        print(f"Written: {path} ({size / 1024:.0f} KB, ~{size / 4000:.0f}k tokens)")

    all_blocks = []
    for section, urls in sections:
        blocks = []
        for url in urls:
            md_path = output_dir / url[len(site_prefix) :] if url.startswith(site_prefix) else None
            if md_path is None or not md_path.exists():
                print(f"[WARN] llms.txt lists {url}, which has no Markdown copy", file=sys.stderr)
                continue
            blocks.append(page_block(md_path.read_text(encoding="utf-8"), url[: -len("index.md")]))
        if not blocks:
            continue
        all_blocks.extend(blocks)
        # A section's first entry is its own landing page, so its directory is the section's.
        section_dir = output_dir / urls[0][len(site_prefix) :]
        # The root's "Start here" group is the home page: it belongs in the
        # whole-site file only, which would overwrite a file of its own anyway.
        if section_dir.parent == output_dir:
            continue
        write(
            section_dir.parent / "llms-full.txt",
            f"# {section} (full text)\n\n> The full text of the {section} section of {title}. "
            f"Index of the whole site: {index_url}",
            blocks,
        )

    write(
        output_dir / "llms-full.txt",
        f"# {title} (full text)\n\n> {summary}\n\nThe full text of every page. "
        f"Index with links to each page and section: {index_url}",
        all_blocks,
    )


def process_directory(input_dir: Path, output_dir: Path, base_url: str | None, verbose: bool) -> None:
    html_files = sorted(p for p in input_dir.rglob("index.html") if "_print" not in p.parts)
    if not html_files:
        print(f"No index.html files found under {input_dir}", file=sys.stderr)
        return

    site_prefix = base_url.rstrip("/") + "/" if base_url else None
    if site_prefix is None:
        root = input_dir / "index.html"
        site_prefix = site_prefix_for(root, input_dir) if root.exists() else None
    if site_prefix is None:
        print("[ERROR] Cannot detect the site URL; pass --base-url", file=sys.stderr)
        sys.exit(1)

    aliases = collect_aliases(html_files, input_dir, site_prefix)

    converted = skipped = 0
    for html_path in html_files:
        relative = html_path.relative_to(input_dir).parent
        rel = relative.as_posix()
        page_url = site_prefix + ("" if rel == "." else rel + "/")
        md = html_file_to_markdown(
            html_path, page_url=page_url, site_prefix=site_prefix, aliases=aliases
        )
        if md is None:
            # Taxonomy listings and alias redirect pages.
            skipped += 1
            continue
        output_path = output_dir / relative / "index.md"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md, encoding="utf-8")
        converted += 1
        if verbose:
            print(f"Written: {output_path}")

    print(f"\nDone. Converted {converted} files, skipped {skipped}.")
    write_full_texts(input_dir, output_dir, site_prefix)


def main():
    parser = argparse.ArgumentParser(description="Hugo HTML → Markdown converter")
    parser.add_argument("--input", required=True, help="HTML file or Hugo public/ directory")
    parser.add_argument("--output", default=None, help="Output .md file or directory (omit to print to stdout)")
    parser.add_argument("--selector", default="div.td-content", help="CSS selector for content element")
    parser.add_argument(
        "--base-url",
        default=None,
        help="Site URL, like https://example.com/docs/ (default: detected from og:url of the home page)",
    )
    parser.add_argument("--verbose", action="store_true", help="Print each written file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    if input_path.is_file():
        md = html_file_to_markdown(input_path, site_prefix=args.base_url, content_selector=args.selector)
        if md is None:
            print(f"[WARN] Nothing to convert in {input_path}", file=sys.stderr)
            return
        if args.output:
            Path(args.output).write_text(md, encoding="utf-8")
        else:
            print(md)
    elif input_path.is_dir():
        output_dir = Path(args.output) if args.output else input_path.parent / "markdown"
        process_directory(input_path, output_dir, args.base_url, args.verbose)
    else:
        print(f"Error: {input_path} does not exist", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
