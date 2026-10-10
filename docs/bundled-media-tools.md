# FFmpeg setup without redistributing FFmpeg — Issue #11

## Overview
The Windows installer/portable ZIP contains only NPU Video Upscaler and its Python/OpenVINO GUI dependencies. **Neither `ffmpeg.exe` nor `ffprobe.exe` is part of our release archive.**

After an interactive installer launches the app (or when a portable build first starts), the user is asked whether to download **GyanD FFmpeg 9.0.2 Essentials** directly from the publisher's immutable GitHub Release. Declining leaves the rest of the UI available, but video export is blocked until the user installs FFmpeg with the **Download FFmpeg from publisher** button. Video files are never uploaded.

## Source and integrity
- Publisher's immutable asset: https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/ffmpeg-9.0.2-essentials_build.zip
- Pinned size: **114,768,076 bytes**
- Pinned SHA-256: `60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba`
- The size and hash were confirmed against GyanD's published GitHub Release asset metadata. HTTP redirects from GitHub to its release-asset CDN are normal; archive bytes must still match the pinned digest.
- Download is HTTPS, streaming with a strict size bound; extract only the two expected `bin/ffmpeg.exe` and `bin/ffprobe.exe` ZIP members. Validate runtime and `libx264`, record internal hashes and atomically move into the per-user cache.
- Cache: `%LOCALAPPDATA%\NpuVideoUpscaler\MediaTools\ffmpeg-9.0.2-60f467265b1e\`. No admin rights, registry installer dependencies, or modification of PATH. Subsequent runs use cached tools and validate the hash manifest; no network required once installed.
- A missing/incomplete/corrupt cache never falls back to arbitrary tools on PATH from a frozen app. Source/developer Python installs may still use FFmpeg/ffprobe from PATH.

**Updates:** The upstream version is intentionally fixed. A future pinned-version update requires a reviewed change to the URI, size, hash and source notices. Do not automatically trust a latest URL or a changed upstream ZIP.

## FFmpeg license
GyanD Essentials enables GPLv3 and `libx264`; see https://ffmpeg.org/legal.html and https://www.gyan.dev/ffmpeg/builds/ . The downloader shows the vendor and license URL before user consent. The application calls publisher-hosted FFmpeg as a subprocess; no publisher FFmpeg binary or archive is redistributed by our Releases. Users obtain a separate license-governed upstream program directly from its publisher.

This workflow is distinct from **rehosting** FFmpeg binaries, which would require complete corresponding GPL source and other notices. No `FFMPEG_GPL_CORRESPONDING_SOURCE_READY` bypass flag should be necessary because GitHub Actions explicitly checks that no FFmpeg binary is present in the distributable directory.

## Windows CI
1. Test the pinned ZIP identity (also independently recorded in upstream GitHub Release metadata), handling corrupt or partial ZIPs with mocks.
2. Build frozen app via PyInstaller, **without** adding downloaded vendor tools to the PyInstaller output.
3. On the Windows CI runner, install FFmpeg directly from the upstream URL into the runner's private LocalAppData. Confirm installed tools run successfully with PATH stripped. Confirm neither binary appears in packaged app.
4. Build the Inno Setup per-user installer, install silently in CI, smoke-test installed frozen app and its media tools.
5. Main-branch push produces immutable new prerelease (v0.2.0a4); PR builds upload temporary app-only artifacts. No bundled FFmpeg distribution.

## Intel NPU driver
The Intel NPU driver is OS-managed and is **not** downloaded or installed by this app. When OpenVINO cannot see `NPU`, show Windows Device Manager → Neural processors → Intel AI Boost instructions and link to Intel's official Windows NPU driver:
https://www.intel.com/content/www/us/en/download/794734/intel-npu-driver-windows.html

OpenVINO still compiles exclusively to `NPU`. Neither FFmpeg presence nor app installation proves model compatibility on the Core Ultra 5 125H; physical NPU validation remains [Issue #3](https://github.com/hglasswater-boop/npu-video-upscaler/issues/3).

## User acceptance
- Install v0.2.0a4 on Windows 11 with no FFmpeg PATH entry.
- Confirm first-start prompt; accept once, download and verify fixed vendor ZIP, then see `ffmpeg.exe` and `ffprobe.exe` in LocalAppData.
- Restart app with network disconnected and verify it finds cached binaries.
- Select an NPU-compatible model, 5–10 second CFR source with AAC, and try 60-second preview (requires real NPU hardware).
- Check existing v0.2.0a3 → v0.2.0a4 in-app update flow separately on an actual Windows installation ([Issue #8](https://github.com/hglasswater-boop/npu-video-upscaler/issues/8)).
