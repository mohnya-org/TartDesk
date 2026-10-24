# TartDesk

TartDesk is a macOS desktop GUI for managing [Tart](https://github.com/cirruslabs/tart) virtual machines and OCI images.

Built with SwiftUI, it provides a native interface for browsing local Tart VMs, creating VMs from OCI images, editing VM settings, running or stopping machines, and accessing SSH information from your Mac.

If Tart is not installed, TartDesk shows an install screen on launch and can install Tart for you from within the app via Homebrew.

## Download

The latest signed app bundle is available from [GitHub Releases](https://github.com/mohnya-org/TartDesk/releases).

1. Download the latest `.dmg` from Releases and open it in Finder.
2. Locate `TartDesk.app` in the mounted image.
3. Drag and drop `TartDesk.app` into your `Applications` folder.
4. Launch `TartDesk`. If `Tart` is missing, the app will prompt you to install it and can run the Homebrew install command for you.
5. Install `Tart` manually if you prefer:

```bash
brew install cirruslabs/cli/tart
```

## Requirements

- macOS 14+
- `tart` installed separately and available on the machine
- Homebrew if you want TartDesk to install `Tart` for you from inside the app
- Tart-compatible VMs or OCI images

`TartDesk` does not bundle `Tart`.

## Features

- List local VMs and OCI images
- Detect when `Tart` is missing and show an install flow on launch
- Install `Tart` from inside the app via Homebrew
- Deduplicate OCI tag and digest entries in the UI
- Run local VMs in graphics or headless mode
- Configure per-VM shared folders from Edit VM Settings and apply them on run
- Stop local VMs
- Create local VMs from OCI images or other local VMs
- Create empty VMs
- Edit local VM settings
  - name
  - CPU
  - memory
  - display size
  - disk size
- Delete local VMs with confirmation
- Show Guest Agent / `tart exec` status
- Show VM IP address for SSH
- Copy SSH command
- Open SSH command in Terminal

## Notes

- OCI images cannot be run directly. Clone them into a local VM first.
- `TartDesk` is a GUI wrapper around the `tart` CLI and depends on a separately installed `Tart`.
- If `Tart` is not installed, TartDesk can trigger `brew install cirruslabs/cli/tart` from the app. This requires Homebrew to already be installed.
- Some features depend on guest setup, for example:
  - SSH requires guest networking and an SSH server
  - `tart exec` requires Tart Guest Agent support in the guest
  - Shared folders require Tart's directory sharing support; macOS guests mount them under `/Volumes/My Shared Files` by default
- `dist/` is a build artifact directory and is not meant to be committed.

## Release Workflow

General distribution uses the notarized GitHub Actions flow in [`.github/workflows/release.yml`](.github/workflows/release.yml).

Merge to `main` to trigger the workflow. CI increments the latest stable patch
and injects it into the app without a version-bump commit. Manual dispatch on
`main` accepts an optional newer version for minor/major releases.

The workflow runs on the self-hosted macOS runner and:

- builds `TartDesk.app`
- signs it with `Developer ID Application`
- notarizes and staples it
- tags the built commit only after artifacts are ready
- uploads the ZIP, checksum, and appcast to a draft, then publishes it

You can also run the workflow manually from the GitHub Actions UI when needed.

## Development

Run the app directly from Swift Package Manager:

```bash
swift run
```

Build only:

```bash
swift build
```

Build a local `.app` bundle:

```bash
./scripts/build-app.sh
```

Local `build-app.sh` builds use ad-hoc signing for development. They are not
Developer ID signed or notarized and are not intended for distribution.

Release CI uses the organization secrets `APPLE_API_ISSUER_ID`, `APPLE_API_KEY_ID`,
`APPLE_API_PRIVATE_KEY`, `APPLE_CERT_BASE64`, `APPLE_CERT_PASSWORD`, and
`APPLE_TEAM_ID`, plus `SPARKLE_PRIVATE_KEY` and `SPARKLE_PUBLIC_ED_KEY` for updates.
The organization must grant this repository access to those secrets. Do not define
same-named Apple secrets at repository level: GitHub gives them precedence over
organization secrets. Certificate Base64 may contain line breaks or ASCII whitespace. Missing
secrets fail before the build; secret values are never printed.

Distribution builds sign Sparkle's nested components and then TartDesk with a
matching Developer ID Application certificate, Hardened Runtime, and timestamps.
This native SwiftUI app requires no additional entitlements. CI uses an isolated
temporary keychain without changing the runner's default. During signing it appends
that keychain to the existing search list, then removes only its own entry while
preserving other jobs' entries. Search-list updates are serialized between TartDesk
jobs, and credentials are cleaned up on exit. After Apple accepts notarization,
CI staples the ticket and creates a ZIP without AppleDouble metadata. It extracts that exact ZIP
and checks the signature, team, ticket, and Gatekeeper assessment before generating
the checksum and Sparkle signature or publishing. A failed check blocks publication.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).

`TartDesk` and `Tart` are licensed separately.

- `TartDesk`: MIT License
- `Tart`: licensed by Cirrus Labs under the Fair Source License 0.9

See the official `Tart` repository and its license for details:

- <https://github.com/cirruslabs/tart>
- <https://github.com/cirruslabs/tart/blob/main/LICENSE>

## First installation: signed DMG

Releases include a signed, notarized `<app>-<version>-macOS.dmg` and its SHA-256 checksum.
Open the DMG in Finder, drag the app onto its Applications shortcut, eject the image,
and launch the installed app from Applications. Sparkle continues to use the ZIP and appcast.
Do not launch the app directly from the mounted image.

The DMG uses the existing `APPLE_CERT_BASE64` / `APPLE_CERT_PASSWORD` Developer ID
Application identity and `APPLE_TEAM_ID`. Notarization reuses `APPLE_API_KEY_ID`,
`APPLE_API_ISSUER_ID`, and `APPLE_API_PRIVATE_KEY`; no separate DMG certificate or API key
is needed. Apple Distribution certificates are not a substitute for Developer ID Application.
The workflow uses a private temporary keychain without changing the default keychain.
It signs and notarizes the image, staples its ticket, then mounts it read-only to verify
Gatekeeper acceptance, the embedded app signature/version, and the Applications shortcut.
All ZIP, DMG, checksum, and appcast files must exist before publication.

To validate a trusted branch without publishing, manually dispatch `release.yml`
with `validate_only=true`. This uses signing secrets but creates no tag or release.
The verified DMG is retained as a workflow artifact for seven days. Offline DMG tests:
`python3 -B scripts/test-macos-dmg.py`.

Prefer organization secrets scoped to selected repositories or protected environments.
Inventory all consumers before narrowing existing all-repository access. Never copy another
organization's private keys into this project. Secret names alone do not establish certificate
validity; successful signing and notarization are required verification.

## Future PKG distribution

PKG creation is not enabled. It requires a separate **Developer ID Installer** certificate,
in addition to the Developer ID Application certificate that signs the bundled app.
An account holder should create it in Apple Developer, export it with its private key as a
password-protected `.p12`, and configure `APPLE_INSTALLER_CERT_BASE64` and
`APPLE_INSTALLER_CERT_PASSWORD` for the intended repositories. Do not replace the existing
Application certificate secrets. The current notarization API credentials can be reused;
a new App Store Connect app record or API key is not required just to add PKG packaging.

A future PKG workflow must sign with that Installer identity, notarize and staple the package,
and verify it with `pkgutil --check-signature`, `stapler validate`, and Gatekeeper's install
assessment before publication. Test installation and subsequent Sparkle updates on a clean Mac.
See [Apple's Developer ID certificate guide](https://developer.apple.com/help/account/certificates/create-developer-id-certificates/).
