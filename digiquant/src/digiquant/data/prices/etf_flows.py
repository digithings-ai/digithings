"""ETF flow proxy from price/volume (Pillar 1D).

True ETF creation/redemption flow data is a paid feed. This derives a FREE proxy from the
``price_history`` volume already stored: a **dollar-volume z-score** (is today's turnover
unusually heavy vs its recent norm?) and an **OBV trend** (is volume accumulating on up-days
or distributing on down-days?). It is explicitly a PROXY — a turnover/participation hint, not
real fund flows — and is labelled as such so the analysts never overstate it.

``compute_etf_flows_proxy`` is pure (frame in, dict out) so it unit-tests with a tiny fixture
and no Supabase fake. The reader that fetches the window lives in
``olympus/atlas/data/queries.py``. Polars only.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any  # noqa  # scored-lint suppression: heterogeneous signal-dict values

import polars as pl

_PROXY_NOTE = "volume-derived proxy (turnover/OBV), NOT true ETF creations/redemptions"
_REQUIRED_COLUMNS = ("ticker", "date", "close", "volume")


def _finite(x: float) -> bool:
    return isinstance(x, float) and math.isfinite(x)


def _ticker_signal(frame: pl.DataFrame) -> dict[str, Any] | None:
    """Per-ticker proxy from a date-sorted close/volume window. ``None`` if too few rows."""
    if frame.height < 2:
        return None
    dollar_vol = (frame["close"] * frame["volume"]).cast(pl.Float64)
    latest = float(dollar_vol[-1])

    # Score the latest day against a LEAVE-ONE-OUT baseline (the prior rows only). Including
    # today in its own mean/std lets a spike inflate its own baseline and self-damp — and on a
    # short window the in-sample z is pinned near (n-1)/sqrt(n) regardless of spike size. A
    # sample std needs >= 2 baseline points, so dv_z is None for a 2-row window. Non-finite
    # inputs (inf/NaN close*volume) also yield None rather than a silent NaN.
    baseline = dollar_vol.head(frame.height - 1)
    base_mean = float(baseline.mean()) if baseline.len() else float("nan")
    base_std = float(baseline.std()) if baseline.len() >= 2 else float("nan")
    dv_z = (
        round((latest - base_mean) / base_std, 2)
        if _finite(latest) and _finite(base_mean) and _finite(base_std) and base_std > 0
        else None
    )

    # OBV trend: sum of volume signed by the day's close direction over the window. Positive =
    # accumulation (volume concentrated on up-days), negative = distribution.
    direction = frame["close"].diff().sign()  # first row -> null
    signed = (direction * frame["volume"]).cast(pl.Float64)
    net = float(signed.sum() or 0.0)
    obv_trend = (
        ("accumulation" if net > 0 else "distribution" if net < 0 else "flat")
        if _finite(net)
        else "flat"
    )

    avg = float(dollar_vol.mean())
    return {
        "dollar_volume_z": dv_z,
        "obv_trend": obv_trend,
        "avg_dollar_volume": round(avg, 2) if _finite(avg) else None,
    }


def compute_etf_flows_proxy(price_window: pl.DataFrame, *, as_of: date) -> dict[str, Any]:
    """Volume-derived flow proxy per ticker from a ``price_history`` window.

    Args:
        price_window: long frame with ``ticker``, ``date``, ``close``, ``volume`` — a trailing
            window per ticker (newest row is "today").
        as_of: run date (``as_of`` stamp + a ``<= as_of`` guard).

    Returns:
        ``{"as_of", "note", "universe_size", "flows": {ticker: {dollar_volume_z, obv_trend,
        avg_dollar_volume}}}``. ``universe_size`` is 0 (and ``flows`` empty) when there isn't
        enough data. ``note`` makes the proxy nature explicit for downstream prompts.
    """
    empty = {"as_of": as_of.isoformat(), "note": _PROXY_NOTE, "universe_size": 0, "flows": {}}
    # Total function: a non-empty frame missing a required column returns the empty shape rather
    # than raising ColumnNotFoundError from the select/cast below.
    if price_window.is_empty() or not set(_REQUIRED_COLUMNS).issubset(price_window.columns):
        return empty

    if price_window.schema.get("date") == pl.Utf8:
        price_window = price_window.with_columns(pl.col("date").str.to_date())

    df = (
        price_window.select(
            pl.col("ticker").cast(pl.Utf8),
            pl.col("date").cast(pl.Date),
            pl.col("close").cast(pl.Float64),
            pl.col("volume").cast(pl.Float64),
        )
        .filter(
            (pl.col("date") <= as_of)
            & pl.col("close").is_not_null()
            & pl.col("volume").is_not_null()
        )
        .sort(["ticker", "date"])
    )
    if df.is_empty():
        return empty

    flows: dict[str, dict[str, Any]] = {}
    for (ticker,), sub in df.group_by(["ticker"], maintain_order=True):
        signal = _ticker_signal(sub)
        if signal is not None:
            flows[str(ticker)] = signal

    return {
        "as_of": as_of.isoformat(),
        "note": _PROXY_NOTE,
        "universe_size": len(flows),
        "flows": flows,
    }


__all__ = ["compute_etf_flows_proxy"]
