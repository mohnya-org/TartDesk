#!/bin/bash
set -euo pipefail
: "${TAG:?}"
: "${ZIP_PATH:?}"
: "${CHECKSUM_PATH:?}"
: "${GITHUB_REPOSITORY:?}"
# All three assets must exist before creating a tag or a draft.
for asset in "$ZIP_PATH" "$CHECKSUM_PATH" dist/appcast.xml; do
  [[ -s "$asset" ]] || { echo "Missing release asset: $asset" >&2; exit 1; }
done
sha=$(git rev-parse HEAD)
git fetch origin --tags
if git show-ref --verify --quiet "refs/tags/$TAG"; then
  [[ "$(git rev-list -n 1 "$TAG")" == "$sha" ]] || {
    echo "$TAG belongs to another commit" >&2; exit 1;
  }
else
  git tag "$TAG" "$sha"
fi
# Also handles a local tag left behind by an interrupted push on a self-hosted runner.
git push origin "refs/tags/$TAG"
release_list=$(mktemp)
trap 'rm -f "$release_list"' EXIT
gh api "repos/$GITHUB_REPOSITORY/releases?per_page=100" --paginate --slurp > "$release_list"
state=$(python3 - "$release_list" "$TAG" <<'PY'
import json, sys
releases = [r for page in json.load(open(sys.argv[1])) for r in page]
release = next((r for r in releases if r['tag_name'] == sys.argv[2]), None)
print('missing' if release is None else 'draft' if release['draft'] else 'published')
PY
)
if [[ "$state" == published ]]; then
  echo "$TAG is already published; leaving its assets unchanged"
  exit 0
fi
if [[ "$state" == missing ]]; then
  gh release create "$TAG" --verify-tag --target "$sha" --draft --title "$TAG" --generate-notes
fi
gh release upload "$TAG" "$ZIP_PATH" "$CHECKSUM_PATH" dist/appcast.xml --clobber
# Publication happens only after every upload succeeds, so release webhooks see complete assets.
gh release edit "$TAG" --draft=false --latest
