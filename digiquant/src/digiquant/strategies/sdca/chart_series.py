"""SDCA diagnostic chart series — allocation %, fill markers, indicator overlays.

Allocation is mark-to-market: ``100 * units * price / (cash + units * price)``.
Do **not** use ``capital_deployed = initial_cash - cash`` (goes negative after
sells). Fill dots use ``book_frac = |trade_usd| / portfolio`` from actual fills,
never curve-rate-sign ``buy_days`` / ``sell_days``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Literal

import polars as pl
from pydantic import BaseModel, ConfigDict, Field

from digiquant.strategies.sdca.composite_risk import z_to_risk
from digiquant.strategies.sdca.indicator_catalog import (
    EXTRA_INDICATOR_NAMES,
    SdcaCompositeWeights,
    indicator_display_name,
)
from digiquant.strategies.sdca.presets import load_preset
from digiquant.strategies.sdca.power_law_zscore import power_law_z_score

_BOOK_FRAC_EPS = 1e-12
# Reconstruction Δunits floor: JSON round-trip jitter, not a real fill.
_UNITS_EPS = 1e-8


class SdcaFillMarker(BaseModel):
    """One day's aggregated buy or sell, sized by fraction of the book moved."""

    model_config = ConfigDict(frozen=True, strict=True)

    t: str
    side: Literal["buy", "sell"]
    book_frac: float = Field(ge=0.0, description="|trade_usd| / portfolio that day")
    price: float
    trade_usd: float = Field(description="Signed notional: buy > 0, sell < 0")


class SdcaIndicatorCurve(BaseModel):
    """One composite-member series on the 0–100 risk scale (same map as the index)."""

    model_config = ConfigDict(frozen=True, strict=True)

    name: str
    display_name: str
    weight: float = Field(ge=0.0)
    in_index: bool
    points: list[dict[str, float | str]]


class SdcaCurveKnees(BaseModel):
    """Buy-start / sell-start thresholds from the published curve shape."""

    model_config = ConfigDict(frozen=True, strict=True)

    buy_knee_risk: float
    sell_knee_risk: float
    preset: str


def allocated_pct(cash: float, units: float, price: float) -> float:
    """Percent of mark-to-market equity held in the asset (0–100)."""
    asset = float(units) * float(price)
    total = float(cash) + asset
    if total <= 0.0:
        return 0.0
    return 100.0 * asset / total


def allocated_pct_series(
    *,
    cash: Sequence[float],
    units: Sequence[float],
    prices: Sequence[float],
) -> list[float]:
    """Daily percent allocated from the running cash/units book."""
    if not (len(cash) == len(units) == len(prices)):
        raise ValueError("allocated_pct_series requires equal-length cash, units, prices")
    return [allocated_pct(c, u, p) for c, u, p in zip(cash, units, prices, strict=True)]


def cash_from_net_deployed(net_deployed: Sequence[float], initial_cash: float) -> list[float]:
    """Venue cash from ``net_deployed = initial_cash - cash`` (may exceed initial)."""
    return [float(initial_cash) - float(v) for v in net_deployed]


def fill_markers_from_daily(
    *,
    dates: Sequence[str],
    daily_trade_usd: Sequence[float],
    portfolio_values: Sequence[float],
    prices: Sequence[float],
) -> list[SdcaFillMarker]:
    """One marker per non-zero fill day. Size is ``|trade_usd| / portfolio``."""
    n = len(dates)
    if not (len(daily_trade_usd) == len(portfolio_values) == len(prices) == n):
        raise ValueError("fill_markers_from_daily requires equal-length daily series")
    out: list[SdcaFillMarker] = []
    for day, trade, port, price in zip(
        dates, daily_trade_usd, portfolio_values, prices, strict=True
    ):
        traded = float(trade)
        if abs(traded) <= _BOOK_FRAC_EPS:
            continue
        denom = float(port)
        book_frac = abs(traded) / denom if denom > _BOOK_FRAC_EPS else 0.0
        out.append(
            SdcaFillMarker(
                t=day,
                side="buy" if traded > 0 else "sell",
                book_frac=book_frac,
                price=float(price),
                trade_usd=traded,
            )
        )
    return out


def indicator_curve_from_z(
    *,
    name: str,
    dates: Sequence[str],
    z_values: Sequence[float | None],
    weight: float,
) -> SdcaIndicatorCurve:
    """Map a z-score series onto the 0–100 risk scale used by the composite index."""
    points: list[dict[str, float | str]] = []
    for day, z in zip(dates, z_values, strict=True):
        if z is None:
            continue
        zf = float(z)
        if zf != zf:  # NaN
            continue
        points.append({"t": day, "v": z_to_risk(zf)})
    return SdcaIndicatorCurve(
        name=name,
        display_name=indicator_display_name(name),
        weight=float(weight),
        in_index=float(weight) > 0.0,
        points=points,
    )


