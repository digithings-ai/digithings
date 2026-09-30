"""Data directories for models and history."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from digivoice.models import VoicePaths

APP_DIR_NAME = "digivoice"
# whisper.cpp weights for the snappy push-to-talk default.
DEFAULT_MODEL = "ggml-base.en"
DEFAULT_MODEL_FILE = "ggml-base.en.bin"


def mac_data_dir(home: Path) -> Path:
    return home / "Library" / "Application Support" / APP_DIR_NAME


def linux_data_dir(home: Path, xdg_data_home: str | None) -> Path:
    base = Path(xdg_data_home) if xdg_data_home else home / ".local" / "share"
    return base / APP_DIR_NAME


def piper_fallback(home: Path) -> Path:
    return home / ".local" / "bin" / "piper"


def resolve_paths(platform: str, home: Path, env: Mapping[str, str]) -> VoicePaths:
    override = env.get("DIGIVOICE_DATA_DIR", "")
    if override:
        data_dir = Path(override).expanduser().resolve()
    elif platform == "darwin":
        data_dir = mac_data_dir(home)
    else:
        xdg = env.get("XDG_DATA_HOME") or None
        data_dir = linux_data_dir(home, xdg)
    return VoicePaths(
        data_dir=str(data_dir),
        models_dir=str(data_dir / "models"),
        history_file=str(data_dir / "history.jsonl"),
    )
