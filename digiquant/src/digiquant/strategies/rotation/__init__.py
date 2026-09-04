"""Relative-strength asset-rotation strategy package (#1084)."""

from digiquant.strategies.rotation.backtest import (
    RsRotationReport,
    backtest_rs_rotation,
    build_allocation_frame,
)

__all__ = [
    "RsRotationReport",
    "backtest_rs_rotation",
    "build_allocation_frame",
]
