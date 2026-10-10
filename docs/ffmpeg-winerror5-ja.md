# Windows FFmpeg setup WinError 5 regression + Japanese UI (Issue #13)

## Reproduced evidence
A user on Windows 11 attempted publisher-direct FFmpeg 9.0.2 setup using v0.2.0a4. The error is `[WinError 5] Access denied` while moving `MediaTools/.setup-.../expanded` → `MediaTools/ffmpeg-9.0.2-60f467265b1e`. Previous code launched both FFmpeg and ffprobe from **staging** to validate the runtime and only *then* renamed staging. Windows may hold the executed PE images open briefly, preventing the directory rename. This explains a likely cause, not definitive proof of the locking actor.

## Safe order
1. Download directly from pinned GyanD publisher, verify exact archive length and SHA-256, securely extract only expected `bin/ffmpeg.exe`/`bin/ffprobe.exe`.
2. Compute file checksums in staging. **Move staging into final destination before launching either executable.** If OS sharing/antivirus blocks the move, retry transient `PermissionError` for a short bounded period.
3. Run `-version` for both, and `-encoders` for libx264, from the **final destination**. Only after successful checks, write a `checksums.json` commit marker. Until it exists, `find_installed_media_tools` must refuse the cache.
4. On runtime test failure, remove the incomplete destination where possible; any undeletable incomplete cache is not active and a future attempt must safely remove it before retry. Never overwrite or follow an untrusted symlink in the target path.
5. If access is still denied after retry, present an actionable Japanese error indicating the user's software security policy may block the action, and the known LocalAppData cache path.

## Japanese GUI
- All navigation, picker labels, statuses, completion, update, model-install and FFmpeg prompts are Japanese; retained technology names, filenames and links are fine.
- All app-owned yes/no and warning dialogs use Japanese button text via a localized message-box helper. Native OS File Dialogs follow the OS language.
- The app can preserve raw low-level error details after a Japanese explanation. This is not a broad translation of FFmpeg or OpenVINO diagnostic logs.
- Window title includes the prerelease version and `開発版`; progress and 60-second preview labels are Japanese.
- No functional changes to updater security checks, model NPU-only compile, or video export paths.

## Tests / release
- Unit: run only final-path executables, with monkeypatched Windows-staging-executable lock simulation; manifest absent during runtime verification, and absent after failure; idempotent repeat; transient rename failure retries.
- GUI offscreen: major interactive texts and confirmed behavior translated, default full mode + first-60-second mode still work.
- Windows Actions: actual FFmpeg direct-publisher install on fresh runner, full packaging/installer test, no FFmpeg binaries in release asset.
- Release v0.2.0a5 only after CI success. Real Windows user regression and Core Ultra 5 125H hardware NPU validation remain manual.
