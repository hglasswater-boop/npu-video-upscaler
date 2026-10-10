"""Absolute-import desktop entry point for PyInstaller packaging."""

import sys

from npu_upscaler import __version__


def main() -> int:
    if sys.argv[1:] == ["--version"]:
        print(__version__)
        return 0
    if sys.argv[1:] == ["--check-media"]:
        from subprocess import run
        from npu_upscaler.media_tools import MediaToolsError, resolve_media_tools
        try:
            tools = resolve_media_tools()
            for binary in (tools.ffmpeg, tools.ffprobe):
                result = run([binary, '-version'], capture_output=True, timeout=20)
                if result.returncode:
                    return 1
            return 0
        except (OSError, MediaToolsError):
            return 1
    from npu_upscaler.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
