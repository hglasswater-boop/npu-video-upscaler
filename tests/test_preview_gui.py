"""Quick preview GUI behavior without starting a conversion or live update request."""
import os
from pathlib import Path

import pytest


@pytest.fixture
def win(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from npu_upscaler import gui
    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(gui.QTimer, 'singleShot', lambda *args: None)
    window = gui.MainWindow()
    yield window
    window.close()


def test_filename_suggestion_tracks_preview_but_never_replaces_manual_output(win, tmp_path):
    win.source.setText(str(tmp_path / 'movie.mkv'))
    assert win.destination.text().endswith('movie_upscaled.mp4')
    win.preview.setChecked(True)
    assert win.destination.text().endswith('movie_upscaled_preview60.mp4')
    win.destination.setText(str(tmp_path / 'my_output.mp4'))
    win.preview.setChecked(False)
    assert win.destination.text().endswith('my_output.mp4')


def test_full_video_is_default_and_preview_worker_passes_duration(monkeypatch, win, tmp_path):
    from npu_upscaler import gui
    assert not win.preview.isChecked()
    assert win.start_btn.text() == 'Start NPU conversion'
    win.preview.setChecked(True)
    assert win.start_btn.text() == 'Start 60s preview'
    observed = {}

    def fake_run_video(source, model, destination, progress, cancel, preview_seconds):
        observed['seconds'] = preview_seconds
        return 3

    monkeypatch.setattr(gui, 'run_video', fake_run_video)
    worker = gui.Worker(tmp_path / 'input.mp4', tmp_path / 'model.xml',
                        tmp_path / 'output.mp4', preview_seconds=60)
    worker.run()
    assert observed['seconds'] == 60
