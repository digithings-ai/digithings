# M2 Liquidity Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the "M2 Liquidity BTC" PineScript strategy into a Python backtest: fetch global M2 money supply from FRED, compute a time-shifted composite, derive 5 sub-indicator states, aggregate into a voting signal, and run it through the NautilusTrader pipeline.

**Architecture:** A `M2DataFetcher` module fetches and caches M2 + FX data from FRED (free API) into a Polars DataFrame. A `M2SignalComputer` computes all 5 indicator states and the aggregate vote on that DataFrame. `M2LiquidityStrategy` pre-loads the signal series at start and reads pre-computed buy/sell flags on each bar — avoiding the complexity of injecting custom data types into NautilusTrader's live event loop.

**Tech Stack:** Python 3.12, Polars, `fredapi>=0.5`, `yfinance>=0.2` (already in digiquant deps for FX rates), NautilusTrader ≥1.190, statsmodels (already added in Slapper plan), existing `digiquant.strategies.registry`.

---

## ⚠️ Data Source Notes

- TradingView tickers like `ECONOMICS:USM2` map to FRED series. The mapping is:
  | Pine ticker | FRED series ID |
  |---|---|
  | `ECONOMICS:USM2` | `M2SL` (monthly, billions USD) |
  | `ECONOMICS:EUM2` | `MABMM301EZM189S` (monthly) |
  | `ECONOMICS:CNM2` | `MABMM301CNM189S` (monthly) |
  | `ECONOMICS:JPM2` | `MABMM301JPM189S` (monthly) |
  | `ECONOMICS:GBM2` | `MABMM301GBM189S` (monthly) |
- FRED data is monthly. The strategy applies `offset` days of forward-shift; this is still valid on a daily chart — the monthly M2 value is forward-filled to daily.
- FX rates (CNYUSD, JPYUSD, GBPUSD, EURUSD) are fetched from yfinance at daily frequency, then resampled to align with M2.
- FRED requires a free API key: set `FRED_API_KEY` env var. The fetcher raises `EnvironmentError` if missing.

---

## File Structure

**New files:**
```
digiquant/src/digiquant/data/m2.py              # M2DataFetcher: FRED + FX fetch, composite, cache
digiquant/src/digiquant/indicators/m2_signals.py  # M2SignalComputer: 5 indicators + aggregate
digiquant/src/digiquant/strategies/m2_liquidity.py  # M2LiquidityConfig + M2LiquidityStrategy
tests/dq/data/test_m2.py
tests/dq/indicators/test_m2_signals.py
tests/dq/strategies/test_m2_liquidity_config.py
```

**Modified files:**
```
digiquant/pyproject.toml   # add fredapi to optional deps
digiquant/src/digiquant/indicators/__init__.py  # export M2SignalComputer
```

---

## Task 1: Add fredapi dependency

**Files:**
- Modify: `digiquant/pyproject.toml`

- [ ] **Step 1: Add fredapi to pyproject.toml**

In `digiquant/pyproject.toml`, add a new optional group:

```toml
m2 = ["fredapi>=0.5", "yfinance>=0.2"]
```

Update the `dev` extras to include it:

```toml
dev = ["digiquant[atlas]", "digiquant[indicators]", "digiquant[m2]", "pytest>=8", "pytest-cov>=4", "ruff>=0.8"]
```

- [ ] **Step 2: Install**

```bash
cd digiquant && pip install -e ".[m2,dev]"
python -c "import fredapi; print('fredapi ok')"
```

Expected: `fredapi ok`

- [ ] **Step 3: Commit**

```bash
git add digiquant/pyproject.toml
git commit -m "feat(digiquant): add fredapi dep for M2 Liquidity strategy"
```

---

## Task 2: M2 data fetcher

**Files:**
- Create: `digiquant/src/digiquant/data/m2.py`
- Create: `tests/dq/data/test_m2.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dq/data/test_m2.py`:

