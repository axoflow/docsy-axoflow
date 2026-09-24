#!/usr/bin/env bash
# Build the site as it is deployed (HTML, Markdown copies, llms.txt), serve it on
# localhost, and score it with afdocs (https://afdocs.dev), the checker for the
# Agent-Friendly Documentation spec. Exits with afdocs' own status: 1 when a
# check fails, so CI can gate on it. Run from the site's root:
#
#   themes/docsy-axoflow/scripts/check_agent_docs.sh
#
# Needs hugo, python3 with scripts/requirements-markdown.txt, and Node 22+.
#
# Skipped, because a local static server cannot answer them the way production
# does: content-negotiation (needs a rule at the CDN) and cache-header-hygiene
# (the deploy sets the headers). page-size-html is skipped too: every page still
# carries the navigation, so pages stay over its 100K limit, and what matters to
# agents -- that the article comes first -- is content-start-position, which runs.
set -euo pipefail

PORT="${AFDOCS_PORT:-8765}"
AFDOCS="${AFDOCS_PACKAGE:-afdocs}"          # pin it, e.g. afdocs@0.12.0
SKIP="${AFDOCS_SKIP:-content-negotiation,cache-header-hygiene,page-size-html}"
THEME_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# The site's path below the host, from the production baseURL, so the local
# build has the same URL layout as the deployed one.
base_path="$(sed -nE 's/^[[:space:]]*baseurl[[:space:]]*=[[:space:]]*"[a-z]+:\/\/[^/]+(\/[^"]*)?".*/\1/Ip' config/production/config.toml | head -1)"
base_path="/${base_path#/}"; base_path="${base_path%/}/"

out="$(mktemp -d)"
server=""
cleanup() { [ -n "$server" ] && kill "$server" 2>/dev/null; rm -rf "$out"; }
trap cleanup EXIT

site="http://localhost:${PORT}${base_path}"
hugo --minify --quiet --baseURL "$site" -d "${out}${base_path}"
python3 "${THEME_DIR}/scripts/hugo_to_markdown.py" --input "${out}${base_path}" --output "${out}${base_path}" > /dev/null

python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$out" > /dev/null 2>&1 &
server=$!
for _ in $(seq 50); do
  curl -sf -o /dev/null "$site" && break
  sleep 0.1
done

npx --yes "$AFDOCS" check "$site" --format scorecard --sampling deterministic --skip-checks "$SKIP"
