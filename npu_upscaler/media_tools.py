"""Install FFmpeg directly from its publisher on opt-in, never redistribute it in our EXE."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from tempfile import TemporaryDirectory
from typing import Callable
from urllib.error import URLError
from urllib.request import urlopen
from zipfile import BadZipFile, ZipFile


# Fixed upstream GitHub release; sha256 independently matched its published digest.
VENDOR_URL = (
    "https://github.com/GyanD/codexffmpeg/releases/download/9.0.2/"
    "ffmpeg-9.0.2-essentials_build.zip"
)
VENDOR_SIZE = 114768076
VENDOR_SHA256 = "60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba"
_MAX_FILE_SIZE = 256 * 1024 * 1024
_CHUNK = 1024 * 1024
_FILES = ("ffmpeg.exe", "ffprobe.exe")


class MediaToolsError(RuntimeError):
    """Media tools are absent or a direct-from-publisher install failed."""


@dataclass(frozen=True)
class MediaTools:
    ffmpeg: str
    ffprobe: str


def media_cache_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "NpuVideoUpscaler" / "MediaTools"


def _version_dir(root: Path) -> Path:
    return root / ("ffmpeg-9.0.2-" + VENDOR_SHA256[:12])


def _sha_file(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(_CHUNK), b""):
            digest.update(block)
    return digest.hexdigest()


def find_installed_media_tools(root: Path | None = None) -> MediaTools | None:
    root = Path(root) if root is not None else media_cache_root()
    directory = _version_dir(root)
    try:
        manifest = json.loads((directory / "checksums.json").read_text("utf-8"))
        if manifest.get("vendor_sha256") != VENDOR_SHA256:
            return None
        for name in _FILES:
            if not (directory / name).is_file() or manifest.get(name) != _sha_file(directory / name):
                return None
        return MediaTools(str(directory / "ffmpeg.exe"), str(directory / "ffprobe.exe"))
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def resolve_media_tools(root: Path | None = None) -> MediaTools:
    """Always use validated user cache; source-only fallback permits PATH tools."""
    installed = find_installed_media_tools(root)
    if installed:
        return installed
    if getattr(sys, "frozen", False):
        raise MediaToolsError(
            "FFmpeg が未設定です。アプリの「FFmpegをダウンロード」からセットアップしてください。"
            " システムのPATH設定は不要です。"
        )
    ffmpeg, ffprobe = shutil.which("ffmpeg"), shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        missing = "/".join(name for name, value in (
            ("ffmpeg", ffmpeg), ("ffprobe", ffprobe)
        ) if not value)
        raise MediaToolsError(
            f"{missing} missing. Use the app's Download FFmpeg action or install FFmpeg on PATH."
        )
    return MediaTools(ffmpeg, ffprobe)


def _extract_executables(archive: Path, target: Path) -> None:
    try:
        with ZipFile(archive) as z:
            selected = {}
            for item in z.infolist():
                name = item.filename.replace("\\", "/").lower()
                for binary in _FILES:
                    if name.endswith("/bin/" + binary):
                        if binary in selected:
                            raise MediaToolsError(f"Vendor ZIP has duplicate {binary}")
                        if item.is_dir() or not (0 < item.file_size <= _MAX_FILE_SIZE):
                            raise MediaToolsError(f"Invalid vendor file size: {binary}")
                        selected[binary] = item
            for binary in _FILES:
                if binary not in selected:
                    raise MediaToolsError(f"Vendor ZIP missing {binary}")
                info = selected[binary]
                with z.open(info) as source, (target / binary).open("wb") as dst:
                    copied = 0
                    while block := source.read(_CHUNK):
                        copied += len(block)
                        if copied > info.file_size:
                            raise MediaToolsError("Invalid expanded vendor binary size")
                        dst.write(block)
                    if copied != info.file_size:
                        raise MediaToolsError("Incomplete vendor binary extraction")
    except BadZipFile as exc:
        raise MediaToolsError(f"Invalid vendor ZIP: {exc}") from exc


def _check_runtime(tools: MediaTools, runner: Callable) -> None:
    try:
        for binary in (tools.ffmpeg, tools.ffprobe):
            result = runner([binary, "-version"], capture_output=True, timeout=30)
            if result.returncode:
                raise MediaToolsError(f"FFmpeg execution failed: {Path(binary).name}")
        encoders = runner([tools.ffmpeg, "-hide_banner", "-encoders"],
                          capture_output=True, timeout=30)
        if encoders.returncode or b"libx264" not in encoders.stdout:
            raise MediaToolsError("Downloaded FFmpeg lacks required libx264 encoder")
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaToolsError(f"Downloaded FFmpeg execution failed: {exc}") from exc


def install_vendor_media_tools(
    root: Path | None = None, *,
    opener: Callable = urlopen,
    runner: Callable = subprocess.run,
    progress: Callable[[int, int], None] = lambda done, total: None,
) -> MediaTools:
    """Publisher-direct one-time install, strict archive identity and atomic cache.

    Caller must first get user consent. No bundled distribution or global PATH.
    """
    root = Path(root) if root is not None else media_cache_root()
    existing = find_installed_media_tools(root)
    if existing:
        return existing
    root.mkdir(parents=True, exist_ok=True)
    try:
        with TemporaryDirectory(prefix=".setup-", dir=root) as temp:
            workspace = Path(temp)
            archive = workspace / "publisher.zip"
            digest = sha256()
            received = 0
            with opener(VENDOR_URL, timeout=60) as response, archive.open("wb") as dst:
                while block := response.read(_CHUNK):
                    received += len(block)
                    if received > VENDOR_SIZE:
                        raise MediaToolsError("Vendor archive is larger than the pinned version")
                    digest.update(block)
                    dst.write(block)
                    progress(received, VENDOR_SIZE)
            if received != VENDOR_SIZE or digest.hexdigest() != VENDOR_SHA256:
                raise MediaToolsError("FFmpeg vendor archive SHA-256/size mismatch")
            staging = workspace / "expanded"
            staging.mkdir()
            _extract_executables(archive, staging)
            manifest = {
                "vendor_sha256": VENDOR_SHA256,
                **{name: _sha_file(staging / name) for name in _FILES}
            }
            target = _version_dir(root)
            if target.exists() or target.is_symlink():
                other = find_installed_media_tools(root)
                if other:
                    return other
                if target.is_symlink():
                    raise MediaToolsError("FFmpeg の保存先がシンボリックリンクです。安全のため中止しました。")
                # A previous interrupted setup may leave an invalid directory.
                shutil.rmtree(target)
            # Never run PE files from a directory before renaming it on Windows.
            for attempt in range(7):
                try:
                    os.replace(staging, target)
                    break
                except PermissionError:
                    if attempt == 6:
                        raise MediaToolsError(
                            "FFmpeg フォルダーへの書き込みが拒否されました。"
                            " セキュリティソフトの保護設定を確認し、アプリを再起動してお試しください。"
                        )
                    time.sleep(0.25)
            tools = MediaTools(str(target / "ffmpeg.exe"), str(target / "ffprobe.exe"))
            try:
                # Cache becomes active only after successfully running final-path tools.
                _check_runtime(tools, runner)
                (target / "checksums.json").write_text(
                    json.dumps(manifest, indent=2), encoding="utf-8"
                )
            except Exception:
                try:
                    shutil.rmtree(target)
                except OSError:
                    pass  # Absent manifest guarantees incomplete cache is never used.
                raise
            return tools
    except (URLError, TimeoutError, OSError, BadZipFile) as exc:
        raise MediaToolsError(f"FFmpeg のダウンロードまたはインストールに失敗しました。{exc}") from exc
