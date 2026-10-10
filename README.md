# NPU Video Upscaler

Windows 11 **experimental desktop app** for offline MP4/MKV video upscaling with Intel Core Ultra **NPU-only** inference using OpenVINO + FFmpeg. Development: [Issue #1](https://github.com/hglasswater-boop/npu-video-upscaler/issues/1).

> **Not yet tested on a Core Ultra 5 125H.** This prototype requires a **user-prepared, compatible OpenVINO IR super-resolution model** (`.xml` and matching `.bin`). BSRGAN conversion and weight distribution are **not automated**. Do not expect one-click conversion from a fresh install.

## Supported MVP

- PySide6 GUI: choose video, model XML and MP4 destination; start, progress and cancel.
- `OpenVINO Core().compile_model(model, "NPU")` uses the NPU exclusively. **No silent CPU/GPU fallback.**
- Static [1,3,H,W] normalized RGB model input and [1,3,H×S,W×S] output, where S is **2 or 4**. Overlapping tiles handle arbitrary input image width/height while retaining a fixed model shape.
- Constant-frame-rate **SDR, 8-bit** MP4/MKV source; fractional FPS (e.g., 30000/1001) retained nominally.
- 8-bit H.264 `libx264` MP4 output and stream copy of compatible AAC/MP3/AC-3/E-AC-3/ALAC audio. A silent source yields silent output.
- Temporary output and cleanup on failure/cancel; no server uploads.

## Install / launch from source

1. Windows 11 64-bit; install latest [Intel NPU driver](https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/npu-device.html) compatible with your device.
2. Install Python 3.11 or 3.12 and FFmpeg, ensuring both `ffmpeg` and `ffprobe` are on PATH.
3. In PowerShell in this repository:

   ```powershell
   py -3.12 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -e ".[dev]"
   python -c "import openvino as ov; print(ov.Core().available_devices)"
   python -m npu_upscaler
   ```

4. Confirm the device list includes `NPU`. Select an actual NPU-compilable OpenVINO IR `.xml` (with companion `.bin`). Intel provides an [AI Upscaling with NPU sample](https://github.com/intel/AI-PC-Samples/tree/main/AI-Upscaling-With-NPU) demonstrating BSRGAN model conversion/weight compression. Prepare and export a compatible **static-shape** IR using the original model's license, and confirm its normalized RGB I/O contract. The sample by itself does not guarantee your converted IR or NPU driver supports these settings.
5. First process a short, low-resolution, CFR sample and compare quality and audio sync. Conversion time on the 125H is **unknown until measured**.

Run pure contract tests:

```powershell
python -m pytest -q
```

## Known limitations / pending validation

- No bundled upscaling model, one-click IR conversion, tested installer, signed EXE, or NPU hardware smoke test.
- Accepts only simple **nominally CFR** sources. Matching avg/r frame-rate does not conclusively detect VFR. Source per-frame timestamps, rotation, HDR metadata, and subtitle/attachment tracks are not preserved.
- Unsupported audio codecs are rejected rather than transcoded or dropped. Audio stream-copy is supported for listed codecs, but complex sync cases need validation.
- HEVC / Intel Quick Sync encoder path and seamless output guarantees across different super-resolution models are out of scope for this first iteration.
- This is a **development prototype**, not a production-ready release.

See [requirements](docs/requirements.md) and [architecture](docs/architecture.md).
