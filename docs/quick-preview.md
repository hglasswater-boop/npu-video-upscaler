# Quick preview: first 60 seconds — Issue #6

## User flow
- Select a source MP4/MKV and model, then choose **Full video** (default) or **First 60 seconds (quick test)**.
- When output has not been manually edited, suggest `<source>_upscaled_preview60.mp4` for preview; full export suggests `<source>_upscaled.mp4`.
- Start saves an independent MP4 file in the same folder as the input by default. Never modify the input; existing output is replaced only after a successful export, as before.
- Display preview progress as completed frames out of at most 60 seconds of the source's **nominal CFR**. If the input video is shorter, process only available frames. Standard cancellation remains available.
- Save compatible source audio as stream copy, and cap the output timeline at 60 seconds; source with no audio remains silent.
- This is AI **NPU inference** with the selected model, not a separate preview-quality scaler or CPU fallback. External compatible OpenVINO IR is still required.

## Time/frame policy
1. For nominal input frame rate `fps = numerator/denominator`, maximum video frame count is **floor(60 * numerator / denominator)**. This keeps encoded video duration at or under 60 s for rational rates (e.g. 30000/1001 → 1798 frames).
2. FFmpeg raw RGB decoder is given `-frames:v <limit>` so it exits successfully after the cap; Python **must not** stop reading and then hang waiting for an undecoded FFmpeg process.
3. The mux/encode command is given output `-t 60` after all inputs, capping copied audio even if the source is longer. Audio codec restrictions from [requirements](requirements.md) still apply; timestamp granularity may cause a last AAC frame close to 60 seconds.
4. Input shorter than 60 seconds: decoder reaches normal EOF, preserving the number of actual frames; ffmpeg audio also ends with the source. No artificial padding.
5. Duration and frame progress are an **estimate** based on nominal CFR metadata. True VFR, offsets, gaps, HDR and subtitles remain unsupported.

## Acceptance / TDD
- [ ] Unit: no limit for full export; 24 fps preview = 1440 frames; 30000/1001 preview = 1798 frames; unknown metadata still limits decode.
- [ ] Unit: decoder command adds `-frames:v` only for preview; encoder adds `-t 60` only for preview and retains `-map 1:a? -c:a copy`.
- [ ] Unit: GUI passes selected mode and suggests preview-specific filename without overwriting an edited destination.
- [ ] FFmpeg integration: 65s tiny CFR video with AAC previews as 60s output with video and audio durations no greater than 60 seconds plus one encoded audio packet.
- [ ] FFmpeg integration: a short input is not padded.
- [ ] Windows CI build/installer smoke tests, no NPU claims.

## Release
Version bump to `0.2.0a2` and publication of a new experimental alpha asset **only after successful CI**, enabling existing `v0.2.0a1` updater users to detect the new release.

## Separate work
Model bundling and first-run preparation plus NPU 125H validation remain under [Issue #3](https://github.com/hglasswater-boop/npu-video-upscaler/issues/3). End-to-end updater installation across versions is not validated by this feature alone.
