# NPU Video Upscaler

Windows 11 **experimental desktop app** for offline MP4/MKV video upscaling with Intel Core Ultra **NPU-only** inference using OpenVINO + FFmpeg. Development: [Issue #1](https://github.com/hglasswater-boop/npu-video-upscaler/issues/1).

> **Not yet tested on a Core Ultra 5 125H.** The v0.2.0a3 alpha offers an opt-in download of a **separate experimental BSRGANx2 OpenVINO model ZIP** from this project's GitHub Releases. It can be used only after compilation on the local Intel NPU succeeds; successful compilation on Core Ultra 5 125H remains unverified.

## Supported MVP

- PySide6 GUI: choose video, model XML and MP4 destination; start, progress and cancel.
- `OpenVINO Core().compile_model(model, "NPU")` uses the NPU exclusively. **No silent CPU/GPU fallback.**
- Static [1,3,H,W] normalized RGB model input and [1,3,H×S,W×S] output, where S is **2 or 4**. Overlapping tiles handle arbitrary input image width/height while retaining a fixed model shape.
- Constant-frame-rate **SDR, 8-bit** MP4/MKV source; fractional FPS (e.g., 30000/1001) retained nominally.
- 8-bit H.264 `libx264` MP4 output and stream copy of compatible AAC/MP3/AC-3/E-AC-3/ALAC audio. A silent source yields silent output.
- Temporary output and cleanup on failure/cancel; no server uploads.

## Planned self-contained FFmpeg installer (Issue #11)

**Development branch only — not released yet.** The Windows installer / portable build will include the verified vendor `ffmpeg.exe` and `ffprobe.exe` in an application-private directory. The frozen app uses only that pair, does not change system PATH, and provides a `--check-media` command for offline testing. Python/source checkouts still require their own FFmpeg on PATH.

The selected Gyan Essentials build includes GPLv3-licensed code (`libx264`). **The public release is intentionally blocked until the complete corresponding source and related license obligations can be provided and checked.** A copy of the GPLv3 license, notices and `ffmpeg -buildconf` will travel with the binaries, but those documents **alone are insufficient** for compliant redistribution. See [bundled media tool specification](docs/bundled-media-tools.md).

Intel NPU drivers are never silently installed or bundled. If the app cannot see `NPU`, use the in-app **Intel NPU driver help** link or the [Intel download page](https://www.intel.com/content/www/us/en/download/794734/intel-npu-driver-windows.html). A reboot may be required after driver installation. Real Intel Core Ultra 5 125H inference is still unverified.

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

- Installer does **not** contain model weights; alpha v0.2.0a3 publishes a separate checksummed BSRGANx2 model ZIP for consent-based setup. Windows CI has installer smoke tests, but the EXE is unsigned and no Core Ultra 5 125H NPU smoke test has passed.
- Accepts only simple **nominally CFR** sources. Matching avg/r frame-rate does not conclusively detect VFR. Source per-frame timestamps, rotation, HDR metadata, and subtitle/attachment tracks are not preserved.
- Unsupported audio codecs are rejected rather than transcoded or dropped. Audio stream-copy is supported for listed codecs, but complex sync cases need validation.
- HEVC / Intel Quick Sync encoder path and seamless output guarantees across different super-resolution models are out of scope for this first iteration.
- This is a **development prototype**, not a production-ready release.

See [requirements](docs/requirements.md) and [architecture](docs/architecture.md).

## First-minute quality test (v0.2.0a2)

Choose **First 60 seconds only (quick quality test)** in the Windows GUI to upscale just the first minute using the selected **NPU-only** model and save a separate `_upscaled_preview60.mp4`. This is useful for judging visual quality and elapsed conversion time before running the complete file. Full-length export remains the default. Source shorter than 60 seconds is exported without padding.

The preview pipeline limits decoded **video frames** to at most `floor(60 × source_fps)` and caps copied source audio at 60 seconds. Fractions (29.97fps) are handled exactly; the final audio packet may end within approximately one encoded audio frame after the 60-second mark. Source timelines must satisfy the nominal constant-FPS limitations documented in [quick preview spec](docs/quick-preview.md). NPU-compatible model and FFmpeg remain prerequisites.

## Experimental Windows installer and built-in updates

**Alpha version v0.2.0a1** adds a Windows x64 per-user Inno Setup installer and portable ZIP. After CI completes and the change is merged to main, packages are published under [GitHub Releases](https://github.com/hglasswater-boop/npu-video-upscaler/releases). PR builds provide temporary [GitHub Actions artifacts](https://github.com/hglasswater-boop/npu-video-upscaler/actions) only. **An alpha installer is a testing convenience, not evidence that NPU inference is supported on your 125H yet.**

Install the `NpuVideoUpscaler-Setup-v*-win-x64.exe` asset (unsigned), then launch via Start Menu. Portable ZIP contains a self-contained application folder; FFmpeg and the Intel NPU driver must still be installed separately. The BSRGANx2 model is provided as a separate GitHub Release asset (v0.2.0a3+) and can be set up from the GUI after consent.

The desktop app checks GitHub Releases in a background thread at startup (toggle via **Check for updates on startup**) and has a **Check for updates** button. If a newer eligible release exists, approve the download, SHA-256 verification and interactive installer launch. Conversion jobs are not intentionally interrupted. Stable builds ignore prereleases; experimental builds may see alpha versions. Network activity for release checks is limited to the GitHub API and installer asset download; video data is never uploaded.

Release tags and installer/portable archive names are derived from the package's single version string. Every new update requires a **new version**, rather than overwriting existing assets. See [release/update specification](docs/releases-and-updates.md) and [Issue #4](https://github.com/hglasswater-boop/npu-video-upscaler/issues/4).

## Experimental BSRGANx2 model setup (v0.2.0a3)

First launch offers a confirmation to download a **separate** BSRGANx2 model ZIP from this repository's versioned GitHub Releases. The archive is verified against the published SHA-256 and per-file hashes before OpenVINO tries to compile it **only on NPU**. It is saved and auto-selected after a successful NPU compilation; failure leaves the app without an active default model. Alternatively, use **Install model ZIP** to import the matching trusted build artifact. The installer/EXE itself contains no pretrained model, PyTorch or NNCF; the model is provisioned on demand.

**This is experimental:** v0.2.0a3's conversion pipeline has only been validated in Windows CI on CPU. **No Core Ultra 5 125H NPU test has passed yet.** Image quality, seam artifacts and execution speed are unknown. The app displays a clear error if the NPU cannot compile the model. See [model preparation, licensing and limitations](docs/model-preparation.md) and [Issue #3](https://github.com/hglasswater-boop/npu-video-upscaler/issues/3).
