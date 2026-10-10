"""Release selection and verified installer acquisition, without live network."""

import hashlib
import io
from pathlib import Path

import pytest

from npu_upscaler.updates import (
    API_URL, UpdateError, choose_update, download_installer,
    fetch_releases, make_installer_name,
)


def release(tag="v0.2.0a2", prerelease=True, digest=None, url=None, size=6):
    name = make_installer_name(tag.removeprefix("v"))
    if digest is None:
        digest = "sha256:" + hashlib.sha256(b"hello!").hexdigest()
    if url is None:
        url = f"https://github.com/hglasswater-boop/npu-video-upscaler/releases/download/{tag}/{name}"
    return {
        "tag_name": tag, "draft": False, "prerelease": prerelease,
        "html_url": f"https://github.com/hglasswater-boop/npu-video-upscaler/releases/tag/{tag}",
        "assets": [{
            "name": name, "browser_download_url": url, "digest": digest, "size": size
        }],
    }


def test_alpha_build_accepts_newer_alpha_or_stable_with_max_version():
    result = choose_update([release("v0.2.0a2"), release("v0.2.0"), release("v0.1.0")], "0.2.0a1")
    assert str(result.version) == "0.2.0"


def test_stable_build_ignores_alpha_and_older_stable():
    result = choose_update([release("v0.3.0a1"), release("v0.2.0", False), release("v0.1.9", False)], "0.1.9")
    assert str(result.version) == "0.2.0"
    assert choose_update([release("v0.3.0a1")], "0.2.0") is None


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(draft=True),
    lambda r: r["assets"][0].update(digest=""),
    lambda r: r["assets"][0].update(digest="sha256:abcd"),
    lambda r: r["assets"][0].update(browser_download_url="https://evil.example/setup.exe"),
    lambda r: r["assets"][0].update(name="arbitrary.exe"),
    lambda r: r["assets"][0].update(size=0),
    lambda r: r.update(tag_name="not-a-version"),
])
def test_untrusted_release_metadata_is_ignored(mutation):
    r = release()
    mutation(r)
    assert choose_update([r], "0.2.0a1") is None


def test_download_hash_and_size_verification(tmp_path):
    update = choose_update([release()], "0.2.0a1")
    class Response(io.BytesIO):
        def geturl(self):
            return update.asset_url
    def opener(req, timeout):
        return Response(b"hello!")
    result = download_installer(update, tmp_path, opener=opener)
    assert result.read_bytes() == b"hello!"
    assert download_installer(update, tmp_path, opener=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should cache"))) == result


def test_corrupt_bytes_are_not_executable_or_cached(tmp_path):
    update = choose_update([release()], "0.2.0a1")
    class Response(io.BytesIO):
        def geturl(self):
            return update.asset_url
    with pytest.raises(UpdateError, match="SHA-256"):
        download_installer(update, tmp_path, opener=lambda *_args, **_kwargs: Response(b"BADBAD"))
    assert not list(tmp_path.iterdir())


def test_download_redirect_must_be_trusted(tmp_path):
    update = choose_update([release()], "0.2.0a1")
    class Response(io.BytesIO):
        def geturl(self):
            return "https://malware.example/payload"
    with pytest.raises(UpdateError, match="redirect"):
        download_installer(update, tmp_path, opener=lambda *_args, **_kwargs: Response(b"hello!"))


def test_fetch_release_response_is_bounded_json():
    class Response(io.BytesIO):
        pass
    def opener(request, timeout):
        assert request.full_url == API_URL
        return Response(b'[]')
    assert fetch_releases(opener=opener) == []
    with pytest.raises(UpdateError):
        fetch_releases(opener=lambda *_args, **_kwargs: Response(b'{malformed'))


def test_asset_naming_is_exact():
    assert make_installer_name("0.2.0a1") == "NpuVideoUpscaler-Setup-v0.2.0a1-win-x64.exe"
