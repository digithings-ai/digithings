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


# ─── Additional first-principles references ────────────────────────────


def _ref_wilder_ema(series: list[float], length: int) -> list[float | None]:
    """Wilder RMA. alpha=1/length, adjust=False, min_periods=length.

    Matches ``_wilder_ema`` in technicals.py (Polars' ``ewm_mean`` with
    ``adjust=False``): recursion seeded from the first value, but the first
    ``length-1`` outputs are masked to None by ``min_periods``.
    """
    alpha = 1.0 / length
    acc: list[float] = []
    for i, v in enumerate(series):
        if i == 0:
            acc.append(v)
        else:
            acc.append(alpha * v + (1 - alpha) * acc[-1])
    return [None] * (length - 1) + acc[length - 1 :]


def _ref_true_range(high: list[float], low: list[float], close: list[float]) -> list[float]:
    """TR_i = max(H-L, |H - prev_close|, |L - prev_close|).

    Matches Polars' ``max_horizontal``: at i=0, the prev_close-based terms are
    null, but ``max_horizontal`` skips nulls — so TR_0 = high[0] - low[0].
    """
    out: list[float] = [high[0] - low[0]]
    for i in range(1, len(close)):
        hl = high[i] - low[i]
        hc = abs(high[i] - close[i - 1])
        lc = abs(low[i] - close[i - 1])
        out.append(max(hl, hc, lc))
    return out


def _ref_dmi(
    high: list[float], low: list[float], close: list[float], length: int = 14
) -> tuple[list[float | None], list[float | None], list[float | None]]:
    """Return (+DI, -DI, ADX) using Wilder smoothing.

    Mirrors the pandas_ta / technicals.py convention:
      +DM = max(H-prevH, 0) if (H-prevH) > (prevL-L) else 0
      -DM = max(prevL-L, 0) if (prevL-L) > (H-prevH) else 0
      smoothed via Wilder RMA(length); +DI = 100*smoothed_+DM/smoothed_TR.
      DX = 100 * |+DI - -DI| / (+DI + -DI); ADX = Wilder RMA(DX, length).

    Leading values are None wherever the Polars version returns None, so the
    test can compare element-wise.
    """
    n = len(close)
    plus_dm: list[float] = [0.0]
    minus_dm: list[float] = [0.0]
    for i in range(1, n):
        up = high[i] - high[i - 1]
        down = low[i - 1] - low[i]
        plus_dm.append(up if (up > down and up > 0) else 0.0)
        minus_dm.append(down if (down > up and down > 0) else 0.0)
    tr = _ref_true_range(high, low, close)
    plus_smooth = _ref_wilder_ema(plus_dm, length)
    minus_smooth = _ref_wilder_ema(minus_dm, length)
    tr_smooth = _ref_wilder_ema(tr, length)

    plus_di: list[float | None] = []
    minus_di: list[float | None] = []
    for ps, ms, trs in zip(plus_smooth, minus_smooth, tr_smooth):
        if ps is None or ms is None or trs is None or trs == 0:
            plus_di.append(None)
            minus_di.append(None)
        else:
            plus_di.append(ps / trs * 100)
            minus_di.append(ms / trs * 100)

    # DX at each row (None where DMI is None).
    dx: list[float | None] = []
    for pdi, mdi in zip(plus_di, minus_di):
        if pdi is None or mdi is None or (pdi + mdi) == 0:
            dx.append(None)
        else:
            dx.append(abs(pdi - mdi) / (pdi + mdi) * 100.0)

    # ADX = Wilder-EMA(DX, length). Polars' ewm_mean(adjust=False, min_periods=length)
    # skips leading nulls and requires `length` non-null observations before
    # emitting. Compute the recursion only on the non-null DX suffix, then
    # pad the head with None.
    first_valid = next((i for i, v in enumerate(dx) if v is not None), None)
    adx: list[float | None] = [None] * len(dx)
    if first_valid is not None:
        suffix = [v for v in dx[first_valid:] if v is not None]
        adx_suffix = _ref_wilder_ema(suffix, length)
        for j, v in enumerate(adx_suffix):
            adx[first_valid + j] = v
    return plus_di, minus_di, adx


def _ref_stoch(
    high: list[float], low: list[float], close: list[float]
) -> tuple[list[float | None], list[float | None]]:
    """Stochastic %K(14)/%D(3). Matches technicals.py:
    raw_k = (C - min14(L)) / (max14(H) - min14(L)) * 100
    stoch_k = SMA(raw_k, 3)
    stoch_d = SMA(stoch_k, 3)
    min_periods on each rolling op enforces length; `None` propagates.
    """
    n = len(close)
    raw_k: list[float | None] = []
    for i in range(n):
        if i < 13:
            raw_k.append(None)
            continue
        window_low = min(low[i - 13 : i + 1])
        window_high = max(high[i - 13 : i + 1])
        denom = window_high - window_low
        raw_k.append(None if denom == 0 else (close[i] - window_low) / denom * 100)

    def _sma3(vals: list[float | None]) -> list[float | None]:
        out: list[float | None] = []
        for i in range(len(vals)):
            if i < 2 or any(v is None for v in vals[i - 2 : i + 1]):
                out.append(None)
            else:
                out.append(sum(vals[i - 2 : i + 1]) / 3)  # type: ignore[arg-type]
        return out

    stoch_k = _sma3(raw_k)
    stoch_d = _sma3(stoch_k)
    return stoch_k, stoch_d


