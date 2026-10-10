"""First 60-second NPU preview contracts. FFmpeg integration uses a mock model."""
import json
import shutil
import subprocess
from fractions import Fraction

import numpy as np
import pytest

from npu_upscaler import pipeline
from npu_upscaler.media import (
    VideoInfo, decoder_command, encoder_command, preview_frame_cap,
)
from npu_upscaler.npu import ModelShape


def info(fps: Fraction = Fraction(30000, 1001), frames=2500):
    return VideoInfo(32, 32, fps, 1, frames)


@pytest.mark.parametrize(("rate", "expected"), [
    (Fraction(24), 1440),
    (Fraction(30000, 1001), 1798),
    (Fraction(24000, 1001), 1438),
    (Fraction(2), 120),
])
def test_preview_frame_cap_uses_exact_fraction(rate, expected):
    assert preview_frame_cap(rate) == expected


def test_preview_decoder_exits_after_frame_limit_and_full_mode_does_not():
    full = decoder_command('input.mkv')
    short = decoder_command('input.mkv', max_frames=1798)
    assert '-frames:v' not in full
    assert short[short.index('-frames:v') + 1] == '1798'
    assert short[-1] == 'pipe:1'
    assert '-fps_mode' in short


def test_preview_encoder_cuts_audio_without_changing_full_export():
    full = encoder_command('input.mkv', 'out.mp4', info(), 2)
    preview = encoder_command('input.mkv', 'out.mp4', info(), 2, max_duration=60)
    assert '-t' not in full
    assert preview[preview.index('-t') + 1] == '60'
    assert preview.index('-t') > preview.index('-c:a')
    assert preview[-1] == 'out.mp4'
    assert preview[preview.index('-c:a') + 1] == 'copy'
    assert '1:a?' in preview
    assert '-shortest' not in preview


def test_preview_invalid_limits_are_rejected():
    with pytest.raises(ValueError):
        decoder_command('in.mp4', max_frames=0)
    with pytest.raises(ValueError):
        encoder_command('in.mp4', 'out.mp4', info(), 2, max_duration=0)
    with pytest.raises(ValueError):
        pipeline.preview_limit_seconds(20)


def test_preview_progress_cap_even_when_frame_total_unknown():
    rate = Fraction(30000, 1001)
    assert pipeline.preview_progress_total(VideoInfo(20, 20, rate, 0, None)) == 1798
    assert pipeline.preview_progress_total(VideoInfo(20, 20, rate, 0, 120)) == 120


class FakeModel:
    def __call__(self, x):
        return {'y': np.repeat(np.repeat(x, 2, axis=2), 2, axis=3)}


@pytest.fixture
def prepare(tmp_path, monkeypatch):
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        pytest.skip('FFmpeg tools not available')
    monkeypatch.setattr(pipeline, 'load_npu_model', lambda path: (FakeModel(), ModelShape(24, 32, 2)))

    def create(seconds):
        source = tmp_path / f'src{seconds}.mp4'
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-f', 'lavfi', '-i', f'color=c=blue:s=32x32:r=2:d={seconds}',
                        '-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                        '-c:a', 'aac', str(source)], check=True, capture_output=True)
        xml = tmp_path / 'mock.xml'
        xml.write_text('mock')
        xml.with_suffix('.bin').write_bytes(b'mock')
        return source, xml

    return create


def metadata(path):
    return json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)
    ]))


def test_preview_65_second_source_is_60_seconds_with_audio(prepare, tmp_path):
    source, xml = prepare(65)
    dest = tmp_path / 'preview.mp4'
    values = []
    count = pipeline.run_video(source, xml, dest, preview_seconds=60,
                               progress=lambda current, total: values.append((current, total)))
    assert count == 120
    assert values[-1] == (120, 120)
    probe = metadata(dest)
    video = next(s for s in probe['streams'] if s['codec_type'] == 'video')
    audio = next(s for s in probe['streams'] if s['codec_type'] == 'audio')
    assert video['width'] == 64 and video['height'] == 64
    assert int(video['nb_frames']) == 120
    assert 59.5 <= float(video['duration']) <= 60.0
    assert 59.5 <= float(audio['duration']) <= 60.1
    assert float(probe['format']['duration']) <= 60.1


def test_preview_short_video_is_not_padded(prepare, tmp_path):
    source, xml = prepare(2)
    dest = tmp_path / 'preview_short.mp4'
    count = pipeline.run_video(source, xml, dest, preview_seconds=60)
    assert count == 4
    probe = metadata(dest)
    assert float(probe['format']['duration']) <= 2.1
    assert any(s['codec_type'] == 'audio' for s in probe['streams'])
