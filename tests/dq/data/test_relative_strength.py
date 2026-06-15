"""Tests for sector relative-strength compute (Pillar 1D)."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from digiquant.data.prices.relative_strength import compute_relative_strength


def _rows() -> list[dict]:
    # 4 closes per ticker; window=2 → return = close[-1] / close[-3] - 1.
    # SPY: 110/100 - 1 = 0.10 ; XLK: 121/100 - 1 = 0.21 ; XLF: 105/100 - 1 = 0.05.
    dates = ["2026-06-10", "2026-06-11", "2026-06-12", "2026-06-15"]
    series = {
        "SPY": [100.0, 100.0, 100.0, 110.0],
        "XLK": [100.0, 100.0, 100.0, 121.0],
        "XLF": [100.0, 100.0, 100.0, 105.0],
    }
    return [
        {"date": d, "ticker": t, "close": c}
        for t, closes in series.items()
        for d, c in zip(dates, closes)
    ]


@pytest.mark.unit
class TestComputeRelativeStrength:
    def test_excess_return_rank_and_trend(self) -> None:
        out = compute_relative_strength(
            pl.DataFrame(_rows()), benchmark="SPY", windows=(2,), as_of=date(2026, 6, 15)
        )
        assert "SPY" not in out  # benchmark excluded
        assert out["XLK"]["rs_2d"] == 11.0  # (0.21 - 0.10) * 100
        assert out["XLF"]["rs_2d"] == -5.0  # (0.05 - 0.10) * 100
        # XLK strongest → rank 1.0 / leading ; XLF weakest → lagging.
        assert out["XLK"]["rs_rank"] == 1.0
        assert out["XLK"]["trend"] == "leading"
        assert out["XLF"]["trend"] == "lagging"

    def test_missing_benchmark_returns_empty(self) -> None:
        rows = [r for r in _rows() if r["ticker"] != "SPY"]
        out = compute_relative_strength(
            pl.DataFrame(rows), benchmark="SPY", windows=(2,), as_of=date(2026, 6, 15)
        )
        assert out == {}

    def test_window_longer_than_history_yields_none(self) -> None:
        out = compute_relative_strength(
            pl.DataFrame(_rows()), benchmark="SPY", windows=(100,), as_of=date(2026, 6, 15)
        )
        # Not enough rows for a 100-day window → excess is None, no rank assigned.
        assert out["XLK"]["rs_100d"] is None
        assert "rs_rank" not in out["XLK"]

    def test_empty_frame(self) -> None:
        assert compute_relative_strength(pl.DataFrame(), as_of=date(2026, 6, 15)) == {}
