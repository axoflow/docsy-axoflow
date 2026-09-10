#!/usr/bin/env bash
#
# Build the whole documentation set as one PDF, locally.
#
#   themes/docsy-axoflow/scripts/pdf/build.sh
#   themes/docsy-axoflow/scripts/pdf/build.sh -o /tmp/docs.pdf -e chrome
#
# Steps: Hugo renders every page into one HTML document, prepare.py rewrites
# its links and images for print, a throwaway HTTP server makes the site's
# root-relative asset URLs resolve, and render.mjs paginates the result.
#
# The HTTP server is not optional: Hugo emits `/img/…` paths, which a file://
# page would resolve against the filesystem root.
#
# Requires: hugo (extended), python3 with beautifulsoup4, and `npm install`
# having pulled in puppeteer and pagedjs. pypdf is optional — without it the
# PDF is still produced, just without its Author/Subject properties.

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Find the Hugo site root. `git rev-parse` is no help here: this script lives
# in a submodule, so from its own directory git reports the theme, and the
# theme ships content/ and config/ of its own — those alone don't identify a
# site. A site also has themes/ or a top-level hugo config file.
find_site_root() {
  local dir="$1"
  while [[ "$dir" != "/" && -n "$dir" ]]; do
    if [[ -d "$dir/content" && -d "$dir/config" ]] &&
       [[ -d "$dir/themes" || -f "$dir/hugo.toml" || -f "$dir/hugo.yaml" ]]; then
      printf '%s' "$dir"
      return 0
    fi
    dir="$(dirname "$dir")"
  done
  return 1
}

ROOT="$(find_site_root "$PWD" || true)"
[[ -n "$ROOT" ]] || ROOT="$(find_site_root "$SCRIPT_DIR" || true)"
[[ -n "$ROOT" ]] || { echo "can't find the Hugo site root — run this from the site directory" >&2; exit 1; }

OUT=""
ENGINE="paged"
PORT="8099"
BUILD_DIR=""
STRICT=""
SKIP_BUILD=""

usage() {
  cat <<'USAGE'
Build the whole documentation set as one PDF.

  -o, --output FILE     where to write the PDF
                        (default: <site>/axoflow-docs-<version>.pdf)
  -e, --engine ENGINE   paged (default) or chrome; see render.mjs
  -p, --port PORT       port for the throwaway HTTP server (default: 8099)
  -d, --build-dir DIR   Hugo output directory (default: <site>/public_pdf)
      --skip-build      reuse an existing build; for iterating on render.mjs
                        (stylesheet changes need a Hugo build, so not this)
      --strict          fail if any internal link can't be resolved
USAGE
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) OUT="$2"; shift 2 ;;
    -e|--engine) ENGINE="$2"; shift 2 ;;
    -p|--port) PORT="$2"; shift 2 ;;
    -d|--build-dir) BUILD_DIR="$2"; shift 2 ;;
    --strict) STRICT="--strict"; shift ;;
    --skip-build) SKIP_BUILD="1"; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown argument: $1" >&2; usage 1 ;;
  esac
done

cd "$ROOT"
BUILD_DIR="${BUILD_DIR:-$ROOT/public_pdf}"

VERSION="$(sed -nE 's/^[[:space:]]*version_tag[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' config/_default/config.toml | head -1)"
OUT="${OUT:-$ROOT/axoflow-docs${VERSION:+-$VERSION}.pdf}"

# The canonical site URL, so links this document can't resolve internally still
# work as web links, and so hand-written absolute links get recognised as ours.
PUBLIC_BASE="$(sed -nE 's/^[[:space:]]*baseurl[[:space:]]*=[[:space:]]*"([^"]+)".*/\1/p' config/production/config.toml | head -1)"
PUBLIC_BASE="${PUBLIC_BASE:-/}"
LOCAL_BASE="http://127.0.0.1:${PORT}/"

if [[ -n "$SKIP_BUILD" ]]; then
  echo "==> Reusing the existing build in $BUILD_DIR"
else
  echo "==> Hugo build (environment: pdf)"
  hugo --environment pdf --destination "$BUILD_DIR" --baseURL "$LOCAL_BASE" --cleanDestinationDir
fi

DOC="$BUILD_DIR/_pdf/index.html"
[[ -f "$DOC" ]] || { echo "no $DOC — is the pdf output format enabled in config/pdf/?" >&2; exit 1; }

echo "==> Preparing the document for print"
python3 "$SCRIPT_DIR/prepare.py" "$DOC" \
  --site-base "$PUBLIC_BASE" \
  --site-base "$LOCAL_BASE" \
  --public-base "$PUBLIC_BASE" \
  --site-root "$BUILD_DIR" \
  ${STRICT}

echo "==> Serving $BUILD_DIR on $LOCAL_BASE"
python3 -m http.server "$PORT" --bind 127.0.0.1 --directory "$BUILD_DIR" >/dev/null 2>&1 &
SERVER_PID=$!
trap 'kill "$SERVER_PID" 2>/dev/null || true' EXIT

for _ in $(seq 1 30); do
  if curl -sf -o /dev/null "${LOCAL_BASE}_pdf/index.html"; then break; fi
  sleep 0.2
done
curl -sf -o /dev/null "${LOCAL_BASE}_pdf/index.html" || {
  echo "the local server never came up on port $PORT — is it already in use?" >&2
  exit 1
}

echo "==> Rendering (engine: $ENGINE)"
node "$SCRIPT_DIR/render.mjs" "${LOCAL_BASE}_pdf/index.html" "$OUT" --engine "$ENGINE"

echo "==> Writing document properties"
python3 "$SCRIPT_DIR/metadata.py" "$OUT" --html "$DOC"

echo "==> $OUT"
