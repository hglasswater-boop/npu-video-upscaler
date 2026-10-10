"""Fail-closed updater for this repository's GitHub Release installers.

Only canonical release URLs and matching GitHub-published SHA-256 digests
are accepted. Downloading never launches an installer; the GUI must obtain
separate user consent before starting the installer.
"""

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from packaging.version import InvalidVersion, Version


API_URL = "https://api.github.com/repos/hglasswater-boop/npu-video-upscaler/releases?per_page=20"
_RELEASE_BASE = "https://github.com/hglasswater-boop/npu-video-upscaler/releases"
_VERSION_TAG = re.compile(r"^v\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$")
_DIGEST = re.compile(r"^sha256:([a-fA-F0-9]{64})$")
_MAX_INSTALLER_SIZE = 2 * 1024 * 1024 * 1024
_MAX_RELEASE_JSON = 2 * 1024 * 1024
_TRUSTED_DOWNLOAD_HOSTS = {"github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}


class UpdateError(RuntimeError):
    """Update check, validation, or acquisition failed."""


@dataclass(frozen=True)
class ReleaseUpdate:
    version: Version
    tag: str
    asset_name: str
    asset_url: str
    sha256_hex: str
    expected_size: int
    page_url: str


def make_installer_name(version: str) -> str:
    return f"NpuVideoUpscaler-Setup-v{version}-win-x64.exe"


def choose_update(releases: list[dict], current_version: str) -> ReleaseUpdate | None:
    try:
        current = Version(current_version)
    except InvalidVersion as exc:
        raise UpdateError(f"Invalid installed application version: {current_version}") from exc

    possible = []
    for release in releases:
        if not isinstance(release, dict) or release.get("draft") is not False:
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not _VERSION_TAG.fullmatch(tag):
            continue
        try:
            version = Version(tag[1:])
        except InvalidVersion:
            continue
        if version <= current or (not current.is_prerelease and release.get("prerelease") is True):
            continue
        name = make_installer_name(tag[1:])
        canonical = f"{_RELEASE_BASE}/download/{quote(tag)}/{quote(name)}"
        asset = next((a for a in release.get("assets", [])
                      if isinstance(a, dict) and a.get("name") == name), None)
        if not asset or asset.get("browser_download_url") != canonical:
            continue
        digest = asset.get("digest")
        match = _DIGEST.fullmatch(digest) if isinstance(digest, str) else None
        size = asset.get("size")
        if not match or type(size) is not int or not 0 < size <= _MAX_INSTALLER_SIZE:
            continue
        page_url = f"{_RELEASE_BASE}/tag/{quote(tag)}"
        if release.get("html_url") != page_url:
            continue
        possible.append(ReleaseUpdate(version, tag, name, canonical, match.group(1).lower(), size, page_url))
    return max(possible, key=lambda item: item.version, default=None)


def fetch_releases(opener: Callable = urlopen) -> list[dict]:
    request = Request(API_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": "NpuVideoUpscaler-UpdateChecker",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with opener(request, timeout=15) as response:
            payload = response.read(_MAX_RELEASE_JSON + 1)
        if len(payload) > _MAX_RELEASE_JSON:
            raise UpdateError("GitHub Releases response exceeds safety limit")
        result = json.loads(payload)
        if not isinstance(result, list):
            raise UpdateError("Unexpected GitHub Releases response")
        return result
    except (OSError, ValueError, UnicodeError) as exc:
        if isinstance(exc, UpdateError):
            raise
        raise UpdateError(f"Unable to check GitHub Releases: {exc}") from exc


def _file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_installer(update: ReleaseUpdate, updates_dir: Path,
                       opener: Callable = urlopen,
                       progress: Callable[[int, int], None] = lambda done, total: None) -> Path:
    """Download + verify only; never starts the installer.

    If a cached valid file exists, it may be reused. A failed verification never
    exposes a ready-to-launch filename.
    """
    updates_dir = Path(updates_dir)
    updates_dir.mkdir(parents=True, exist_ok=True)
    destination = updates_dir / update.asset_name
    if destination.is_file():
        if destination.stat().st_size == update.expected_size and _file_digest(destination) == update.sha256_hex:
            return destination
        destination.unlink()
    fd, temp_name = tempfile.mkstemp(prefix=".npu-download-", suffix=".part", dir=updates_dir)
    os.close(fd)
    temporary = Path(temp_name)
    try:
        request = Request(update.asset_url, headers={"User-Agent": "NpuVideoUpscaler-Updater"})
        with opener(request, timeout=30) as response, temporary.open("wb") as output:
            final_url = response.geturl()
            final = urlsplit(final_url)
            if final.scheme != "https" or final.hostname not in _TRUSTED_DOWNLOAD_HOSTS:
                raise UpdateError("Refusing an untrusted installer redirect")
            received = 0
            digest = sha256()
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                received += len(chunk)
                if received > update.expected_size or received > _MAX_INSTALLER_SIZE:
                    raise UpdateError("Installer exceeds expected download size")
                output.write(chunk)
                digest.update(chunk)
                progress(received, update.expected_size)
        if received != update.expected_size:
            raise UpdateError("Installer download size does not match GitHub Release")
        if digest.hexdigest() != update.sha256_hex:
            raise UpdateError("Installer SHA-256 verification failed")
        os.replace(temporary, destination)
        return destination
    except OSError as exc:
        raise UpdateError(f"Unable to download update: {exc}") from exc
    finally:
        temporary.unlink(missing_ok=True)
