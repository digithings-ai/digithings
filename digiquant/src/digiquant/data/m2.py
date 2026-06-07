"""M2 global liquidity data fetching and composite computation.

Replicates the TradingView M2 Liquidity strategy's data sourcing:
  total = (CNM2*CNYUSD + USM2 + EUM2*EURUSD + JPM2*JPYUSD + GBM2*GBPUSD) / 1e12

FRED series IDs:
  USM2  → M2SL            EUM2 → MABMM301EZM189S
  CNM2  → MABMM301CNM189S JPM2 → MABMM301JPM189S
  GBM2  → MABMM301GBM189S

FX rates fetched via yfinance (daily tickers: CNYUSD=X, EURUSD=X, JPYUSD=X, GBPUSD=X).

All M2 series are monthly; this module forward-fills them to daily frequency
before computing the composite.
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import polars as pl
import yfinance as yf
from fredapi import Fred

_FRED_SERIES = {
    "usm2": "M2SL",
    "cnm2": "MABMM301CNM189S",
    "eum2": "MABMM301EZM189S",
    "jpm2": "MABMM301JPM189S",
    "gbm2": "MABMM301GBM189S",
}

_FX_TICKERS = {
    "cnyusd": "CNYUSD=X",
    "eurusd": "EURUSD=X",
    "jpyusd": "JPYUSD=X",
    "gbpusd": "GBPUSD=X",
}

_CACHE_FILENAME = "m2_composite.parquet"


def _fred_series_to_polars(series, name: str) -> pl.DataFrame:
    """Convert a fredapi pandas Series to a Polars DataFrame with columns [date, value]."""
    import pandas as pd

    df = series.reset_index()
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return pl.from_pandas(df).with_columns(pl.col("value").cast(pl.Float64))


def _yf_to_polars(ticker_obj, name: str) -> pl.DataFrame:
    """Fetch daily close prices from yfinance and return as Polars [date, value]."""
    hist = ticker_obj.history(period="max", auto_adjust=True)
    import pandas as pd

    hist = hist[["Close"]].rename(columns={"Close": "value"})
    hist.index = pd.to_datetime(hist.index).date
    hist.index.name = "date"
    hist = hist.reset_index()
    return pl.from_pandas(hist).with_columns(pl.col("value").cast(pl.Float64))


def _forward_fill_to_daily(df: pl.DataFrame, start: date, end: date) -> pl.DataFrame:
    """Forward-fill a monthly Polars DataFrame [date, value] to daily frequency."""
    all_dates = pl.DataFrame(
        {"date": [start + timedelta(days=i) for i in range((end - start).days + 1)]}
    )
    return all_dates.join(df, on="date", how="left").with_columns(pl.col("value").forward_fill())


def build_m2_composite(
    *,
    usm2: pl.DataFrame,
    cnm2: pl.DataFrame,
    cnyusd: pl.DataFrame,
    eum2: pl.DataFrame,
    eurusd: pl.DataFrame,
    jpm2: pl.DataFrame,
    jpyusd: pl.DataFrame,
    gbm2: pl.DataFrame,
    gbpusd: pl.DataFrame,
    offset_days: int = 86,
    roc_length: int = 100,
) -> pl.DataFrame:
    """Compute the M2 composite from pre-fetched component DataFrames.

    Each input is a Polars DataFrame with columns [date: date, value: Float64].
    Monthly M2 series are forward-filled to daily frequency.
    Returns a DataFrame with columns: date, total, total_shifted, roc_sig, roc_plot.
    """
    # Determine date range
    all_starts = [df["date"].min() for df in [usm2, cnm2, eum2, jpm2, gbm2]]
    all_ends = [df["date"].max() for df in [cnyusd, eurusd, jpyusd, gbpusd]]
    start = max(d for d in all_starts if d is not None)
    end = min(d for d in all_ends if d is not None)

    def _ffill(df: pl.DataFrame) -> pl.DataFrame:
        return _forward_fill_to_daily(df, start, end)

    daily_usm2 = _ffill(usm2)
    daily_cnm2 = _ffill(cnm2)
    daily_eum2 = _ffill(eum2)
    daily_jpm2 = _ffill(jpm2)
    daily_gbm2 = _ffill(gbm2)
    daily_cnyusd = _ffill(cnyusd)
    daily_eurusd = _ffill(eurusd)
    daily_jpyusd = _ffill(jpyusd)
    daily_gbpusd = _ffill(gbpusd)

    # Join all on date
    base = daily_usm2.rename({"value": "usm2"})
    for name, df in [
        ("cnm2", daily_cnm2),
        ("eum2", daily_eum2),
        ("jpm2", daily_jpm2),
        ("gbm2", daily_gbm2),
        ("cnyusd", daily_cnyusd),
        ("eurusd", daily_eurusd),
        ("jpyusd", daily_jpyusd),
        ("gbpusd", daily_gbpusd),
    ]:
        base = base.join(df.rename({"value": name}), on="date", how="left")

    base = base.with_columns(
        (
            (
                pl.col("cnm2") * pl.col("cnyusd")
                + pl.col("usm2")
                + pl.col("eum2") * pl.col("eurusd")
                + pl.col("jpm2") * pl.col("jpyusd")
                + pl.col("gbm2") * pl.col("gbpusd")
            )
            / 1e12
        ).alias("total")
    )

    # Time shift: total_shifted[t] = total[t - offset_days]
    base = base.with_columns(pl.col("total").shift(offset_days).alias("total_shifted"))

    # ROC series
    base = base.with_columns(
        [
            (
                100.0
                * (pl.col("total_shifted") - pl.col("total_shifted").shift(roc_length))
                / pl.col("total_shifted").shift(roc_length)
            ).alias("roc_sig"),
            (
                100.0
                * (pl.col("total") - pl.col("total").shift(roc_length))
                / pl.col("total").shift(roc_length)
            ).alias("roc_plot"),
        ]
    )

    return base.select(["date", "total", "total_shifted", "roc_sig", "roc_plot"])


class M2DataFetcher:
    """Fetches M2 + FX data from FRED and yfinance, caches as parquet.

    Requires env var: FRED_API_KEY (free at https://fred.stlouisfed.org/docs/api/api_key.html)
    """

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        api_key = os.environ.get("FRED_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "FRED_API_KEY environment variable not set. "
                "Get a free key at https://fred.stlouisfed.org/docs/api/api_key.html"
            )
        self._fred = Fred(api_key=api_key)
        self._cache_dir = Path(cache_dir) if cache_dir else Path.home() / ".digiquant" / "cache"
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(
        self,
        offset_days: int = 86,
        roc_length: int = 100,
        force_refresh: bool = False,
    ) -> pl.DataFrame:
        """Return M2 composite DataFrame. Uses cached parquet if available."""
        cache_path = self._cache_dir / _CACHE_FILENAME
        if cache_path.exists() and not force_refresh:
            return pl.read_parquet(cache_path)

        fred_dfs = {
            name: _fred_series_to_polars(self._fred.get_series(series_id), name)
            for name, series_id in _FRED_SERIES.items()
        }

        fx_dfs = {
            name: _yf_to_polars(yf.Ticker(ticker), name) for name, ticker in _FX_TICKERS.items()
        }

        df = build_m2_composite(
            usm2=fred_dfs["usm2"],
            cnm2=fred_dfs["cnm2"],
            cnyusd=fx_dfs["cnyusd"],
            eum2=fred_dfs["eum2"],
            eurusd=fx_dfs["eurusd"],
            jpm2=fred_dfs["jpm2"],
            jpyusd=fx_dfs["jpyusd"],
            gbm2=fred_dfs["gbm2"],
            gbpusd=fx_dfs["gbpusd"],
            offset_days=offset_days,
            roc_length=roc_length,
        )

        df.write_parquet(cache_path)
        return df
