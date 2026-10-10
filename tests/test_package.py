"""Packaging invariants. No GUI or network required."""

import re
from pathlib import Path
import tomllib

from npu_upscaler import __version__
from npu_upscaler.updates import make_installer_name


ROOT = Path(__file__).resolve().parents[1]


def test_single_source_version_matches_release_asset():
    assert re.fullmatch(r"\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+)?", __version__)
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert "version" not in pyproject["project"]
    assert pyproject["tool"]["setuptools"]["dynamic"]["version"]["attr"] == "npu_upscaler.__version__"
    assert "version" in pyproject["project"]["dynamic"]
    assert make_installer_name(__version__).endswith("-win-x64.exe")


def test_packaging_has_stable_installer_and_versioned_release():
    workflow = (ROOT / ".github/workflows/windows-build-release.yml").read_text(encoding="utf-8")
    installer = (ROOT / "installer.iss").read_text(encoding="utf-8")
    assert "upload-artifact@" in workflow
    assert "gh release create" in workflow
    assert "--prerelease" in workflow
    assert "PrivilegesRequired=lowest" in installer
    assert "AppId=" in installer
    assert "NpuVideoUpscaler.exe" in installer
