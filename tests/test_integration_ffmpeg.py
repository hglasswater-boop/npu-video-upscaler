"""Real FFmpeg stream-copy smoke test; NPU is stubbed because CI has no NPU."""

import json
from pathlib import Path
import shutil
import subprocess
from threading import Event

import numpy as np
import pytest

from npu_upscaler import pipeline
from npu_upscaler.npu import ModelShape


pytestmark = pytest.mark.skipif(
    not shutil.which('ffmpeg') or not shutil.which('ffprobe'),
    reason='FFmpeg and ffprobe required for integration test',
)


class NearestNeighborModel:
    def __call__(self, tensor):
        return {'output': np.repeat(np.repeat(tensor, 2, axis=2), 2, axis=3)}


def setup_input(tmp_path):
    source = tmp_path / 'sample.mp4'
    args = ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
            '-f', 'lavfi', '-i', 'testsrc=size=64x48:rate=24:duration=1',
            '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
            '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', str(source)]
    try:
        subprocess.run(args, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        pytest.skip(f'FFmpeg test fixture encoders unavailable: {exc.stderr!r}')
    xml = tmp_path / 'test.xml'
    xml.write_text('fake model')
    xml.with_suffix('.bin').write_bytes(b'fake weights')
    return source, xml


def test_real_ffmpeg_audio_is_copied_and_resolution_doubled(monkeypatch, tmp_path):
    source, xml = setup_input(tmp_path)
    monkeypatch.setattr(pipeline, 'load_model', lambda path, **kwargs: (NearestNeighborModel(), ModelShape(24, 32, 2)))
    dest = tmp_path / 'export.mp4'
    detailed = []
    frames = pipeline.run_video(source, xml, dest,
                                detail_progress=lambda *args: detailed.append(args))
    assert frames == 24
    assert detailed[0] == (0, 24, 0, 0)
    tiles = detailed[1][3]
    assert tiles > 0
    assert detailed[-1] == (23, 24, tiles, tiles)
    assert all(0 <= done < 24 and total == 24 and 0 <= tile <= count
               for done, total, tile, count in detailed)
    output = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(dest)
    ]))
    video, audio = [s for s in output['streams'] if s['codec_type'] in ('video', 'audio')]
    assert (video['width'], video['height']) == (128, 96)
    assert video['r_frame_rate'] == '24/1'
    assert audio['codec_name'] == 'aac'


def test_cancel_preserves_existing_destination(monkeypatch, tmp_path):
    source, xml = setup_input(tmp_path)
    monkeypatch.setattr(pipeline, 'load_model', lambda path, **kwargs: (NearestNeighborModel(), ModelShape(24, 32, 2)))
    dest = tmp_path / 'export.mp4'
    dest.write_bytes(b'old content')
    cancel = Event()

    def cancel_after_first(done, total):
        cancel.set()

    with pytest.raises(pipeline.JobCancelled):
        pipeline.run_video(source, xml, dest, cancel=cancel, progress=cancel_after_first)
    assert dest.read_bytes() == b'old content'
    assert not list(tmp_path.glob('.export-*.mp4'))


def test_real_ffprobe_utf8_filename_and_metadata(monkeypatch, tmp_path):
    from npu_upscaler.media import probe_video
    source, _ = setup_input(tmp_path)
    unicode_source = tmp_path / '日本語😀.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(source),
                    '-c', 'copy', '-metadata', 'title=日本語😀', str(unicode_source)],
                   capture_output=True, check=True)
    import locale
    monkeypatch.setattr(locale, 'getencoding', lambda: 'cp932')
    info = probe_video(unicode_source)
    assert (info.width, info.height, info.audio_streams) == (64, 48, 1)


def test_timestamp_gap_is_filled_before_rawvideo_loses_timing(monkeypatch, tmp_path):
    """Isolate time resampling; metadata admission has separate boundary tests."""
    from fractions import Fraction
    from npu_upscaler.media import VideoInfo
    source = tmp_path / 'timestamp-gap.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y',
                    '-f', 'lavfi', '-i', 'testsrc=size=32x32:rate=2:duration=2',
                    '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2.5',
                    '-vf', 'setpts=PTS+0.5/TB*floor(N/2)',
                    '-fps_mode', 'passthrough', '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                    '-c:a', 'aac', str(source)], check=True, capture_output=True)
    # This small synthetic gap fixture isn't a nominal-CFR admission fixture.
    # Supply the selected rate to verify the pipeline's timestamp handling.
    monkeypatch.setattr(pipeline, 'probe_video', lambda *a, **k:
                        VideoInfo(32, 32, Fraction(2), 1, 5))
    monkeypatch.setattr(pipeline, 'load_model', lambda path, **kwargs:
                        (NearestNeighborModel(), ModelShape(24, 32, 2)))
    xml = tmp_path / 'model.xml'
    xml.write_text('fake model')
    xml.with_suffix('.bin').write_bytes(b'fake weights')
    dest = tmp_path / 'normalized.mp4'
    assert pipeline.run_video(source, xml, dest) == 5
    output = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(dest)]))
    video = next(s for s in output['streams'] if s['codec_type'] == 'video')
    assert video['r_frame_rate'] == '2/1'
    assert float(video['duration']) == 2.5

    def audio_hashes(path):
        data = json.loads(subprocess.check_output([
            'ffprobe', '-v', 'error', '-select_streams', 'a:0', '-show_packets',
            '-show_data_hash', 'sha256', '-of', 'json', str(path)]))
        return [p['data_hash'] for p in data['packets']]
    assert audio_hashes(dest) == audio_hashes(source)
