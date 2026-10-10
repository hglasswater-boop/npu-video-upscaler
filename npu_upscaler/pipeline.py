"""Stream RGB frames through a single NPU model into an atomic MP4 export."""

from pathlib import Path
from threading import Event
from typing import Callable
import os
import shutil
import subprocess
import tempfile
import time

import numpy as np

from .media import decoder_command, encoder_command, preview_frame_cap, probe_video
from .npu import load_npu_model, upscale_frame, UpscaleCancelled


class JobCancelled(Exception):
    """Processing cancelled by user."""


def check_not_cancelled(flag: Event) -> None:
    if flag.is_set():
        raise JobCancelled('Processing cancelled')


def validate_paths(source: Path, model: Path, destination: Path) -> None:
    if source.suffix.lower() not in ('.mp4', '.mkv') or not source.is_file():
        raise ValueError('Source must be an existing MP4 or MKV file')
    if model.suffix.lower() != '.xml' or not model.is_file() or not model.with_suffix('.bin').is_file():
        raise ValueError('Model requires an OpenVINO .xml and matching .bin file')
    if destination.suffix.lower() != '.mp4' or not destination.parent.is_dir():
        raise ValueError('Destination must be an MP4 in an existing directory')
    if source.resolve() == destination.resolve():
        raise ValueError('Cannot overwrite the input video')


def temporary_output_path(destination: Path) -> Path:
    descriptor, name = tempfile.mkstemp(prefix=f'.{destination.stem}-', suffix='.mp4', dir=destination.parent)
    os.close(descriptor)
    Path(name).unlink()
    return Path(name)


def _read_frame(stream, size: int) -> bytes | None:
    chunk = stream.read(size)
    if not chunk:
        return None
    if len(chunk) != size:
        raise RuntimeError('Truncated frame from FFmpeg decoder')
    return chunk


def _remove_temporary(path: Path) -> None:
    """Allow Windows a bounded interval to release FFmpeg's output handle."""
    for attempt in range(20):
        try:
            path.unlink(missing_ok=True)
            return
        except PermissionError:
            if attempt == 19:
                raise
            time.sleep(0.1)


def _stop(process) -> None:
    if process is None:
        return
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
    for handle in (process.stdin, process.stdout):
        if handle:
            handle.close()


def preview_limit_seconds(requested: int | None) -> int | None:
    if requested not in (None, 60):
        raise ValueError('Preview duration must be exactly 60 seconds')
    return requested


def preview_progress_total(info) -> int:
    maximum = preview_frame_cap(info.fps)
    return min(maximum, info.total_frames) if info.total_frames is not None else maximum


def run_video(source: Path, model: Path, destination: Path,
              progress: Callable[[int, int | None], None] = lambda done, total: None,
              cancel: Event | None = None, preview_seconds: int | None = None) -> int:
    preview_seconds = preview_limit_seconds(preview_seconds)
    cancel = cancel if cancel is not None else Event()
    source, model, destination = Path(source), Path(model), Path(destination)
    validate_paths(source, model, destination)
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('FFmpeg and ffprobe must be on PATH')
    check_not_cancelled(cancel)
    info = probe_video(source)
    max_frames = preview_frame_cap(info.fps) if preview_seconds is not None else None
    progress_total = preview_progress_total(info) if preview_seconds is not None else info.total_frames
    compiled, shape = load_npu_model(model)
    temporary = temporary_output_path(destination)
    decoder = encoder = None
    count = 0
    # Store error logs in disk-backed files so FFmpeg cannot block on a full stderr pipe.
    with tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as decode_log, \
         tempfile.TemporaryFile(mode='w+t', encoding='utf-8') as encode_log:
        try:
            decoder = subprocess.Popen(decoder_command(source, max_frames=max_frames), stdout=subprocess.PIPE,
                                       stdin=subprocess.DEVNULL, stderr=decode_log)
            encoder = subprocess.Popen(encoder_command(source, temporary, info, shape.scale, max_duration=preview_seconds),
                                       stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=encode_log)
            frame_size = info.width * info.height * 3

            def infer_tile(tensor):
                output = compiled(tensor)
                return next(iter(output.values()))

            while True:
                check_not_cancelled(cancel)
                pixels = _read_frame(decoder.stdout, frame_size)
                if pixels is None:
                    break
                frame = np.frombuffer(pixels, dtype=np.uint8).reshape(info.height, info.width, 3)
                try:
                    upscaled = upscale_frame(frame, shape, infer_tile, cancel.is_set)
                except UpscaleCancelled as exc:
                    raise JobCancelled(str(exc)) from exc
                encoder.stdin.write(upscaled.tobytes())
                count += 1
                progress(count, progress_total)
            encoder.stdin.close()
            decode_status = decoder.wait()
            encode_status = encoder.wait()
            if decode_status or encode_status:
                decode_log.seek(0)
                encode_log.seek(0)
                details = (decode_log.read() + '\n' + encode_log.read()).strip()[-2500:]
                raise RuntimeError(f'FFmpeg failed (decode={decode_status}, encode={encode_status}): {details}')
            check_not_cancelled(cancel)
            if count == 0 or not temporary.is_file() or temporary.stat().st_size == 0:
                raise RuntimeError('Video produced no output frames')
            os.replace(temporary, destination)
            return count
        finally:
            _stop(decoder)
            _stop(encoder)
            _remove_temporary(temporary)
