"""R2 market-data freshness gate tests (#4013, Phase B Task 6).

A silent universe drop or a stale seal must fail loud before a research run
consumes the R2 generations. ``_FixedDate`` freezes ``date.today()`` so the
age arithmetic is deterministic regardless of the wall clock.
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.data.freshness import assert_market_data_fresh

# Registers Task 1's `r2_market` builder fixture for this module; pytest requires
# plugin modules to be named here rather than imported (an imported fixture would
# collide with the fixture-name parameters below under ruff F811).
pytest_plugins = ["tests.fixtures.r2_market"]

pytestmark = pytest.mark.unit


class _FixedDate(date):
    """``date`` shim whose ``today()`` is the freshness fixtures' seal date."""

    @classmethod
    def today(cls) -> "_FixedDate":
        return cls(2026, 9, 13)


def test_fresh_seal_passes(r2_market, monkeypatch: pytest.MonkeyPatch) -> None:
    r2_market(
        {f"T{i}": [{"date": "2026-09-13", "close": 1.0}] for i in range(120)},
        as_of="2026-09-13",
    )
    monkeypatch.setattr("digiquant.research.data.freshness.date", _FixedDate)
    assert_market_data_fresh(max_age_days=0, min_tickers=100)


def test_stale_seal_raises(r2_market, monkeypatch: pytest.MonkeyPatch) -> None:
    r2_market({"SPY": [{"date": "2026-09-01", "close": 1.0}]}, as_of="2026-09-01")
    monkeypatch.setattr("digiquant.research.data.freshness.date", _FixedDate)
    with pytest.raises(RuntimeError, match="stale"):
        assert_market_data_fresh(max_age_days=1, min_tickers=1)


def test_collapsed_universe_raises(r2_market, monkeypatch: pytest.MonkeyPatch) -> None:
    r2_market(
        {f"T{i}": [{"date": "2026-09-13", "close": 1.0}] for i in range(3)},
        as_of="2026-09-13",
    )
    monkeypatch.setattr("digiquant.research.data.freshness.date", _FixedDate)
    with pytest.raises(RuntimeError, match="collapsed"):
        assert_market_data_fresh(max_age_days=0, min_tickers=100)
