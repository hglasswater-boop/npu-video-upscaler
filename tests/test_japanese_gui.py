"""All primary desktop actions are Japanese; FFmpeg error remains actionable."""
import pytest


@pytest.fixture
def window(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import npu_upscaler.gui as gui
    app = QApplication.instance() or QApplication([])

    class NoStartTimer:
        @staticmethod
        def singleShot(*args):
            pass

    monkeypatch.setattr(gui, "QTimer", NoStartTimer)
    win = gui.MainWindow()
    yield gui, win
    win.close()


def test_major_labels_in_japanese(window):
    _, win = window
    assert "開発版" in win.windowTitle()
    assert "FFmpeg" in win.media_setup_btn.text()
    assert "ダウンロード" in win.media_setup_btn.text()
    assert "ドライバー" in win.driver_help_btn.text()
    assert "モデル" in win.model_setup_btn.text()
    assert "更新" in win.update_btn.text()
    assert "起動時" in win.auto_update.text()
    assert "先頭60秒" in win.preview.text()
    assert win.start_btn.text() == "NPUで変換を開始"
    win.preview.setChecked(True)
    assert win.start_btn.text() == "先頭60秒を試す"
    assert win.cancel_btn.text() == "キャンセル"


def test_ffmpeg_failure_is_japanese_but_preserves_winerror_diagnostics(monkeypatch, window):
    gui, win = window
    captured = []
    monkeypatch.setattr(gui.QMessageBox, "warning",
                        lambda parent, title, body: captured.append((title, body)))
    win._media_failed("[WinError 5] Access denied at local path")
    assert "失敗" in captured[0][0]
    assert "[WinError 5]" in captured[0][1]
    assert "失敗" in win.status.text()


def test_localized_confirmation_button_labels_are_defined():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "npu_upscaler/gui.py").read_text("utf-8")
    assert 'addButton("はい"' in source
    assert 'addButton("いいえ"' in source
    assert 'addButton("閉じる"' in source