```python
"""Tests for M2DataFetcher — unit tests use mocked FRED/yfinance, no real API calls."""
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
        dates = ["2024-01-01"]
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
        usm2 = pl.DataFrame({
            "date": [date(2024, 1, 1), date(2024, 2, 1)],
            "value": [100.0, 110.0],
        })
        # For simplicity, use 1.0 for all FX rates
        ones = pl.DataFrame({"date": [date(2024, 1, 1), date(2024, 2, 1)], "value": [1.0, 1.0]})
        df = build_m2_composite(
            usm2=usm2, cnm2=ones, cnyusd=ones, eum2=ones, eurusd=ones,
            jpm2=ones, jpyusd=ones, gbm2=ones, gbpusd=ones,
        )
        # Should have daily rows between Jan 1 and Feb 1 (at minimum ~31 rows)
        assert len(df) >= 31

    def test_shifted_series_has_correct_offset(self) -> None:
        usm2 = pl.DataFrame({
            "date": [date(2024, 1, 1), date(2024, 2, 1)],
            "value": [100.0, 200.0],
        })
        ones = pl.DataFrame({"date": [date(2024, 1, 1), date(2024, 2, 1)], "value": [1.0, 1.0]})
        df = build_m2_composite(
            usm2=usm2, cnm2=ones, cnyusd=ones, eum2=ones, eurusd=ones,
            jpm2=ones, jpyusd=ones, gbm2=ones, gbpusd=ones,
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
        mock_fred.get_series.return_value = pd.Series(
            np.linspace(10000, 12000, 24), index=dates
        )

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
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/dq/data/test_m2.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'digiquant.data.m2'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/data/m2.py`**

```python
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
    return (
        all_dates.join(df, on="date", how="left")
        .with_columns(pl.col("value").forward_fill())
    )


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
        ("cnm2", daily_cnm2), ("eum2", daily_eum2), ("jpm2", daily_jpm2), ("gbm2", daily_gbm2),
        ("cnyusd", daily_cnyusd), ("eurusd", daily_eurusd),
        ("jpyusd", daily_jpyusd), ("gbpusd", daily_gbpusd),
    ]:
        base = base.join(df.rename({"value": name}), on="date", how="left")

    base = base.with_columns(
        (
            (pl.col("cnm2") * pl.col("cnyusd")
             + pl.col("usm2")
             + pl.col("eum2") * pl.col("eurusd")
             + pl.col("jpm2") * pl.col("jpyusd")
             + pl.col("gbm2") * pl.col("gbpusd")) / 1e12
        ).alias("total")
    )

    # Time shift: total_shifted[t] = total[t - offset_days]
    base = base.with_columns(
        pl.col("total").shift(offset_days).alias("total_shifted")
    )

    # ROC series
    base = base.with_columns([
        (100.0 * (pl.col("total_shifted") - pl.col("total_shifted").shift(roc_length))
         / pl.col("total_shifted").shift(roc_length)).alias("roc_sig"),
        (100.0 * (pl.col("total") - pl.col("total").shift(roc_length))
         / pl.col("total").shift(roc_length)).alias("roc_plot"),
    ])

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
        from fredapi import Fred

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
        import yfinance as yf

        cache_path = self._cache_dir / _CACHE_FILENAME
        if cache_path.exists() and not force_refresh:
            return pl.read_parquet(cache_path)

        fred_dfs = {
            name: _fred_series_to_polars(self._fred.get_series(series_id), name)
            for name, series_id in _FRED_SERIES.items()
        }

        fx_dfs = {
            name: _yf_to_polars(yf.Ticker(ticker), name)
            for name, ticker in _FX_TICKERS.items()
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
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dq/data/test_m2.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/data/m2.py tests/dq/data/test_m2.py
git commit -m "feat(data): add M2DataFetcher — FRED + FX composite with daily forward-fill and cache"
```

---

