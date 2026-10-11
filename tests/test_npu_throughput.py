"""Bounded async NPU contract; request execution is simulated, not hardware."""
import numpy as np
import pytest

from npu_upscaler import npu


class Tensor:
    def __init__(self, shape):
        self.data = np.empty(shape, dtype=np.float32)


class Requests:
    def __init__(self, optimal=4, fail_on=None, fail_start_on=None):
        self.optimal = optimal
        self.fail_on = fail_on
        self.fail_start_on = fail_start_on
        self.requests = []
        self.running = 0
        self.maximum_running = 0
        self.starts = 0

    def get_property(self, name):
        assert name == 'OPTIMAL_NUMBER_OF_INFER_REQUESTS'
        return self.optimal

    def create_infer_request(self):
        req = Request(self)
        self.requests.append(req)
        return req


class Request:
    def __init__(self, owner):
        self.owner = owner
        self.input = Tensor((1,3,24,32))
        self.output = Tensor((1,3,96,128))
        self.running = False
        self.waits = 0

    def get_input_tensor(self):
        assert not self.running, 'Input reused while an inference is pending'
        return self.input

    def get_output_tensor(self):
        assert not self.running
        return self.output

    def start_async(self):
        assert not self.running
        self.running = True
        self.owner.running += 1
        self.owner.starts += 1
        self.number = self.owner.starts
        self.owner.maximum_running = max(self.owner.maximum_running, self.owner.running)
        if self.number == self.owner.fail_start_on:
            raise RuntimeError('NPU launch outcome unknown')

    def wait(self):
        self.waits += 1
        if not self.running:
            return
        self.running = False
        self.owner.running -= 1
        if self.number == self.owner.fail_on:
            raise RuntimeError('NPU request failed')
        self.output.data[:] = np.repeat(np.repeat(self.input.data,4,axis=2),4,axis=3)


def frame():
    return np.random.default_rng(37).integers(0,256,size=(19,35,3),dtype=np.uint8)


def run(pool, **kwargs):
    return npu.upscale_frame(frame(), npu.ModelShape(24,32,4), None,
                             infer_tiles=pool.infer_tiles, **kwargs)


def test_async_pixels_match_serial_and_borrowed_outputs_are_not_reused_early():
    compiled = Requests()
    pool = npu.NpuTilePool(compiled)
    progress = []
    actual = run(pool, tile_progress=lambda *value:progress.append(value))
    expected = np.repeat(np.repeat(frame(),4,axis=0),4,axis=1)
    assert np.array_equal(actual, expected)
    assert progress == [(i,9) for i in range(10)]
    assert compiled.maximum_running == 4
    assert compiled.running == 0
    assert len(compiled.requests) == 4
    assert np.array_equal(run(pool),expected)
    assert len(compiled.requests) == 4, 'Reuse the same requests across frames'


@pytest.mark.parametrize('recommended,expected', [(1,1),(2,2),(8,4)])
def test_request_memory_is_bounded(recommended, expected):
    compiled = Requests(optimal=recommended)
    run(npu.NpuTilePool(compiled))
    assert len(compiled.requests) == expected
    assert compiled.maximum_running == expected


def test_cancel_stops_new_submissions_and_drains_inflight_requests():
    compiled = Requests()
    cancel = [False]
    def progress(done, total):
        if done == 1:
            cancel[0] = True
    with pytest.raises(npu.UpscaleCancelled):
        run(npu.NpuTilePool(compiled), should_cancel=lambda:cancel[0], tile_progress=progress)
    assert compiled.starts == 4
    assert compiled.running == 0
    assert all(request.waits for request in compiled.requests)


def test_request_error_is_preserved_and_other_requests_are_drained():
    compiled = Requests(fail_on=2)
    with pytest.raises(RuntimeError, match='NPU request failed'):
        run(npu.NpuTilePool(compiled))
    assert compiled.running == 0
    assert compiled.starts == 5


def test_pixel_consumer_error_also_drains_inflight_requests():
    compiled = Requests()
    def fail(done,total):
        if done:
            raise ValueError('progress consumer failed')
    with pytest.raises(ValueError, match='progress consumer failed'):
        run(npu.NpuTilePool(compiled),tile_progress=fail)
    assert compiled.running == 0


def test_launch_error_with_unknown_outcome_drains_the_attempted_request():
    compiled = Requests(fail_start_on=3)
    with pytest.raises(RuntimeError, match='NPU launch outcome unknown'):
        run(npu.NpuTilePool(compiled))
    assert compiled.running == 0
