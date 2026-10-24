"""Installed-model discovery. The finder is injected; the apps are not required."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from digivoice.installed_models import (
    InstalledModel,
    discover_installed_models,
    install_roots,
)
from digivoice.menu_tree import browse_settings, rows_at
from digivoice.paths import resolve_paths
from digivoice.settings import VoiceSettings, load_settings

pytestmark = pytest.mark.unit


def _paths(tmp_path: Path):
    return resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(tmp_path)})


def test_missing_apps_are_an_empty_list(tmp_path: Path) -> None:
    assert discover_installed_models(tmp_path, {}) == []
    assert discover_installed_models(tmp_path, {}, finder=lambda _root: []) == []


def test_install_roots_match_the_app_directories(tmp_path: Path) -> None:
    roots = install_roots(tmp_path, {"OLLAMA_MODELS": str(tmp_path / "custom-ollama")})
    assert roots == [
        ("lmstudio", tmp_path / ".lmstudio" / "models"),
        ("lmstudio", tmp_path / ".cache" / "lm-studio" / "models"),
        ("ollama", tmp_path / "custom-ollama"),
        ("mlxstudio", tmp_path / ".mlxstudio" / "models"),
    ]


def test_discovers_runnable_files_and_skips_the_rest(tmp_path: Path) -> None:
    lm = tmp_path / ".lmstudio" / "models" / "publisher" / "demo"
    lm.mkdir(parents=True)
    gguf = lm / "demo.gguf"
    gguf.write_bytes(b"GGUFxxxx")
    (lm / "weights.safetensors").write_bytes(b"nope")
    whisper = tmp_path / ".cache" / "lm-studio" / "models"
    whisper.mkdir(parents=True)
    ggml = whisper / "ggml-custom.en.bin"
    ggml.write_bytes(b"whisper")
    (whisper / "notes.json").write_bytes(b"{}")
    mlx = tmp_path / ".mlxstudio" / "models" / "image"
    mlx.mkdir(parents=True)
    (mlx / "model.safetensors").write_bytes(b"mlx")
    (mlx / "extra.gguf").write_bytes(b"GGUF")
    ollama = tmp_path / ".ollama" / "models"
    blob = ollama / "blobs" / "sha256-abc"
    blob.parent.mkdir(parents=True)
    blob.write_bytes(b"GGUFblob")
    missing = ollama / "manifests" / "registry.ollama.ai" / "library" / "ghost" / "latest"
    missing.parent.mkdir(parents=True)
    missing.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": "sha256:missing",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    present = ollama / "manifests" / "registry.ollama.ai" / "library" / "llama3" / "latest"
    present.parent.mkdir(parents=True)
    present.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": "application/vnd.ollama.image.model",
                        "digest": "sha256:abc",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (ollama / "manifests" / "registry.ollama.ai" / "library" / "llama3" / "q4").write_text(
        present.read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    found = discover_installed_models(tmp_path, {})
    by_path = {item.path: item for item in found}
    assert gguf.resolve() in {Path(item) for item in by_path} or str(gguf.resolve()) in by_path
    demo = by_path[str(gguf.resolve())]
    assert demo.kind == "rewrite"
    assert demo.source == "lmstudio"
    assert demo.languages == "multilingual"
    audio = by_path[str(ggml.resolve())]
    assert audio.kind == "stt"
    assert audio.languages == "en"
    assert audio.source == "lmstudio"
    extra = by_path[str((mlx / "extra.gguf").resolve())]
    assert extra.source == "mlxstudio"
    ollama_item = by_path[str(blob.resolve())]
    assert ollama_item.name == "llama3"
    assert ollama_item.source == "ollama"
    assert "llama3:latest" not in {item.path for item in found}
    assert all("safetensors" not in item.path for item in found)
    assert all("ghost" not in item.name for item in found)
    assert sum(1 for item in found if item.path == str(blob.resolve())) == 1


def test_selecting_an_installed_model_stores_its_path(tmp_path: Path) -> None:
    gguf = tmp_path / "studio.gguf"
    gguf.write_bytes(b"GGUF")
    item = InstalledModel(
        name="studio",
        path=str(gguf),
        kind="rewrite",
        languages="multilingual",
        source="lmstudio",
    )
    rows = rows_at(VoiceSettings(), "/settings/rewrite/model", installed=[item])
    assert rows[-1].choice == str(gguf)
    block = rows[-1].as_block("/settings/rewrite/model")
    visible = f"{block.action}\n{block.meta}"
    assert visible.count("multilingual") == 1
    assert "English" not in rows[-1].name
    paths = _paths(tmp_path)
    index = len(rows)
    browse_settings(
        paths,
        io.StringIO(f"2\n3\n{index}\n\n\n"),
        io.StringIO(),
        installed=[item],
    )
    assert load_settings(paths).rewrite_model == str(gguf)


def test_catalog_file_is_not_listed_twice(tmp_path: Path) -> None:
    root = tmp_path / ".lmstudio" / "models"
    root.mkdir(parents=True)
    (root / "qwen2.5-1.5b-instruct-q4_k_m.gguf").write_bytes(b"GGUF")
    found = discover_installed_models(tmp_path, {})
    assert found == []


def test_catalog_file_with_different_case_is_not_listed_twice(tmp_path: Path) -> None:
    root = tmp_path / ".mlxstudio" / "models" / "whisper"
    root.mkdir(parents=True)
    (root / "GGML-small.en.bin").write_bytes(b"x")
    assert discover_installed_models(tmp_path, {}) == []
