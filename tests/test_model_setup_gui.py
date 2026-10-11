"""Pre-verified model path is suggested at first GUI launch."""
import pytest


def test_installed_model_is_selected_at_gui_startup(monkeypatch, tmp_path, qt_app):
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


def test_large_tile_setting_is_persisted_and_passed_to_worker(monkeypatch,tmp_path,qt_app):
    from npu_upscaler import gui
    values={}
    class Settings:
        def value(self,key,default,type=None):
            return values.get(key,default)
        def setValue(self,key,value):
            values[key]=value
    monkeypatch.setattr(gui,'QSettings',lambda *args:Settings())
    monkeypatch.setattr(gui,'QTimer',type('Timer',(),{'singleShot':staticmethod(lambda *a:None)}))
    monkeypatch.setattr(gui,'resolve_media_tools',lambda:object())
    monkeypatch.setattr(gui.Worker,'start',lambda self:None)
    window=gui.MainWindow()
    try:
        assert window.optimize_tiles.isChecked()
        window.optimize_tiles.setChecked(False)
        assert values['optimizeNpuTiles'] is False
        window.source.setText(str(tmp_path/'clip.mp4'))
        window.model.setText(str(tmp_path/'model.xml'))
        window.start_job()
        assert window.worker.optimize_tiles is False
    finally:
        window.close()
    second=gui.MainWindow()
    try:
        assert not second.optimize_tiles.isChecked()
    finally:
        second.close()
