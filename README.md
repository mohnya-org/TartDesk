# TartDesk

TartDesk is a macOS desktop GUI for managing [Tart](https://github.com/cirruslabs/tart) virtual machines and OCI images.

Built with SwiftUI, it provides a native interface for browsing local Tart VMs, creating VMs from OCI images, editing VM settings, running or stopping machines, and accessing SSH information from your Mac.

If Tart is not installed, TartDesk shows an install screen on launch and can install Tart for you from within the app via Homebrew.

## Download

The latest signed app bundle is available from [GitHub Releases](https://github.com/Moomo/TartDesk/releases).

1. Download the latest `.zip` from Releases.
2. Extract `TartDesk.app`.
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
temporary keychain without changing the runner's default or search list, and
cleans up credentials on exit. After Apple accepts notarization, CI staples the
ticket and creates a ZIP without AppleDouble metadata. It extracts that exact ZIP
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
