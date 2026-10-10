"""Choose an application-private FFmpeg/ffprobe pair without changing PATH."""
from dataclasses import dataclass
from pathlib import Path
import shutil
import sys


class MediaToolsError(RuntimeError):
    """Media tools missing from the installer or developer environment."""


@dataclass(frozen=True)
class MediaTools:
    ffmpeg: str
    ffprobe: str


def resolve_media_tools() -> MediaTools:
    """Frozen distribution never silently switches to arbitrary tools on PATH."""
    if getattr(sys, 'frozen', False):
        # PyInstaller 6 onedir sets _MEIPASS to <app>/_internal.
        bundled = Path(sys._MEIPASS) / 'media-tools'
        ffmpeg = bundled / 'ffmpeg.exe'
        ffprobe = bundled / 'ffprobe.exe'
        if not (ffmpeg.is_file() and ffprobe.is_file()):
            raise MediaToolsError(
                'FFmpeg/ffprobe are missing from this app installation. '
                'Please reinstall the complete Windows installer or portable ZIP.'
            )
        return MediaTools(str(ffmpeg), str(ffprobe))

    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        missing = '/'.join(name for name, value in [('ffmpeg', ffmpeg), ('ffprobe', ffprobe)] if not value)
        raise MediaToolsError(
            f'{missing} not found. Source installations require FFmpeg and ffprobe on PATH.'
        )
    return MediaTools(ffmpeg, ffprobe)
