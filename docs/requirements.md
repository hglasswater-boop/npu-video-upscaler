# Requirements — current GPU standard (from Issue #23, #28)

## Goal
On Windows 11 with an Intel Core Ultra 5 125H, upscale local MP4/MKV using **GPU-default** OpenVINO inference and optional manually selected NPU, saving MP4 with compatible source audio copied.

## MVP interface
- PySide6 file selection: source video, OpenVINO model XML, output MP4. Start, cancel, progress, completion/errors.
- Mandatory detection of the explicitly selected GPU/NPU; compile on that device only. Never automatically fall back to CPU, AUTO, HETERO, MULTI or another device.
- No cloud, downloads, telemetry or network during conversion; initial FFmpeg/model setup and checksummed updates require user consent.
- FFmpeg/ffprobe are SHA-256 verified and installed from the publisher with user consent in an application-local cache; PATH is not required.

## Media contract
- Source first video stream: SDR, 8-bit, no rotation, nominal **constant** FPS; `avg_frame_rate` and `r_frame_rate` must be equal, but that test alone **cannot conclusively prove CFR**. VFR/timebase reconstruction is out of scope.
- Decode as RGB24, encode H.264 `libx264` 8-bit yuv420p with exact nominal rational FPS. HEVC/Quick Sync are deferred pending encoder availability.
- Preserve audio via `-map 1:a? -c:a copy` for MP4-compatible codecs AAC, MP3, AC-3, E-AC-3, ALAC; **reject** other audio codecs before conversion. Silent videos supported.
- Subtitles, chapters, attachments, video timestamp details, HDR and rotation metadata are not preserved. Do not claim lossless A/V sync on non-CFR sources.
- Frames stream one by one; output written to temporary .mp4 beside destination and moved into place **only on success**; cancellation and errors clean up.
- If `nb_frames` is absent, duration-based progress is approximate, not a termination bound.

## Model contract
- User provides a previously converted OpenVINO IR (.xml and .bin), one static [1,3,H,W] input and [1,3,H*S,W*S] output, scale S=2 or 4.
- RGB float32 0..1 input and 0..1 output. No arbitrary model preprocessing contract detection.
- Fixed-shape tile processing with 8px input-space overlap, edge padding, output cropping. Tile dimensions > 16.
- A separately downloaded and verified BSRGANx2 INT8 model ZIP is published in this project's Releases; physical NPU operation on 125H has evidence, but GPU model compilation, quality and performance remain unverified.

## Acceptance checks
1. Detect/probe selected GPU or NPU, compile the model only on that device, no fallback. For GPU standard releases verify the frozen EXE contains the GPU/NPU UI and the released tag uses the same GPU-capable source.
2. Test parser for invalid streams, fractional FPS, audio codec validation.
3. Test FFmpeg argv including audio track copy, partial-output cleanup and cancellation.
4. Test exact dimensions and placement of overlap-tiled image output.
5. GUI handles selecting paths, start and cancel without blocking UI.
6. Hardware smoke test on 125H: 5–10 second video; verify scale/fps/audio via ffprobe, image quality/seams/sync and conversion time.

## Non-goals
HDR, VFR, 10-bit video, subtitle retention, audio transcode, models with arbitrary shapes/layouts/normalization, real-time playback, 4x switch with unvalidated models, signed executable, backward compatibility/data migration.
