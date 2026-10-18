#!/bin/bash
set -euo pipefail
app=${1:?Pass the app bundle path}
: "${SIGNING_IDENTITY:?Set the Developer ID Application identity}"
framework="$app/Contents/Frameworks/Sparkle.framework"
# Sign Sparkle's nested code inside-out before signing the host app.
for component in \
  "$framework/Versions/B/XPCServices/Downloader.xpc" \
  "$framework/Versions/B/XPCServices/Installer.xpc" \
  "$framework/Versions/B/Autoupdate" \
  "$framework/Versions/B/Updater.app" \
  "$framework" "$app"; do
  codesign --force --options runtime --timestamp --sign "$SIGNING_IDENTITY" "$component"
done
codesign --verify --deep --strict --verbose=2 "$app"
