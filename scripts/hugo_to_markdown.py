#!/usr/bin/env python3
"""
Convert Hugo rendered HTML pages to Markdown, extracting only the
main content from <div class="td-content">.

Usage:
    # Single file
    python hugo_to_markdown.py --input public/docs/my-page/index.html

    # Entire Hugo output directory (batch)
    python hugo_to_markdown.py --input public/ --output markdown/

Dependencies:
    pip install beautifulsoup4 html2text
"""

import argparse
import sys
from pathlib import Path

import html2text
from bs4 import BeautifulSoup


def html_file_to_markdown(
    html_path: Path,
    content_selector: str = "div.td-content",
    base_url: str = "",
) -> str | None:
    """
    Parse an HTML file and convert the selected element to Markdown.

    Args:
        html_path: Path to the HTML file.
        content_selector: CSS selector for the content element.
        base_url: Optional base URL to resolve relative links.

    Returns:
        Markdown string, or None if the selector matched nothing.
    """
    html = html_path.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "html.parser")

    content = soup.select_one(content_selector)
    if content is None:
        return None

    # Optional: strip elements you don't want in the LLM output
    for tag in content.select("script, style, .td-page-meta, nav"):
        tag.decompose()

    converter = html2text.HTML2Text()
    converter.baseurl = base_url       # resolves relative hrefs
    converter.ignore_links = False     # keep links as [text](url)
    converter.ignore_images = False    # keep images as ![alt](src)
    converter.body_width = 0          # no hard line wrapping
    converter.protect_links = True    # don't mangle URLs
    converter.wrap_links = False
    converter.mark_code = True     # use ``` for code blocks

    md = converter.handle(str(content)).strip()
 
    # html2text's mark_code wraps blocks in [code]...[/code] — convert to fences
    import re
    md = re.sub(r"\[code\]\n?", "```\n", md)
    md = re.sub(r"\n?\[/code\]", "\n```", md)
 
    return md

def process_single(html_path: Path, output_path: Path | None, verbose: bool = False, **kwargs) -> None:
    md = html_file_to_markdown(html_path, **kwargs)
    if md is None:
        print(f"[WARN] Selector not found in {html_path}", file=sys.stderr)
        return
    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(md, encoding="utf-8")
        if verbose:
            print(f"Written: {output_path}")
    else:
        print(md)


def process_directory(input_dir: Path, output_dir: Path, **kwargs) -> None:
    html_files = list(input_dir.rglob("index.html"))
    if not html_files:
        print(f"No index.html files found under {input_dir}", file=sys.stderr)
        return

    converted = 0
    for html_path in html_files:
        # Skip files inside _print directories
        if "_print" in html_path.parts:
            continue
        # Mirror the directory structure, replacing index.html with .md
        relative = html_path.relative_to(input_dir).parent  # e.g. docs/getting-started
        output_path = output_dir / relative / "index.md"
        process_single(html_path, output_path, **kwargs)
        converted += 1

    print(f"\nDone. Converted {converted} files.")


def main():
    parser = argparse.ArgumentParser(description="Hugo HTML → Markdown converter")
    parser.add_argument("--input", required=True, help="HTML file or Hugo public/ directory")
    parser.add_argument("--output", default=None, help="Output .md file or directory (omit to print to stdout)")
    parser.add_argument("--selector", default="div.td-content", help="CSS selector for content element")
    parser.add_argument("--base-url", default="", help="Base URL to resolve relative links (e.g. https://example.com)")
    parser.add_argument("--verbose", action="store_true", help="Print each written file path")
    args = parser.parse_args()

    input_path = Path(args.input)
    kwargs = dict(content_selector=args.selector, base_url=args.base_url, verbose=args.verbose)

    if input_path.is_file():
        output_path = Path(args.output) if args.output else None
        process_single(input_path, output_path, **kwargs)
    elif input_path.is_dir():
        output_dir = Path(args.output) if args.output else input_path.parent / "markdown"
        process_directory(input_path, output_dir, **kwargs)
    else:
        print(f"Error: {input_path} does not exist", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
