"""Media metadata validation and deterministic FFmpeg argv builders."""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from fractions import Fraction
import json
from pathlib import Path
import subprocess


class MediaError(ValueError):
    """Input media cannot be exported without violating the MVP contract."""


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: Fraction
    audio_streams: int
    total_frames: int | None


_ALLOWED_PIXEL_FORMATS = {'yuv420p', 'yuv422p', 'yuv444p', 'yuvj420p', 'yuvj422p', 'yuvj444p', 'nv12', 'rgb24', 'bgr24'}
_ALLOWED_AUDIO = {'aac', 'mp3', 'ac3', 'eac3', 'alac'}
_HDR_TRANSFERS = {'smpte2084', 'arib-std-b67'}


def _fps(value: object) -> Fraction:
    try:
        result = Fraction(str(value))
    except (ValueError, TypeError, ZeroDivisionError) as exc:
        raise MediaError(f'Invalid frame rate: {value}') from exc
    if result <= 0 or result > 240:
        raise MediaError(f'Unsupported frame rate: {value}')
    return result


def parse_probe(data: dict) -> VideoInfo:
    streams = data.get('streams', [])
    videos = [stream for stream in streams if stream.get('codec_type') == 'video' and not stream.get('disposition', {}).get('attached_pic')]
    if len(videos) != 1:
        raise MediaError('Exactly one normal video stream is required')
    video = videos[0]
    try:
        width, height = int(video['width']), int(video['height'])
    except (ValueError, TypeError, KeyError) as exc:
        raise MediaError('Missing video dimensions') from exc
    if width <= 0 or height <= 0:
        raise MediaError('Invalid video dimensions')
    if video.get('pix_fmt') not in _ALLOWED_PIXEL_FORMATS:
        raise MediaError(f"Unsupported SDR 8-bit pixel format: {video.get('pix_fmt')}")
    if video.get('color_transfer', '') in _HDR_TRANSFERS:
        raise MediaError('HDR transfer is not supported')
    if str(video.get('tags', {}).get('rotate', '0')) not in ('0', '0.0'):
        raise MediaError('Rotated video is not supported')
    for entry in video.get('side_data_list', []):
        if float(entry.get('rotation', 0)) != 0:
            raise MediaError('Rotated video is not supported')
    fps = _fps(video.get('r_frame_rate'))
    average = _fps(video.get('avg_frame_rate'))
    # Container duration rounding can make avg_frame_rate differ slightly.
    # Accepted frames are resampled by their timestamps before rawvideo output.
    if abs(average - fps) > fps / 100000:
        raise MediaError('フレームレートが可変または曖昧な動画には対応していません。固定フレームレート（CFR）のSDR動画を使用してください。')
    audio = [stream for stream in streams if stream.get('codec_type') == 'audio']
    for stream in audio:
        if stream.get('codec_name') not in _ALLOWED_AUDIO:
            raise MediaError(f"Audio codec cannot be copied to MP4: {stream.get('codec_name')}")
    total = None
    try:
        count = int(video.get('nb_frames', 0))
        if count > 0:
            total = count
    except (ValueError, TypeError):
        pass
    if total is None:
        try:
            seconds = Decimal(str(data.get('format', {}).get('duration', '0')))
            if seconds.is_finite() and seconds > 0:
                total = round(seconds * fps.numerator / fps.denominator)
        except (ValueError, TypeError, InvalidOperation):
            pass
    return VideoInfo(width, height, fps, len(audio), total)


def probe_video(source: Path, ffprobe_executable: str = 'ffprobe') -> VideoInfo:
    args = [ffprobe_executable, '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(source)]
    try:
        # Windows text-mode reader threads can die on a locale decode error and
        # return stdout=None. Decode FFprobe's UTF-8 in this thread instead.
        output = subprocess.run(args, capture_output=True, check=True, timeout=30)
    except (subprocess.SubprocessError, OSError) as exc:
        stderr = _probe_stderr(getattr(exc, 'stderr', None))
        raise MediaError(f'動画情報を取得できませんでした（ffprobe）：{exc}\n{stderr}') from exc
    stderr = _probe_stderr(output.stderr)
    status = f'ffprobe exit={output.returncode}, stdout={type(output.stdout).__name__}'
    if not isinstance(output.stdout, (str, bytes, bytearray)) or not output.stdout.strip():
        raise MediaError(f'動画情報が空または取得不能です（{status}）。\n{stderr}')
    try:
        text = output.stdout if isinstance(output.stdout, str) else output.stdout.decode('utf-8')
        data = json.loads(text)
        if not isinstance(data, dict):
            raise MediaError('動画情報のJSONがオブジェクトではありません。')
        return parse_probe(data)
    except (UnicodeDecodeError, json.JSONDecodeError, MediaError, TypeError, AttributeError, KeyError) as exc:
        raise MediaError(f'動画情報を解析できませんでした（{status}）：{exc}\n{stderr}') from exc


def _probe_stderr(stderr) -> str:
    if isinstance(stderr, (bytes, bytearray)):
        stderr = stderr.decode('utf-8', errors='replace')
    return str(stderr or '').strip()[-2500:]


def preview_frame_cap(fps: Fraction) -> int:
    """Use floor to ensure encoded nominal video duration does not exceed 60s."""
    cap = (60 * fps.numerator) // fps.denominator
    if cap < 1:
        raise MediaError('Frame rate too low for a 60-second preview')
    return cap


def decoder_command(source: str | Path, max_frames: int | None = None,
                    ffmpeg_executable: str = 'ffmpeg', fps: Fraction | None = None) -> list[str]:
    args = [ffmpeg_executable, '-hide_banner', '-loglevel', 'error', '-nostdin',
            '-noautorotate', '-i', str(source), '-map', '0:v:0', '-an', '-sn', '-dn',
            '-fps_mode', 'passthrough', '-f', 'rawvideo', '-pix_fmt', 'rgb24']
    if fps is not None:
        rate = _fps(fps)
        args += ['-vf', f'fps={rate.numerator}/{rate.denominator}:start_time=0:round=near']
    if max_frames is not None:
        if type(max_frames) is not int or max_frames < 1:
            raise ValueError('Maximum frame count must be positive')
        args += ['-frames:v', str(max_frames)]
    return args + ['pipe:1']


def encoder_command(source: str | Path, destination: str | Path, info: VideoInfo,
                    scale: int, max_duration: int | None = None,
                    ffmpeg_executable: str = 'ffmpeg') -> list[str]:
    if scale not in (2, 4):
        raise ValueError('Scale must be 2 or 4')
    args = [ffmpeg_executable, '-hide_banner', '-loglevel', 'error', '-nostdin', '-y',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-video_size', f'{info.width * scale}x{info.height * scale}',
            '-framerate', f'{info.fps.numerator}/{info.fps.denominator}', '-i', 'pipe:0',
            '-i', str(source), '-map', '0:v:0', '-map', '1:a?',
            '-c:v', 'libx264', '-preset', 'medium', '-crf', '20', '-pix_fmt', 'yuv420p',
            '-c:a', 'copy', '-movflags', '+faststart']
    if max_duration is not None:
        if type(max_duration) is not int or max_duration < 1:
            raise ValueError('Maximum duration must be a positive integer')
        args += ['-t', str(max_duration)]
    return args + [str(destination)]
