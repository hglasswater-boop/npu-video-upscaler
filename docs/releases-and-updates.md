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
- If a bad prerelease is published, GitHub Release maintainers must issue a newer version; do not replace checksummed artifacts at the same version. Main pushes that only change tests/docs should detect an existing identical version and skip publishing that version (successfully) rather than attempting to overwrite it. Only a new version may publish new release assets.

## Real published installer upgrade regression — Issue #8

The automated Windows runner must download **actual published** v0.2.0a1 and v0.2.0a2 installer assets, validate each against pinned GitHub Release SHA-256 digest and size, and install in sequence. Neither package may be rebuilt from sources for this scenario.

1. Verify the update checker returns **exactly v0.2.0a2** when asked to check the published v0.2.0a2 record from current version 0.2.0a1. Exercise `download_installer` to verify the complete release asset SHA-256; no installer is executed inside downloader.
2. Install the exact downloaded v0.2.0a1 installer per-user. Inspect the single uninstall registry entry with DisplayName `NPU Video Upscaler` and DisplayVersion `0.2.0a1` and presence of installed `NpuVideoUpscaler.exe`.
3. Seed the application's per-user QSettings location (`HKCU\\Software\\NpuVideoUpscaler\\NpuVideoUpscaler`) with `autoCheckUpdates=0` as a sentinel.
4. Run v0.2.0a2 installer to the **same** installation path (no migration logic); require one uninstall entry and DisplayVersion 0.2.0a2. Verify the setting remains. The UI should still require consent before launching the installer; CI uses `/VERYSILENT` strictly to automate the regression, not as the app update policy.
5. A corrupted/broken SHA-256 is already rejected by unit tests; updater must never trigger an installer if verification fails. A live device interactive update through GUI is still **not tested by CI** and remains a manual smoke test.

For repeatability, pinned release artifact hashes come from published immutable-versioned assets and are documented in the workflow. Network/download errors fail the CI job. This workflow is manually triggerable to avoid repeated ~200 MB binary downloads on every commit and runs on a real Windows hosted runner (VM), **not** the Core Ultra 5 125H hardware.

## Experimental SR model Release asset (v0.2.0a3+)

The Windows build includes a separate **BSRGANx2-OpenVINO-INT8.zip** in GitHub Release assets (not the application installer), plus its entry in SHA256SUMS.txt. The CI build downloads checkpoint bytes only from the author's HTTPS GitHub Release, requires the pinned 64-digit SHA-256, converts them using vendored RRDBNet plus NNCF, verifies static model dimensions and CPU OpenVINO compile, and bundles Apache-2.0 license notice with the IR and manifest. The EXE must not include PyTorch or NNCF.

On first launch, if no cached model exists, the GUI offers an explicit opt-in download. It selects only this repository's exact named Release asset and validated GitHub-published digest/URL; downloads asynchronously, verifies SHA-256, rejects unsupported archive entries, compares internal IR checksums, then attempts OpenVINO NPU-only compilation. Only a successful NPU compile installs/auto-selects the model in the per-user cache. Declining the opt-in disables repeated startup prompts; the manual button stays available.

**Alpha status (2026-10-11):** Core Ultra 5 125H physical NPU compilation/inference and short synthetic A/V clips have been verified separately from CI; see [Issue #3](https://github.com/hglasswater-boop/npu-video-upscaler/issues/3). Representative 1080p 60-second completion, subjective quality/audio sync and power use remain unverified. The model remains experimental. If NPU compilation fails, the app reports the error; no silent CPU fallback.

Starting with a10, verified cached BSRGAN uses static 128px tiles for inputs at least 256px on both axes. XML/BIN weights and compression remain unchanged. The advanced Japanese checkbox can restore 48px processing; manual external IR and initial package compatibility checks retain original shapes. Tile context changes can change pixels. [Physical timing and limitations](npu-throughput.md) describe the measured improvement, not a full-export time guarantee.
