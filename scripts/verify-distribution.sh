#!/bin/bash
set -euo pipefail
: "${APPLE_TEAM_ID:?Set APPLE_TEAM_ID}"
archive=${1:?Pass final ZIP}
python3 scripts/release-security.py archive "$archive"
staging=$(mktemp -d)
trap 'rm -rf "$staging"' EXIT
# A plain unzip deliberately exposes AppleDouble files instead of merging them.
unzip -q "$archive" -d "$staging"
app="$staging/TartDesk.app"
codesign --verify --deep --strict --verbose=2 "$app"
metadata=$(codesign -dv --verbose=4 "$app" 2>&1)
grep -Fxq "TeamIdentifier=$APPLE_TEAM_ID" <<< "$metadata"
grep -q '^Authority=Developer ID Application:' <<< "$metadata"
grep -q 'flags=.*runtime' <<< "$metadata"
grep -q '^Timestamp=' <<< "$metadata"
xcrun stapler validate "$app"
spctl --assess --type execute --verbose=4 "$app"
