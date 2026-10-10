# BSRGANx2 OpenVINO model preparation — Issue #3

## Evidence and provenance

Intel's [AI-Upscaling-With-NPU](https://github.com/intel/AI-PC-Samples/tree/main/AI-Upscaling-With-NPU) sample uses pretrained BSRGAN weights, converts the PyTorch RRDBNet to a static OpenVINO model, uses NNCF weight compression (the default for BSRGAN's convolution layers was measured as INT8) and compiles for device `NPU`. The original [BSRGAN](https://github.com/cszn/BSRGAN) project publishes BSRGANx2 weights through the author's [KAIR v1.0 GitHub Release](https://github.com/cszn/KAIR/releases/tag/v1.0) (~67MB). The BSRGAN code repository declares Apache-2.0; the KAIR source repository declares MIT. Do **not** infer that all checkpoints have unconditional redistribution permission from the source-code license alone.

## Build contract

1. Model input: user/admin supplies a downloaded `BSRGANx2.pth` and its **independently recorded, exact SHA-256**. No runtime random third-party code execution and no implicit network access.
2. Model architecture: a vendor snapshot of original `cszn/BSRGAN/models/network_rrdbnet.py`, accompanied by its Apache-2.0 attribution. No `torch.hub.load` and no remote Python imports.
3. Prepare static RGB `[1,3,48,48]` input, 2× output `[1,3,96,96]`, NCHW float32 normalized 0–1; NNCF INT8 asymmetric weight compression for a reproducible first baseline, serialize OpenVINO `.xml` plus `.bin`.
4. Compare the model input/output contract to the application before using it. CPU-only smoke inference confirms *conversion*, **not Core Ultra 5 125H NPU compatibility**. Real NPU compile is a separate release gate.
5. Produce deterministic packaging metadata: source URL + SHA-256, resulting IR SHA-256 for both files, OpenVINO/NNCF versions, shape, licenses and actual smoke-test details. Do not distribute raw PyTorch pickle or weights as part of this installer.
6. Public **experimental** alpha may publish the converted IR only as a separate versioned model ZIP, with upstream license attribution, published GitHub SHA-256 and an explicit warning that 125H compatibility is unverified. Before any *production* or bundled offline release, perform a real Meteor Lake NPU smoke test. Old v0.2.0a2 remains model-less.

## Model-enabled alpha: first-launch flow

- The app obtains its separately published IR asset only from the project's canonical GitHub Releases URL and verifies the published SHA-256 digest plus internal hashes. The installer itself contains no weights.
- First launch detects an available packaged validated model and automatically selects it. When only a downloadable model package is available, show explicit **Download model** consent and progress; verify checksum before enabling conversion.
- Verify NPU availability and `compile_model(..., 'NPU')` before advertising “Ready”. Display errors and remediation instead of falling back to CPU/GPU.
- Existing user-provided models remain an option until default weights are genuinely validated. No migration or backward-compatibility code.

## Outstanding physical acceptance

Test on Core Ultra 5 125H NPU with driver version recorded. Compile model on **NPU**, run 5–10 seconds of two SDR CFR test clips and check resultant dimensions, tile artifacts, fps, audio sync, NPU utilization, wall-time and memory. This cannot be certified from GitHub hosted CI or an unrelated NPU.

## Offline conversion CLI (developer / build worker)

```powershell
py -3.12 -m venv .model-venv
.\\.model-venv\\Scripts\\Activate.ps1
python -m pip install -r scripts/model-build-requirements.txt
# Download BSRGANx2.pth yourself from the AUTHOR's KAIR v1.0 GitHub Release.
# Enter its SHA-256 after independent verification; never invent a digest.
python -m scripts.build_bsrgan_ir --checkpoint BSRGANx2.pth --sha256 YOUR_VERIFIED_64_HEX --output model-output
```

Output includes `BSRGANx2.xml`, `BSRGANx2.bin`, `model-manifest.json`. Inputs remain offline; the tool itself does **not** access the internet. Heavy PyTorch/NNCF build dependencies are isolated from the desktop application and its Windows installer. This standalone CLI is a build-only conversion tool. The desktop application separately provides an opt-in, first-launch verified model download and installation flow. The checkpoint hash is a mandatory parameter so unverified source weights are not silently deserialized.

## Upstream checkpoint digest (observed in CI audit)

The original author's `cszn/KAIR` v1.0 `BSRGANx2.pth` download was fetched by [the dedicated checksum audit workflow](../.github/workflows/model-audit.yml) on a GitHub-hosted Ubuntu runner. The observed file size was **66,894,171 bytes**, and SHA-256 was `614f68bcafcf123a1ea51cc75ae5741640a8b1d49dd75757ad3ad531f772c736`. This is the pinned byte identity for future conversion jobs, **not** proof of 125H NPU compatibility or permission to redistribute the checkpoint.

## Recorded precision correction (CI conversion result)

The Windows OpenVINO 2026.4.1 + NNCF 2.19 conversion of this RRDBNet returned **350/350 convolution layers as INT8_ASYM**, even when `CompressWeightsMode.INT4_SYM` was requested. NNCF documents convolution layers as INT8 backup precision by default. For the first dependable artifact, explicitly request **INT8_ASYM** and record it in the manifest. INT4 compression (`all_layers=True`) is only an optional future performance/accuracy experiment, not a verified capability of this BSRGANx2 IR on the 125H.

The secondary [kadirnar/BSRGANx2 model card](https://huggingface.co/kadirnar/BSRGANx2) explicitly declares Apache-2.0; its listed SHA-256 is the same as the upstream checkpoint. Preserve the source model and Apache license attribution if distributing a derivative IR. Physical NPU compatibility is still unverified.

## Experimental model ZIP import (manual alternative)

After Windows conversion CI passes, upload an archive containing `BSRGANx2.xml`, `BSRGANx2.bin`, `model-manifest.json` and the Apache-2.0 license notice as **short-lived GitHub Actions artifacts**. The app may offer **Install local model ZIP**. The ZIP must be obtained from this project's build artifacts; embedded manifest hashes verify the extracted IR but **do not cryptographically authenticate the entire ZIP**. Do not use untrusted third-party ZIPs. Do not install unless `NPU` compiles the IR on the target device.

The installer validates: exact file names, expected model/source SHA-256, static 48×48 RGB / 96×96 RGB, INT8_ASYM, XML+BIN nonempty bounded size, hashes from manifest, path traversal avoidance, and `compile_model('NPU')`. The app stores a verified model below the user's `LOCALAPPDATA/NpuVideoUpscaler/Models` path and selects it on subsequent launches. Errors leave no incomplete model selected. The local ZIP importer is an alternative to the separate first-run, consent-based project Release asset downloader; both require a successful local NPU compilation before install.

## First-run experimental model acquisition — new alpha only

A model-enabled alpha publishes the exact `BSRGANx2-OpenVINO-INT8.zip` alongside its Windows installer. The ZIP contains validated IR/manifest/Apache license notice but **no PyTorch pickle**. The app checks its own GitHub Releases API for a published prerelease with that **exact** filename, a GitHub `sha256:` asset digest, a bounded size and canonical project download URL. Do not trust a download supplied by a third-party web page. User explicitly approves downloading the model. The app verifies ZIP SHA-256 and each XML/BIN hash, compiles the IR on **NPU** (never CPU fallback), installs only after success, and auto-selects the installed IR at later launches. First-run setup must not block the UI and must not trigger during a running conversion.

The initial model is an **experimental INT8 baseline**. BSRGAN checkpoints and RRDBNet source are attributed with the upstream Apache-2.0 license and the [kadirnar/BSRGANx2 Apache-2.0 model card](https://huggingface.co/kadirnar/BSRGANx2); model deployment is still unverified on the Core Ultra 5 125H hardware. Installer size is kept smaller by publishing the IR ZIP as a separate GitHub Release asset rather than bundling PyTorch/NNCF or IR weights in the EXE. This achieves first-run *automatic setup after consent*, but not completely offline model availability.
