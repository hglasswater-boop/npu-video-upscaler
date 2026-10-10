"""Absolute-import desktop entry point for PyInstaller packaging."""

import sys

from npu_upscaler import __version__


def main() -> int:
    if sys.argv[1:] == ["--version"]:
        print(__version__)
        return 0
    from npu_upscaler.gui import main as gui_main
    return gui_main()


if __name__ == "__main__":
    raise SystemExit(main())
