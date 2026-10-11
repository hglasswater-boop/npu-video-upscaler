import json
from pathlib import Path
from types import SimpleNamespace
from threading import Event

import pytest

from npu_upscaler import pipeline


def inputs(tmp_path):
    source, model, dest = [tmp_path / s for s in ('private-video.mp4', 'private-model.xml', 'private-out.mp4')]
    source.write_bytes(b'original')
    model.write_text('IR')
    model.with_suffix('.bin').write_bytes(b'weights')
    dest.write_bytes(b'previous export')
    return source, model, dest


@pytest.mark.parametrize(('target', 'stage'), [
    ('validate_paths', '入力検査'), ('resolve_media_tools', 'FFmpeg準備'),
    ('probe_video', '動画情報解析'), ('load_model', 'GPUモデル読み込み'),
    ('temporary_output_path', '変換準備'),
])
def test_job_logs_exact_stage_traceback_and_preserves_output(monkeypatch, tmp_path, target, stage):
    paths = inputs(tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setattr(pipeline, 'resolve_media_tools', lambda: SimpleNamespace(ffprobe='ffprobe', ffmpeg='ffmpeg'))
    monkeypatch.setattr(pipeline, 'probe_video', lambda *a, **k: SimpleNamespace(
        fps=24, total_frames=120, width=640, height=360))
    monkeypatch.setattr(pipeline, 'load_model', lambda *a, **k: (None, None))
    def fail(*a, **k):
        try:
            json.loads(None)
        except TypeError as exc:
            raise RuntimeError(f'failure at {paths[0]} and {paths[1]}') from exc
    monkeypatch.setattr(pipeline, target, fail)
    stages = []
    with pytest.raises(pipeline.VideoJobError) as caught:
        pipeline.run_video(*paths, preview_seconds=60, stage_changed=stages.append)
    error = caught.value
    assert error.stage == stage and stages[-1] == stage
    assert error.__cause__.__cause__.__class__ is TypeError
    log = error.log_path.read_text(encoding='utf-8')
    assert stage in log and 'NoneType' in log and 'fail' in log
    assert 'test_job_diagnostics.py' in log and 'preview_seconds=60' in log
    assert all(str(p) not in log and p.name not in log for p in paths)
    assert 'previous export' == paths[2].read_text()


def test_log_failure_does_not_replace_original_exception(monkeypatch, tmp_path):
    paths = inputs(tmp_path)
    blocked = tmp_path / 'blocked'
    blocked.write_text('file instead of directory')
    monkeypatch.setenv('LOCALAPPDATA', str(blocked))
    with pytest.raises(pipeline.VideoJobError) as caught:
        pipeline.run_video(paths[0], paths[1], paths[0])
    assert isinstance(caught.value.__cause__, ValueError)
    assert caught.value.log_path is None
    assert 'ログを保存できません' in str(caught.value)


def test_cancellation_is_not_reported_as_failure(monkeypatch, tmp_path):
    paths = inputs(tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    monkeypatch.setattr(pipeline, 'resolve_media_tools', lambda: None)
    flag = Event()
    flag.set()
    with pytest.raises(pipeline.JobCancelled):
        pipeline.run_video(*paths, cancel=flag)
    assert not list(tmp_path.rglob('*.log'))


@pytest.mark.parametrize(('width', 'height', 'enabled', 'expected'), [
    (1920,1080,True,True), (640,360,False,False),
    (64,48,True,False), (320,180,True,False), (256,256,True,True),
])
def test_pipeline_optimizes_only_enabled_large_video(monkeypatch,tmp_path,width,height,enabled,expected):
    paths=inputs(tmp_path)
    monkeypatch.setattr(pipeline,'resolve_media_tools',lambda:SimpleNamespace(ffprobe='unused'))
    monkeypatch.setattr(pipeline,'probe_video',lambda *a,**k:SimpleNamespace(
        fps=24,total_frames=120,width=width,height=height))
    calls=[]
    def compiled(path,*,optimize_tiles,device):
        assert device == 'GPU'
        calls.append(optimize_tiles)
        raise RuntimeError('stop before media subprocesses')
    monkeypatch.setattr(pipeline,'load_model',compiled)
    with pytest.raises(pipeline.VideoJobError,match='GPUモデル読み込み'):
        pipeline.run_video(*paths,optimize_tiles=enabled)
    assert calls == [expected]
    assert paths[2].read_bytes() == b'previous export'


@pytest.mark.parametrize('device', ['GPU', 'NPU'])
def test_failure_log_records_requested_device_not_hardcoded_npu(monkeypatch, tmp_path, device):
    paths = inputs(tmp_path)
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path / 'local'))
    def fail_setup():
        raise RuntimeError('diagnostic failure')
    monkeypatch.setattr(pipeline, 'resolve_media_tools', fail_setup)
    with pytest.raises(pipeline.VideoJobError) as caught:
        pipeline.run_video(*paths, device=device)
    log = caught.value.log_path.read_text(encoding='utf-8')
    assert f'inference_device={device}' in log
    assert (('inference_device=NPU' in log) == (device == 'NPU'))
