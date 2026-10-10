"""Cross-release upgrade safety: metadata selection is independent of installer execution."""
from hashlib import sha256
from io import BytesIO
from unittest.mock import Mock

import pytest

from npu_upscaler.updates import choose_update, download_installer, UpdateError


def record(version, payload):
    name = f"NpuVideoUpscaler-Setup-v{version}-win-x64.exe"
    root = "https://github.com/hglasswater-boop/npu-video-upscaler/releases"
    return {
        "draft": False, "prerelease": True, "tag_name": f"v{version}",
        "html_url": f"{root}/tag/v{version}",
        "assets": [{
            "name": name,
            "browser_download_url": f"{root}/download/v{version}/{name}",
            "size": len(payload),
            "digest": f"sha256:{sha256(payload).hexdigest()}",
        }],
    }


def test_a1_to_a2_release_selection_uses_canonical_asset():
    update = choose_update([record("0.2.0a2", b"a2"), record("0.2.0a1", b"a1")], "0.2.0a1")
    assert str(update.version) == "0.2.0a2"
    assert update.asset_name == "NpuVideoUpscaler-Setup-v0.2.0a2-win-x64.exe"


def test_checksum_is_required_before_exposing_installer(tmp_path):
    update = choose_update([record("0.2.0a2", b"new")], "0.2.0a1")
    class Response(BytesIO):
        def geturl(self):
            return update.asset_url
    with pytest.raises(UpdateError, match="SHA-256"):
        download_installer(update, tmp_path, opener=lambda *_a, **_kw: Response(b"old"))
    assert not list(tmp_path.glob("*.exe"))
    result = download_installer(update, tmp_path, opener=lambda *_a, **_kw: Response(b"new"))
    assert result.read_bytes() == b"new"


def test_older_release_cannot_reinstall_or_downgrade():
    assert choose_update([record("0.2.0a1", b"old")], "0.2.0a2") is None
