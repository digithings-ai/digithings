"""digiquant stats package — honesty envelope (#4828)."""

from __future__ import annotations

from .honesty import (
    DISCLAIMER,
    REFUSE_FLOOR,
    WARN_FLOOR,
    Z_95,
    GuardResult,
    HalfStats,
    HonestRate,
    HonestRateBlock,
    StabilitySplit,
    Wilson,
    apply_guards,
    format_honest_rate,
    honest_rate,
    stability_split,
    wilson,
)
from .series import normalize_series

__all__ = [
    "DISCLAIMER",
    "REFUSE_FLOOR",
    "WARN_FLOOR",
    "Z_95",
    "GuardResult",
    "HalfStats",
    "HonestRate",
    "HonestRateBlock",
    "StabilitySplit",
    "Wilson",
    "apply_guards",
    "format_honest_rate",
    "honest_rate",
    "normalize_series",
    "stability_split",
    "wilson",
]
