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
    rsi = (
        pl.when(avg_loss == 0)
        .then(100.0)
        .when(avg_gain == 0)
        .then(0.0)
        .otherwise(100.0 - (100.0 / (1.0 + rs)))
    )
    return pl.select(rsi.alias("rsi")).to_series()


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
        window_size=length,
        min_periods=length,
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
    return (
        pl.DataFrame({"bull": bull, "bear": bear})
        .select(
            pl.when(pl.col("bull"))
            .then(pl.lit(1))
            .when(pl.col("bear"))
            .then(pl.lit(0))
            .otherwise(pl.lit(None))
            .cast(pl.Int32)
            .forward_fill()
            .fill_null(0)
            .alias("state")
        )
        .to_series()
    )


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
        bbr_raw = pl.select(
            pl.when(bb_range == 0).then(0.5).otherwise((roc_sig - bb_dn) / bb_range)
        ).to_series()
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
        avg_score = (
            score_sum.cast(pl.Float64) / float(active)
            if active > 0
            else pl.Series("avg_score", [0.0] * len(df))
        )

        buy_signal = (avg_score.shift(1) < 0.5) & (avg_score >= 0.5)
        sell_signal = (avg_score.shift(1) > 0.5) & (avg_score <= 0.5)

        return df.with_columns(
            [
                state1.alias("state1"),
                state2.alias("state2"),
                state3.alias("state3"),
                state4.alias("state4"),
                state5.alias("state5"),
                avg_score.alias("avg_score"),
                buy_signal.fill_null(False).alias("buy_signal"),
                sell_signal.fill_null(False).alias("sell_signal"),
            ]
        )
