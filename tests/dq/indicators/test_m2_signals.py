"""Tests for M2SignalComputer — 5 indicator states + aggregate vote."""

from __future__ import annotations

import numpy as np
import polars as pl
from digiquant.indicators.m2_signals import M2SignalComputer


def _make_m2_df(n: int = 300) -> pl.DataFrame:
    """Generate synthetic M2 composite DataFrame for testing."""
    rng = np.random.default_rng(42)
    dates = pl.date_range(
        start=pl.date(2019, 1, 1),
        end=pl.date(2019, 1, 1) + pl.duration(days=n - 1),
        interval="1d",
        eager=True,
    )
    total = pl.Series("total", 20.0 + np.cumsum(rng.standard_normal(n)) * 0.1)
    shifted = total.shift(86).alias("total_shifted")
    roc_sig = (100.0 * (shifted - shifted.shift(100)) / shifted.shift(100)).alias("roc_sig")
    roc_plot = (100.0 * (total - total.shift(100)) / total.shift(100)).alias("roc_plot")
    close = pl.Series("close", 30000.0 + np.cumsum(rng.standard_normal(n)) * 500)
    return pl.DataFrame([dates.alias("date"), total, shifted, roc_sig, roc_plot, close])


class TestM2SignalComputer:
    def test_output_has_required_columns(self) -> None:
        df = _make_m2_df()
        comp = M2SignalComputer()
        result = comp.compute(df)
        for col in [
            "state1",
            "state2",
            "state3",
            "state4",
            "state5",
            "avg_score",
            "buy_signal",
            "sell_signal",
        ]:
            assert col in result.columns, f"Missing column: {col}"

    def test_states_are_0_or_1(self) -> None:
        df = _make_m2_df()
        comp = M2SignalComputer()
        result = comp.compute(df)
        for col in ["state1", "state2", "state3", "state4", "state5"]:
            vals = result[col].drop_nulls().unique().sort().to_list()
            assert all(v in (0, 1) for v in vals), f"{col} has values outside {{0, 1}}: {vals}"

    def test_avg_score_between_0_and_1(self) -> None:
        df = _make_m2_df()
        comp = M2SignalComputer()
        result = comp.compute(df)
        valid = result["avg_score"].drop_nulls()
        assert valid.min() >= 0.0
        assert valid.max() <= 1.0

    def test_buy_sell_are_boolean(self) -> None:
        df = _make_m2_df()
        comp = M2SignalComputer()
        result = comp.compute(df)
        assert result["buy_signal"].dtype == pl.Boolean
        assert result["sell_signal"].dtype == pl.Boolean

    def test_buy_and_sell_not_simultaneously_true(self) -> None:
        df = _make_m2_df()
        comp = M2SignalComputer()
        result = comp.compute(df)
        both = result.filter(pl.col("buy_signal") & pl.col("sell_signal"))
        assert len(both) == 0, "buy_signal and sell_signal should never both be True on same bar"

    def test_custom_weights(self) -> None:
        df = _make_m2_df()
        # Disable ind2, ind4
        comp = M2SignalComputer(
            use_ind1=True, use_ind2=False, use_ind3=True, use_ind4=False, use_ind5=True
        )
        result = comp.compute(df)
        # avg_score should only use 3 indicators
        assert "avg_score" in result.columns

    def test_same_length_as_input(self) -> None:
        df = _make_m2_df(200)
        comp = M2SignalComputer()
        result = comp.compute(df)
        assert len(result) == len(df)