## Task 3: M2 signal computer (5 indicators + aggregate)

**Files:**
- Create: `digiquant/src/digiquant/indicators/m2_signals.py`
- Create: `tests/dq/indicators/test_m2_signals.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dq/indicators/test_m2_signals.py`:

```python
"""Tests for M2SignalComputer — 5 indicator states + aggregate vote."""
from __future__ import annotations

import numpy as np
import polars as pl
import pytest
from digiquant.indicators.m2_signals import M2SignalComputer


def _make_m2_df(n: int = 300) -> pl.DataFrame:
    """Generate synthetic M2 composite DataFrame for testing."""
    rng = np.random.default_rng(42)
    dates = pl.date_range(
        start=pl.date(2019, 1, 1), end=pl.date(2019, 1, 1) + pl.duration(days=n - 1),
        interval="1d", eager=True,
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
        for col in ["state1", "state2", "state3", "state4", "state5", "avg_score", "buy_signal", "sell_signal"]:
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
        comp = M2SignalComputer(use_ind1=True, use_ind2=False, use_ind3=True, use_ind4=False, use_ind5=True)
        result = comp.compute(df)
        # avg_score should only use 3 indicators
        assert "avg_score" in result.columns

    def test_same_length_as_input(self) -> None:
        df = _make_m2_df(200)
        comp = M2SignalComputer()
        result = comp.compute(df)
        assert len(result) == len(df)
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/dq/indicators/test_m2_signals.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'digiquant.indicators.m2_signals'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/indicators/m2_signals.py`**

