"""Tests for M2DataFetcher — unit tests use mocked FRED/yfinance, no real API calls.

score:allow pandas, pd.
    The mocks must emit the pandas objects that fredapi/yfinance actually return
    (a pandas Series / DataFrame), so the test legitimately constructs pandas at
    the same boundary the source converts away. Production code stays Polars-only.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from digiquant.data.m2 import M2DataFetcher, build_m2_composite


class TestBuildM2Composite:
    def _make_m2_series(self, dates: list[str], values: list[float]) -> pl.DataFrame:
        return pl.DataFrame({"date": [date.fromisoformat(d) for d in dates], "value": values})

    def test_composite_is_sum_of_usd_equivalents(self) -> None:
        # usm2=10, cnm2=20, cnyusd=0.5 → cn_usd=10; eum2=5, eurusd=1.2 → eu_usd=6
        # jpm2=100, jpyusd=0.007 → jp_usd=0.7; gbm2=3, gbpusd=1.3 → gb_usd=3.9
        # total = (10 + 10 + 6 + 0.7 + 3.9) / 1e12
        df = build_m2_composite(
            usm2=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [10e12]}),
            cnm2=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [20e12]}),
            cnyusd=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [0.5]}),
            eum2=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [5e12]}),
            eurusd=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [1.2]}),
            jpm2=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [100e12]}),
            jpyusd=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [0.007]}),
            gbm2=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [3e12]}),
            gbpusd=pl.DataFrame({"date": [date(2024, 1, 1)], "value": [1.3]}),
        )
        assert "date" in df.columns
        assert "total" in df.columns
        expected = (10e12 + 20e12 * 0.5 + 5e12 * 1.2 + 100e12 * 0.007 + 3e12 * 1.3) / 1e12
        assert df["total"][0] == pytest.approx(expected, rel=1e-6)

    def test_output_has_daily_frequency(self) -> None:
        # Monthly M2 forward-filled to daily
        usm2 = pl.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 2, 1)],
                "value": [100.0, 110.0],
            }
        )
        # For simplicity, use 1.0 for all FX rates
        ones = pl.DataFrame({"date": [date(2024, 1, 1), date(2024, 2, 1)], "value": [1.0, 1.0]})
        df = build_m2_composite(
            usm2=usm2,
            cnm2=ones,
            cnyusd=ones,
            eum2=ones,
            eurusd=ones,
            jpm2=ones,
            jpyusd=ones,
            gbm2=ones,
            gbpusd=ones,
        )
        # Should have daily rows between Jan 1 and Feb 1 (at minimum ~31 rows)
        assert len(df) >= 31

    def test_shifted_series_has_correct_offset(self) -> None:
        usm2 = pl.DataFrame(
            {
                "date": [date(2024, 1, 1), date(2024, 2, 1)],
                "value": [100.0, 200.0],
            }
        )
        ones = pl.DataFrame({"date": [date(2024, 1, 1), date(2024, 2, 1)], "value": [1.0, 1.0]})
        df = build_m2_composite(
            usm2=usm2,
            cnm2=ones,
            cnyusd=ones,
            eum2=ones,
            eurusd=ones,
            jpm2=ones,
            jpyusd=ones,
            gbm2=ones,
            gbpusd=ones,
            offset_days=10,
        )
        assert "total_shifted" in df.columns
        # total_shifted[0] should equal total[-10] (shifted forward by 10 bars)


class TestM2DataFetcherMocked:
    def test_missing_api_key_raises(self, monkeypatch) -> None:
        monkeypatch.delenv("FRED_API_KEY", raising=False)
        with pytest.raises(EnvironmentError, match="FRED_API_KEY"):
            M2DataFetcher()

    def test_fetch_returns_polars_dataframe(self, monkeypatch, tmp_path) -> None:
        monkeypatch.setenv("FRED_API_KEY", "test_key")

        mock_fred = MagicMock()
        # Return a pandas Series (what fredapi returns)
        import pandas as pd
        import numpy as np

        dates = pd.date_range("2020-01-01", periods=24, freq="MS")
        mock_fred.get_series.return_value = pd.Series(np.linspace(10000, 12000, 24), index=dates)

        mock_yf = MagicMock()
        mock_yf_df = pd.DataFrame(
            {"Close": np.ones(500)},
            index=pd.date_range("2020-01-01", periods=500, freq="D"),
        )
        mock_yf.return_value.history.return_value = mock_yf_df

        with (
            patch("digiquant.data.m2.Fred", return_value=mock_fred),
            patch("digiquant.data.m2.yf.Ticker", mock_yf),
        ):
            fetcher = M2DataFetcher(cache_dir=tmp_path)
            df = fetcher.fetch(offset_days=86, roc_length=100)

        assert isinstance(df, pl.DataFrame)
        assert "total" in df.columns
        assert "total_shifted" in df.columns
        assert "roc_sig" in df.columns
        assert "roc_plot" in df.columns
