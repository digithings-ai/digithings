from __future__ import annotations

import pytest
from digiquant.stages import ConsensusTimeframe, split_timeframe

pytestmark = pytest.mark.unit


def test_medium_and_long_are_consensus() -> None:
    assert split_timeframe("medium") == (ConsensusTimeframe.MEDIUM, None)
    assert split_timeframe("long") == (ConsensusTimeframe.LONG, None)


def test_free_string_is_display_only() -> None:
    assert split_timeframe("1-3M") == (None, "1-3M")
    assert split_timeframe(" Medium ") == (None, "Medium")


def test_blank_is_neither() -> None:
    assert split_timeframe(None) == (None, None)
    assert split_timeframe("  ") == (None, None)
