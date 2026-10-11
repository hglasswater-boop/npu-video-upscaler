"""Release smoke checks for the *frozen* Windows UI, not just the version string."""

import sys

from launcher import main as launcher_main


def test_release_probe_requires_real_gpu_and_npu_choices(monkeypatch, qt_app):
    monkeypatch.setenv("NPU_UPSCALER_SMOKE_TEST", "1")
    monkeypatch.setattr(sys, "argv", ["launcher", "--check-gpu-ui"])
    assert launcher_main() == 0


def test_release_probe_fails_for_a10_style_npu_only_gui(monkeypatch, qt_app):
    from npu_upscaler import gui

    class NpuOnlyWindow:
        def close(self):
            pass

    monkeypatch.setenv("NPU_UPSCALER_SMOKE_TEST", "1")
    monkeypatch.setattr(sys, "argv", ["launcher", "--check-gpu-ui"])
    monkeypatch.setattr(gui, "MainWindow", NpuOnlyWindow)
    assert launcher_main() != 0
