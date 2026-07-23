"""Shared preference semantics for advisory position risk envelopes."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any  # noqa  # scored-lint suppression: duck-typed preferences mapping from Supabase rows

DEFAULT_RISK_HORIZON_DAYS = 21


def risk_horizon_days(preferences: Mapping[str, Any]) -> int:
    """Return the explicit risk horizon without reusing decision evaluation days."""
    value = preferences.get("risk_horizon_days")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return int(value)
    return DEFAULT_RISK_HORIZON_DAYS


__all__ = ["DEFAULT_RISK_HORIZON_DAYS", "risk_horizon_days"]
