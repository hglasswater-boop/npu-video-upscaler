"""Reproducible model conversion preflight tests; no torch or NPU required."""
import hashlib
import json
import pytest

from scripts.build_bsrgan_ir import (
    OFFICIAL_WEIGHTS_URL,
    verify_checkpoint,
    write_model_manifest,
)


def test_mismatched_checkpoint_rejected_before_loading_torch(tmp_path):
    src = tmp_path / "BSRGANx2.pth"
    src.write_bytes(b"dummy")
    with pytest.raises(ValueError, match="SHA-256"):
        verify_checkpoint(src, "0" * 64)


def test_checkpoint_requires_exact_hash_not_unverified_url(tmp_path):
    src = tmp_path / "BSRGANx2.pth"
    src.write_bytes(b"dummy")
    with pytest.raises(ValueError, match="64"):
        verify_checkpoint(src, "")
    assert verify_checkpoint(src, hashlib.sha256(b"dummy").hexdigest()) is None


def test_manifest_contains_provenance_and_file_hashes(tmp_path):
    xml = tmp_path / "BSRGANx2.xml"
    bin_file = tmp_path / "BSRGANx2.bin"
    xml.write_bytes(b"<xml/>")
    bin_file.write_bytes(b"weights")
    manifest = tmp_path / "model-manifest.json"
    data = write_model_manifest(manifest, xml, bin_file, "f" * 64, "2026.3.0", "2.20")
    assert data["source_url"] == OFFICIAL_WEIGHTS_URL
    assert data["source_sha256"] == "f" * 64
    assert data["scale"] == 2
    assert data["weight_compression"] == "INT8_ASYM"
    assert data["input_shape"] == [1, 3, 48, 48]
    assert data["output_shape"] == [1, 3, 96, 96]
    assert data["files"]["BSRGANx2.bin"] == hashlib.sha256(b"weights").hexdigest()
    assert json.loads(manifest.read_text()) == data
