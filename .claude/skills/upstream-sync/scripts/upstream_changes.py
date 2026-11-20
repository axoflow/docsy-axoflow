#!/usr/bin/env python3
"""List the upstream doc changes a downstream docs repo has to review, sorted into buckets.

A downstream repo (axosyslog-cv, locker-docs, ...) pins an upstream docs repo as a
submodule under upstream/ and mounts its folders after its own in Hugo's
[module] config, so a local file at the same mounted path overrides the upstream one.

Usage (from the downstream repo root):
  upstream_changes.py                      # preview: pinned SHA -> upstream origin/<default>
  upstream_changes.py --no-fetch           # preview without fetching first
  upstream_changes.py --last-bump          # what the last committed bump brought in
  upstream_changes.py --base A --target B  # explicit range
Prints JSON to stdout.
"""
import argparse
import configparser
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path

CONTENT_EXT = {".md", ".html"}


def git(*args, cwd="."):
    return subprocess.run(["git", "-C", str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def find_upstream(repo):
    cfg = configparser.ConfigParser()
    cfg.read(repo / ".gitmodules")
    paths = [cfg[s]["path"] for s in cfg.sections() if cfg[s].get("path", "").startswith("upstream/")]
    if len(paths) != 1:
        sys.exit(f"Expected one upstream/* submodule in .gitmodules, found: {paths}. Use --upstream.")
    return paths[0]


def load_config(repo):
    cfg_file = repo / "config/_default/config.toml"
    if not cfg_file.exists():
        cfg_file = repo / "hugo.toml"
    data = tomllib.loads(cfg_file.read_text())
    mounts = data.get("module", {}).get("mounts", [])
    product = data.get("params", {}).get("product_name") or next(
        (lang.get("params", {}).get("product_name") for lang in data.get("languages", {}).values()
         if lang.get("params", {}).get("product_name")), "")
    return mounts, product


def resolve_range(repo, sub, args):
    if args.base and args.target:
        return args.base, args.target, "explicit"
    if args.last_bump:
        bump = git("log", "-1", "--format=%H", "--", sub, cwd=repo)
        if not bump:
            sys.exit(f"No commit touches {sub}.")
        base = git("rev-parse", f"{bump}^:{sub}", cwd=repo)
        target = git("rev-parse", f"{bump}:{sub}", cwd=repo)
        return base, target, f"last-bump ({bump[:8]})"
    # Preview: what bumping to the latest upstream would bring in.
    base = args.base or git("rev-parse", f"HEAD:{sub}", cwd=repo)
    if not args.no_fetch:
        try:
            git("fetch", "--quiet", "origin", cwd=repo / sub)
        except subprocess.CalledProcessError as e:
            print(f"warning: fetch failed, using the local origin refs: {e.stderr.strip()}", file=sys.stderr)
    try:
        default = git("symbolic-ref", "--short", "refs/remotes/origin/HEAD", cwd=repo / sub)
    except subprocess.CalledProcessError:
        default = "origin/main"
    target = git("rev-parse", args.target or default, cwd=repo / sub)
    return base, target, f"preview (pinned -> {args.target or default})"


def mount_maps(mounts, sub):
    """Return {upstream source dir: target} and {target: [local source dirs]}."""
    up, local = {}, {}
    for m in mounts:
        src, tgt = m["source"].rstrip("/"), m["target"].rstrip("/")
        if src.startswith(sub + "/"):
            up[src[len(sub) + 1:]] = tgt
        elif not src.startswith("upstream/"):
            local.setdefault(tgt, []).append(src)
    if not up:  # no explicit mounts: assume the upstream repo layout mirrors the local one
        up = {d: d for d in ("content", "layouts", "static", "i18n", "data", "assets")}
        local = {d: [d] for d in up}
    return up, local


def mounted(path, up):
    """Map an upstream repo path to (target, relative path), or None if not mounted."""
    for src, tgt in sorted(up.items(), key=lambda kv: -len(kv[0])):
        if path == src or path.startswith(src + "/"):
            return tgt, path[len(src) + 1:]
    return None


def page_variants(rel):
    """Paths that render the same content page: foo.md, foo/index.md, foo/_index.md."""
    p = Path(rel)
    if p.suffix not in CONTENT_EXT:
        return [rel]
    if p.stem in ("index", "_index"):
        base = p.parent
        return [str(base / "index.md"), str(base / "_index.md"), str(base) + ".md"]
    base = p.with_suffix("")
    return [rel, str(base / "index.md"), str(base / "_index.md")]


def local_override(repo, tgt, rel, local):
    for src in local.get(tgt, []):
        for variant in page_variants(rel) if tgt == "content" else [rel]:
            f = repo / src / variant
            if f.is_file():
                return str(f.relative_to(repo)), variant != rel
    return None, False


def is_stub(path):
    text = path.read_text(errors="ignore")
    fm = text.split("---", 2)[1] if text.startswith("---") else ""
    return bool(re.search(r"render:\s*never", fm))


def unrendered_ancestor(repo, rel, local):
    """The nearest local section _index.md with `render: never` (itself or in a cascade).

    Without a cascade the children still build, but lose their place in the sidebar."""
    for parent in list(Path(rel).parents)[:-1]:
        if str(parent / "_index.md") == rel:
            continue
        for src in local.get("content", []):
            f = repo / src / parent / "_index.md"
            if f.is_file() and is_stub(f):
                return str(f.relative_to(repo))
    return None


def local_users(repo, local, needle_re):
    hits = []
    for src in local.get("content", []) + local.get("layouts", []):
        root = repo / src
        if not root.is_dir():
            continue
        for f in root.rglob("*"):
            if f.suffix in CONTENT_EXT and f.is_file() and needle_re.search(f.read_text(errors="ignore")):
                hits.append(str(f.relative_to(repo)))
    return sorted(hits)


def shared_users(repo, local, tgt, rel):
    """Local pages that pull in a changed headless snippet, shortcode or partial."""
    p = Path(rel)
    if tgt == "content" and rel.startswith("headless/"):
        tail = rel[len("headless/"):]
        return local_users(repo, local, re.compile(re.escape(tail)))
    if tgt == "layouts" and p.parts[0] in ("_shortcodes", "shortcodes"):
        return local_users(repo, local, re.compile(r"\{\{[<%]\s*/?" + re.escape(p.stem) + r"\b"))
    if tgt == "layouts" and p.parts[0] in ("_partials", "partials"):
        return local_users(repo, local, re.compile(re.escape("/".join(p.parts[1:]))))
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=".")
    ap.add_argument("--upstream", help="submodule path, default: the upstream/* entry in .gitmodules")
    ap.add_argument("--base")
    ap.add_argument("--target")
    ap.add_argument("--last-bump", action="store_true")
    ap.add_argument("--no-fetch", action="store_true")
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    sub = args.upstream or find_upstream(repo)
    mounts, product = load_config(repo)
    base, target, mode = resolve_range(repo, sub, args)
    up, local = mount_maps(mounts, sub)

    out = {"upstream": sub, "product_name": product, "mode": mode, "base": base, "target": target,
           "diff_cmd": f"git -C {sub} diff {base[:12]} {target[:12]} -- <path>",
           "overridden": [], "orphaned_override": [], "shared": [], "new": [], "changed": [],
           "deleted": [], "not_mounted": []}
    if base == target:
        print(json.dumps(out, indent=2))
        return

    lines = git("diff", "--name-status", "-M", base, target, cwd=repo / sub).splitlines()
    for line in lines:
        status, *paths = line.split("\t")
        old, new = paths[0], paths[-1]
        kind = status[0]
        m_new, m_old = mounted(new, up), mounted(old, up)
        if not m_new and not m_old:
            out["not_mounted"].append({"status": status, "path": new})
            continue
        tgt, rel = m_new or m_old
        entry = {"status": status, "path": new, "mounted_as": f"{tgt}/{rel}"}
        if old != new:
            entry["old_path"] = old

        # Renamed or deleted upstream while an override sits at the old path: the override
        # becomes a standalone page, and the upstream page reappears unreviewed at its new path.
        if kind in "RD" and m_old:
            ov, _ = local_override(repo, m_old[0], m_old[1], local)
            if ov:
                entry["local"] = ov
                out["orphaned_override"].append(entry)
                continue

        ov, variant = local_override(repo, tgt, rel, local) if kind != "D" else (None, False)
        if ov:
            entry["local"] = ov
            entry["stub"] = is_stub(repo / ov)
            if variant:
                entry["note"] = "local file uses a different page-bundle form; both may build"
            out["overridden"].append(entry)
            continue

        if tgt == "content":
            anc = unrendered_ancestor(repo, rel, local)
            if anc:
                entry["under_unrendered_section"] = anc

        users = shared_users(repo, local, tgt, rel)
        if users is not None or tgt != "content":
            entry["used_by_local"] = users or []
            out["shared"].append(entry)
        elif kind == "A":
            out["new"].append(entry)
        elif kind == "D":
            slug = re.sub(r"(/_?index)?\.(md|html)$", "", rel)
            entry["linked_from_local"] = local_users(repo, local, re.compile(re.escape(slug) + r"\b"))
            out["deleted"].append(entry)
        else:
            out["changed"].append(entry)

    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
