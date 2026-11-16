#!/usr/bin/env bash
# The multi-pass R2 sync behind action.yml; reads its settings from the
# environment. Runnable by hand with AWS_DRYRUN=1 to print the commands.
set -euo pipefail

: "${BUCKET:?}" "${DESTINATION:?}" "${AWS_S3_ENDPOINT:?}"
SOURCE_DIR="${SOURCE_DIR:-public}"
AWS_REGION="${AWS_REGION:-auto}"
DESTINATION="${DESTINATION#/}"
DESTINATION="${DESTINATION%/}"

[[ -d "$SOURCE_DIR" ]] || { echo "no build in $SOURCE_DIR" >&2; exit 1; }

# A protected directory covers everything under it.
protect=()
for p in ${PROTECT:-}; do
  p="${p%/}"
  [[ "$p" == *"*"* ]] || p="$p/*"
  protect+=(--exclude "$p")
done

dry=()
[[ -n "${AWS_DRYRUN:-}" ]] && dry=(--dryrun)

sync() {
  aws s3 sync "$SOURCE_DIR" "s3://$BUCKET/$DESTINATION" \
    --endpoint-url "$AWS_S3_ENDPOINT" --region "$AWS_REGION" \
    --checksum-algorithm CRC32 ${dry[@]+"${dry[@]}"} "$@"
}

echo "::group::Pass 1 — fingerprinted assets, cached for a year"
# Everything here is fingerprinted by Hugo (the content hash is in the file
# name), so a change is a new file and the old one can be cached immutably.
sync --exclude "*" \
  --include "scss/*" --include "js/*" --include "css/*" \
  --include "webfonts/*" --include "fonts/*" \
  --include "icons/*" --include "img/*" --include "favicons/*" \
  --cache-control "public, max-age=31536000, immutable"
echo "::endgroup::"

echo "::group::Pass 2 — Pagefind index, 30 days"
sync --exclude "*" --include "pagefind/*" \
  --cache-control "public, max-age=2592000"
echo "::endgroup::"

# The CLI guesses the type without a charset, and the text is full of ’ and –.
# Same caching as HTML; pass 3 then skips these as already up to date. The
# protected dirs are excluded here too: on a root deploy they hold copies of
# the archived versions pulled in for the unified search index.
echo "::group::Pass 2b — Markdown copies and llms*.txt, with a charset"
sync --exclude "*" --include "*.md" ${protect[@]+"${protect[@]}"} \
  --content-type "text/markdown; charset=utf-8" \
  --cache-control "public, max-age=345600, must-revalidate"
sync --exclude "*" \
  --include "llms.txt" --include "*/llms.txt" \
  --include "llms-full.txt" --include "*/llms-full.txt" ${protect[@]+"${protect[@]}"} \
  --content-type "text/plain; charset=utf-8" \
  --cache-control "public, max-age=345600, must-revalidate"
echo "::endgroup::"

# --delete prunes what the build no longer produces. The protected dirs and
# the PDF edition are not in this build but must stay. PDFs of earlier
# version_tags are not protected, so they get cleared out.
echo "::group::Pass 3 — HTML and everything else, 4 days, with --delete"
pdf=()
[[ -n "${PDF_FILE:-}" ]] && pdf=(--exclude "$PDF_FILE")
sync --delete ${protect[@]+"${protect[@]}"} ${pdf[@]+"${pdf[@]}"} \
  --cache-control "public, max-age=345600, must-revalidate"
echo "::endgroup::"
