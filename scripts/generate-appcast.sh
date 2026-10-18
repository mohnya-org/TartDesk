#!/bin/bash
set -euo pipefail
# Supply the private key through the environment, never as a command-line argument.
: "${SPARKLE_PRIVATE_KEY:?Set the Sparkle private signing key}"
: "${GITHUB_REPOSITORY:?Set the owner/repository}"
: "${TAG:?Set the release tag}"
: "${ZIP_PATH:?Set the final notarized ZIP path}"
: "${SPARKLE_BIN:?Set the directory containing generate_appcast}"
[[ -f "$ZIP_PATH" ]] || { echo "Release archive missing" >&2; exit 1; }
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
cp "$ZIP_PATH" "$staging/"
printf '%s' "$SPARKLE_PRIVATE_KEY" | "$SPARKLE_BIN/generate_appcast" \
  --ed-key-file - --maximum-deltas 0 \
  --download-url-prefix "https://github.com/$GITHUB_REPOSITORY/releases/download/$TAG/" \
  -o "$staging/appcast.xml" "$staging"
python3 - "$staging/appcast.xml" <<'CHECK'
import sys
import xml.etree.ElementTree as ET
root = ET.parse(sys.argv[1]).getroot()
items = root.findall('./channel/item')
assert len(items) == 1, "Expected exactly one update"
enclosure = items[0].find('enclosure')
assert enclosure is not None
assert enclosure.get('{http://www.andymatuschak.org/xml-namespaces/sparkle}edSignature'), "Unsigned update"
assert int(enclosure.get('length', '0')) > 0
assert enclosure.get('url', '').startswith('https://github.com/')
CHECK
mkdir -p dist
cp "$staging/appcast.xml" dist/appcast.xml