```python
"""M2 Liquidity signal computation — 5 sub-indicators on M2 ROC.

Converts the 5-indicator system from the PineScript M2 Liquidity strategy
into vectorized Polars expressions. Each indicator produces a state column
(0 = bear, 1 = bull). The aggregate vote fires buy/sell when the score
crosses 0.5.

Input DataFrame must contain columns: total, total_shifted, roc_sig, roc_plot, close.
All indicator computations operate on the `_sig` variants for strategy entries.
"""
from __future__ import annotations

import polars as pl


def _rsi_series(series: pl.Series, length: int) -> pl.Series:
    """Compute RSI on an arbitrary Polars Series using Wilder's smoothing."""
    change = series.diff()
    gain = change.map_elements(lambda x: max(x, 0.0), return_dtype=pl.Float64)
    loss = change.map_elements(lambda x: max(-x, 0.0), return_dtype=pl.Float64)
    avg_gain = gain.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=length)
    avg_loss = loss.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=length)
    rs = avg_gain / avg_loss
    rsi = pl.when(avg_loss == 0).then(100.0).when(avg_gain == 0).then(0.0).otherwise(
        100.0 - (100.0 / (1.0 + rs))
    )
    return rsi.alias("rsi")


def _wilder_ma(series: pl.Series, length: int) -> pl.Series:
    return series.ewm_mean(alpha=1.0 / length, adjust=False, min_periods=length)


def _sma(series: pl.Series, length: int) -> pl.Series:
    return series.rolling_mean(window_size=length, min_periods=length)


def _rma(series: pl.Series, length: int) -> pl.Series:
    return _wilder_ma(series, length)


def _ema(series: pl.Series, length: int) -> pl.Series:
    return series.ewm_mean(span=length, adjust=False, min_periods=length)


def _wma(series: pl.Series, length: int) -> pl.Series:
    weights = list(range(1, length + 1))
    denom = float(sum(weights))
    return series.rolling_map(
        lambda x: sum(w * v for w, v in zip(weights, x)) / denom,
        window_size=length, min_periods=length,
    )


def _make_ma_series(series: pl.Series, length: int, ma_type: str) -> pl.Series:
    match ma_type.upper():
        case "SMA":
            return _sma(series, length)
        case "EMA":
            return _ema(series, length)
        case "RMA":
            return _rma(series, length)
        case "WMA":
            return _wma(series, length)
        case _:
            return _ema(series, length)


def _state_from_crossovers(bull: pl.Series, bear: pl.Series) -> pl.Series:
    """Build a latching 0/1 state series from bull/bear crossover boolean series."""
    states = []
    current = 0
    for b, br in zip(bull.to_list(), bear.to_list()):
        if b:
            current = 1
        elif br:
            current = 0
        states.append(current)
    return pl.Series("state", states, dtype=pl.Int32)


class M2SignalComputer:
    """Compute all 5 M2 sub-indicator states and the aggregate buy/sell signal.

    Parameters match the PineScript defaults. All can be overridden at init time.
    """

    def __init__(
        self,
        # Ind 1 — RSI of M2 ROC
        use_ind1: bool = True,
        rsi_len: int = 21,
        rsi_ma_len: int = 9,
        # Ind 2 — Relative Strength vs M2
        use_ind2: bool = True,
        rs_lb: int = 100,
        rs_smo: int = 14,
        zs_per: int = 100,
        # Ind 3 — ROC MA cross
        use_ind3: bool = True,
        roc_ma_type: str = "RMA",
        roc_ma_l: int = 30,
        roc_short_type: str = "RMA",
        roc_short_l: int = 10,
        # Ind 4 — BB%b of M2 ROC
        use_ind4: bool = True,
        bb_len: int = 80,
        bb_mult: float = 2.0,
        # Ind 5 — MACD of M2 total
        use_ind5: bool = True,
        macd_fast: int = 50,
        macd_slow: int = 200,
        macd_signal: int = 10,
    ) -> None:
        self.use_ind1 = use_ind1
        self.rsi_len = rsi_len
        self.rsi_ma_len = rsi_ma_len

        self.use_ind2 = use_ind2
        self.rs_lb = rs_lb
        self.rs_smo = rs_smo
        self.zs_per = zs_per

        self.use_ind3 = use_ind3
        self.roc_ma_type = roc_ma_type
        self.roc_ma_l = roc_ma_l
        self.roc_short_type = roc_short_type
        self.roc_short_l = roc_short_l

        self.use_ind4 = use_ind4
        self.bb_len = bb_len
        self.bb_mult = bb_mult

        self.use_ind5 = use_ind5
        self.macd_fast = macd_fast
        self.macd_slow = macd_slow
        self.macd_signal = macd_signal

    def compute(self, df: pl.DataFrame) -> pl.DataFrame:
        """Compute all states and signals. Returns df with additional signal columns."""
        roc_sig = df["roc_sig"]
        total_shifted = df["total_shifted"]
        close = df["close"]

        # ── Ind 1: RSI of M2 ROC ──────────────────────────────────────────────
        rsi1 = _rsi_series(roc_sig, self.rsi_len)
        rsi1_ma = _rma(rsi1, self.rsi_ma_len)
        bull1 = (rsi1_ma.shift(1) < 50) & (rsi1_ma >= 50)
        bear1 = (rsi1_ma.shift(1) > 50) & (rsi1_ma <= 50)
        state1 = _state_from_crossovers(bull1.fill_null(False), bear1.fill_null(False))

        # ── Ind 2: Relative Strength vs M2 ───────────────────────────────────
        sym_pct = (close / close.shift(self.rs_lb) - 1.0) * 100.0
        m2_pct = (total_shifted / total_shifted.shift(self.rs_lb) - 1.0) * 100.0
        rs_delta = sym_pct - m2_pct
        rs_ma = _sma(rs_delta, self.rs_smo)
        rs_mean = _sma(rs_delta, self.zs_per)
        bull2 = (rs_ma.shift(1) < rs_mean.shift(1)) & (rs_ma >= rs_mean)
        bear2 = (rs_ma.shift(1) > rs_mean.shift(1)) & (rs_ma <= rs_mean)
        state2 = _state_from_crossovers(bull2.fill_null(False), bear2.fill_null(False))

        # ── Ind 3: ROC MA Cross ───────────────────────────────────────────────
        roc_long = _make_ma_series(roc_sig, self.roc_ma_l, self.roc_ma_type)
        roc_short = _make_ma_series(roc_sig, self.roc_short_l, self.roc_short_type)
        bull3 = (roc_short.shift(1) < roc_long.shift(1)) & (roc_short >= roc_long)
        bear3 = (roc_short.shift(1) > roc_long.shift(1)) & (roc_short <= roc_long)
        state3 = _state_from_crossovers(bull3.fill_null(False), bear3.fill_null(False))

        # ── Ind 4: BB%b of M2 ROC ────────────────────────────────────────────
        bb_mid = _sma(roc_sig, self.bb_len)
        bb_std = roc_sig.rolling_std(window_size=self.bb_len, min_periods=self.bb_len, ddof=1)
        bb_up = bb_mid + self.bb_mult * bb_std
        bb_dn = bb_mid - self.bb_mult * bb_std
        bb_range = bb_up - bb_dn
        bbr_raw = pl.when(bb_range == 0).then(0.5).otherwise((roc_sig - bb_dn) / bb_range)
        bbr = _sma(bbr_raw, 9)
        bull4 = (bbr.shift(1) < 0.5) & (bbr >= 0.5)
        bear4 = (bbr.shift(1) > 0.5) & (bbr <= 0.5)
        state4 = _state_from_crossovers(bull4.fill_null(False), bear4.fill_null(False))

        # ── Ind 5: MACD of M2 total ───────────────────────────────────────────
        mf = _sma(total_shifted, self.macd_fast)
        ms = _sma(total_shifted, self.macd_slow)
        mc = mf - ms
        sg = _ema(mc, self.macd_signal)
        hist = mc - sg
        bull5 = (hist.shift(1) < 0) & (hist >= 0)
        bear5 = (hist.shift(1) > 0) & (hist <= 0)
        state5 = _state_from_crossovers(bull5.fill_null(False), bear5.fill_null(False))

        # ── Aggregate vote ───────────────────────────────────────────────────
        active = sum([self.use_ind1, self.use_ind2, self.use_ind3, self.use_ind4, self.use_ind5])
        score_sum = (
            (state1 * int(self.use_ind1))
            + (state2 * int(self.use_ind2))
            + (state3 * int(self.use_ind3))
            + (state4 * int(self.use_ind4))
            + (state5 * int(self.use_ind5))
        )
        avg_score = score_sum.cast(pl.Float64) / float(active) if active > 0 else pl.Series(
            "avg_score", [0.0] * len(df)
        )

        buy_signal = (avg_score.shift(1) < 0.5) & (avg_score >= 0.5)
        sell_signal = (avg_score.shift(1) > 0.5) & (avg_score <= 0.5)

        return df.with_columns([
            state1.alias("state1"),
            state2.alias("state2"),
            state3.alias("state3"),
            state4.alias("state4"),
            state5.alias("state5"),
            avg_score.alias("avg_score"),
            buy_signal.fill_null(False).alias("buy_signal"),
            sell_signal.fill_null(False).alias("sell_signal"),
        ])
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dq/indicators/test_m2_signals.py -v
```

Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/indicators/m2_signals.py tests/dq/indicators/test_m2_signals.py
git commit -m "feat(indicators): add M2SignalComputer — 5-indicator voting aggregate on M2 ROC"
```

---

## Task 4: M2LiquidityStrategy + M2LiquidityConfig

**Files:**
- Create: `digiquant/src/digiquant/strategies/m2_liquidity.py`
- Create: `tests/dq/strategies/test_m2_liquidity_config.py`

- [ ] **Step 1: Write failing tests**

Create `tests/dq/strategies/test_m2_liquidity_config.py`:

```python
"""Tests for M2LiquidityConfig and M2LiquidityStrategy instantiation."""
from __future__ import annotations

