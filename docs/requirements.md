# Requirements — Issue #1

## Goal
On Windows 11 with an Intel Core Ultra 5 125H, upscale a local MP4/MKV file with **NPU-only** OpenVINO inference, and save the video as MP4 with compatible source audio tracks copied.

## MVP interface
- PySide6 file selection: source video, OpenVINO model XML, output MP4. Start, cancel, progress, completion/errors.
- Mandatory NPU check; `core.compile_model(model, "NPU")` only. Never silently use CPU, GPU, AUTO, HETERO or MULTI.
- No cloud, downloads, telemetry or network during conversion.
- FFmpeg/ffprobe must be present on PATH; clear failure if missing.

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
- BSRGAN conversion is shown in Intel's sample, but **no converted model or weights are distributed**, and compatibility on this physical 125H is unverified.

## Acceptance checks
1. Detect/probe NPU, read and compile model on actual device, no fallback.
2. Test parser for invalid streams, fractional FPS, audio codec validation.
3. Test FFmpeg argv including audio track copy, partial-output cleanup and cancellation.
4. Test exact dimensions and placement of overlap-tiled image output.
5. GUI handles selecting paths, start and cancel without blocking UI.
6. Hardware smoke test on 125H: 5–10 second video; verify scale/fps/audio via ffprobe, image quality/seams/sync and conversion time.

## Non-goals
HDR, VFR, 10-bit video, subtitle retention, audio transcode, models with arbitrary shapes/layouts/normalization, real-time playback, 4x switch with unvalidated models, signed executable, backward compatibility/data migration.
