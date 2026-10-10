"""Select only our published, checksum-advertised GitHub model release asset."""
from __future__ import annotations

import re

from packaging.version import InvalidVersion, Version

from .updates import ReleaseUpdate

MODEL_ASSET_NAME = "BSRGANx2-OpenVINO-INT8.zip"
_RELEASE_BASE = "https://github.com/hglasswater-boop/npu-video-upscaler/releases"
_VERSION_TAG = re.compile(r"^v\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?$")
_SHA = re.compile(r"^sha256:([a-fA-F0-9]{64})$")


def choose_model_release(releases: list[dict]) -> ReleaseUpdate | None:
    found = []
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
        if release.get("html_url") != f"{_RELEASE_BASE}/tag/{tag}":
            continue
        expected_url = f"{_RELEASE_BASE}/download/{tag}/{MODEL_ASSET_NAME}"
        assets = release.get("assets")
        if not isinstance(assets, list):
            continue
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            if asset.get("name") != MODEL_ASSET_NAME or asset.get("browser_download_url") != expected_url:
                continue
            digest = asset.get("digest")
            size = asset.get("size")
            match = _SHA.fullmatch(digest) if isinstance(digest, str) else None
            if not match or type(size) is not int or not (0 < size <= 300 * 1024 * 1024):
                continue
            found.append(ReleaseUpdate(version, tag, MODEL_ASSET_NAME, expected_url,
                                       match.group(1).lower(), size, f"{_RELEASE_BASE}/tag/{tag}"))
    return max(found, key=lambda update: update.version, default=None)
