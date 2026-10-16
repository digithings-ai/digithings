"""Unit tests for TradingProfile constraint conversion."""

from __future__ import annotations

import pytest
from digigraph.trading_profile import optimization_constraints_dict_from_profile


@pytest.mark.unit
def test_profile_drawdown_fraction_converts_to_digiquant_percent() -> None:
    constraints = optimization_constraints_dict_from_profile({"max_drawdown_pct": -0.2})

    assert constraints == {"max_drawdown_pct": -20.0}
