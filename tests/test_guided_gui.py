"""Primary screen is a guided compact Japanese workflow."""
from pathlib import Path
import pytest


@pytest.fixture
def screen(monkeypatch):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import npu_upscaler.gui as gui

    app = QApplication.instance() or QApplication([])

    class TimerDisabled:
        @staticmethod
        def singleShot(*args, **kwargs):
            pass
    monkeypatch.setattr(gui, "QTimer", TimerDisabled)
    monkeypatch.setattr(gui, "find_installed_media_tools", lambda: None)
    monkeypatch.setattr(gui, "find_prepared_model", lambda: None)
    win = gui.MainWindow()
    yield win
    win.close()


def test_compact_guided_sections(screen):
    from PySide6.QtWidgets import QGroupBox
    sections = [g.title() for g in screen.findChildren(QGroupBox)]
    assert "① 動画を選ぶ" in sections
    assert "② 初回準備" in sections
    assert "③ 変換する" in sections
    assert screen.maximumWidth() <= 840
    assert screen.status.wordWrap()
    assert screen.guidance.wordWrap()
    assert not screen.advanced_area.isVisible()


def test_user_knows_what_to_do_next(screen, tmp_path):
    assert "動画" in screen.guidance.text()
    screen.source.setText(str(tmp_path / "example.mp4"))
    assert "FFmpeg" in screen.guidance.text()
    assert "未設定" in screen.media_state.text()
    screen._media_ready_known = True
    screen._refresh_guidance()
    assert "AIモデル" in screen.guidance.text()
    screen.model.setText(str(tmp_path / "model.xml"))
    assert "先頭60秒" in screen.guidance.text()
    screen.preview.setChecked(True)
    assert "先頭60秒" in screen.start_btn.text()
    screen.advanced_btn.setChecked(True)
    assert not screen.advanced_area.isHidden()


def test_long_errors_can_be_inspected_without_expanding_main_window(screen):
    assert screen.status.wordWrap()
    assert screen.maximumWidth() <= 840
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / "npu_upscaler/gui.py").read_text("utf-8")
    assert "setDetailedText(message)" in source
    assert "setMaximumWidth(600)" in source
