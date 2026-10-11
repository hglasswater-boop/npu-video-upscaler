"""First-launch verified model package importer contracts without NPU hardware."""
from hashlib import sha256
import json
from pathlib import Path
from zipfile import ZipFile
import pytest

from npu_upscaler.model_packages import install_model_zip, find_prepared_model, ModelPackageError


SOURCE_SHA = "614f68bcafcf123a1ea51cc75ae5741640a8b1d49dd75757ad3ad531f772c736"


def sample_zip(tmp_path, tamper=None):
    pieces = {"BSRGANx2.xml": b'<net name="BSRGANx2"/>', "BSRGANx2.bin": b'weights'}
    meta = {
        "model": "BSRGANx2", "source_sha256": SOURCE_SHA,
        "weight_compression": "INT8_ASYM",
        "input_shape": [1, 3, 48, 48], "output_shape": [1, 3, 96, 96],
        "files": {key: sha256(value).hexdigest() for key, value in pieces.items()},
    }
    if tamper:
        tamper(pieces, meta)
    archive = tmp_path / 'model.zip'
    with ZipFile(archive, 'w') as zipfile:
        for name, bytes_ in pieces.items():
            zipfile.writestr(name, bytes_)
        zipfile.writestr('model-manifest.json', json.dumps(meta))
    return archive


def test_valid_zip_is_compiled_with_npu_and_cached(tmp_path):
    calls = []
    def compile_npu(path):
        calls.append(path)
        return object(), object()
    root = tmp_path / 'Models'
    archive = sample_zip(tmp_path)
    chosen = install_model_zip(archive, root, compile_npu=compile_npu)
    assert chosen.is_file()
    assert chosen.name == 'BSRGANx2.xml'
    assert chosen.with_suffix('.bin').is_file()
    assert len(calls) == 1
    assert find_prepared_model(root) == chosen


def test_tile_optimization_identifies_only_verified_user_cache(monkeypatch,tmp_path):
    from npu_upscaler.model_packages import is_packaged_bsrgan,model_cache_root
    from shutil import copytree
    monkeypatch.setenv('LOCALAPPDATA',str(tmp_path))
    chosen=install_model_zip(sample_zip(tmp_path),model_cache_root(),compile_npu=lambda *_:None)
    assert is_packaged_bsrgan(chosen)
    copytree(chosen.parent,tmp_path/'external')
    assert not is_packaged_bsrgan(tmp_path/'external'/'BSRGANx2.xml')
    chosen.with_suffix('.bin').write_bytes(b'changed weights')
    with pytest.raises(ModelPackageError,match='SHA-256'):
        is_packaged_bsrgan(chosen)


def test_changed_binary_is_rejected_and_not_installed(tmp_path):
    archive = sample_zip(tmp_path, lambda pieces, meta: pieces.update({"BSRGANx2.bin": b'evil'}))
    with pytest.raises(ModelPackageError, match="SHA-256"):
        install_model_zip(archive, tmp_path/'Models', compile_npu=lambda *_: None)
    assert find_prepared_model(tmp_path/'Models') is None


def test_wrong_source_digest_fails_closed(tmp_path):
    archive = sample_zip(tmp_path, lambda pieces, meta: meta.update(source_sha256="0"*64))
    with pytest.raises(ModelPackageError, match="source"):
        install_model_zip(archive, tmp_path/'Models', compile_npu=lambda *_: None)


def test_npu_compilation_failure_keeps_no_usable_model(tmp_path):
    archive = sample_zip(tmp_path)
    def fail(_):
        raise RuntimeError("no NPU available")
    with pytest.raises(ModelPackageError, match="NPU"):
        install_model_zip(archive, tmp_path/'Models', compile_npu=fail)
    assert find_prepared_model(tmp_path/'Models') is None


def test_unsafe_zip_member_is_rejected(tmp_path):
    def mutate(pieces, _):
        pieces['../outside.xml'] = b'bad'
    archive = sample_zip(tmp_path, mutate)
    with pytest.raises(ModelPackageError, match="archive"):
        install_model_zip(archive, tmp_path/'Models', compile_npu=lambda *_: None)


def test_prepared_model_mutation_is_not_auto_selected(tmp_path):
    archive = sample_zip(tmp_path)
    root = tmp_path/'Models'
    chosen = install_model_zip(archive, root, compile_npu=lambda *_: None)
    chosen.with_suffix('.bin').write_bytes(b'corrupted!')
    assert find_prepared_model(root) is None


def test_malformed_cached_manifest_does_not_crash_first_launch(tmp_path):
    root = tmp_path / "Models"
    invalid = root / ("BSRGANx2-" + "0" * 12)
    invalid.mkdir(parents=True)
    (invalid / "model-manifest.json").write_text('[]')
    assert find_prepared_model(root) is None
