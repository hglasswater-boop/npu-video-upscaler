import numpy as np
import pytest

from npu_upscaler.npu import ModelError, ModelShape, validate_shape, load_npu_model, upscale_frame, UpscaleCancelled


def test_valid_shape_4x_and_core_dimensions():
    shape = validate_shape([1, 3, 24, 32], [1, 3, 96, 128])
    assert shape == ModelShape(tile_height=24, tile_width=32, scale=4)
    assert (shape.core_height, shape.core_width) == (8, 16)


@pytest.mark.parametrize("inp,out", [
    ([1, 3, -1, 32], [1, 3, 96, 128]),
    ([1, 1, 24, 24], [1, 3, 96, 96]),
    ([1, 3, 16, 24], [1, 3, 64, 96]),
    ([1, 3, 24, 24], [1, 3, 72, 72]),
])
def test_unsupported_model_shapes(inp, out):
    with pytest.raises(ModelError):
        validate_shape(inp, out)


def fake_inference(tile):
    return np.repeat(np.repeat(tile, 4, axis=2), 4, axis=3)


def test_tiles_handle_odd_dimensions_with_exact_pixels():
    rng = np.random.default_rng(12)
    frame = rng.integers(0, 256, size=(19, 35, 3), dtype=np.uint8)
    result = upscale_frame(frame, ModelShape(24, 32, 4), fake_inference)
    expected = np.repeat(np.repeat(frame, 4, axis=0), 4, axis=1)
    assert result.shape == (76, 140, 3)
    assert np.max(np.abs(result.astype('int16') - expected.astype('int16'))) <= 1


def test_tiles_cancel_before_inference():
    with pytest.raises(UpscaleCancelled):
        upscale_frame(np.zeros((18, 34, 3), dtype=np.uint8), ModelShape(24, 32, 4), fake_inference, lambda: True)


def test_tile_progress_counts_real_completed_tiles_without_changing_pixels():
    frame = np.arange(19 * 35 * 3, dtype=np.uint8).reshape(19, 35, 3)
    values = []
    result = upscale_frame(frame, ModelShape(24, 32, 4), fake_inference,
                           tile_progress=lambda done, total: values.append((done, total)))
    assert values == [(i, 9) for i in range(10)]
    assert np.array_equal(result, np.repeat(np.repeat(frame, 4, axis=0), 4, axis=1))


class FakeCore:
    available_devices = ["CPU", "NPU"]

    def read_model(self, path):
        self.path = path
        return "ir"

    def compile_model(self, model, device_name):
        self.compiled_args = (model, device_name)
        return FakeCompiled()


class FakePort:
    shape = [1, 3, 24, 32]


class FakeOutput:
    shape = [1, 3, 96, 128]


class FakeCompiled:
    def input(self, index):
        return FakePort()

    def output(self, index):
        return FakeOutput()


def test_core_compiles_exclusively_to_npu(tmp_path):
    xml = tmp_path / 'demo.xml'
    xml.write_text('not examined by fake')
    core = FakeCore()
    compiled, shape = load_npu_model(xml, core=core)
    assert core.compiled_args == ('ir', 'NPU')
    assert compiled is not None and shape.scale == 4


def test_missing_npu_never_falls_back(tmp_path):
    xml = tmp_path / 'demo.xml'
    xml.write_text('placeholder')
    core = FakeCore()
    core.available_devices = ['CPU', 'GPU']
    with pytest.raises(ModelError, match='NPU'):
        load_npu_model(xml, core=core)
    assert not hasattr(core, 'compiled_args')


class ReshapableModel:
    def __init__(self):
        self.input_shape = [1,3,48,48]
        self.output_shape = [1,3,96,96]

    def input(self, index):
        from types import SimpleNamespace
        return SimpleNamespace(shape=self.input_shape)

    def output(self, index):
        from types import SimpleNamespace
        return SimpleNamespace(shape=self.output_shape)

    def reshape(self, shape):
        self.input_shape = shape
        self.output_shape = [1,3,shape[2]*2,shape[3]*2]


class ReshapeCore:
    available_devices = ['NPU']

    def __init__(self, fail=False):
        self.ir = ReshapableModel()
        self.calls = []
        self.fail = fail

    def read_model(self, path):
        return self.ir

    def compile_model(self, ir, device, config=None):
        self.calls.append((device,config))
        if self.fail:
            raise RuntimeError('128px compile failed')
        return ir


def test_verified_stock_model_uses_larger_static_npu_tiles_and_cache(monkeypatch,tmp_path):
    from npu_upscaler import npu
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    monkeypatch.setattr(npu,'is_packaged_bsrgan',lambda path:True)
    xml=tmp_path/'BSRGANx2.xml'
    xml.write_bytes(b'unchanged model')
    core=ReshapeCore()
    _,shape=load_npu_model(xml,core=core,optimize_tiles=True)
    assert shape == ModelShape(128,128,2)
    assert core.calls[0][0] == 'NPU'
    config=core.calls[0][1]
    assert config['PERFORMANCE_HINT'] == 'LATENCY'
    from pathlib import Path
    cache=Path(config['CACHE_DIR'])
    assert cache.is_dir() and tmp_path in cache.parents
    assert xml.read_bytes() == b'unchanged model'


def test_optimization_can_be_disabled_and_external_models_keep_original_shape(monkeypatch,tmp_path):
    from npu_upscaler import npu
    for packaged,optimize in [(True,False),(False,True)]:
        monkeypatch.setattr(npu,'is_packaged_bsrgan',lambda path:packaged)
        core=ReshapeCore()
        _,shape=load_npu_model(tmp_path/'model.xml',core=core,optimize_tiles=optimize)
        assert shape == ModelShape(48,48,2)
        assert core.calls == [('NPU',None)]


def test_larger_tile_failure_does_not_retry_on_any_device(monkeypatch,tmp_path):
    from npu_upscaler import npu
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    monkeypatch.setattr(npu,'is_packaged_bsrgan',lambda path:True)
    core=ReshapeCore(fail=True)
    with pytest.raises(ModelError,match='128px compile failed'):
        load_npu_model(tmp_path/'model.xml',core=core,optimize_tiles=True)
    assert [device for device,_ in core.calls] == ['NPU']