import pytest
from datetime import date
import polars as pl
import numpy as np

try:
    from nautilus_trader.model.identifiers import InstrumentId
    from nautilus_trader.model.data import BarType, BarSpecification
    from nautilus_trader.model.enums import BarAggregation, PriceType
    NAUTILUS_AVAILABLE = True
except ImportError:
    NAUTILUS_AVAILABLE = False

pytestmark = pytest.mark.skipif(not NAUTILUS_AVAILABLE, reason="nautilus_trader not installed")


def _write_signal_parquet(tmp_path, n: int = 400) -> tuple[str, int]:
    """Write a synthetic signal parquet, returning (path, row_count)."""
    import datetime as _dt

    rng = np.random.default_rng(0)
    dates = [date(2020, 1, 1) + _dt.timedelta(days=i) for i in range(n)]
    avg = pl.Series("avg_score", rng.uniform(0, 1, n))
    buy = (avg.shift(1) < 0.5) & (avg >= 0.5)
    sell = (avg.shift(1) > 0.5) & (avg <= 0.5)
    df = pl.DataFrame({
        "date": dates,
        "avg_score": avg,
        "buy_signal": buy.fill_null(False),
        "sell_signal": sell.fill_null(False),
    })
    path = tmp_path / "signals.parquet"
    df.write_parquet(path)
    return str(path), n


