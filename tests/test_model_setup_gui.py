"""Pre-verified model path is suggested at first GUI launch."""
import pytest


def test_installed_model_is_selected_at_gui_startup(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    import npu_upscaler.gui as gui
    app = QApplication.instance() or QApplication([])
    ir = tmp_path / "BSRGANx2.xml"
    ir.write_text("mock")
    monkeypatch.setattr(gui, "find_prepared_model", lambda: ir)
    class NoStartupTimer:
        @staticmethod
        def singleShot(*_args):
            pass
    monkeypatch.setattr(gui, "QTimer", NoStartupTimer)
    window = gui.MainWindow()
    try:
        assert window.model.text() == str(ir)
        assert window.model_setup_btn.text() == "モデルZIPをインストール"
        window._model_ready(str(ir))
        assert window.model.text() == str(ir)
    finally:
        window.close()
