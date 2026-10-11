"""Static-shape OpenVINO NPU inference with deterministic overlap tiling."""

from dataclasses import dataclass
from collections import deque
from contextlib import closing
from pathlib import Path
import sys
from typing import Callable

import numpy as np


class ModelError(ValueError):
    """The IR cannot be used by the narrow MVP inference contract."""


class UpscaleCancelled(Exception):
    """The caller requested cancellation during a frame."""


@dataclass(frozen=True)
class ModelShape:
    tile_height: int
    tile_width: int
    scale: int

    @property
    def core_height(self) -> int:
        return self.tile_height - 16

    @property
    def core_width(self) -> int:
        return self.tile_width - 16


def validate_shape(input_shape, output_shape) -> ModelShape:
    try:
        inp = [int(d) for d in input_shape]
        out = [int(d) for d in output_shape]
    except (TypeError, ValueError) as exc:
        raise ModelError('Model must have static shapes') from exc
    if len(inp) != 4 or len(out) != 4 or inp[0:2] != [1, 3] or out[0:2] != [1, 3]:
        raise ModelError('Expected one NCHW RGB model input and output')
    h, w = inp[2:]
    if h <= 16 or w <= 16:
        raise ModelError('Model input tile must exceed 16px in each dimension')
    if out[2] <= 0 or out[3] <= 0 or out[2] % h or out[3] % w:
        raise ModelError('Model output shape is not an integer upscale')
    scale = out[2] // h
    if scale not in (2, 4) or out[3] // w != scale:
        raise ModelError('Only 2x and 4x identical-axis scaling supported')
    return ModelShape(h, w, scale)


def load_npu_model(model_path: Path, core=None):
    if core is None:
        try:
            import openvino as ov
        except ImportError as exc:
            raise ModelError('OpenVINO is not installed') from exc
        core = ov.Core()
    if 'NPU' not in core.available_devices:
        raise ModelError(
            'Intel NPU is not visible to OpenVINO. For Core Ultra 5 125H, open '
            'Windows Device Manager > Neural processors and verify Intel AI Boost; '
            'install/update the official Intel NPU driver, then reboot if needed: '
            'https://www.intel.com/content/www/us/en/download/794734/intel-npu-driver-windows.html'
        )
    try:
        model = core.read_model(str(model_path))
        compiled = core.compile_model(model, 'NPU')
        shape = validate_shape(compiled.input(0).shape, compiled.output(0).shape)
        return compiled, shape
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError(f'OpenVINO could not compile this model for NPU: {exc}') from exc


class NpuTilePool:
    """Bounded NPU requests; borrowed outputs remain valid until next yield."""

    def __init__(self, compiled):
        count = max(1, min(4, int(compiled.get_property('OPTIMAL_NUMBER_OF_INFER_REQUESTS'))))
        self.requests = [compiled.create_infer_request() for _ in range(count)]

    def infer_tiles(self, tiles, should_cancel):
        available = deque(self.requests)
        pending = deque()
        try:
            for tensor, region in tiles:
                if should_cancel():
                    raise UpscaleCancelled('Conversion cancelled')
                request = available.popleft()
                np.copyto(request.get_input_tensor().data, tensor)
                pending.append((request, region))
                request.start_async()
                if not available:
                    request, region = pending[0]
                    request.wait()
                    if should_cancel():
                        raise UpscaleCancelled('Conversion cancelled')
                    yield request.get_output_tensor().data, region
                    pending.popleft()
                    available.append(request)
            while pending:
                request, region = pending[0]
                request.wait()
                if should_cancel():
                    raise UpscaleCancelled('Conversion cancelled')
                yield request.get_output_tensor().data, region
                pending.popleft()
        finally:
            original_error = sys.exc_info()[0] is not None
            cleanup_error = None
            for request, _ in pending:
                try:
                    request.wait()
                except Exception as exc:
                    cleanup_error = cleanup_error or exc
            if cleanup_error is not None and not original_error:
                raise cleanup_error


def upscale_frame(frame: np.ndarray, model_shape: ModelShape,
                  infer_tile: Callable[[np.ndarray], np.ndarray] | None,
                  should_cancel: Callable[[], bool] = lambda: False,
                  tile_progress: Callable[[int, int], None] = lambda done, total: None,
                  infer_tiles: Callable | None = None) -> np.ndarray:
    if frame.ndim != 3 or frame.shape[2] != 3 or frame.dtype != np.uint8:
        raise ValueError('Input frame must be HxWx3 RGB uint8')
    h, w = frame.shape[:2]
    scale = model_shape.scale
    result = np.empty((h * scale, w * scale, 3), dtype=np.uint8)
    padded = np.pad(frame, ((8, 8), (8, 8), (0, 0)), mode='edge')
    total_tiles = ((h + model_shape.core_height - 1) // model_shape.core_height
                   * ((w + model_shape.core_width - 1) // model_shape.core_width))
    completed_tiles = 0
    tile_progress(0, total_tiles)
    def inputs():
        for y in range(0, h, model_shape.core_height):
            for x in range(0, w, model_shape.core_width):
                if should_cancel():
                    raise UpscaleCancelled('Conversion cancelled')
                patch = padded[y:y + model_shape.tile_height, x:x + model_shape.tile_width]
                missing_h = model_shape.tile_height - patch.shape[0]
                missing_w = model_shape.tile_width - patch.shape[1]
                if missing_h or missing_w:
                    patch = np.pad(patch, ((0, missing_h), (0, missing_w), (0, 0)), mode='edge')
                tensor = np.transpose(patch.astype(np.float32) / 255.0, (2, 0, 1))[None, ...]
                yield tensor, (y, x)

    predictions = (infer_tiles(inputs(), should_cancel) if infer_tiles is not None else
                   ((infer_tile(tensor), region) for tensor, region in inputs()))
    with closing(predictions):
        for prediction, (y, x) in predictions:
            prediction = np.asarray(prediction)
            expected = (1, 3, model_shape.tile_height * scale, model_shape.tile_width * scale)
            if prediction.shape != expected:
                raise ModelError(f'Unexpected model output: {prediction.shape}; expected {expected}')
            crop_height = min(model_shape.core_height, h - y)
            crop_width = min(model_shape.core_width, w - x)
            rgb = np.transpose(prediction[0], (1, 2, 0))
            core = rgb[8 * scale:(8 + crop_height) * scale,
                       8 * scale:(8 + crop_width) * scale]
            result[y * scale:(y + crop_height) * scale,
                   x * scale:(x + crop_width) * scale] = np.rint(np.clip(core * 255.0, 0, 255)).astype(np.uint8)
            completed_tiles += 1
            tile_progress(completed_tiles, total_tiles)
    return result
