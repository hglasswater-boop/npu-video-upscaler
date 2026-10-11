"""Quick preview GUI behavior without starting a conversion or live update request."""
import os
from pathlib import Path

import pytest


@pytest.fixture
def win(monkeypatch, qt_app):
    monkeypatch.setenv('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from npu_upscaler import gui
    app = QApplication.instance() or QApplication([])
    class NoStartupTimer:
        @staticmethod
        def singleShot(*args):
            pass

    monkeypatch.setattr(gui, 'QTimer', NoStartupTimer)
    window = gui.MainWindow()
    yield window
    window.close()


def test_filename_suggestion_tracks_preview_but_never_replaces_manual_output(win, tmp_path):
    win.source.setText(str(tmp_path / 'movie.mkv'))
    assert win.destination.text().endswith('movie_upscaled_preview60.mp4')
    win.preview.setChecked(False)
    assert win.destination.text().endswith('movie_upscaled.mp4')
    win.destination.setText(str(tmp_path / 'my_output.mp4'))
    win.preview.setChecked(False)
    assert win.destination.text().endswith('my_output.mp4')


def test_preview_is_default_and_preview_worker_passes_duration(monkeypatch, win, tmp_path):
    from npu_upscaler import gui
    assert win.preview.isChecked()
    assert win.start_btn.text() == '先頭60秒を試す'
    win.preview.setChecked(False)
    assert win.start_btn.text() == 'NPUで変換を開始'
    win.preview.setChecked(True)
    assert win.start_btn.text() == '先頭60秒を試す'
    observed = {}

    def fake_run_video(source, model, destination, progress, cancel, preview_seconds, stage_changed,
                       detail_progress, optimize_tiles):
        observed['seconds'] = preview_seconds
        observed['optimize_tiles'] = optimize_tiles
        stage_changed('NPUモデル読み込み')
        return 3

    monkeypatch.setattr(gui, 'run_video', fake_run_video)
    worker = gui.Worker(tmp_path / 'input.mp4', tmp_path / 'model.xml',
                        tmp_path / 'output.mp4', preview_seconds=60)
    stages = []
    worker.stage_changed.connect(stages.append)
    worker.run()
    assert observed['seconds'] == 60
    assert observed['optimize_tiles'] is True
    assert stages == ['NPUモデル読み込み']


def test_worker_emits_japanese_failure_and_log_path(monkeypatch, qt_app, tmp_path):
    from npu_upscaler import gui
    from npu_upscaler.pipeline import VideoJobError
    log = tmp_path / 'diagnosis.log'
    def fail(*a, **k):
        raise VideoJobError('NPUモデル読み込み', log)
    monkeypatch.setattr(gui, 'run_video', fail)
    worker = gui.Worker(tmp_path / 'input.mp4', tmp_path / 'model.xml', tmp_path / 'out.mp4')
    messages = []
    worker.failed.connect(messages.append)
    worker.run()
    assert 'NPUモデル読み込みで失敗しました' in messages[0]
    assert str(log) in messages[0]


def test_partial_frame_progress_is_visible_and_not_overwritten_by_stage(win, monkeypatch):
    from npu_upscaler import gui
    clock = [0.0]
    monkeypatch.setattr(gui.time, 'monotonic', lambda: clock[0])
    win._started_at = 0.0
    win.update_detailed_progress(0, 1798, 0, 2040)
    clock[0] = 10.0
    win.update_detailed_progress(0, 1798, 1020, 2040)
    assert '0.028%' in win.progress_label.text()
    assert '0 / 約1798' in win.progress_label.text()
    assert '1020 / 2040' in win.progress_label.text()
    assert '経過：10秒' in win.progress_label.text()
    assert '残り：計算中' in win.progress_label.text()
    text = win.progress_label.text()
    win.status.setText('NPU推論中…')
    assert win.progress_label.text() == text
    assert win.bar.value() > 0


def test_eta_waits_for_one_frame_and_completion_waits_for_output_commit(win, monkeypatch):
    from npu_upscaler import gui
    clock = [0.0]
    monkeypatch.setattr(gui.time, 'monotonic', lambda: clock[0])
    win._started_at = 0.0
    win.update_detailed_progress(0, 10, 0, 4)
    clock[0] = 5.0
    win.update_detailed_progress(1, 10, 0, 0)
    assert '残り目安：45秒' in win.progress_label.text()
    win.update_detailed_progress(10, 10, 0, 0)
    assert win.bar.value() < win.bar.maximum()
    win.finish('完了：10 フレーム')
    assert win.bar.value() == win.bar.maximum()
    assert '100.000%' in win.progress_label.text()


def test_unknown_total_and_cancel_keep_honest_progress(win, monkeypatch):
    from npu_upscaler import gui
    monkeypatch.setattr(gui.time, 'monotonic', lambda: 20.0)
    win._started_at = 0.0
    win.update_detailed_progress(2, 0, 3, 8)
    assert '2 フレーム' in win.progress_label.text()
    assert '残り：計算中' in win.progress_label.text()
    assert '%' not in win.progress_label.text()
    text = win.progress_label.text()
    win.finish('キャンセルしました')
    assert win.progress_label.text() == text
    assert win.bar.maximum() > 0


def test_worker_throttles_tile_signals_but_delivers_first_and_last(monkeypatch, qt_app, tmp_path):
    from npu_upscaler import gui
    clock = [0.0]
    monkeypatch.setattr(gui.time, 'monotonic', lambda: clock[0])
    def fake(*args, detail_progress, **kwargs):
        for tile in range(101):
            clock[0] = tile / 100
            detail_progress(0, 5, tile, 100)
        return 1
    monkeypatch.setattr(gui, 'run_video', fake)
    worker = gui.Worker(tmp_path/'in.mp4', tmp_path/'model.xml', tmp_path/'out.mp4')
    values = []
    worker.detail_progress_changed.connect(lambda *args: values.append(args))
    worker.run()
    assert 3 <= len(values) <= 7
    assert values[0] == (0, 5, 0, 100)
    assert values[-1] == (0, 5, 100, 100)
