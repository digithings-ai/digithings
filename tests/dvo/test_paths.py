"""Path resolution for macOS, Linux, and DIGIVOICE_DATA_DIR."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.paths import linux_data_dir, mac_data_dir, resolve_paths

pytestmark = pytest.mark.unit


def test_macos_application_support() -> None:
    paths = resolve_paths("darwin", Path("/Users/chris"), {})
    assert paths.data_dir == str(mac_data_dir(Path("/Users/chris")))
    assert paths.models_dir == "/Users/chris/Library/Application Support/digivoice/models"
    assert paths.recordings_dir == ("/Users/chris/Library/Application Support/digivoice/recordings")
    assert paths.history_file == (
        "/Users/chris/Library/Application Support/digivoice/history.jsonl"
    )


def test_linux_xdg_fallback() -> None:
    paths = resolve_paths("linux", Path("/home/chris"), {})
    assert paths.data_dir == str(linux_data_dir(Path("/home/chris"), None))
    assert paths.models_dir == "/home/chris/.local/share/digivoice/models"
    assert paths.recordings_dir == "/home/chris/.local/share/digivoice/recordings"
    assert paths.history_file == "/home/chris/.local/share/digivoice/history.jsonl"


def test_linux_honors_xdg_data_home() -> None:
    paths = resolve_paths("linux", Path("/home/chris"), {"XDG_DATA_HOME": "/xdg/data"})
    assert paths.models_dir == "/xdg/data/digivoice/models"


def test_data_dir_override() -> None:
    paths = resolve_paths(
        "darwin",
        Path("/Users/chris"),
        {"DIGIVOICE_DATA_DIR": "/tmp/digivoice-data"},
    )
    root = Path("/tmp/digivoice-data").resolve()
    assert paths.data_dir == str(root)
    assert paths.models_dir == str(root / "models")
    assert paths.recordings_dir == str(root / "recordings")
    assert paths.history_file == str(root / "history.jsonl")
