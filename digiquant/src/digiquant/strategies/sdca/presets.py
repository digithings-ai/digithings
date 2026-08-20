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

from pydantic import BaseModel, ConfigDict, TypeAdapter, field_validator, model_validator

from digiquant.strategies.sdca.curve import RISK_NODES

_PRESETS_PATH = Path(__file__).parent / "presets.json"


class SdcaPreset(BaseModel):
    """One hand-authored SDCA curve personality, validated at load time."""

    model_config = ConfigDict(frozen=True)

    curve_nodes: tuple[float, ...]
    long_only: bool
    description: str

    @field_validator("curve_nodes")
    @classmethod
    def _validate_node_count(cls, v: tuple[float, ...]) -> tuple[float, ...]:
        if len(v) != len(RISK_NODES):
            raise ValueError(f"curve_nodes must have {len(RISK_NODES)} nodes, got {len(v)}")
        return v

    @model_validator(mode="after")
    def _validate_long_only_nonnegative(self) -> SdcaPreset:
        if self.long_only and any(node < 0 for node in self.curve_nodes):
            raise ValueError("long_only presets must have all curve_nodes >= 0")
        return self


_PRESET_MAP_ADAPTER = TypeAdapter(dict[str, SdcaPreset])


def _load_all() -> dict[str, SdcaPreset]:
    with _PRESETS_PATH.open() as f:
        raw = json.load(f)
    return _PRESET_MAP_ADAPTER.validate_python(raw)


def list_presets() -> list[str]:
    """List all available preset names."""
    return list(_load_all().keys())


def load_preset(name: str) -> SdcaPreset:
    """Load one preset's ``curve_nodes``, ``long_only``, and ``description``."""
    presets = _load_all()
    if name not in presets:
        raise ValueError(f"Unknown preset: {name}. Available: {list(presets.keys())}")
    return presets[name]


__all__ = ["SdcaPreset", "list_presets", "load_preset"]
