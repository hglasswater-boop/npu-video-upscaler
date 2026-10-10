"""Tests for user-consented, vendor-direct FFmpeg setup and local PATH independence."""

from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import subprocess
import sys
from zipfile import ZipFile

import pytest

from npu_upscaler import media_tools


def _zip_bytes(files=None):
    out = BytesIO()
    with ZipFile(out, 'w') as archive:
        for name, contents in (files or {
            'ffmpeg-9.0.2-essentials_build/bin/ffmpeg.exe': b'fake-ffmpeg',
            'ffmpeg-9.0.2-essentials_build/bin/ffprobe.exe': b'fake-ffprobe',
        }).items():
            archive.writestr(name, contents)
    return out.getvalue()


def _mock_vendor(monkeypatch, data):
    """Hash + size fixture override only; the runtime uses an upstream pinned hash."""
    monkeypatch.setattr(media_tools, 'VENDOR_SHA256', sha256(data).hexdigest())
    monkeypatch.setattr(media_tools, 'VENDOR_SIZE', len(data))
    return lambda url, timeout=60: BytesIO(data)


def _success_run(argv, **kwargs):
    exe = Path(argv[0]).name.lower()
    return subprocess.CompletedProcess(
        argv, 0,
        stdout=b'libx264' if 'ffmpeg' in exe else b'ffprobe version test',
        stderr=b''
    )


def test_vendor_zip_is_fixed_version_and_reproducibly_pinned():
    assert '/GyanD/codexffmpeg/releases/download/9.0.2/' in media_tools.VENDOR_URL
    assert media_tools.VENDOR_SIZE == 114768076
    assert media_tools.VENDOR_SHA256 == '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'


def test_direct_download_verified_and_cached_without_system_path(monkeypatch, tmp_path):
    data = _zip_bytes()
    opener = _mock_vendor(monkeypatch, data)
    statuses = []
    paths = media_tools.install_vendor_media_tools(tmp_path, opener=opener,
                                                   runner=_success_run,
                                                   progress=lambda done, total: statuses.append((done, total)))
    assert paths.ffmpeg.endswith('ffmpeg.exe')
    assert Path(paths.ffmpeg).read_bytes() == b'fake-ffmpeg'
    assert Path(paths.ffprobe).read_bytes() == b'fake-ffprobe'
    assert statuses[-1] == (len(data), len(data))
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: 'C:/unexpected/' + name)
    assert media_tools.resolve_media_tools(root=tmp_path) == paths
    assert media_tools.install_vendor_media_tools(tmp_path, opener=lambda *a, **k: pytest.fail('redownload')) == paths


def test_corrupt_vendor_download_never_installs(monkeypatch, tmp_path):
    data = _zip_bytes()
    opener = _mock_vendor(monkeypatch, data)
    monkeypatch.setattr(media_tools, 'VENDOR_SHA256', '0' * 64)
    with pytest.raises(media_tools.MediaToolsError, match='SHA-256'):
        media_tools.install_vendor_media_tools(tmp_path, opener=opener, runner=_success_run)
    assert media_tools.find_installed_media_tools(tmp_path) is None
    assert not list(tmp_path.rglob('ffmpeg.exe'))


def test_missing_probe_does_not_cache_partial_files(monkeypatch, tmp_path):
    data = _zip_bytes({'release/bin/ffmpeg.exe': b'only-one'})
    opener = _mock_vendor(monkeypatch, data)
    with pytest.raises(media_tools.MediaToolsError, match='ffprobe'):
        media_tools.install_vendor_media_tools(tmp_path, opener=opener, runner=_success_run)
    assert media_tools.find_installed_media_tools(tmp_path) is None


def test_vendor_zip_rejects_duplicate_tool_names(monkeypatch, tmp_path):
    data = _zip_bytes({
        'one/bin/ffmpeg.exe': b'first',
        'two/bin/ffmpeg.exe': b'second',
        'one/bin/ffprobe.exe': b'probe'
    })
    opener = _mock_vendor(monkeypatch, data)
    with pytest.raises(media_tools.MediaToolsError, match='duplicate'):
        media_tools.install_vendor_media_tools(tmp_path, opener=opener, runner=_success_run)


def test_download_failure_does_not_leave_active_executables(monkeypatch, tmp_path):
    data = _zip_bytes()
    opener = _mock_vendor(monkeypatch, data)

    def failed_run(*a, **kw):
        return subprocess.CompletedProcess(a, 1, b'', b'unsupported libx264')

    with pytest.raises(media_tools.MediaToolsError, match='実行|エンコーダー|execution|encoder'):
        media_tools.install_vendor_media_tools(tmp_path, opener=opener, runner=failed_run)
    assert media_tools.find_installed_media_tools(tmp_path) is None


def test_frozen_missing_media_tools_refuses_path_fallback(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: 'C:/bad/' + name)
    with pytest.raises(media_tools.MediaToolsError, match='FFmpeg'):
        media_tools.resolve_media_tools(root=tmp_path)


def test_source_running_can_use_existing_path(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: 'C:/tools/' + name)
    paths = media_tools.resolve_media_tools(root=tmp_path)
    assert paths.ffmpeg == 'C:/tools/ffmpeg'
    assert paths.ffprobe == 'C:/tools/ffprobe'


def test_source_missing_path_refuses_partial_tools(monkeypatch, tmp_path):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: '/usr/bin/ffmpeg' if name == 'ffmpeg' else None)
    with pytest.raises(media_tools.MediaToolsError, match='ffprobe'):
        media_tools.resolve_media_tools(root=tmp_path)


def test_build_cannot_distribute_ffmpeg_binaries():
    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/windows-build-release.yml').read_text(encoding='utf-8')
    assert 'dist/NpuVideoUpscaler/_internal/media-tools' not in workflow
    assert 'Stage verified FFmpeg' not in workflow
    assert 'install_vendor_media_tools' in workflow
    assert 'gh release create' in workflow


def test_release_installer_invokes_first_run_app_setup():
    installer = (Path(__file__).resolve().parents[1] / 'installer.iss').read_text(encoding='utf-8')
    assert 'Launch NPU Video Upscaler and set up FFmpeg' in installer
    assert 'postinstall' in installer


def test_npu_missing_error_includes_vendor_driver_remediation():
    from npu_upscaler.npu import ModelError, load_npu_model
    class FakeCore:
        available_devices = ['CPU', 'GPU']
    with pytest.raises(ModelError, match='intel.com/content/www/us/en/download/794734'):
        load_npu_model(Path('missing.xml'), core=FakeCore())
