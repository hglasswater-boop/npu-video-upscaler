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
