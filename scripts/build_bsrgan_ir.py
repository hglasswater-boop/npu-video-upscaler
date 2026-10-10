"""Opt-in offline BSRGANx2 checkpoint -> static OpenVINO IR converter.

Heavy build-only dependencies (torch, NNCF) are NOT part of the desktop app.
Source checkpoint SHA-256 must be independently pinned by the caller.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

OFFICIAL_WEIGHTS_URL = "https://github.com/cszn/KAIR/releases/download/v1.0/BSRGANx2.pth"
INPUT_SHAPE = [1, 3, 48, 48]
OUTPUT_SHAPE = [1, 3, 96, 96]


def file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checkpoint(checkpoint: Path, expected_sha256: str) -> None:
    if not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
        raise ValueError("Checkpoint SHA-256 must contain exactly 64 hexadecimal characters")
    if checkpoint.name != "BSRGANx2.pth" or not checkpoint.is_file():
        raise ValueError("Expected a local BSRGANx2.pth checkpoint")
    if file_sha256(checkpoint) != expected_sha256.lower():
        raise ValueError("Checkpoint SHA-256 mismatch — refusing to deserialize unknown weights")


def write_model_manifest(path: Path, xml: Path, binary: Path, source_sha256: str,
                         openvino_version: str, nncf_version: str) -> dict:
    for artifact in (xml, binary):
        if not artifact.is_file() or not artifact.stat().st_size:
            raise ValueError(f"Missing/empty OpenVINO IR: {artifact}")
    data = {
        "model": "BSRGANx2",
        "source_url": OFFICIAL_WEIGHTS_URL,
        "source_sha256": source_sha256.lower(),
        "source_license_review": "PENDING: checkpoint redistribution terms",
        "architecture_license": "Apache-2.0 (cszn/BSRGAN)",
        "openvino_version": openvino_version,
        "nncf_version": nncf_version,
        "input_shape": INPUT_SHAPE,
        "output_shape": OUTPUT_SHAPE,
        "scale": 2,
        "weight_compression": "INT8_ASYM",
        "files": {xml.name: file_sha256(xml), binary.name: file_sha256(binary)},
        "npu_125h_tested": False,
    }
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return data


def convert(checkpoint: Path, output: Path, expected_sha256: str) -> None:
    # Crucial: checksum is checked BEFORE torch.load/deserialization.
    verify_checkpoint(checkpoint, expected_sha256)
    try:
        import openvino as ov
        import torch
        import nncf
        from scripts.network_rrdbnet import RRDBNet
    except ImportError as exc:
        raise RuntimeError("Install model-build dependencies first: see docs/model-preparation.md") from exc

    # The original BSRGAN x2 published checkpoint stores a plain PyTorch state dict.
    state = torch.load(checkpoint, map_location="cpu", weights_only=True)
    if not isinstance(state, dict):
        raise RuntimeError("Checkpoint is not a model state dict")
    model = RRDBNet(in_nc=3, out_nc=3, nf=64, nb=23, gc=32, sf=2)
    model.load_state_dict(state, strict=True)
    model.eval()
    for param in model.parameters():
        param.requires_grad_(False)

    ov_model = ov.convert_model(model, input=INPUT_SHAPE,
                                example_input=torch.zeros(*INPUT_SHAPE))
    compressed = nncf.compress_weights(ov_model, mode=nncf.CompressWeightsMode.INT8_ASYM)
    output.mkdir(parents=True, exist_ok=True)
    xml = output / "BSRGANx2.xml"
    ov.save_model(compressed, str(xml))
    binary = xml.with_suffix(".bin")
    from npu_upscaler.npu import validate_shape
    core = ov.Core()
    ir = core.read_model(str(xml))
    shape = validate_shape(ir.input(0).shape, ir.output(0).shape)
    if shape.scale != 2:
        raise RuntimeError(f"Unexpected conversion scale: {shape.scale}")
    # CPU-only compile proves the IR can load. It is NOT an NPU hardware test.
    core.compile_model(ir, "CPU")
    write_model_manifest(output / "model-manifest.json", xml, binary,
                         expected_sha256, ov.__version__, nncf.__version__)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--sha256", required=True, help="Independently verified SHA-256 of the checkpoint")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    convert(args.checkpoint, args.output, args.sha256)


if __name__ == "__main__":
    main()
