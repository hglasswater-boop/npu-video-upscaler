# Architecture — docs first → TDD → implementation

## Conversion pipeline
```text
PySide6 GUI → conversion QThread
       ↓
ffprobe validate media → OpenVINO IR compile_model(selected 'GPU' or 'NPU')
       ↓
FFmpeg RGB decode → overlap tile → selected GPU/NPU inference → FFmpeg encode + audio copy
       ↓
temporary MP4 → atomic final rename on success
```
The CPU handles tiling and frame transfer, the explicitly selected GPU (default) or NPU handles inference, and FFmpeg handles media. No automatic fallback to another inference device.

## Release and update pipeline (Issue #4)
```text
PR → Windows GitHub Actions unit tests → PyInstaller onedir + Inno Setup
   → upload short-lived installer/portable/sha256 CI artifacts
main push (successful build only) → GitHub prerelease v{version} with installer + portable + sums
app startup/manual click → QThread query GitHub Releases API
   → filter version/channel → strict asset + digest validation
   → confirm download → QThread streaming download + sha256
   → confirm install → run interactive installer → quit (only while idle)
```
`npu_upscaler.__version__` is single source of truth. PyInstaller uses absolute-import `launcher.py` so entry works outside `python -m`. Inno Setup uses a fixed AppId, per-user install and a standard uninstall path. Failed network or integrity check cannot trigger an install. HTTPS only; model data never sent.

Detailed release/update criteria: [releases-and-updates.md](releases-and-updates.md). Other source constraints: [requirements.md](requirements.md).

## Primary sources
- https://www.intel.com/content/www/us/en/developer/articles/technical/enhance-ai-upscaling-with-intel-ai-boost-npu.html
- https://github.com/intel/AI-PC-Samples/tree/main/AI-Upscaling-With-NPU
- https://docs.openvino.ai/2026/openvino-workflow/running-inference/inference-devices-and-modes/npu-device.html
- https://docs.github.com/en/rest/releases/releases
- https://jrsoftware.org/ishelp/index.php?topic=setupcmdline
