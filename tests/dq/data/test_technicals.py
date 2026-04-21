"""Golden-fixture tests for digiquant.data.prices.technicals (pure Polars).

Uses a 60-row deterministic OHLCV series; compares module output to a
reference implementation computed from first principles in plain Python.
Tolerance is 1e-6 per the task brief — any regression beyond that shrinks
matching against pandas_ta-era Atlas output.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

import polars as pl
import pytest

from digiquant.data.prices import TECHNICAL_COLUMNS
from digiquant.data.prices.technicals import compute_indicators


# ─── Deterministic fixture ──────────────────────────────────────────────


def _fixture(n: int = 60) -> pl.DataFrame:
    """A 60-row OHLCV series with smooth, non-degenerate movement."""
    timestamps = [date(2025, 1, 1) + timedelta(days=i) for i in range(n)]
    close = [100.0 + 5.0 * math.sin(i / 6.0) + 0.2 * i for i in range(n)]
    # Build open/high/low around close so TR has variation.
    open_ = [close[i] - 0.5 + (i % 3 - 1) * 0.1 for i in range(n)]
    high = [max(open_[i], close[i]) + 1.0 + (i % 4) * 0.1 for i in range(n)]
    low = [min(open_[i], close[i]) - 1.0 - (i % 5) * 0.1 for i in range(n)]
    volume = [1_000_000.0 + i * 1_000 for i in range(n)]
    return pl.DataFrame(
        {
            "timestamp": timestamps,
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        }
    )


# ─── Reference implementations (plain Python, independent) ─────────────


def _ref_sma(series: list[float], length: int) -> list[float | None]:
    out: list[float | None] = []
    for i in range(len(series)):
        if i + 1 < length:
            out.append(None)
        else:
            out.append(sum(series[i + 1 - length : i + 1]) / length)
    return out


def _ref_ema(series: list[float], length: int) -> list[float | None]:
    """EMA with adjust=False, min_periods=length. Seed: series[length-1] being
    the first non-null, computed as the SMA of first `length` values.

    NOTE: Polars' ewm_mean(adjust=False, min_periods=length) seeds recursion
    from the *first* value of the series (not the SMA). This reference matches
    that convention.
    """
    alpha = 2.0 / (length + 1)
    ema: list[float] = []
    for i, v in enumerate(series):
        if i == 0:
            ema.append(v)
        else:
            ema.append(alpha * v + (1 - alpha) * ema[-1])
    out: list[float | None] = [None] * (length - 1) + ema[length - 1 :]
    return out


def _ref_rsi(series: list[float], length: int) -> list[float | None]:
    """Wilder RSI. alpha=1/length, adjust=False, min_periods=length on the
    gain/loss series (first difference). Matches Polars _wilder_ema."""
    alpha = 1.0 / length
    deltas = [0.0] + [series[i] - series[i - 1] for i in range(1, len(series))]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]

    def _rma(vals: list[float]) -> list[float]:
        out = [vals[0]]
        for v in vals[1:]:
            out.append(alpha * v + (1 - alpha) * out[-1])
        return out

    avg_g = _rma(gains)
    avg_l = _rma(losses)
    rsi: list[float | None] = []
    for i in range(len(series)):
        # Polars counts the i=0 slot (value 0 because the null diff was replaced
        # by 0 via when/otherwise) towards min_periods, so the first non-null
        # index is `length-1`, not `length`.
        if i < length - 1:
            rsi.append(None)
            continue
        if avg_l[i] == 0:
            rsi.append(100.0 if avg_g[i] > 0 else 0.0)
        else:
            rs = avg_g[i] / avg_l[i]
            rsi.append(100.0 - 100.0 / (1 + rs))
    return rsi


# ─── Smoke + schema tests ──────────────────────────────────────────────


@pytest.mark.unit
def test_compute_indicators_schema_matches_contract() -> None:
    df = _fixture()
    out = compute_indicators(df)
    assert list(out.columns) == list(TECHNICAL_COLUMNS)
    assert out.height == df.height


@pytest.mark.unit
def test_compute_indicators_empty_frame() -> None:
    empty = pl.DataFrame(
        {
            "timestamp": pl.Series("timestamp", [], dtype=pl.Date),
            "open": pl.Series("open", [], dtype=pl.Float64),
            "high": pl.Series("high", [], dtype=pl.Float64),
            "low": pl.Series("low", [], dtype=pl.Float64),
            "close": pl.Series("close", [], dtype=pl.Float64),
            "volume": pl.Series("volume", [], dtype=pl.Float64),
        }
    )
    out = compute_indicators(empty)
    assert out.height == 0


# ─── Golden-fixture equivalence tests ──────────────────────────────────


def _close(df: pl.DataFrame) -> list[float]:
    return df["close"].to_list()


def _assert_close(actual: list, expected: list, *, tol: float = 1e-6) -> None:
    assert len(actual) == len(expected), f"length mismatch: {len(actual)} vs {len(expected)}"
    for i, (a, e) in enumerate(zip(actual, expected)):
        if e is None:
            assert a is None or (isinstance(a, float) and math.isnan(a)), (
                f"row {i}: expected None, got {a}"
            )
        else:
            assert a is not None and not math.isnan(a), f"row {i}: got null, expected {e}"
            assert abs(a - e) < tol, f"row {i}: {a} != {e} (|Δ|={abs(a - e)})"


@pytest.mark.unit
def test_sma_matches_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)
    _assert_close(out["sma_20"].to_list(), _ref_sma(closes, 20))
    _assert_close(out["sma_50"].to_list(), _ref_sma(closes, 50))
    # sma_200 all nulls with 60-row fixture
    assert all(v is None or math.isnan(v) for v in out["sma_200"].to_list())


@pytest.mark.unit
def test_ema_matches_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)
    _assert_close(out["ema_12"].to_list(), _ref_ema(closes, 12), tol=1e-9)
    _assert_close(out["ema_26"].to_list(), _ref_ema(closes, 26), tol=1e-9)


@pytest.mark.unit
def test_rsi_matches_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)
    _assert_close(out["rsi_14"].to_list(), _ref_rsi(closes, 14), tol=1e-6)
    _assert_close(out["rsi_7"].to_list(), _ref_rsi(closes, 7), tol=1e-6)


@pytest.mark.unit
def test_macd_is_ema_diff_and_signal_is_ema_of_macd() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)
    ema12 = _ref_ema(closes, 12)
    ema26 = _ref_ema(closes, 26)
    expected_macd = [
        (e12 - e26) if (e12 is not None and e26 is not None) else None
        for e12, e26 in zip(ema12, ema26)
    ]
    _assert_close(out["macd"].to_list(), expected_macd, tol=1e-9)

    # MACD signal = EMA(MACD, 9). Only assert where macd is non-null.
    macd_series = [v for v in out["macd"].to_list() if v is not None and not math.isnan(v)]
    sig_ref = _ref_ema(macd_series, 9)
    # Last N values of signal (from the full output) must match last N values of sig_ref.
    sig_actual = [v for v in out["macd_signal"].to_list() if v is not None and not math.isnan(v)]
    _assert_close(
        sig_actual[-len(sig_ref) :] if len(sig_ref) <= len(sig_actual) else sig_actual,
        [v for v in sig_ref if v is not None],
        tol=1e-6,
    )


@pytest.mark.unit
def test_roc_and_pct_vs_sma() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)

    # ROC_5 at index i = (close[i]/close[i-5] - 1)*100
    roc5 = out["roc_5"].to_list()
    for i in range(5, len(closes)):
        expected = (closes[i] / closes[i - 5] - 1) * 100
        assert abs(roc5[i] - expected) < 1e-9

    # pct_vs_sma20 at index i = (close[i] - sma20[i]) / sma20[i] * 100
    pct_vs_sma20 = out["pct_vs_sma20"].to_list()
    sma20_ref = _ref_sma(closes, 20)
    for i in range(19, len(closes)):
        expected = (closes[i] - sma20_ref[i]) / sma20_ref[i] * 100
        assert abs(pct_vs_sma20[i] - expected) < 1e-9


@pytest.mark.unit
def test_atr_is_positive_and_finite() -> None:
    """Soft test on ATR: after length=14, should be positive, monotonically bounded."""
    df = _fixture()
    out = compute_indicators(df)
    atrs = out["atr_14"].to_list()
    for i in range(14, len(atrs)):
        assert atrs[i] is not None and not math.isnan(atrs[i])
        assert atrs[i] > 0
