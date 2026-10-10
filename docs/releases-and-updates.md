# Windows release packaging and update contract — Issue #4

## Scope and channel
- App package is **Windows 11 x64**, installed **per user** without administrator permissions.
- Versions are read from `npu_upscaler.__version__`; Python package metadata is generated dynamically from that string.
- Version tags: `v{PEP-440-version}`. First channel is `v0.2.0a1` (experimental alpha).
- CI builds per-commit installer and portable zip and uploads both as Actions artifacts (short-lived). **Only a successful main-branch build publishes a GitHub prerelease**. Never publish assets for an unmerged PR.
- Release asset names: `NpuVideoUpscaler-Setup-v{version}-win-x64.exe`, `NpuVideoUpscaler-v{version}-win-x64-portable.zip`, `SHA256SUMS.txt`. Installer built from the same PyInstaller `onedir` executable as the portable zip.
- Product dependencies: FFmpeg and ffprobe are **separate and must be on PATH**; Intel NPU driver and OpenVINO-compatible static IR model are **not included**. App does not run without appropriate NPU and model. Installer executable is currently **unsigned**, so Windows may warn.
- CI must test unit contracts, build and smoke-test the packaged CLI version and installer. No assertion that actual NPU inference ran on GitHub runners.

## Update policy
- At launch (unless disabled via Settings checkbox), query `https://api.github.com/repos/hglasswater-boop/npu-video-upscaler/releases?per_page=20` asynchronously. Manual **Check for updates** is always available.
- Update channel is derived from the running build: prerelease builds can see newer prerelease or stable versions; stable builds only stable versions.
- Ignore drafts; versions must parse using `packaging.version.Version`, tags must begin with `v`. Pick highest eligible semver/PEP-440 version strictly newer than current.
- Require an installer asset with exact name and a `sha256:<64-hex>` API digest. Do not consume arbitrary URLs, alternate repositories, missing checksums or unsigned arbitrary scripts.
- Download via HTTPS from the exact canonical GitHub release URL; follow HTTPS redirects normally, hash the downloaded installer and compare against GitHub's published SHA-256 digest before offering installation. Download to a local user updates directory; if verification fails, delete partial file and do **not** execute.
- **No background install:** prompt before downloading and separately before launching the verified installer. On confirmation, launch the interactive Inno Setup installer and close the app. Never interrupt running conversions; pending update may be applied only when idle.
- Network timeout, rate limit, non-JSON response or malformed releases: show actionable status, keep app operational. No silent self-update.
- `QSettings` preference controls automatic check; default enabled. Update checks expose app version User-Agent and send no video content.

## Test plan
1. Release filtering (drafts, stable versus alpha, invalid version, out-of-order responses, exact asset, missing/invalid digest, external download URL).
2. Download hash validates good bytes and fails closed on mismatch, HTTP error, size mismatch and oversized file. No live network in unit tests.
3. Windows CI builds the source interpreter executable; `--version` must equal package version, uses Inno Setup script; portable archive must contain app EXE.
4. UI checks are worker-threaded; manual and startup checks use the same service; update not offered while video job is active; installer launched only after confirmation.
5. Manual Windows 11 smoke test: install vA, release vB, update prompt, verify vB starts and app preferences remain. Hardware NPU inference remains blocked by #3.

## Windows FFmpeg cancellation invariant
- FFmpeg must be terminated and reaped before temporary export deletion.
- Windows may delay releasing file handles immediately after subprocess exit; retry deletion for a **bounded** interval on `PermissionError`, without ever deleting the prior completed destination.
- CI installs actual FFmpeg so the audio-copy and cancellation integration tests execute on Windows instead of being skipped.

## Installation and rollback
- Installer installs to `{localappdata}\\Programs\\NpuVideoUpscaler` (stable AppId and location).
- Inno Setup uninstaller handles removal; new version replaces previous installation. No bespoke migration logic or versioned executable replacement.
- If a bad prerelease is published, GitHub Release maintainers must issue a newer version; do not replace checksummed artifacts at the same version.