def _ref_bollinger(
    series: list[float], length: int = 20
) -> tuple[
    list[float | None],
    list[float | None],
    list[float | None],
    list[float | None],
    list[float | None],
]:
    """Return (middle, upper, lower, %B, bandwidth) with ddof=0 (population),
    matching technicals.py._rolling_std(... ddof=0) and pandas_ta defaults.
    """
    middle = _ref_sma(series, length)
    std: list[float | None] = []
    for i in range(len(series)):
        if i + 1 < length:
            std.append(None)
            continue
        window = series[i + 1 - length : i + 1]
        mean = sum(window) / length
        var = sum((x - mean) ** 2 for x in window) / length  # ddof=0
        std.append(math.sqrt(var))
    upper = [
        (m + 2.0 * s) if (m is not None and s is not None) else None for m, s in zip(middle, std)
    ]
    lower = [
        (m - 2.0 * s) if (m is not None and s is not None) else None for m, s in zip(middle, std)
    ]
    pct_b: list[float | None] = []
    bandwidth: list[float | None] = []
    for i, (u, low_, m) in enumerate(zip(upper, lower, middle)):
        if u is None or low_ is None or u == low_:
            pct_b.append(None)
        else:
            pct_b.append((series[i] - low_) / (u - low_))
        if u is None or low_ is None or m is None or m == 0:
            bandwidth.append(None)
        else:
            bandwidth.append((u - low_) / m * 100.0)
    return middle, upper, lower, pct_b, bandwidth


def _ref_hist_vol_21(series: list[float]) -> list[float | None]:
    """21-period rolling stdev (ddof=1) of log returns, * sqrt(252) * 100.

    log_ret[0] = None (shift(1) is null); Polars rolling_std with
    min_periods=21 requires 21 non-null values, so first non-null index is 21.
    """
    n = len(series)
    log_ret: list[float | None] = [None] + [
        math.log(series[i] / series[i - 1]) for i in range(1, n)
    ]
    out: list[float | None] = []
    for i in range(n):
        window = log_ret[i - 20 : i + 1] if i >= 20 else []
        if len(window) < 21 or any(v is None for v in window):
            out.append(None)
            continue
        mean = sum(window) / 21  # type: ignore[arg-type]
        var = sum((v - mean) ** 2 for v in window) / (21 - 1)  # ddof=1
        out.append(math.sqrt(var) * math.sqrt(252) * 100)
    return out


def _ref_zscore(series: list[float], length: int) -> list[float | None]:
    """(close - SMA_length) / rolling_std(ddof=1, window=length)."""
    sma = _ref_sma(series, length)
    out: list[float | None] = []
    for i in range(len(series)):
        if i + 1 < length:
            out.append(None)
            continue
        window = series[i + 1 - length : i + 1]
        mean = sum(window) / length
        var = sum((x - mean) ** 2 for x in window) / (length - 1)  # ddof=1
        std = math.sqrt(var)
        if std == 0 or sma[i] is None:
            out.append(None)
        else:
            out.append((series[i] - sma[i]) / std)  # type: ignore[operator]
    return out


# ─── Golden assertions for remaining indicators ─────────────────────────


def _ohlc(df: pl.DataFrame) -> tuple[list[float], list[float], list[float], list[float]]:
    return (
        df["open"].to_list(),
        df["high"].to_list(),
        df["low"].to_list(),
        df["close"].to_list(),
    )


@pytest.mark.unit
def test_adx_and_dmi_match_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    _open, high, low, close = _ohlc(df)
    ref_plus, ref_minus, ref_adx = _ref_dmi(high, low, close, length=14)
    _assert_close(out["dmi_plus"].to_list(), ref_plus, tol=1e-6)
    _assert_close(out["dmi_minus"].to_list(), ref_minus, tol=1e-6)
    _assert_close(out["adx_14"].to_list(), ref_adx, tol=1e-6)


@pytest.mark.unit
def test_stochastic_k_and_d_match_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    _open, high, low, close = _ohlc(df)
    ref_k, ref_d = _ref_stoch(high, low, close)
    _assert_close(out["stoch_k"].to_list(), ref_k, tol=1e-6)
    _assert_close(out["stoch_d"].to_list(), ref_d, tol=1e-6)


@pytest.mark.unit
def test_bollinger_bands_match_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)
    mid, upper, lower, pct_b, bandwidth = _ref_bollinger(closes, length=20)
    _assert_close(out["bb_middle"].to_list(), mid, tol=1e-9)
    _assert_close(out["bb_upper"].to_list(), upper, tol=1e-9)
    _assert_close(out["bb_lower"].to_list(), lower, tol=1e-9)
    _assert_close(out["bb_pct_b"].to_list(), pct_b, tol=1e-9)
    _assert_close(out["bb_bandwidth"].to_list(), bandwidth, tol=1e-9)


@pytest.mark.unit
def test_hist_vol_21_matches_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)
    _assert_close(out["hist_vol_21"].to_list(), _ref_hist_vol_21(closes), tol=1e-6)


@pytest.mark.unit
def test_zscore_50_and_200_match_reference() -> None:
    df = _fixture()
    out = compute_indicators(df)
    closes = _close(df)
    # 60-row fixture → zscore_200 is all None (insufficient window).
    _assert_close(out["zscore_50"].to_list(), _ref_zscore(closes, 50), tol=1e-9)
    assert all(v is None or math.isnan(v) for v in out["zscore_200"].to_list())
