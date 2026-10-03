"""Data directories for models and history."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from digivoice.models import VoicePaths

APP_DIR_NAME = "digivoice"
RECORDINGS_DIR_NAME = "recordings"
# whisper.cpp weights for the snappy push-to-talk default.
DEFAULT_MODEL = "ggml-base.en"
DEFAULT_MODEL_FILE = "ggml-base.en.bin"


def stt_model_id(model_id: str | None = None) -> str:
    """Stable id for logs/doctor: `ggml-small.en.bin` → `ggml-small.en`."""
    text = (model_id or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    name = Path(text).expanduser().name
    for suffix in (".bin", ".gguf"):
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return name


def resolve_stt_model_path(paths: VoicePaths, model_id: str | None = None) -> Path:
    """Weights file for `settings.stt_model` (or the default).

    `ggml-base.en` → `<models_dir>/ggml-base.en.bin`. A `.bin`/`.gguf` name is
    used under the models dir; an absolute path is used as-is.
    """
    text = (model_id or DEFAULT_MODEL).strip() or DEFAULT_MODEL
    candidate = Path(text).expanduser()
    if candidate.is_absolute():
        return candidate
    if text.endswith((".bin", ".gguf")):
        return Path(paths.models_dir) / text
    return Path(paths.models_dir) / f"{text}.bin"


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
        recordings_dir=str(data_dir / RECORDINGS_DIR_NAME),
        history_file=str(data_dir / "history.jsonl"),
    )
