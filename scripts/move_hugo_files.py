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

def get_alias_path(hugo_path):
    # Remove 'content' prefix and filename if present
    alias = hugo_path[len("content"):]
    if alias.endswith("/_index.md") or alias.endswith("index.md"):
        alias = alias[:alias.rfind("/")]
    elif alias.endswith(".md"):
        alias = alias[:alias.rfind(".md")]
    if not alias.endswith("/"):
        alias += "/"
    return alias

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
    print(f"✅ Move complete: {original_path} → {new_path}")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python move_hugo_content.py <original_path> <new_path>")
        sys.exit(1)

    original = sys.argv[1].rstrip("/")
    new = sys.argv[2].rstrip("/")

    move_and_update(original, new)
