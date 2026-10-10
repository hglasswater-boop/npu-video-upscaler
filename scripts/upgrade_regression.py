"""Actual published Windows installers regression: v0.2.0a1 -> v0.2.0a2.

Runs ONLY on a disposable Windows CI runner. Installer downloads use the application's
release selection + SHA-256 verification path; tests do not rely on unpinned assets.
"""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.request import Request, urlopen

import winreg

from npu_upscaler.updates import choose_update, download_installer


REPOSITORY = "hglasswater-boop/npu-video-upscaler"
PINNED = {
    "0.2.0a1": "bf6c882186ac8d0845552f568373ab10683b5370074143171c196a64a0ca252d",
    "0.2.0a2": "4c45d5147ed14881f299bc105134451475a01b6a0b985d22036c52c1af7e9add",
}
UNINSTALL = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
PREFERENCES = r"Software\NpuVideoUpscaler\NpuVideoUpscaler"
EXE = Path(os.environ["LOCALAPPDATA"]) / "Programs" / "NpuVideoUpscaler" / "NpuVideoUpscaler.exe"


def published_version(version: str) -> dict:
    request = Request(
        f"https://api.github.com/repos/{REPOSITORY}/releases/tags/v{version}",
        headers={"Accept": "application/vnd.github+json", "User-Agent": "NpuVideoUpscaler-UpgradeRegression"},
    )
    with urlopen(request, timeout=30) as response:
        return json.load(response)


def get_installer(version: str, previous: str, directory: Path) -> Path:
    update = choose_update([published_version(version)], previous)
    if update is None or str(update.version) != version:
        raise AssertionError(f"Missing canonical v{version} update")
    if update.sha256_hex != PINNED[version]:
        raise AssertionError(f"Published installer v{version} changed unexpectedly")
    installer = download_installer(update, directory)
    if sha256(installer.read_bytes()).hexdigest() != PINNED[version]:
        raise AssertionError(f"Installer v{version} hash verification failed")
    return installer


def installed_versions() -> list[str]:
    versions = []
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL) as uninstall:
        for index in range(winreg.QueryInfoKey(uninstall)[0]):
            subname = winreg.EnumKey(uninstall, index)
            with winreg.OpenKey(uninstall, subname) as sub:
                try:
                    name = str(winreg.QueryValueEx(sub, "DisplayName")[0])
                    version = str(winreg.QueryValueEx(sub, "DisplayVersion")[0])
                except FileNotFoundError:
                    continue
                if name.startswith("NPU Video Upscaler"):
                    versions.append(version)
    return versions


def assert_installed(expected: str):
    versions = installed_versions()
    if versions != [expected]:
        raise AssertionError(f"Expected one installed NPU Video Upscaler {expected}, got {versions}")
    if not EXE.is_file():
        raise AssertionError(f"Installed executable missing: {EXE}")
    proc = subprocess.run([str(EXE), "--version"], timeout=30, check=False)
    if proc.returncode:
        raise AssertionError(f"Installed application --version returned {proc.returncode}")


def install(installer: Path):
    subprocess.run([str(installer), "/VERYSILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
                   timeout=240, check=True)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("Windows only")
    if EXE.exists():
        raise AssertionError("Upgrade CI must start without a previous installation")
    staging = Path(os.environ["RUNNER_TEMP"]) / "npu-upgrade-verified"
    old = get_installer("0.2.0a1", "0.1.0a1", staging)
    new = get_installer("0.2.0a2", "0.2.0a1", staging)

    # No install operation is performed by get_installer/download_installer.
    if EXE.exists():
        raise AssertionError("Updater downloaded an installer without permission")

    install(old)
    assert_installed("0.2.0a1")

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, PREFERENCES) as key:
        winreg.SetValueEx(key, "autoCheckUpdates", 0, winreg.REG_DWORD, 0)

    install(new)
    assert_installed("0.2.0a2")

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, PREFERENCES) as key:
        value, _ = winreg.QueryValueEx(key, "autoCheckUpdates")
    if str(value) not in ("0", "false", "False"):
        raise AssertionError(f"Per-user application settings changed during upgrade: {value}")

    print("OK: real published a1 -> a2 upgrade; single install, same exe, settings retained.")


if __name__ == "__main__":
    main()