def catalog_indicator_curves(
    *,
    dates: Sequence[str],
    z_by_name: Mapping[str, Sequence[float | None]],
    weights: SdcaCompositeWeights,
) -> list[SdcaIndicatorCurve]:
    """Power-law first, then extras. Zero-weight extras stay in the layout."""
    payload = weights.model_dump()
    ordered = ("power_law", *EXTRA_INDICATOR_NAMES)
    out: list[SdcaIndicatorCurve] = []
    for name in ordered:
        z_vals = z_by_name.get(name)
        weight = float(payload.get(name, 0.0))
        if z_vals is None:
            out.append(
                SdcaIndicatorCurve(
                    name=name,
                    display_name=indicator_display_name(name),
                    weight=weight,
                    in_index=weight > 0.0,
                    points=[],
                )
            )
            continue
        out.append(indicator_curve_from_z(name=name, dates=dates, z_values=z_vals, weight=weight))
    return out


def knees_from_preset(preset_name: str) -> SdcaCurveKnees:
    """Buy/sell start thresholds from ``presets.json`` (``btc_optimized``: 25 / 70)."""
    preset = load_preset(preset_name)
    if preset.shape is None:
        raise ValueError(f"preset {preset_name!r} has no shape knees")
    return SdcaCurveKnees(
        buy_knee_risk=float(preset.shape.buy_knee_risk),
        sell_knee_risk=float(preset.shape.sell_knee_risk),
        preset=preset_name,
    )


def z_from_risk_index(risk_df: pl.DataFrame) -> dict[str, list[float | None]]:
    """Pull ``power_law_z`` / ``{extra}_z`` columns off the #3168 diagnostic frame."""
    out: dict[str, list[float | None]] = {}
    if "power_law_z" in risk_df.columns:
        out["power_law"] = [
            None if v is None else float(v) for v in risk_df["power_law_z"].to_list()
        ]
    for name in EXTRA_INDICATOR_NAMES:
        col = f"{name}_z"
        if col in risk_df.columns:
            out[name] = [None if v is None else float(v) for v in risk_df[col].to_list()]
    return out


def power_law_z_from_rails(
    prices: Sequence[float],
    rails: Sequence[tuple[float | None, float | None, float | None]],
) -> list[float | None]:
    """Rebuild power-law z from published rails + close (no extra cache needed)."""
    if len(prices) != len(rails):
        raise ValueError("power_law_z_from_rails requires equal-length prices and rails")
    lows = [r[0] for r in rails]
    medians = [r[1] for r in rails]
    highs = [r[2] for r in rails]
    price_vals = [None if p != p else float(p) for p in prices]
    z = power_law_z_score(
        pl.Series("price", price_vals, dtype=pl.Float64),
        pl.Series("low", lows, dtype=pl.Float64),
        pl.Series("median", medians, dtype=pl.Float64),
        pl.Series("high", highs, dtype=pl.Float64),
    )
    return [None if v is None else float(v) for v in z.to_list()]


def reconstruct_allocated_pct(
    *,
    equity: Sequence[float],
    capital_deployed_pct: Sequence[float],
    initial_cash: float,
) -> list[float]:
    """Recover ``100 * (equity - cash) / equity``; cash from capital_deployed %."""
    if len(equity) != len(capital_deployed_pct):
        raise ValueError("reconstruct_allocated_pct requires equal-length series")
    out: list[float] = []
    for eq, dep in zip(equity, capital_deployed_pct, strict=True):
        cash = float(initial_cash) * (1.0 - float(dep) / 100.0)
        port = float(eq)
        asset = port - cash
        if port <= 0.0:
            out.append(0.0)
        else:
            out.append(100.0 * max(asset, 0.0) / port)
    return out


def reconstruct_fill_markers(
    *,
    dates: Sequence[str],
    equity: Sequence[float],
    capital_deployed_pct: Sequence[float],
    prices: Sequence[float],
    initial_cash: float,
) -> list[SdcaFillMarker]:
    """Δunits × price when the payload has no ``fill_markers``."""
    if not (len(dates) == len(equity) == len(capital_deployed_pct) == len(prices)):
        raise ValueError("reconstruct_fill_markers requires equal-length series")
    units: list[float] = []
    for eq, dep, price in zip(equity, capital_deployed_pct, prices, strict=True):
        cash = float(initial_cash) * (1.0 - float(dep) / 100.0)
        px = float(price)
        units.append((float(eq) - cash) / px if px > 0 else 0.0)
    daily: list[float] = []
    prev = 0.0
    for i, (u, px) in enumerate(zip(units, prices, strict=True)):
        delta = u - (prev if i else 0.0)
        prev = u
        daily.append(delta * float(px) if abs(delta) > _UNITS_EPS else 0.0)
    return fill_markers_from_daily(
        dates=dates,
        daily_trade_usd=daily,
        portfolio_values=equity,
        prices=prices,
    )


def _points(series: Sequence[Mapping[str, object]] | None) -> list[tuple[str, float]]:
    if not series:
        return []
    return [(str(p["t"]), float(p["v"])) for p in series]  # type: ignore[index]


