#!/usr/bin/env python3

import os
import sys
import shutil
import subprocess
import re
import frontmatter

def is_markdown_file(file_path):
    return file_path.endswith(".md")

def git_mv(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    subprocess.run(["git", "mv", src, dst], check=True)

def url_path_for(hugo_path):
    """Site-relative URL for a content path, which may be a file or a directory.

    content/architecture/_index.md      -> /architecture/
    content/reference/aql/syntax.md     -> /reference/aql/syntax/
    content/concepts                    -> /concepts/
    """
    url = hugo_path[len("content"):]
    if url.endswith("/_index.md") or url.endswith("/index.md"):
        url = url[:url.rfind("/")]
    elif url.endswith(".md"):
        url = url[:-len(".md")]
    if not url.endswith("/"):
        url += "/"
    return url

def get_alias_path(hugo_path):
    # The alias a moved page keeps is its old URL, so this is the same
    # computation the glossary rewriting below needs. One implementation.
    return url_path_for(hugo_path)

def update_alias_in_frontmatter(file_path, original_alias):
    post = frontmatter.load(file_path)
    aliases = post.get("aliases", [])
    if not isinstance(aliases, list):
        aliases = [aliases]
    if original_alias not in aliases:
        aliases.append(original_alias)
    post["aliases"] = aliases
    with open(file_path, "w") as f:
        f.write(frontmatter.dumps(post))

def update_links_in_markdown(root_dir, old_path, new_path):
    old_path_relative = old_path[len("content"):]
    new_path_relative = new_path[len("content"):]

    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if not is_markdown_file(fname):
                continue

            fpath = os.path.join(dirpath, fname)
            with open(fpath, "r") as f:
                content = f.read()

            # Replace xref, relref, and ref links
            new_content = re.sub(
                r'(xref|relref)\s+"(' + re.escape(old_path_relative) + r'[^"]*)"',
                lambda m: f'{m.group(1)} "{m.group(2).replace(old_path_relative, new_path_relative)}"',
                content
            )
            new_content = re.sub(
                r'(ref:\s+)' + re.escape(old_path_relative),
                lambda m: f'{m.group(1)}{new_path_relative}',
                new_content
            )

            if content != new_content:
                with open(fpath, "w") as f:
                    f.write(new_content)

# `full_link: /architecture/#router`, optionally quoted. The value is a URL and
# not a content path, which is why the xref/relref rewriting above cannot see it.
FULL_LINK_RE = re.compile(
    r'^(\s*full_link:\s*)(["\']?)(?P<url>[^"\'\s#]+)(?P<frag>#[^"\'\s]*)?\2\s*$',
    re.MULTILINE,
)

def update_glossary_full_links(root_dir, old_url, new_url):
    """Repoint glossary `full_link` front matter at a page that moved.

    A glossary term links to the page that documents it through `full_link`,
    which holds a site-relative URL rather than a content path. Nothing else in
    this script looks at URLs, and Hugo's link render hook never sees front
    matter, so without this a move leaves every tooltip for that term pointing
    at a 404.

    NOT EVERY PROJECT HAS A GLOSSARY, and this needs no flag for that: a project
    without one has no `full_link` keys anywhere under content/, so the walk
    finds nothing and changes nothing. It also does not care where the glossary
    lives, which matters because the directory is configurable
    (`params.glossary.path`).

    Rewrites the matching line textually rather than through the frontmatter
    library, so files that merely happen to be near a match keep their YAML
    formatting: folded scalars and list styles survive untouched.

    Both URLs end in "/", so prefix matching cannot confuse /data-sources/ with
    /data-sources-legacy/. An absolute `full_link` to another site starts with a
    scheme and never matches.
    """
    changed = []

    def repoint(match):
        url = match.group("url")
        if not url.startswith(old_url):
            return match.group(0)
        moved = new_url + url[len(old_url):]
        quote = match.group(2)
        return f'{match.group(1)}{quote}{moved}{match.group("frag") or ""}{quote}'

    for dirpath, _, filenames in os.walk(root_dir):
        for fname in filenames:
            if not is_markdown_file(fname):
                continue
            fpath = os.path.join(dirpath, fname)
            with open(fpath, "r") as f:
                content = f.read()
            new_content = FULL_LINK_RE.sub(repoint, content)
            if content != new_content:
                with open(fpath, "w") as f:
                    f.write(new_content)
                changed.append(fpath)

    return changed

def move_and_update(original_path, new_path):
    if not os.path.exists(original_path):
        print(f"Error: {original_path} does not exist.")
        return

    if os.path.isdir(original_path):
        for root, dirs, files in os.walk(original_path):
            for file in files:
                old_file_path = os.path.join(root, file)
                relative = os.path.relpath(old_file_path, original_path)
                new_file_path = os.path.join(new_path, relative)

                git_mv(old_file_path, new_file_path)

                if is_markdown_file(new_file_path):
                    alias = get_alias_path(os.path.join("content", os.path.relpath(old_file_path, "content")))
                    update_alias_in_frontmatter(new_file_path, alias)
    else:
        new_file_path = new_path
        git_mv(original_path, new_file_path)

        if is_markdown_file(new_file_path):
            alias = get_alias_path(os.path.join("content", os.path.relpath(original_path, "content")))
            update_alias_in_frontmatter(new_file_path, alias)

    update_links_in_markdown("content", original_path, new_path)

    # After the git mv, so read off the paths rather than the filesystem.
    retargeted = update_glossary_full_links(
        "content", url_path_for(original_path), url_path_for(new_path)
    )

    print(f"✅ Move complete: {original_path} → {new_path}")
    if retargeted:
        print(f"   Repointed full_link in {len(retargeted)} glossary term(s):")
        for path in retargeted:
            print(f"     {path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python move_hugo_content.py <original_path> <new_path>")
        sys.exit(1)

    original = sys.argv[1].rstrip("/")
    new = sys.argv[2].rstrip("/")

    move_and_update(original, new)
