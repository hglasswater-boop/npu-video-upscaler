> **方針更新 2026-10-11:** GPU（Intel Arc）を標準推論先とし、NPUは明示選択できる省電力モードとして残す。CPU/AUTOへの自動フォールバック禁止。旧NPU-only指示よりユーザーの最新方針と docs/gpu-migration.md / Issue #23 を優先。\n\n# Repository instructions for Codex

Read [docs/CODEX_HANDOFF.md](docs/CODEX_HANDOFF.md) at the start of a task. Also read the issue, relevant sources, tests and existing CI workflows. The handoff is a dated snapshot; **verify current GitHub state** and do not assume branches or issue statuses are still unchanged.

## Product and hard constraints

- Product: **NPU Video Upscaler**, a Japanese-language Windows 11 x64 desktop app for offline MP4/MKV → upscaled H.264 MP4.
- Target hardware: **Intel Core Ultra 5 125H**, Intel NPU via OpenVINO. Use `core.compile_model(model, "NPU")` only. **Never silently fall back to CPU, GPU, AUTO, MULTI or HETERO**. GitHub Windows runners are not evidence of real-device NPU support.
- Main user path: choose video → first-run FFmpeg/model setup → preview first 60 s (default) → optionally export full file. Keep the GUI understandable, **Japanese**, compact and responsive.
- Media: nominally CFR SDR 8-bit, compatible audio copied via `-map 1:a? -c:a copy`; preserve exact rational FPS; no HDR/VFR/subtitle promises. Process with streaming FFmpeg input/output and temporary MP4, atomically replace destination **only on success**; cancel without harming prior output.
- FFmpeg/ffprobe are downloaded **with explicit user consent directly from the publisher** as a pinned SHA-256-verified archive and cached per user. **Do not bundle or rehost GPLv3 Gyan FFmpeg binaries in our Release assets.** Frozen builds must not silently use arbitrary PATH FFmpeg. Intel NPU driver remains OS-managed.
- AI model: separate experimental BSRGANx2 static OpenVINO INT8 ZIP, verified and compiled exclusively on NPU before selection. 125H physical compilation/inference/quality remain unverified unless a physical test is documented.
- Updates: only canonical versioned GitHub Releases assets, verify SHA-256, obtain consent before download and installer launch, and do not interrupt active conversions. Never mutate published versioned assets.

## Engineering sequence

1. Verify facts and write/update a focused issue or design note **before** implementation.
2. Write failing regression tests for the specific bug/behavior; then implement the minimum correct change.
3. Run targeted pytest, whole test suite, GUI offscreen tests and Windows Actions package/installer integration. No claims about passes before results are available.
4. Preserve safety, error reporting and existing behavior. Prefer KISS and no compatibility/migration scaffolding unless specifically required.
5. Open a PR referencing the issue. Merge and publish an **immutable new alpha version** only after CI succeeds and publishing is authorized; never overwrite an existing tag/release.
6. Clearly separate CI simulation/Windows VM checks from the user's physical Core Ultra 5 125H test. For unresolved hardware bugs, request exact log/stack trace from the actual installed build.

## Key files and commands

- `npu_upscaler/gui.py`, `gui_layout.py`: Japanese PySide6 interface / worker threads.
- `npu_upscaler/media.py`, `pipeline.py`: ffprobe/FFmpeg media processing.
- `npu_upscaler/media_tools.py`: consent-based FFmpeg bootstrap and verified per-user cache.
- `npu_upscaler/npu.py`, `model_packages.py`, `model_download.py`: NPU model and download.
- `npu_upscaler/updates.py`: updater; `launcher.py`: Windows frozen executable entry.
- `installer.iss`, `.github/workflows/test.yml`, `.github/workflows/windows-build-release.yml`: packaging, tests and alpha release.
- `npu_upscaler/__init__.py`: single source for the application version.
- Install dev deps on Python 3.12: `python -m pip install -e ".[dev]"`
- Run tests: `python -m pytest -q`. Windows release workflow fetches pinned FFmpeg and generates the experimental model ZIP separately; a local machine may skip FFmpeg integration tests.
- Source app: `python -m npu_upscaler`
- Design/spec references: `docs/architecture.md`, `docs/quick-preview.md`, `docs/model-preparation.md`, `docs/bundled-media-tools.md`, `docs/releases-and-updates.md`.

**Important:** Some older documents (notably `docs/requirements.md` and parts of `docs/releases-and-updates.md`) still describe the original FFmpeg-on-PATH flow. Treat the current code, recent issues and the publisher-direct FFmpeg specification as the more recent source of truth and bring outdated docs into sync when touching them.
