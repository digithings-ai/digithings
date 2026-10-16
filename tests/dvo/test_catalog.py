"""Suggested local STT + rewrite catalog: list, download, wire. No cloud endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.catalog import (
    REWRITE_CATALOG,
    STT_CATALOG,
    find_rewrite,
    find_stt,
    find_voice,
    install_catalog_model,
    stt_filename,
    stt_language,
)
from digivoice.paths import resolve_paths
from digivoice.settings import LOCAL_REWRITE_MODEL_FILE

pytestmark = pytest.mark.unit


def _paths(tmp_path: Path):
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def test_stt_catalog_has_english_and_multilingual() -> None:
    ids = [item.id for item in STT_CATALOG]
    assert "ggml-base.en" in ids
    assert "ggml-tiny.en" in ids
    assert "ggml-base" in ids
    assert "ggml-tiny" in ids
    assert "ggml-medium.en" in ids
    assert "ggml-medium" in ids
    assert "ggml-large-v3-turbo" in ids
    assert "ggml-large-v3" in ids
    assert ids[0] == "ggml-tiny.en"
    assert any(item.languages == "en" for item in STT_CATALOG)
    assert any(item.languages == "multilingual" for item in STT_CATALOG)
    assert all(item.kind == "stt" for item in STT_CATALOG)
    assert all(item.filename.endswith(".bin") for item in STT_CATALOG)
    assert all("huggingface" in item.url for item in STT_CATALOG)
    assert all("://" in item.url for item in STT_CATALOG)


def test_rewrite_catalog_offers_more_than_one_local_gguf() -> None:
    assert len(REWRITE_CATALOG) >= 2
    files = [item.filename for item in REWRITE_CATALOG]
    assert LOCAL_REWRITE_MODEL_FILE in files
    assert "Qwen2.5-7B-Instruct-Q4_K_M.gguf" in files
    assert "Llama-3.2-3B-Instruct-Q4_K_M.gguf" in files
    assert "gemma-2-2b-it-Q4_K_M.gguf" in files
    assert len(files) == len(set(files))
    assert all(item.filename.endswith(".gguf") for item in REWRITE_CATALOG)
    assert all(item.kind == "rewrite" for item in REWRITE_CATALOG)
    assert all(item.languages == "multilingual" for item in REWRITE_CATALOG)
    assert all("huggingface" in item.url for item in REWRITE_CATALOG)
    assert not any("openrouter" in item.url or "openai.com" in item.url for item in REWRITE_CATALOG)


def test_stt_filename_and_language() -> None:
    assert stt_filename("ggml-base.en") == "ggml-base.en.bin"
    assert stt_filename("ggml-tiny") == "ggml-tiny.bin"
    assert stt_filename(None) == "ggml-base.en.bin"
    assert stt_language("ggml-base.en") == "en"
    assert stt_language("ggml-tiny.en") == "en"
    assert stt_language("ggml-base") == "auto"
    assert stt_language("ggml-small") == "auto"


def test_find_helpers_match_id_or_filename() -> None:
    assert find_stt("ggml-base.en") is not None
    assert find_stt("ggml-base.en.bin") is not None
    assert find_stt("nope") is None
    assert find_rewrite(LOCAL_REWRITE_MODEL_FILE) is not None
    assert find_rewrite("https://example.com/x.gguf") is None


def test_install_catalog_model_downloads_and_is_idempotent(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    entry = STT_CATALOG[0]
    seen: list[str] = []

    def fetch(url: str, dest: Path, progress=None) -> None:
        seen.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"weights")
        if progress is not None:
            progress(len(b"weights"), len(b"weights"))

    installed = install_catalog_model(paths, entry, fetch=fetch)
    target = Path(paths.models_dir) / entry.filename
    assert installed == str(target)
    assert target.read_bytes() == b"weights"
    assert seen == [entry.url]

    def boom(url: str, dest: Path) -> None:
        raise AssertionError("should not fetch when present")

    again = install_catalog_model(paths, entry, fetch=boom)
    assert again == str(target)


def test_failed_download_removes_the_partial_and_keeps_other_models(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    models = Path(paths.models_dir)
    models.mkdir()
    sibling = models / "ggml-base.en.bin"
    sibling.write_bytes(b"keep")
    entry = next(item for item in STT_CATALOG if item.id == "ggml-tiny.en")
    seen: list[tuple[int, int | None]] = []

    def fetch(url: str, dest: Path, progress=None) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"partial")
        if progress is not None:
            progress(1, 8)
            progress(4, 8)
        raise OSError("stopped")

    def progress(got: int, total: int | None) -> None:
        seen.append((got, total))

    with pytest.raises(OSError, match="stopped"):
        install_catalog_model(paths, entry, fetch=fetch, progress=progress)
    assert sibling.read_bytes() == b"keep"
    assert not (models / entry.filename).exists()
    assert not (models / f"{entry.filename}.partial").exists()
    assert seen == [(1, 8), (4, 8)]


def test_voice_download_keeps_both_pieces_or_neither(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    models = Path(paths.models_dir)
    models.mkdir()
    sibling = models / "ggml-base.en.bin"
    sibling.write_bytes(b"keep")
    entry = find_voice("en_US-amy-medium.onnx")
    assert entry is not None

    def fetch(url: str, dest: Path, progress=None) -> None:
        dest.write_bytes(b"ok")
        if progress is not None:
            progress(3, 6)
            progress(6, 6)

    install_catalog_model(paths, entry, fetch=fetch)
    assert (models / entry.filename).read_bytes() == b"ok"
    assert (models / f"{entry.filename}.json").read_bytes() == b"ok"
    assert not list(models.glob("*.partial"))
    assert sibling.read_bytes() == b"keep"

    other = find_voice("en_GB-alba-medium.onnx")
    assert other is not None
    calls = {"n": 0}

    def fail(url: str, dest: Path, progress=None) -> None:
        calls["n"] += 1
        dest.write_bytes(b"half")
        if calls["n"] == 2:
            raise OSError("sidecar")

    with pytest.raises(OSError, match="sidecar"):
        install_catalog_model(paths, other, fetch=fail)
    assert not (models / other.filename).exists()
    assert not (models / f"{other.filename}.json").exists()
    assert not list(models.glob("*.partial"))
    assert (models / entry.filename).is_file()


def test_install_catalog_accepts_legacy_two_arg_fetch(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    entry = REWRITE_CATALOG[0]

    def fetch(url: str, dest: Path) -> None:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"gguf")

    installed = install_catalog_model(paths, entry, fetch=fetch)
    assert Path(installed).read_bytes() == b"gguf"
