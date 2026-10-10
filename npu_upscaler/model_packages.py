"""Validated local OpenVINO model ZIP installation for NPU-only inference.

The archive's self-reported hashes detect corruption, but do not authenticate
the archive source. Only install ZIPs obtained from trusted project releases.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from typing import Callable
from zipfile import ZipFile, BadZipFile


class ModelPackageError(ValueError):
    pass


_SOURCE_SHA = "614f68bcafcf123a1ea51cc75ae5741640a8b1d49dd75757ad3ad531f772c736"
_FILES = {"BSRGANx2.xml", "BSRGANx2.bin"}
_ALLOWED = _FILES | {"model-manifest.json", "BSRGAN-LICENSE.txt"}
_MAX_TOTAL = 300 * 1024 * 1024


def model_cache_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NpuVideoUpscaler" / "Models"


def _manifest(data: dict) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ModelPackageError("Invalid model manifest format")
    if data.get("model") != "BSRGANx2" or data.get("source_sha256") != _SOURCE_SHA:
        raise ModelPackageError("Unexpected model source SHA-256 or model name")
    if data.get("weight_compression") != "INT8_ASYM":
        raise ModelPackageError("Unsupported model compression mode")
    if data.get("input_shape") != [1, 3, 48, 48] or data.get("output_shape") != [1, 3, 96, 96]:
        raise ModelPackageError("Unsupported OpenVINO model shape")
    files = data.get("files")
    if not isinstance(files, dict) or set(files) != _FILES or any(
        not isinstance(v, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", v) for v in files.values()
    ):
        raise ModelPackageError("Missing validated model file SHA-256 metadata")
    return files


def _sha(path: Path) -> str:
    h = sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _check_files(directory: Path) -> str:
    try:
        data = json.loads((directory / "model-manifest.json").read_text(encoding="utf-8"))
        hashes = _manifest(data)
        for name, expected in hashes.items():
            path = directory / name
            if not path.is_file() or _sha(path) != expected.lower():
                raise ModelPackageError(f"Model file SHA-256 mismatch: {name}")
        return hashes["BSRGANx2.xml"].lower()
    except (OSError, ValueError, TypeError, KeyError) as exc:
        if isinstance(exc, ModelPackageError):
            raise
        raise ModelPackageError(f"Invalid model package: {exc}") from exc


def find_prepared_model(root: Path | None = None) -> Path | None:
    root = Path(root) if root is not None else model_cache_root()
    if not root.is_dir():
        return None
    for path in sorted(root.iterdir(), reverse=True):
        if not path.is_dir() or not path.name.startswith("BSRGANx2-"):
            continue
        try:
            sha = _check_files(path)
            if path.name != f"BSRGANx2-{sha[:12]}":
                continue
            return path / "BSRGANx2.xml"
        except ModelPackageError:
            continue
    return None


def install_model_zip(archive: Path, root: Path | None = None,
                      compile_npu: Callable | None = None) -> Path:
    """Unpack checked bytes into private per-user cache only after NPU compile.

    ZIP is locally supplied by user: its self-reported hashes are integrity
    protection, NOT proof that it came from the project.
    """
    root = Path(root) if root is not None else model_cache_root()
    try:
        with ZipFile(archive) as z:
            members = z.infolist()
            names = [info.filename for info in members]
            if len(set(names)) != len(names) or not _FILES.issubset(names) or "model-manifest.json" not in names:
                raise ModelPackageError("Model archive lacks required files or duplicates entries")
            if any(name not in _ALLOWED for name in names):
                raise ModelPackageError("Unsafe or unexpected model archive contents")
            if any(info.file_size > _MAX_TOTAL for info in members) or sum(i.file_size for i in members) > _MAX_TOTAL:
                raise ModelPackageError("Model archive is too large")
            root.mkdir(parents=True, exist_ok=True)
            with TemporaryDirectory(prefix=".model-install-", dir=root) as tempdir:
                staging = Path(tempdir) / "model"
                staging.mkdir()
                for info in members:
                    target = staging / info.filename
                    with z.open(info) as src, target.open("wb") as dst:
                        remaining = info.file_size
                        while True:
                            block = src.read(min(1024 * 1024, remaining + 1))
                            if not block:
                                break
                            remaining -= len(block)
                            if remaining < 0:
                                raise ModelPackageError("Model archive exceeds declared size")
                            dst.write(block)
                        dst.flush()
                        if target.stat().st_size != info.file_size:
                            raise ModelPackageError("Truncated model archive")
                sha = _check_files(staging)
                target_dir = root / f"BSRGANx2-{sha[:12]}"
                if target_dir.exists():
                    if _check_files(target_dir) == sha:
                        return target_dir / "BSRGANx2.xml"
                    raise ModelPackageError("Prepared model cache is corrupted")
                try:
                    if compile_npu is None:
                        from .npu import load_npu_model
                        compile_npu = load_npu_model
                    compile_npu(staging / "BSRGANx2.xml")
                except Exception as exc:
                    raise ModelPackageError(f"NPU failed to compile model: {exc}") from exc
                os.replace(staging, target_dir)
                return target_dir / "BSRGANx2.xml"
    except (OSError, BadZipFile) as exc:
        raise ModelPackageError(f"Cannot open model archive: {exc}") from exc
