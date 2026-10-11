"""Primary screen is a guided compact Japanese workflow."""
from pathlib import Path
import pytest


@pytest.fixture
def screen(monkeypatch, qt_app):
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


def drop_video(screen, mime):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication
    actions = Qt.DropAction.CopyAction | Qt.DropAction.MoveAction
    enter = QDragEnterEvent(QPoint(20, 20), actions, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(screen, enter)
    drop = QDropEvent(QPointF(20, 20), actions, mime,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(screen, drop)
    return enter.isAccepted(), drop.isAccepted(), drop.dropAction()


def file_mime(*paths):
    from PySide6.QtCore import QMimeData, QUrl
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path)) for path in paths])
    return mime


@pytest.mark.parametrize("suffix", [".mp4", ".MKV"])
def test_drop_selects_video_and_suggests_preview_without_starting(screen, tmp_path, suffix):
    from PySide6.QtCore import Qt
    video = tmp_path / ("日本語 動画" + suffix)
    video.touch()
    entered, dropped, action = drop_video(screen, file_mime(video))
    assert entered and dropped
    assert action == Qt.DropAction.CopyAction
    assert screen.source.text() == str(video)
    assert Path(screen.destination.text()).name == "日本語 動画_upscaled_preview60.mp4"
    assert screen.preview.isChecked()
    assert screen.worker is None
    assert video.exists()


def test_drop_preserves_manual_destination_and_model(screen, tmp_path):
    video = tmp_path / "input.mp4"
    video.touch()
    screen.destination.setText(str(tmp_path / "chosen.mp4"))
    screen.model.setText(str(tmp_path / "model.xml"))
    drop_video(screen, file_mime(video))
    assert screen.destination.text() == str(tmp_path / "chosen.mp4")
    assert screen.model.text() == str(tmp_path / "model.xml")
    assert not screen.source.acceptDrops()
    assert not screen.destination.acceptDrops()
    assert not screen.model.acceptDrops()


@pytest.mark.parametrize("kind", ["multiple", "folder", "missing", "other", "web", "text"])
def test_invalid_drop_keeps_selection(screen, tmp_path, kind):
    from PySide6.QtCore import QMimeData, QUrl
    video = tmp_path / "input.mp4"
    video.touch()
    other = tmp_path / "other.txt"
    other.touch()
    mime = {"multiple": file_mime(video, other), "folder": file_mime(tmp_path),
            "missing": file_mime(tmp_path / "missing.mp4"), "other": file_mime(other),
            "web": QMimeData(), "text": QMimeData()}[kind]
    if kind == "web":
        mime.setUrls([QUrl("https://example.com/video.mp4")])
    if kind == "text":
        mime.setText(str(video))
    screen.source.setText(str(video))
    original_output = screen.destination.text()
    entered, dropped, _ = drop_video(screen, mime)
    assert not entered and not dropped
    assert screen.source.text() == str(video)
    assert screen.destination.text() == original_output


def test_drop_during_conversion_is_rejected_even_after_drag_enter(screen, tmp_path):
    from PySide6.QtCore import QPoint, QPointF, Qt
    from PySide6.QtGui import QDragEnterEvent, QDropEvent
    from PySide6.QtWidgets import QApplication
    from types import SimpleNamespace
    video = tmp_path / "input.mp4"
    video.touch()
    mime = file_mime(video)
    enter = QDragEnterEvent(QPoint(20, 20), Qt.DropAction.CopyAction, mime,
                           Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(screen, enter)
    assert enter.isAccepted()
    screen.worker = SimpleNamespace(isRunning=lambda: True)
    drop = QDropEvent(QPointF(20, 20), Qt.DropAction.CopyAction, mime,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    QApplication.sendEvent(screen, drop)
    assert not drop.isAccepted()
    assert not screen.source.text()
    entered2, _, _ = drop_video(screen, mime)
    assert not entered2
    screen.worker = None
