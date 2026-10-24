# Shared DMG installation background

This app-neutral artwork is shared byte-for-byte by PrismWindow, FinderOne,
TartDesk and Lingly. A dimensional arrow and flowing light indicate dragging the
real app icon on the left to the real Applications link on the right. Neither
icon is painted into the background. The only text is “Drag to install”.

`layout.json` defines a 660 × 360 point window and icon positions. `source.png`
is the original generated artwork; `PROMPT.md` records the built-in image_gen
prompt. Release builds use checked-in assets and do not generate artwork.

The TIFF contains 1× and 2× representations with 72/144 DPI respectively.
Regenerate the packaging sizes on macOS, then copy this directory to all four
repositories:

```sh
sips -z 360 660 -s dpiWidth 72 -s dpiHeight 72 packaging/dmg/source.png --out packaging/dmg/background.png
sips -z 720 1320 -s dpiWidth 144 -s dpiHeight 144 packaging/dmg/source.png --out packaging/dmg/background@2x.png
tiffutil -cathidpicheck packaging/dmg/background.png packaging/dmg/background@2x.png -out packaging/dmg/background.tiff
```

Native packaging uses dmgbuild to write Finder metadata without AppleScript or
UI automation. Electron uses the same TIFF and coordinates via electron-builder.
Customize before signing and notarizing; never modify a released image. ZIP
updater payloads do not include this installation artwork.
