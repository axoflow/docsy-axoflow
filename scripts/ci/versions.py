#!/usr/bin/env python3
"""Everything a publish pipeline needs from data/versions.yaml, in one place.

Versioned docsy-axoflow sites (axosyslog-core-docs, axoflow-docs, locker-docs)
deploy each documentation version to its own sub-directory, and their workflows
used to carry four inline copies of the same parsing. This script replaces them:

  plan            for one deploy: target URL and bucket prefix, the version
                  dirs to protect and to pull in for search, and the version
                  list to overlay onto an archived ref
  matrix          the archived versions to rebuild, as JSON for a job matrix
  branch-version  the archived version a release branch tracks

versions.yaml is a list of entries:

  version  id; also the URL sub-path and bucket sub-dir ("4.28")
  ref      branch or tag an archived version is built from
  latest   true on the one entry deployed to the site root
  hidden   true for a preview: published at its sub-path, but left out of
           every other version's switcher and of the unified search index

With --github-output, results are written as `key=value` lines (multi-line
values in heredoc form) for $GITHUB_OUTPUT; otherwise they are printed.

Needs PyYAML.
"""

import argparse
import json
import os
import re
import secrets
import sys
import tomllib

import yaml


def load(path):
    # A site without versions yet runs the same pipeline: plan gives the root
    # deploy with nothing to protect, matrix and branch-version come back empty.
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or []
    if not isinstance(data, list):
        sys.exit(f"{path}: expected a list of versions")
    return data


def vid(entry):
    return str(entry.get("version") or "").strip()


def archived(data):
    """Non-latest entries with an id, in file order."""
    return [v for v in data if not v.get("latest") and vid(v)]


def production_baseurl(config_path):
    with open(config_path, "rb") as f:
        conf = tomllib.load(f)
    url = conf.get("baseurl") or conf.get("baseURL")
    if not url:
        sys.exit(f"{config_path}: no baseurl")
    return url.rstrip("/") + "/"


def bucket_path(url):
    """https://axoflow.com/docs/axosyslog-core/4.28/ -> docs/axosyslog-core/4.28"""
    return re.sub(r"^[a-z]+://[^/]+/", "", url).strip("/")


def emit(results, github_output):
    if not github_output:
        for k, v in results.items():
            print(f"{k}={v}" if "\n" not in v else f"{k}:\n{v}")
        return
    with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
        for k, v in results.items():
            if "\n" in v:
                delim = f"EOF_{secrets.token_hex(8)}"
                out.write(f"{k}<<{delim}\n{v}\n{delim}\n")
            else:
                out.write(f"{k}={v}\n")
    for k, v in results.items():
        print(f"{k}={v}" if "\n" not in v else f"{k}: ({v.count(chr(10)) + 1} lines)")


def cmd_plan(args):
    data = load(args.versions)
    root = production_baseurl(args.production_config)
    if args.latest:
        baseurl = root
    else:
        if not args.version:
            sys.exit("plan: --version is required unless --latest")
        if args.version not in {vid(v) for v in archived(data)}:
            print(f"warning: {args.version} is not an archived entry of {args.versions}", file=sys.stderr)
        baseurl = f"{root}{args.version}/"

    old = archived(data)
    results = {
        "baseurl": baseurl,
        "dest": bucket_path(baseurl),
        "root_dest": bucket_path(root),
        # The root deploy's --delete must leave every sub-site alone, previews
        # included, or it deletes them. An archived deploy is already scoped to
        # its own prefix.
        "protect": " ".join(vid(v) for v in old) if args.latest else "",
        # Previews search their own index only.
        "search_dirs": " ".join(vid(v) for v in old if not v.get("hidden")) if args.latest else "",
        # An archived ref is built with this list instead of its own frozen
        # one, so its switcher lists versions released after it. Previews are
        # stripped (frozen refs have layouts that predate `hidden` and would
        # list them), except the one being built.
        "versions_yaml": "" if args.latest else yaml.safe_dump(
            [v for v in data if not v.get("hidden") or vid(v) == args.version],
            sort_keys=False, allow_unicode=True,
        ).rstrip("\n"),
    }
    emit(results, args.github_output)


def cmd_matrix(args):
    out = []
    for v in archived(load(args.versions)):
        ref = str(v.get("ref") or "").strip()
        if not ref or (args.only and vid(v) != args.only):
            continue
        out.append({"version": vid(v), "ref": ref})
    if args.only and not out:
        print(f"warning: no archived version {args.only} with a ref", file=sys.stderr)
    emit({"versions": json.dumps(out)}, args.github_output)


def cmd_branch_version(args):
    ver = next((vid(v) for v in archived(load(args.versions))
                if str(v.get("ref") or "").strip() == args.branch), "")
    emit({"version": ver}, args.github_output)


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--versions", default="data/versions.yaml")
    p.add_argument("--github-output", action="store_true",
                   help="append the results to $GITHUB_OUTPUT")
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("plan", help="target and version lists for one deploy")
    pl.add_argument("--production-config", default="config/production/config.toml")
    pl.add_argument("--version", default="")
    pl.add_argument("--latest", action="store_true")
    pl.set_defaults(func=cmd_plan)

    m = sub.add_parser("matrix", help="archived versions to rebuild, as JSON")
    m.add_argument("--only", default="", help="just this version")
    m.set_defaults(func=cmd_matrix)

    b = sub.add_parser("branch-version", help="the archived version a branch tracks")
    b.add_argument("branch")
    b.set_defaults(func=cmd_branch_version)

    args = p.parse_args()
    args.only = getattr(args, "only", "").strip()
    args.version = getattr(args, "version", "").strip()
    args.func(args)


if __name__ == "__main__":
    main()
