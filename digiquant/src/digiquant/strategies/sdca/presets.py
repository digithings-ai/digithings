"""Public, hand-authored SDCA curve personalities (#1081).

Presets are public config, not tuned/optimized values — they document a
personality (conservative <-> aggressive; long-only vs. distribution) for
``SdcaStrategyConfig.curve_nodes``/``long_only``. This is deliberately
separate from the private, per-symbol calibration system in
``calibrations.py`` (Slapper), which tunes indicator parameters rather than
choosing a strategy personality.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

_PRESETS_PATH = Path(__file__).parent / "presets.json"


class _RawPreset(TypedDict):
    curve_nodes: list[float]
    long_only: bool
    description: str


class PresetDict(TypedDict):
    curve_nodes: tuple[float, ...]
    long_only: bool
    description: str


def _load_all() -> dict[str, _RawPreset]:
    with _PRESETS_PATH.open() as f:
        return json.load(f)


def list_presets() -> list[str]:
    """List all available preset names."""
    return list(_load_all().keys())


def load_preset(name: str) -> PresetDict:
    """Load one preset's ``curve_nodes``, ``long_only``, and ``description``."""
    presets = _load_all()
    if name not in presets:
        raise ValueError(f"Unknown preset: {name}. Available: {list(presets.keys())}")
    preset = presets[name]
    return {
        "curve_nodes": tuple(preset["curve_nodes"]),
        "long_only": preset["long_only"],
        "description": preset["description"],
    }


__all__ = ["PresetDict", "list_presets", "load_preset"]