def chart_inputs_from_payload(payload: Mapping[str, object]) -> dict[str, object]:
    """Chart bundle from TearsheetData JSON; reconstructs missing overlay keys."""
    dates_eq = _points(payload.get("equity_curve"))  # type: ignore[arg-type]
    dates = [t for t, _ in dates_eq]
    equity = [v for _, v in dates_eq]
    initial_cash = float(payload.get("initial_capital") or 0.0)

    ohlc = payload.get("ohlc_bars") or []
    price_by_t = {str(b["t"]): float(b["c"]) for b in ohlc}  # type: ignore[index]
    prices = [price_by_t.get(t, float("nan")) for t in dates]

    deployed_pts = _points(payload.get("capital_deployed_curve"))  # type: ignore[arg-type]
    deployed_by_t = {t: v for t, v in deployed_pts}
    deployed = [deployed_by_t.get(t, 0.0) for t in dates]

    persisted_alloc = payload.get("allocated_pct_curve")
    if persisted_alloc:
        alloc_by_t = {str(p["t"]): float(p["v"]) for p in persisted_alloc}  # type: ignore[index]
        allocated = [alloc_by_t.get(t, 0.0) for t in dates]
    else:
        allocated = reconstruct_allocated_pct(
            equity=equity, capital_deployed_pct=deployed, initial_cash=initial_cash
        )

    persisted_fills = payload.get("fill_markers")
    if persisted_fills:
        markers = [SdcaFillMarker.model_validate(m) for m in persisted_fills]  # type: ignore[union-attr]
    else:
        markers = reconstruct_fill_markers(
            dates=dates,
            equity=equity,
            capital_deployed_pct=deployed,
            prices=prices,
            initial_cash=initial_cash,
        )

    risk_pts = _points(payload.get("risk_curve"))  # type: ignore[arg-type]
    lump_pts = _points(payload.get("lump_equity_curve"))  # type: ignore[arg-type]
    flat_pts = _points(payload.get("flat_dca_equity_curve"))  # type: ignore[arg-type]

    persisted_ind = payload.get("indicator_curves")
    if persisted_ind:
        indicators = [SdcaIndicatorCurve.model_validate(c) for c in persisted_ind]  # type: ignore[union-attr]
    else:
        rails = payload.get("rails") or []
        rail_by_t = {
            str(r["t"]): (
                float(r["low"]),  # type: ignore[index]
                float(r["median"]),  # type: ignore[index]
                float(r["high"]),  # type: ignore[index]
            )
            for r in rails  # type: ignore[union-attr]
        }
        rail_seq = [rail_by_t.get(t, (None, None, None)) for t in dates]
        z_pl = power_law_z_from_rails(prices, rail_seq)
        raw_w = payload.get("indicator_weights")
        wmap = raw_w if isinstance(raw_w, Mapping) else {"power_law": 1.0}
        weights = SdcaCompositeWeights(
            **{
                n: float(wmap.get(n, 1.0 if n == "power_law" else 0.0))  # type: ignore[union-attr]
                for n in ("power_law", *EXTRA_INDICATOR_NAMES)
            }
        )
        indicators = catalog_indicator_curves(
            dates=dates, z_by_name={"power_law": z_pl}, weights=weights
        )

    persisted_knees = payload.get("curve_knees")
    if persisted_knees:
        knees = SdcaCurveKnees.model_validate(persisted_knees)
    else:
        notes = payload.get("notes") or []
        preset = "btc_optimized"
        for note in notes:
            if isinstance(note, str) and "Preset " in note:
                # "Coefficients … Preset btc_optimized."
                tail = note.rsplit("Preset ", 1)[-1].strip().rstrip(".")
                if tail:
                    preset = tail.split()[0]
                    break
        knees = knees_from_preset(preset)

    return {
        "dates": dates,
        "equity": equity,
        "prices": prices,
        "allocated_pct": allocated,
        "fill_markers": markers,
        "risk": risk_pts,
        "lump": lump_pts,
        "flat_dca": flat_pts,
        "indicators": indicators,
        "knees": knees,
        "initial_cash": initial_cash,
        "symbol": str(payload.get("symbol") or ""),
        "strategy": str(payload.get("strategy") or ""),
        "period_start": str(payload.get("period_start") or ""),
        "period_end": str(payload.get("period_end") or ""),
    }


__all__ = [
    "SdcaCurveKnees",
    "SdcaFillMarker",
    "SdcaIndicatorCurve",
    "allocated_pct",
    "allocated_pct_series",
    "cash_from_net_deployed",
    "catalog_indicator_curves",
    "chart_inputs_from_payload",
    "fill_markers_from_daily",
    "indicator_curve_from_z",
    "knees_from_preset",
    "power_law_z_from_rails",
    "reconstruct_allocated_pct",
    "reconstruct_fill_markers",
    "z_from_risk_index",
]
