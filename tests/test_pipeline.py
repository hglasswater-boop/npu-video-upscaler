from threading import Event

import pytest

from npu_upscaler.pipeline import validate_paths, temporary_output_path, JobCancelled, check_not_cancelled


def test_output_paths_are_validated(tmp_path):
    source = tmp_path / 'source.mp4'
    source.write_bytes(b'video')
    model = tmp_path / 'model.xml'
    model.write_text('IR')
    (tmp_path / 'model.bin').write_bytes(b'weights')
    dest = tmp_path / 'out.mp4'
    validate_paths(source, model, dest)
    with pytest.raises(ValueError):
        validate_paths(source, model, source)
    with pytest.raises(ValueError):
        validate_paths(source, model, tmp_path / 'wrong.mkv')
    (tmp_path / 'model.bin').unlink()
    with pytest.raises(ValueError):
        validate_paths(source, model, dest)


def test_temporary_mp4_is_same_directory(tmp_path):
    dest = tmp_path / 'final.mp4'
    temp = temporary_output_path(dest)
    assert temp.parent == dest.parent
    assert temp.name.endswith('.mp4')
    assert temp != dest
    assert not temp.exists()


def test_cancel_raises():
    flag = Event()
    check_not_cancelled(flag)
    flag.set()
    with pytest.raises(JobCancelled):
        check_not_cancelled(flag)



def test_windows_temporary_lock_release_retries(monkeypatch, tmp_path):
    from pathlib import Path
    from npu_upscaler.pipeline import _remove_temporary

    target = tmp_path / 'locked.mp4'
    target.write_bytes(b'incomplete export')
    original = Path.unlink
    attempts = []

    def intermittent_lock(path, *args, **kwargs):
        if path == target:
            attempts.append(1)
            if len(attempts) < 3:
                raise PermissionError('Windows process still releasing handle')
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, 'unlink', intermittent_lock)
    _remove_temporary(target)
    assert len(attempts) == 3
    assert not target.exists()
