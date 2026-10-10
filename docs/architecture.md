# Architecture — docs first → TDD → implementation

## Pipeline
```text
PySide6 GUI → background worker
                 ↓
            ffprobe validate source + input paths
                 ↓
          OpenVINO IR → compile_model("NPU")
                 ↓
   FFmpeg RGB24 decode pipe → per-frame overlap tiling → NPU inference
                 ↓
   FFmpeg RGB24 encode pipe + second input original audio → temporary MP4
                 ↓
     validate subprocess success → rename output atomically
```
NPU handles **only inference**; the CPU handles image tiling and frame transfer; FFmpeg handles decoding, encoding and audio remux. No `AUTO` device selection. One input and one output video frame buffered at a time.

## Overlap tiling
For a static input tile H×W and 8px context margin, process core tiles of (H−16)×(W−16) pixels. Edge-pad the image for partial tiles, infer fixed-size tile, crop model output context and paste into a full-resolution output frame. Verify model output scale is 2 or 4 and tensor shape NCHW.

## Failure semantics
Use subprocess argument arrays without a shell. Check input sizes and media/codecs before starting; kill child processes on cancel/error and remove temp output. Do not replace destination with partial output. Nonzero FFmpeg return codes are failures. CPU/GPU execution is **never** an implicit fallback.

## Model delivery
MVP runtime consumes a user-provided, NPU-compatible, **static-shape** OpenVINO model IR. Preparing BSRGAN weights and automatically distributing a verified IR is a follow-up; official conversion demonstration uses OpenVINO + NNCF and explicit static input dimensions. Verify weight provenance and redistribution license before bundling.

## Primary sources
- https://www.intel.com/content/www/us/en/developer/articles/technical/enhance-ai-upscaling-with-intel-ai-boost-npu.html
- https://github.com/intel/AI-PC-Samples/blob/main/AI-Upscaling-With-NPU/README.md
- https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/npu-device.html

## Delivery stages
1. Document assumptions and limitations.
2. Write contract tests before production modules.
3. Small Python modules, PySide6 UI, CI.
4. Cleanup + quality checks and draft PR. No claims of passing hardware smoke tests until measured.
