"""GPU-default and optional NPU OpenVINO inference with deterministic overlap tiling."""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from .model_packages import is_packaged_bsrgan, model_cache_root


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


def load_model(model_path, device='GPU', core=None, optimize_tiles=False):
    """GPU is the explicit default; NPU is opt-in. Never use CPU/AUTO."""
    if device not in ('GPU', 'NPU'):
        raise ModelError('GPUまたはNPUを選択してください。')
    if device == 'NPU':
        return load_npu_model(model_path, core=core, optimize_tiles=optimize_tiles)
    if core is None:
        import openvino as ov
        core = ov.Core()
    if 'GPU' not in core.available_devices:
        raise ModelError('Intel GPUがOpenVINOで認識されません。'
                         ' ドライバーを確認してください。CPU/NPUへ自動切替しません。')
    try:
        model = core.read_model(str(model_path))
        if optimize_tiles and is_packaged_bsrgan(model_path):
            model.reshape([1, 3, 128, 128])
            cache = model_cache_root().parent / 'GpuCache'
            cache.mkdir(parents=True, exist_ok=True)
            compiled = core.compile_model(model, 'GPU',
                                          {'PERFORMANCE_HINT': 'THROUGHPUT',
                                           'CACHE_DIR': str(cache)})
        else:
            compiled = core.compile_model(model, 'GPU')
        shape = validate_shape(compiled.input(0).shape, compiled.output(0).shape)
        return compiled, shape
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError(f'GPU向けモデルのコンパイルに失敗しました: {exc}') from exc


def load_npu_model(model_path: Path, core=None, optimize_tiles: bool = False):
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
        optimized = optimize_tiles and is_packaged_bsrgan(model_path)
        model = core.read_model(str(model_path))
        if optimized:
            model.reshape([1, 3, 128, 128])
            cache = model_cache_root().parent / 'NpuCache'
            cache.mkdir(parents=True, exist_ok=True)
            compiled = core.compile_model(model, 'NPU',
                                          {'PERFORMANCE_HINT': 'LATENCY', 'CACHE_DIR': str(cache)})
        else:
            compiled = core.compile_model(model, 'NPU')
        shape = validate_shape(compiled.input(0).shape, compiled.output(0).shape)
        return compiled, shape
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError(f'OpenVINO could not compile this model for NPU: {exc}') from exc


def upscale_frame(frame: np.ndarray, model_shape: ModelShape,
                  infer_tile: Callable[[np.ndarray], np.ndarray],
                  should_cancel: Callable[[], bool] = lambda: False,
                  tile_progress: Callable[[int, int], None] = lambda done, total: None) -> np.ndarray:
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
            prediction = np.asarray(infer_tile(tensor))
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
