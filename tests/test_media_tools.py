"""Contract tests for app-private media tools (no downloads, no FFmpeg installation)."""
from pathlib import Path
import sys

import pytest

from npu_upscaler.media import decoder_command, encoder_command, probe_video, VideoInfo
from fractions import Fraction
from npu_upscaler import media_tools


def _bin_pair(directory: Path):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / 'ffmpeg.exe').write_bytes(b'exe')
    (directory / 'ffprobe.exe').write_bytes(b'exe')


def test_frozen_uses_only_pyinstaller_internal_media_tools(monkeypatch, tmp_path):
    base = tmp_path / '_internal'
    _bin_pair(base / 'media-tools')
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(base), raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: '/bad/usr/' + name)
    paths = media_tools.resolve_media_tools()
    assert paths.ffmpeg == str(base / 'media-tools/ffmpeg.exe')
    assert paths.ffprobe == str(base / 'media-tools/ffprobe.exe')


@pytest.mark.parametrize('missing', ['ffmpeg.exe', 'ffprobe.exe'])
def test_frozen_missing_one_tool_never_uses_path(monkeypatch, tmp_path, missing):
    base = tmp_path / '_internal'
    _bin_pair(base / 'media-tools')
    (base / 'media-tools' / missing).unlink()
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(base), raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: 'C:/untrusted/' + name)
    with pytest.raises(media_tools.MediaToolsError, match='installation'):
        media_tools.resolve_media_tools()


def test_unfrozen_resolves_both_from_path(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which',
                        lambda name: 'C:/tools/' + name if name in ('ffmpeg', 'ffprobe') else None)
    paths = media_tools.resolve_media_tools()
    assert paths.ffmpeg == 'C:/tools/ffmpeg'
    assert paths.ffprobe == 'C:/tools/ffprobe'


def test_unfrozen_refuses_incomplete_install(monkeypatch):
    monkeypatch.delattr(sys, 'frozen', raising=False)
    monkeypatch.setattr(media_tools.shutil, 'which', lambda name: '/usr/bin/ffmpeg' if name == 'ffmpeg' else None)
    with pytest.raises(media_tools.MediaToolsError, match='ffprobe'):
        media_tools.resolve_media_tools()


def test_decoder_and_encoder_support_resolved_absolute_executables():
    info = VideoInfo(40, 30, Fraction(30000, 1001), 1, 100)
    dec = decoder_command('in.mkv', ffmpeg_executable='C:/app/media-tools/ffmpeg.exe')
    enc = encoder_command('in.mkv', 'out.mp4', info, 2,
                          ffmpeg_executable='C:/app/media-tools/ffmpeg.exe')
    assert dec[0] == enc[0] == 'C:/app/media-tools/ffmpeg.exe'
    assert dec[-1] == 'pipe:1'
    assert enc[-1] == 'out.mp4'


def test_probe_video_uses_same_ffprobe_executable(monkeypatch, tmp_path):
    observed = []

    def fake_run(argv, **kwargs):
        observed.append(argv)
        class Result:
            stdout = '{"streams":[{"codec_type":"video","width":40,"height":30,"pix_fmt":"yuv420p","r_frame_rate":"24/1","avg_frame_rate":"24/1"}]}'
        return Result()

    monkeypatch.setattr('npu_upscaler.media.subprocess.run', fake_run)
    probe_video(tmp_path / 'x.mp4', ffprobe_executable='C:/app/media-tools/ffprobe.exe')
    assert observed[0][0] == 'C:/app/media-tools/ffprobe.exe'


def test_npu_missing_message_has_official_driver_url():
    from npu_upscaler.npu import ModelError, load_npu_model
    class FakeCore:
        available_devices = ['CPU', 'GPU']
    with pytest.raises(ModelError, match='intel.com/content/www/us/en/download/794734'):
        load_npu_model(Path('irrelevant.xml'), core=FakeCore())


def test_windows_release_workflow_stages_tools_before_installer():
    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/windows-build-release.yml').read_text(encoding='utf-8')
    assert 'dist/NpuVideoUpscaler/_internal/media-tools' in workflow
    assert 'ffprobe.exe' in workflow
    assert 'ffmpeg.exe' in workflow
    assert 'sha256' in workflow.lower()
    assert workflow.index('Stage verified FFmpeg') < workflow.index('Build per-user Inno Setup installer')


def test_public_release_is_gated_on_corresponding_source_verification():
    workflow = (Path(__file__).resolve().parents[1] / '.github/workflows/windows-build-release.yml').read_text(encoding='utf-8')
    assert "vars.FFMPEG_GPL_CORRESPONDING_SOURCE_READY == 'true'" in workflow
    assert "GPL-3.0.txt" in workflow


def test_frozen_binary_check_command_is_a_non_gui_path():
    source = (Path(__file__).resolve().parents[1] / 'launcher.py').read_text(encoding='utf-8')
    assert '"--check-media"' in source
    assert "resolve_media_tools()" in source
