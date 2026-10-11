"""Per-job failure tracebacks without locals, frame data or source paths."""
from datetime import datetime, timezone
from importlib.metadata import version, PackageNotFoundError
from pathlib import Path
import os
import platform
import re
import traceback
import uuid

from . import __version__


def sanitized(text: str, paths=()) -> str:
    sensitive = [str(p) for p in paths] + [str(Path.home()), str(Path.cwd())]
    for value in sorted(set(sensitive), key=len, reverse=True):
        if value and value != '.':
            for form in (value, value.replace('\\', '/'), value.replace('\\', '\\\\')):
                text = re.sub(re.escape(form), '<path>', text, flags=re.IGNORECASE)
    # Other absolute Windows paths (e.g. driver/cache errors), URLs with credentials.
    text = re.sub(r'(?:[A-Za-z]:[\\/]|\\\\)[^\r\n\"\'<>]*', '<path>', text)
    text = re.sub(r'https?://\S+', '<url>', text)
    return text


def save_failure(exc: Exception, stage: str, paths, preview_seconds, device: str) -> Path | None:
    try:
        base = Path(os.environ.get('LOCALAPPDATA', Path.home())) / 'NpuVideoUpscaler' / 'Logs'
        base.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        path = base / f'conversion-{stamp}-{uuid.uuid4().hex[:8]}.log'
        lines = [f'NPU Video Upscaler {__version__}', f'UTC={stamp}',
                 f'Python={platform.python_version()}', f'stage={stage}',
                 f'preview_seconds={preview_seconds}', f'inference_device={device}']
        for package in ('openvino', 'PySide6'):
            try:
                lines.append(f'{package}={version(package)}')
            except PackageNotFoundError:
                lines.append(f'{package}=unavailable')
        trace = traceback.TracebackException.from_exception(exc, capture_locals=False)
        def append_trace(item):
            if item.__cause__ is not None:
                append_trace(item.__cause__)
                lines.append('The above exception was the direct cause of the following exception:')
            elif item.__context__ is not None and not item.__suppress_context__:
                append_trace(item.__context__)
                lines.append('During handling of the above exception, another exception occurred:')
            lines.append('Traceback (most recent call last):')
            for frame in item.stack:
                # Source lines can themselves contain literal paths/secrets. Keep location only.
                lines.append(f'  File "{Path(frame.filename).name}", line {frame.lineno}, in {frame.name}')
            lines.extend(item.format_exception_only())
        append_trace(trace)
        path.write_text(sanitized('\n'.join(lines), paths), encoding='utf-8')
        return path
    except OSError:
        return None
