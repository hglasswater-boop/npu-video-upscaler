"""Selected accelerator is preserved through model setup and the compact GUI."""
import pytest


def test_first_run_model_install_validates_on_gpu(monkeypatch, tmp_path):
    import npu_upscaler.npu as npu
    from tests.test_model_packages import sample_zip
    from npu_upscaler.model_packages import install_model_zip
    called = []
    monkeypatch.setattr(npu, 'load_model', lambda path, device: called.append(device))
    chosen = install_model_zip(sample_zip(tmp_path), tmp_path / 'Models')
    assert chosen.is_file()
    assert called == ['GPU']


def test_explicit_model_install_uses_npu_when_selected(monkeypatch, tmp_path):
    import npu_upscaler.npu as npu
    from tests.test_model_packages import sample_zip
    from npu_upscaler.model_packages import install_model_zip
    called = []
    monkeypatch.setattr(npu, 'load_model', lambda path, device: called.append(device))
    install_model_zip(sample_zip(tmp_path), tmp_path / 'Models', device='NPU')
    assert called == ['NPU']


def test_gpu_mode_is_visible_default_and_persisted(monkeypatch, qt_app):
    from npu_upscaler import gui
    from PySide6.QtWidgets import QApplication
    values = {}
    class Settings:
        def value(self, key, default, type=None):
            return values.get(key, default)
        def setValue(self, key, value):
            values[key] = value
    monkeypatch.setattr(gui, 'QSettings', lambda *a: Settings())
    monkeypatch.setattr(gui, 'QTimer', type('Timer', (), {'singleShot': staticmethod(lambda *a: None)}))
    win = gui.MainWindow()
    try:
        assert win.device_combo.currentData() == 'GPU'
        win.preview.setChecked(False)
        assert win.start_btn.text() == 'GPUで変換を開始'
        win.device_combo.setCurrentIndex(1)
        assert values['inferenceDevice'] == 'NPU'
        assert win.start_btn.text() == 'NPUで変換を開始'
    finally:
        win.close()
    second = gui.MainWindow()
    try:
        assert second.device_combo.currentData() == 'NPU'
    finally:
        second.close()


def test_worker_propagates_selected_gpu(monkeypatch, tmp_path, qt_app):
    from npu_upscaler import gui
    observed = []
    def fake_run(*args, device, **kwargs):
        observed.append(device)
        return 1
    monkeypatch.setattr(gui, 'run_video', fake_run)
    worker = gui.Worker(tmp_path/'v.mp4', tmp_path/'model.xml', tmp_path/'out.mp4')
    worker.run()
    assert observed == ['GPU']
