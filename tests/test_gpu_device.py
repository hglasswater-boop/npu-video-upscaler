"""GPU default and explicit NPU selection; OpenVINO must not silently fall back."""
from pathlib import Path
from types import SimpleNamespace
import pytest

from npu_upscaler.npu import load_model, ModelError


class FakeCompiled:
    def input(self, i):
        return SimpleNamespace(shape=(1, 3, 48, 48))

    def output(self, i):
        return SimpleNamespace(shape=(1, 3, 96, 96))


class FakeCore:
    def __init__(self, devices=('GPU', 'NPU', 'CPU')):
        self.available_devices = list(devices)
        self.calls = []

    def read_model(self, path):
        return SimpleNamespace(reshape=lambda shape: None)

    def compile_model(self, model, device, config=None):
        self.calls.append((device, config))
        return FakeCompiled()


def test_gpu_is_default_even_if_npu_is_present(tmp_path):
    core = FakeCore()
    compiled, shape = load_model(tmp_path / 'ir.xml', core=core)
    assert shape.scale == 2
    assert core.calls[0][0] == 'GPU'


def test_explicit_npu_mode_remains_available(tmp_path):
    core = FakeCore()
    load_model(tmp_path / 'ir.xml', core=core, device='NPU')
    assert [dev for dev, _ in core.calls] == ['NPU']


def test_missing_gpu_is_actionable_and_never_falls_back(tmp_path):
    core = FakeCore(devices=('NPU', 'CPU'))
    with pytest.raises(ModelError, match='GPU'):
        load_model(tmp_path / 'ir.xml', core=core)
    assert core.calls == []


def test_gpu_compile_error_never_retries_other_device(tmp_path):
    core = FakeCore()
    def fail(model, device, config=None):
        core.calls.append((device, config))
        raise RuntimeError('unsupported GPU layer')
    core.compile_model = fail
    with pytest.raises(ModelError, match='GPU'):
        load_model(tmp_path / 'ir.xml', core=core)
    assert [dev for dev, _ in core.calls] == ['GPU']


@pytest.mark.parametrize('device', ['CPU', 'AUTO', 'MULTI:GPU,NPU', '', None])
def test_cpu_and_automatic_device_modes_are_not_permitted(tmp_path, device):
    core = FakeCore()
    with pytest.raises(ModelError):
        load_model(tmp_path / 'ir.xml', core=core, device=device)
    assert core.calls == []


def test_gpu_stock_model_uses_128px_tiles_without_editing_cached_ir(monkeypatch, tmp_path):
    import npu_upscaler.npu as npu
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setattr(npu, 'is_packaged_bsrgan', lambda path: True)
    xml = tmp_path / 'BSRGANx2.xml'
    xml.write_text('keep')
    shapes = []
    core = FakeCore()
    def read(path):
        return SimpleNamespace(reshape=lambda size: shapes.append(size))
    core.read_model = read
    # Shape is returned by fake compiled model; verify reshape request separately.
    load_model(xml, core=core, device='GPU', optimize_tiles=True)
    assert shapes == [[1, 3, 128, 128]]
    assert core.calls[0][0] == 'GPU'
    assert xml.read_text() == 'keep'