@pytest.fixture()
def instrument_id():
    return InstrumentId.from_str("BTCUSDT.BINANCE")


@pytest.fixture()
def bar_type(instrument_id):
    spec = BarSpecification(1, BarAggregation.DAY, PriceType.LAST)
    return BarType(instrument_id, spec)


class TestM2LiquidityConfig:
    def test_defaults(self, instrument_id, bar_type, tmp_path) -> None:
        from decimal import Decimal
        from digiquant.strategies.m2_liquidity import M2LiquidityConfig

        path, _ = _write_signal_parquet(tmp_path)
        cfg = M2LiquidityConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
            signal_path=path,
        )
        assert cfg.use_sl is True
        assert cfg.sl_pct == pytest.approx(10.0)
        assert cfg.enable_long is True
        assert cfg.enable_short is False


class TestM2LiquidityStrategyInstantiation:
    def test_can_instantiate(self, instrument_id, bar_type, tmp_path) -> None:
        from decimal import Decimal
        from digiquant.strategies.m2_liquidity import M2LiquidityConfig, M2LiquidityStrategy

        path, _ = _write_signal_parquet(tmp_path)
        cfg = M2LiquidityConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
            signal_path=path,
        )
        strategy = M2LiquidityStrategy(cfg)
        assert strategy is not None

    def test_signal_index_loaded_on_start(self, instrument_id, bar_type, tmp_path) -> None:
        from decimal import Decimal
        from digiquant.strategies.m2_liquidity import M2LiquidityConfig, M2LiquidityStrategy

        path, n = _write_signal_parquet(tmp_path, 200)
        cfg = M2LiquidityConfig(
            instrument_id=instrument_id,
            bar_type=bar_type,
            trade_size=Decimal("1000"),
            signal_path=path,
        )
        strategy = M2LiquidityStrategy(cfg)
        # Index is loaded in on_start(); call the loader directly to verify mapping.
        index = strategy._load_signal_index()
        assert len(index) == n
