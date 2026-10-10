"""WinError 5: never launch executable from a directory that is yet to be moved."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
import subprocess
from zipfile import ZipFile

import pytest
from npu_upscaler import media_tools


def fake_zip():
    buff = BytesIO()
    with ZipFile(buff, "w") as z:
        z.writestr("ffmpeg/bin/ffmpeg.exe", b"fake-ffmpeg")
        z.writestr("ffmpeg/bin/ffprobe.exe", b"fake-ffprobe")
    return buff.getvalue()


def fixtures(monkeypatch):
    data = fake_zip()
    monkeypatch.setattr(media_tools, "VENDOR_SHA256", sha256(data).hexdigest())
    monkeypatch.setattr(media_tools, "VENDOR_SIZE", len(data))
    return lambda *a, **kw: BytesIO(data)


def test_subprocess_is_launched_only_after_windows_directory_move(monkeypatch, tmp_path):
    opener = fixtures(monkeypatch)
    executed = []
    original_replace = media_tools.os.replace

    def windows_replace(source, target):
        if any(str(path).startswith(str(source)) for path in executed):
            raise PermissionError(13, "locked PE image", str(source))
        return original_replace(source, target)

    def run(args, **kwargs):
        exe = Path(args[0])
        executed.append(exe)
        assert exe.parent == media_tools._version_dir(tmp_path)
        assert not (exe.parent / "checksums.json").exists()
        return subprocess.CompletedProcess(args, 0, b"libx264", b"")

    monkeypatch.setattr(media_tools.os, "replace", windows_replace)
    paths = media_tools.install_vendor_media_tools(tmp_path, opener=opener, runner=run)
    assert media_tools.find_installed_media_tools(tmp_path) == paths
    assert len(executed) == 3


def test_transient_permission_errors_retry(monkeypatch, tmp_path):
    opener = fixtures(monkeypatch)
    original = media_tools.os.replace
    attempts = []

    def locked_twice(src, dst):
        attempts.append(1)
        if len(attempts) <= 2:
            raise PermissionError(13, "transient lock", str(src))
        return original(src, dst)

    monkeypatch.setattr(media_tools.os, "replace", locked_twice)
    monkeypatch.setattr(media_tools.time, "sleep", lambda _: None)
    result = media_tools.install_vendor_media_tools(
        tmp_path, opener=opener,
        runner=lambda args, **kwargs: subprocess.CompletedProcess(args, 0, b"libx264", b"")
    )
    assert Path(result.ffmpeg).is_file()
    assert len(attempts) == 3


def test_failed_runtime_does_not_mark_cache_ready(monkeypatch, tmp_path):
    opener = fixtures(monkeypatch)
    def fail(args, **kwargs):
        assert not (Path(args[0]).parent / "checksums.json").exists()
        return subprocess.CompletedProcess(args, 1, b"", b"failed")

    with pytest.raises(media_tools.MediaToolsError):
        media_tools.install_vendor_media_tools(tmp_path, opener=opener, runner=fail)
    assert media_tools.find_installed_media_tools(tmp_path) is None


def test_incomplete_cache_is_recoverable(monkeypatch, tmp_path):
    opener = fixtures(monkeypatch)
    incomplete = media_tools._version_dir(tmp_path)
    incomplete.mkdir()
    (incomplete / "ffmpeg.exe").write_bytes(b"broken")
    result = media_tools.install_vendor_media_tools(
        tmp_path, opener=opener,
        runner=lambda args, **kwargs: subprocess.CompletedProcess(args, 0, b"libx264", b"")
    )
    assert media_tools.find_installed_media_tools(tmp_path) == result
