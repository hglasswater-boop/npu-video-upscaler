# NPU Video Upscaler — experimental alpha

This prerelease is an **early Windows 11 x64 test build**, *not a validated finished upscaler*.

- Windows per-user installer: `NpuVideoUpscaler-Setup-v*-win-x64.exe`.
- Portable ZIP: `NpuVideoUpscaler-v*-win-x64-portable.zip`.
- SHA-256 sums: `SHA256SUMS.txt`.
- On launch, the app can check GitHub Releases for new versions and safely download a verified installer with your approval.

**Important prerequisites:** install FFmpeg / ffprobe separately and supply a licensed, compatible **static-shape OpenVINO super-resolution model**. The installer **does not bundle an AI model**, Intel NPU driver or FFmpeg. Conversion on Core Ultra 5 125H has **not been hardware validated**. This build is **unsigned** and may trigger a Windows SmartScreen warning.

For requirements and limitations, see the [README](https://github.com/hglasswater-boop/npu-video-upscaler#readme), [model validation issue #3](https://github.com/hglasswater-boop/npu-video-upscaler/issues/3), and [release/update design](https://github.com/hglasswater-boop/npu-video-upscaler/blob/main/docs/releases-and-updates.md).

Do not rely on this build to preserve HDR, VFR timestamps, subtitles, non-MP4-compatible audio or arbitrary model inputs.

## v0.2.0a2 change

- Adds optional **First 60 seconds** NPU quality-test export with a distinct filename.
- Source audio is limited to the same 60-second window; short videos remain short.
- Full export remains available. Pretrained NPU-compatible model still not bundled.

## v0.2.0a3 (experimental model setup)

- New model setup controls: install a trusted local BSRGANx2 model ZIP or download a separately published checksum-verified model from the same GitHub Release, with explicit opt-in.
- Setup fails closed if the model cannot compile on **NPU**; no silent CPU/GPU fallback. Cached validated model is auto-selected at next start.
- Experimental BSRGANx2-OpenVINO-INT8.zip is a separate asset with its own SHA-256 digest, source provenance and Apache-2.0 license notice.
- Core Ultra 5 125H NPU compilation, inference speed, and output quality remain **not physically verified**. This is NOT a production release.


## v0.2.0a4 (publisher-direct FFmpeg bootstrap)

- After installer launch or first portable start, opt in to download and verify FFmpeg 9.0.2 Essentials directly from GyanD's fixed GitHub Release. The app caches the two validated tools in per-user LocalAppData and no longer requires system PATH setup.
- **FFmpeg binaries are NOT inside our installer/portable assets.** They are GPLv3 software with `libx264`, retrieved only from the upstream publisher after user consent. See https://ffmpeg.org/legal.html and docs/bundled-media-tools.md for exact pinned ZIP and SHA-256.
- An Intel NPU driver help button opens Intel's official support site. No driver is bundled or silently installed.
- The AI BSRGAN model remains a separate, opt-in project GitHub Release asset. Core Ultra 5 125H NPU inference and real old→new hardware updates still require validation.