```

- [ ] **Step 2: Run to confirm failure**

```bash
pytest tests/dq/strategies/test_m2_liquidity_config.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError: No module named 'digiquant.strategies.m2_liquidity'`

- [ ] **Step 3: Implement `digiquant/src/digiquant/strategies/m2_liquidity.py`**

```python
"""M2 Liquidity strategy — 5-indicator voting system on global M2 money supply.

The strategy pre-loads a pre-computed signal DataFrame at instantiation time.
On each bar, it looks up the signal for that bar's date and fires entries/exits.

Usage:
    from digiquant.data.m2 import M2DataFetcher
    from digiquant.indicators.m2_signals import M2SignalComputer

    m2_df = M2DataFetcher().fetch(offset_days=86)
    ohlcv_df = ...  # your daily BTC OHLCV Polars DataFrame with 'close' column
    m2_df = m2_df.join(ohlcv_df.select(["date", "close"]), on="date", how="inner")
    signal_df = M2SignalComputer().compute(m2_df)
    signal_df.write_parquet("/tmp/m2_signals.parquet")

    config = M2LiquidityConfig(
        instrument_id=InstrumentId.from_str("BTCUSDT.BINANCE"),
        bar_type=...,
        trade_size=Decimal("1000"),
        signal_path="/tmp/m2_signals.parquet",
    )
    strategy = M2LiquidityStrategy(config)
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

import polars as pl
from nautilus_trader.config import StrategyConfig
from nautilus_trader.core.datetime import unix_nanos_to_dt
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OrderSide, TimeInForce
from nautilus_trader.model.identifiers import InstrumentId
from nautilus_trader.model.instruments import Instrument
from nautilus_trader.trading.strategy import Strategy

from digiquant.strategies.registry import register


class M2LiquidityConfig(StrategyConfig, frozen=True):
    """Configuration for M2 Liquidity strategy."""

    instrument_id: InstrumentId
    bar_type: BarType
    trade_size: Decimal
    # Path to a parquet of the pre-computed signal frame (columns:
    # date, buy_signal, sell_signal). A Polars DataFrame cannot live in a
    # frozen Nautilus StrategyConfig (msgspec struct) — we pass a path and
    # load it in on_start().
    signal_path: str

    # Risk management
    use_sl: bool = True
    sl_pct: float = 10.0

    # Strategy control
    enable_long: bool = True
    enable_short: bool = False  # PineScript default has short disabled


class M2LiquidityStrategy(Strategy):
    """Enters on M2 aggregate signal crossover; exits on reversal or stop loss."""

    def __init__(self, config: M2LiquidityConfig) -> None:
        super().__init__(config)
        self._signal_index: dict[date, tuple[bool, bool]] = {}
        self._long_sl_price: float | None = None
        self._short_sl_price: float | None = None
        self._instrument: Instrument | None = None

    def _load_signal_index(self) -> dict[date, tuple[bool, bool]]:
        """Load the pre-computed signal parquet into a date → (buy, sell) map."""
        df = pl.read_parquet(self.config.signal_path)
        return {
            row["date"]: (bool(row["buy_signal"]), bool(row["sell_signal"]))
            for row in df.select(["date", "buy_signal", "sell_signal"]).to_dicts()
        }

    # ─── Lifecycle ───────────────────────────────────────────────────────────

    def on_start(self) -> None:
        self._instrument = self.cache.instrument(self.config.instrument_id)
        self._signal_index = self._load_signal_index()
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        close = bar.close.as_double()
        bar_date = unix_nanos_to_dt(bar.ts_event).date()

        signals = self._signal_index.get(bar_date)
        if signals is None:
            return  # no M2 data for this date (weekends, M2 gap)

        buy_signal, sell_signal = signals
        pos = self.portfolio.net_position(self.config.instrument_id)

        # ── Stop loss check ──────────────────────────────────────────────────
        if self.config.use_sl:
            if pos > 0 and self._long_sl_price is not None and close <= self._long_sl_price:
                self.close_all_positions(self.config.instrument_id)
                self._long_sl_price = None
                return
            if pos < 0 and self._short_sl_price is not None and close >= self._short_sl_price:
                self.close_all_positions(self.config.instrument_id)
                self._short_sl_price = None
                return

        # ── Entries ──────────────────────────────────────────────────────────
        if buy_signal and self.config.enable_long and pos == 0:
            self._long_sl_price = close * (1 - self.config.sl_pct / 100)
            self._submit_market(OrderSide.BUY)

        if sell_signal:
            if self.config.enable_short and pos == 0:
                self._short_sl_price = close * (1 + self.config.sl_pct / 100)
                self._submit_market(OrderSide.SELL)
            elif pos > 0:
                self.close_all_positions(self.config.instrument_id)
                self._long_sl_price = None

    def _submit_market(self, side: OrderSide) -> None:
        """Submit a fixed-size market order. No explicit client_order_id."""
        assert self._instrument is not None
        order = self.order_factory.market(
            instrument_id=self.config.instrument_id,
            order_side=side,
            quantity=self._instrument.make_qty(self.config.trade_size),
            time_in_force=TimeInForce.GTC,
        )
        self.submit_order(order)

    def on_stop(self) -> None:
        self.cancel_all_orders(self.config.instrument_id)
        self.close_all_positions(self.config.instrument_id)

    def on_reset(self) -> None:
        self._long_sl_price = None
        self._short_sl_price = None


# ─── Registry ────────────────────────────────────────────────────────────────
# Note: signal_df must be injected at runtime — no default registry entry.
# Use the registry for discovery only; instantiate M2LiquidityConfig directly.
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/dq/strategies/test_m2_liquidity_config.py -v
```

Expected: all pass (or skip if nautilus not installed).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/strategies/m2_liquidity.py tests/dq/strategies/test_m2_liquidity_config.py
git commit -m "feat(strategies): add M2LiquidityStrategy — 5-indicator M2 voting with SL"
```

---

## Task 5: Run full test suite and verify

- [ ] **Step 1: Run all new tests**

```bash
cd /Users/chrisstefan/Code/digithings
pytest tests/dq/indicators/ tests/dq/strategies/test_slapper_config.py tests/dq/strategies/test_m2_liquidity_config.py tests/dq/data/test_m2.py -v
```

Expected: all pass (Nautilus tests skip if not installed; indicator tests run regardless).

- [ ] **Step 2: Run ruff**

```bash
cd digiquant
ruff check src/digiquant/indicators/ src/digiquant/data/m2.py src/digiquant/strategies/slapper.py src/digiquant/strategies/m2_liquidity.py
ruff format src/digiquant/indicators/ src/digiquant/data/m2.py src/digiquant/strategies/slapper.py src/digiquant/strategies/m2_liquidity.py
```

Expected: no violations.

- [ ] **Step 3: Commit**

```bash
git add -u
git commit -m "chore(digiquant): fix any ruff violations in indicators + M2 strategy"
```

---

## Self-Review

**Spec coverage:**
- ✅ Ind 1: RSI of M2 ROC with RMA smoothing
- ✅ Ind 2: Relative strength (price % vs M2 %) with SMA smoothing and z-score mean
- ✅ Ind 3: ROC MA cross (short vs long)
- ✅ Ind 4: BB%b of M2 ROC
- ✅ Ind 5: MACD histogram of M2 total
- ✅ Aggregate vote (avg_score crosses 0.5)
- ✅ Stop loss (pct-based, long side; short disabled by default)
- ✅ FRED + yfinance data fetching with cache
- ✅ Monthly M2 forward-filled to daily

**Gaps / known limitations:**
- Walk-forward harness and robustness checks — deferred (separate plan)
- `M2LiquidityStrategy` is registered without a default signal_path (the signal frame must be built at runtime); no registry entry is added. To run a backtest, build the signal parquet first (see module docstring), then pass `signal_path`.
- Config carries `signal_path: str` (not a `pl.DataFrame`) precisely because a frozen Nautilus `StrategyConfig` is a msgspec struct that cannot hold a Polars frame — resolved in Task 4, loaded in `on_start()`.
- M2 end-to-end backtest parity (analogous to Slapper Task 8) requires both the signal parquet and aligned daily BTC OHLCV; add once the Slapper parity harness confirms the `run_backtest` interface.
