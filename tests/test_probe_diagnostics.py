import json
import subprocess
import sys

import pytest

from npu_upscaler import media
from test_media import probe


@pytest.mark.parametrize('stdout', [None, '', ' ', 'not json', 'null', '[]', '42', '"text"'])
def test_invalid_probe_response_is_actionable(monkeypatch, stdout):
    monkeypatch.setattr(media.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a, 0, stdout, 'probe detail'))
    with pytest.raises(media.MediaError, match='動画情報') as caught:
        media.probe_video('input.mp4')
    assert 'probe detail' in str(caught.value)


@pytest.mark.parametrize('error', [
    subprocess.CalledProcessError(7, ['ffprobe'], stderr='decoder detail'),
    subprocess.TimeoutExpired(['ffprobe'], 30, stderr=b'timeout detail'),
    PermissionError('access denied'), FileNotFoundError('missing'),
])
def test_probe_execution_failure_retains_cause(monkeypatch, error):
    def fail(*a, **k):
        raise error
    monkeypatch.setattr(media.subprocess, 'run', fail)
    with pytest.raises(media.MediaError, match='動画情報') as caught:
        media.probe_video('input.mp4')
    assert caught.value.__cause__ is error
    if getattr(error, 'stderr', None):
        assert 'detail' in str(caught.value)


def test_probe_uses_explicit_utf8_and_timeout(monkeypatch):
    def run(*a, **kwargs):
        assert not kwargs.get('text', False)
        assert 'encoding' not in kwargs
        assert 0 < kwargs['timeout'] <= 60
        return subprocess.CompletedProcess(a, 0, json.dumps(probe()).encode('utf-8'), b'')
    monkeypatch.setattr(media.subprocess, 'run', run)
    assert media.probe_video('input.mp4').width == 33


def test_utf8_child_metadata_survives_windows_cp932_default(monkeypatch):
    # Real child process, not a mock returning None: CP932 cannot decode U+1F600 UTF-8.
    data = probe()
    data['format']['tags'] = {'title': '日本語 😀'}
    payload = json.dumps(data, ensure_ascii=False).encode('utf-8')
    import locale
    monkeypatch.setattr(locale, 'getencoding', lambda: 'cp932')
    real_run = subprocess.run
    def child(args, **kwargs):
        return real_run([sys.executable, '-c',
                         f'import sys; sys.stdout.buffer.write({payload!r})'], **kwargs)
    monkeypatch.setattr(media.subprocess, 'run', child)
    assert media.probe_video('input.mp4').audio_streams == 1


def test_invalid_utf8_is_rejected_in_calling_thread(monkeypatch):
    monkeypatch.setattr(media.subprocess, 'run', lambda *a, **k:
                        subprocess.CompletedProcess(a, 0, b'\xff', b'encoding detail'))
    with pytest.raises(media.MediaError, match='動画情報') as caught:
        media.probe_video('input.mp4')
    assert isinstance(caught.value.__cause__, UnicodeDecodeError)
