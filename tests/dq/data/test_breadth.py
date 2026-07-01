"""Tests for market-breadth compute (Pillar 1D)."""

from __future__ import annotations

from datetime import date

import polars as pl
import pytest

from digiquant.data.prices.breadth import compute_breadth


def _rows() -> list[dict]:
    # 4 tickers over a prior (06-12) and current (06-15) day.
    # current above-50dma: A,B,C positive, D negative → 75%.
    # current above-200dma: A,B positive, C,D negative → 50%.
    # prior above-50dma: A positive, B,C,D negative → 25%  → trend improving.
    return [
        {"ticker": "A", "date": "2026-06-12", "pct_vs_sma50": 1.0, "pct_vs_sma200": 1.0},
        {"ticker": "A", "date": "2026-06-15", "pct_vs_sma50": 1.0, "pct_vs_sma200": 1.0},
        {"ticker": "B", "date": "2026-06-12", "pct_vs_sma50": -1.0, "pct_vs_sma200": 1.0},
        {"ticker": "B", "date": "2026-06-15", "pct_vs_sma50": 1.0, "pct_vs_sma200": 1.0},
        {"ticker": "C", "date": "2026-06-12", "pct_vs_sma50": -1.0, "pct_vs_sma200": -1.0},
        {"ticker": "C", "date": "2026-06-15", "pct_vs_sma50": 1.0, "pct_vs_sma200": -1.0},
        {"ticker": "D", "date": "2026-06-12", "pct_vs_sma50": -1.0, "pct_vs_sma200": -1.0},
        {"ticker": "D", "date": "2026-06-15", "pct_vs_sma50": -1.0, "pct_vs_sma200": -1.0},
    ]


@pytest.mark.unit
class TestComputeBreadth:
    def test_pct_above_ma_and_improving_trend(self) -> None:
        out = compute_breadth(pl.DataFrame(_rows()), as_of=date(2026, 6, 15))
        assert out["universe_size"] == 4
        assert out["pct_above_50dma"] == 75.0
        assert out["pct_above_200dma"] == 50.0
        assert out["pct_above_50dma_prior"] == 25.0
        assert out["breadth_trend"] == "improving"

    def test_respects_as_of_cutoff(self) -> None:
        # As of the prior day, only the 06-12 rows count → 25% above 50dma, no prior.
        out = compute_breadth(pl.DataFrame(_rows()), as_of=date(2026, 6, 12))
        assert out["universe_size"] == 4
        assert out["pct_above_50dma"] == 25.0

    def test_empty_frame(self) -> None:
        out = compute_breadth(pl.DataFrame(), as_of=date(2026, 6, 15))
        assert out == {"as_of": "2026-06-15", "universe_size": 0}

    def test_accepts_real_date_dtype(self) -> None:
        frame = pl.DataFrame(_rows()).with_columns(pl.col("date").str.to_date())
        out = compute_breadth(frame, as_of=date(2026, 6, 15))
        assert out["pct_above_50dma"] == 75.0
