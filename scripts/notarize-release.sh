#!/bin/bash
# Keep credential handling in one process so failures and termination clean up.
set +x
set -euo pipefail
umask 077
python3 scripts/release-security.py preflight
: "${ZIP_PATH:?}"
: "${CHECKSUM_PATH:?}"
work=$(mktemp -d "${RUNNER_TEMP:-${TMPDIR:-/tmp}}/tartdesk-signing.XXXXXXXX")
keychain="$work/signing.keychain-db"
cleanup() {
  python3 scripts/signing-keychain.py detach "$keychain" || true
  security delete-keychain "$keychain" >/dev/null 2>&1 || true
  rm -rf "$work"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
# Let the workflow's always() step retry cleanup after forced step termination.
if [[ -n "${GITHUB_ENV:-}" ]]; then
  printf 'SIGNING_TEMP_DIR=%s\n' "$work" >> "$GITHUB_ENV"
fi
# Keep the default keychain unchanged; register only our temporary search entry.
password=$(openssl rand -hex 32)
python3 scripts/release-security.py decode-certificate "$work/certificate.p12"
printf '%s' "$APPLE_API_PRIVATE_KEY" > "$work/api.p8"
security create-keychain -p "$password" "$keychain" >/dev/null 2>&1
security set-keychain-settings -lut 21600 "$keychain" >/dev/null 2>&1
security unlock-keychain -p "$password" "$keychain" >/dev/null 2>&1
security import "$work/certificate.p12" -k "$keychain" -P "$APPLE_CERT_PASSWORD" \
  -T /usr/bin/codesign -T /usr/bin/security >/dev/null 2>&1
security set-key-partition-list -S apple-tool:,apple: -s -k "$password" "$keychain" >/dev/null 2>&1
identities=$(security find-identity -v -p codesigning "$keychain")
SIGNING_IDENTITY=$(python3 -c '
import os, re, sys
matches = re.findall(r"([A-Fa-f0-9]{40}) \"Developer ID Application: [^\"]+ \(" + re.escape(os.environ["APPLE_TEAM_ID"]) + r"\)\"", sys.stdin.read())
if len(matches) != 1:
    sys.exit("Expected one valid Developer ID Application identity matching APPLE_TEAM_ID")
print(matches[0])' <<< "$identities")
export SIGNING_IDENTITY
export SIGNING_KEYCHAIN="$keychain"
app=dist/TartDesk.app
# Remove filesystem metadata before signing, never after signing.
xattr -cr "$app"
find "$app" -name '._*' -type f -delete
python3 scripts/signing-keychain.py attach "$keychain"
bash scripts/sign-app.sh "$app"
python3 scripts/signing-keychain.py detach "$keychain"
metadata=$(codesign -dv --verbose=4 "$app" 2>&1)
grep -Fxq "TeamIdentifier=$APPLE_TEAM_ID" <<< "$metadata"
archive() {
  rm -f "$ZIP_PATH"
  ditto -c -k --norsrc --noextattr --keepParent "$app" "$ZIP_PATH"
  python3 scripts/release-security.py archive "$ZIP_PATH"
}
archive
# Capture responses privately; only report status, never credential-bearing output.
xcrun notarytool submit "$ZIP_PATH" --key "$work/api.p8" \
  --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER_ID" \
  --wait --output-format json > "$work/notary.json" 2> "$work/notary.stderr"
python3 - "$work/notary.json" <<'PY'
import json, sys
if json.load(open(sys.argv[1])).get('status') != 'Accepted':
    sys.exit('Apple notarization was not Accepted; publication blocked')
print('Apple notarization Accepted')
PY
# Stapling is the only permitted post-signing bundle operation.
xcrun stapler staple "$app"
archive
bash scripts/verify-distribution.sh "$ZIP_PATH"
shasum -a 256 "$ZIP_PATH" > "$CHECKSUM_PATH"
