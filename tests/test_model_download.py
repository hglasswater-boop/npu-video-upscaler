"""Only our GitHub Release's pinned model package is eligible for download."""
import pytest

from npu_upscaler.model_download import choose_model_release, MODEL_ASSET_NAME

ROOT = "https://github.com/hglasswater-boop/npu-video-upscaler/releases"


def released(tag="v0.2.0a3"):
    return {
        "tag_name": tag,
        "draft": False,
        "prerelease": True,
        "html_url": f"{ROOT}/tag/{tag}",
        "assets": [{
            "name": MODEL_ASSET_NAME,
            "browser_download_url": f"{ROOT}/download/{tag}/{MODEL_ASSET_NAME}",
            "size": 200000,
            "digest": "sha256:" + "a" * 64,
        }],
    }


def test_model_asset_selects_newest_exact_official_release():
    result = choose_model_release([released("v0.2.0a3"), released("v0.2.0a4")])
    assert str(result.version) == "0.2.0a4"
    assert result.asset_name == MODEL_ASSET_NAME


@pytest.mark.parametrize("mutation", [
    lambda r: r.update(draft=True),
    lambda r: r["assets"][0].update(digest=None),
    lambda r: r["assets"][0].update(browser_download_url="https://wrong.example/model.zip"),
    lambda r: r["assets"][0].update(name="other.zip"),
    lambda r: r["assets"][0].update(size=0),
    lambda r: r.update(html_url="https://wrong.example/release"),
    lambda r: r.update(tag_name="bad"),
])
def test_reject_unverified_model_release(mutation):
    item = released()
    mutation(item)
    assert choose_model_release([item]) is None
