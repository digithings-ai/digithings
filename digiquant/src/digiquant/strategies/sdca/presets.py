"""Public SDCA curve personalities (#1081, authored as shapes since #3169).

Presets are public config, not tuned/optimized values — they document a
personality (conservative <-> aggressive; long-only vs. distribution) for
``SdcaStrategyConfig.curve_nodes``/``long_only``. Since #3169 they are stored
as ``SdcaCurveShape`` parameters; ``curve_nodes`` are generated at load so
``list_presets()``/``load_preset()`` keep returning an ``SdcaPreset`` with a
21-node tuple. This is deliberately separate from the private, per-symbol
calibration system in ``calibrations.py`` (Slapper).
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict, TypeAdapter, field_validator, model_validator

from digiquant.strategies.sdca.curve import RISK_NODES
from digiquant.strategies.sdca.curve_shape import SdcaCurveShape

_PRESETS_PATH = Path(__file__).parent / "presets.json"


class SdcaPreset(BaseModel):
    """One SDCA curve personality, validated at load time.

    ``curve_nodes`` is the 21-node runtime tuple ``AccumDistCurve`` consumes.
    When loaded from ``presets.json``, nodes are generated from ``shape``.
    Direct construction may still pass nodes without a shape (unit tests).
    """

    model_config = ConfigDict(frozen=True)

    curve_nodes: tuple[float, ...]
    long_only: bool
    description: str
    shape: SdcaCurveShape | None = None

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


class _RawPresetFileEntry(BaseModel):
    """On-disk preset: shape parameters plus personality metadata."""

    model_config = ConfigDict(frozen=True)

    description: str
    long_only: bool
    shape: SdcaCurveShape


_PRESET_FILE_ADAPTER = TypeAdapter(dict[str, _RawPresetFileEntry])


def _load_all() -> dict[str, SdcaPreset]:
    with _PRESETS_PATH.open() as f:
        raw = json.load(f)
    entries = _PRESET_FILE_ADAPTER.validate_python(raw)
    return {
        name: SdcaPreset(
            curve_nodes=entry.shape.to_nodes(),
            long_only=entry.long_only,
            description=entry.description,
            shape=entry.shape,
        )
        for name, entry in entries.items()
    }


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
