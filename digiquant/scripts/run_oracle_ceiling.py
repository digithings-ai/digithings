#!/usr/bin/env python3
"""North-star ceiling: fit the best buy/sell curve against a hindsight-perfect
valuation index, so real indicator+curve optimization has a target to measure
progress against.

Chris's brief (2026-09-11): "if we had the perfect indicator, then how much
could we really materially make? ... fit the perfect line, fit the perfect
valuation index, and then fit the perfect buy and sell strategy around that
and make a tier sheet for it ... as we add more indicators and keep
optimizing, that's what we aim for. We won't realistically reach it, but at
least it's a target."

This is NOT a strategy candidate. The "index" here is built directly from
*realized* price (non-causal — it uses future price info no live indicator
could ever have), specifically from the same documented long-term and
medium-term cycle pin sets Stage A already scores every real indicator
against (``cycle_windows.SdcaCycleWindows.btc_v1`` /
``btc_medium_term_v1``). For each timeframe: find the actual local price
extreme inside every peak/trough window (the window's own real high/low, not
just its pin date), then piecewise-interpolate risk between consecutive
extrema by log-price position — 0 exactly at every trough extreme, 100
exactly at every peak extreme, blended 3:1 long:medium wherever both
timeframes have real (non-extrapolated) coverage for a given day, falling
back to whichever timeframe does where only one does (see ``_blend_risk``).

This is NOT guaranteed to be the highest-scoring index under
``stage_a.combined_cycle_overlap_score`` specifically — that score rewards
saturating an *entire* window at risk <=35 or >=80, which a smooth
interpolation does less aggressively than a step function would (a trivial
"flat 0 inside every trough window, flat 100 inside every peak window"
index scores higher on that one metric, at the cost of not being a
meaningful economic signal — it has no gradation of degree-of-cheapness).
The sensitivity sweep below is a diagnostic comparison against the
codebase's own 3:1 default, not a claimed ceiling on that score.

The resulting risk series is then handed to the *unmodified* production
curve search (``curve_optimize.search_wide_knee_curve`` — same bounds/grid a
real trial uses) so the only thing being idealized is the index, not the
curve-fitting methodology. Never persisted as a candidate, never pushed to
the artifact's Strategy Book db, never touches ``settings.json``.

Usage:
    uv run python scripts/run_oracle_ceiling.py
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
from datetime import date
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.backtest import run_backtest
from digiquant.strategies.sdca.curve import AccumDistCurve
from digiquant.strategies.sdca.curve_optimize import search_wide_knee_curve
from digiquant.strategies.sdca.cycle_windows import CycleKind, CycleWindow, SdcaCycleWindows
from digiquant.strategies.sdca.indicator_catalog import SdcaCompositeWeights
from digiquant.strategies.sdca.optimize import load_sdca_ohlcv
from digiquant.strategies.sdca.stage_a import combined_cycle_overlap_score

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "BTC-USD.csv"
OUTPUT_DIR = DIGIQUANT_ROOT / ".scratch" / "oracle_ceiling"

TRADE_START = date(2018, 1, 1)  # same cutoff load_frozen_index/Stage A already use
INITIAL_CASH = 1000.0
DEFAULT_LONG_WEIGHT = 3.0
DEFAULT_MEDIUM_WEIGHT = 1.0
SENSITIVITY_RATIOS: tuple[tuple[float, float], ...] = ((2.0, 1.0), (3.0, 1.0), (5.0, 1.0))

# frozen_weights is a required field on CurveOptimizeResult purely for the
# audit-trail notes string -- the oracle index below is not derived from any
# indicator blend, so this value is a placeholder, not a claim about how the
# index was built. Printed and written to the output file with an explicit
# label so it's never mistaken for a real weight mix.
_PLACEHOLDER_WEIGHTS = SdcaCompositeWeights(power_law=1.0)


class Anchor:
    __slots__ = ("day", "price", "kind")

    def __init__(self, day: date, price: float, kind: CycleKind) -> None:
        self.day = day
        self.price = price
        self.kind = kind


def _local_extreme(dates: list[date], prices: list[float], window: CycleWindow) -> Anchor | None:
    """Actual local min (trough) or max (peak) close within ``window``.

    Returns ``None`` if the window doesn't overlap the available date range
    at all (e.g. a pin older than the cached history).
    """
    lo = bisect.bisect_left(dates, window.start)
    hi = bisect.bisect_right(dates, window.end)
    if lo >= hi:
        return None
    segment = prices[lo:hi]
    if window.kind is CycleKind.TROUGH:
        offset = min(range(len(segment)), key=lambda i: segment[i])
    else:
        offset = max(range(len(segment)), key=lambda i: segment[i])
    idx = lo + offset
    return Anchor(dates[idx], prices[idx], window.kind)


def _build_anchors(
    dates: list[date], prices: list[float], windows: SdcaCycleWindows
) -> list[Anchor]:
    anchors: list[Anchor] = []
    for window in windows.windows:
        anchor = _local_extreme(dates, prices, window)
        if anchor is not None:
            anchors.append(anchor)
    anchors.sort(key=lambda a: a.day)
    for prev, nxt in zip(anchors, anchors[1:], strict=False):
        if prev.kind == nxt.kind:
            raise ValueError(
                f"consecutive {prev.kind.value} anchors {prev.day} -> {nxt.day}: "
                "_oracle_risk_series assumes strict peak/trough alternation; a "
                "same-kind adjacent pair silently interpolates that segment "
                "backwards instead of raising"
            )
    return anchors


def _oracle_risk_series(
    dates: list[date], prices: list[float], anchors: list[Anchor]
) -> list[float]:
    """Piecewise log-price position between bracketing peak/trough anchors.

    0.0 exactly at a trough anchor's own day, 100.0 exactly at a peak
    anchor's. Before the first anchor / after the last, flat-extrapolates to
    that anchor's value rather than inventing a trend. This flat region can
    be long-lived when a timeframe's last anchor trails the end of the price
    series by months (the long-term set's last documented peak does) --
    callers must not blend a flat-extrapolated stretch at its usual weight;
    see ``_blend_risk``, which falls back to whichever timeframe has real
    coverage on a given day.
    """
    if not anchors:
        raise ValueError("no cycle-window anchors overlap the price series")
    anchor_days = [a.day for a in anchors]
    out: list[float] = []
    for day, price in zip(dates, prices, strict=True):
        if day <= anchor_days[0]:
            out.append(0.0 if anchors[0].kind is CycleKind.TROUGH else 100.0)
            continue
        if day >= anchor_days[-1]:
            out.append(0.0 if anchors[-1].kind is CycleKind.TROUGH else 100.0)
            continue
        i = bisect.bisect_right(anchor_days, day) - 1
        a, b = anchors[i], anchors[i + 1]
        trough, peak = (a, b) if a.kind is CycleKind.TROUGH else (b, a)
        lo_p = math.log(trough.price)
        hi_p = math.log(max(peak.price, trough.price * 1.0001))
        frac = (math.log(price) - lo_p) / (hi_p - lo_p)
        out.append(max(0.0, min(100.0, frac * 100.0)))
    return out


def _blend_risk(
    long_ok: list[bool],
    medium_ok: list[bool],
    long_risk: list[float],
    medium_risk: list[float],
    long_weight: float,
    medium_weight: float,
) -> list[float]:
    """Blend timeframes only where each has real (non-extrapolated) coverage.

    Outside a timeframe's own anchor range, ``_oracle_risk_series`` flat-
    extrapolates a stale endpoint value. Mixing that placeholder into the
    blend at its usual weight would drag a day with real coverage from the
    other timeframe toward a number that isn't tracking price at all -- so
    when only one timeframe covers a day, use it alone.
    """
    total = long_weight + medium_weight
    out: list[float] = []
    for lo, mo, long_val, medium_val in zip(
        long_ok, medium_ok, long_risk, medium_risk, strict=True
    ):
        if lo and mo:
            out.append((long_weight * long_val + medium_weight * medium_val) / total)
        elif mo:
            out.append(medium_val)
        elif lo:
            out.append(long_val)
        else:
            out.append((long_val + medium_val) / 2.0)
    return out


def build_report(*, data_path: Path, output_dir: Path) -> dict:
    dates_full, prices_full = load_sdca_ohlcv(
        symbols=["BTC-USD"], data_path=data_path, data_dir=None
    )
    start_idx = bisect.bisect_left(dates_full, TRADE_START)
    dates = dates_full[start_idx:]
    prices = prices_full[start_idx:]
    print(f"Sliced to trade_start={TRADE_START}: {len(dates)} rows, {dates[0]} -> {dates[-1]}")

    long_windows = SdcaCycleWindows.btc_v1()
    medium_windows = SdcaCycleWindows.btc_medium_term_v1()
    long_anchors = _build_anchors(dates, prices, long_windows)
    medium_anchors = _build_anchors(dates, prices, medium_windows)
    print(f"Long-term anchors ({len(long_anchors)}):")
    for a in long_anchors:
        print(f"  {a.day} {a.kind.value:>6} @ {a.price:,.2f}")
    print(
        f"Medium-term anchors: {len(medium_anchors)} (first {medium_anchors[0].day}, "
        f"last {medium_anchors[-1].day})"
    )

    long_risk = _oracle_risk_series(dates, prices, long_anchors)
    medium_risk = _oracle_risk_series(dates, prices, medium_anchors)

    long_days = [a.day for a in long_anchors]
    medium_days = [a.day for a in medium_anchors]
    long_ok = [long_days[0] <= d <= long_days[-1] for d in dates]
    medium_ok = [medium_days[0] <= d <= medium_days[-1] for d in dates]
    medium_only_days = sum(1 for lo, mo in zip(long_ok, medium_ok, strict=True) if mo and not lo)
    long_only_days = sum(1 for lo, mo in zip(long_ok, medium_ok, strict=True) if lo and not mo)
    if medium_only_days or long_only_days:
        print(
            f"Timeframe coverage: {medium_only_days} day(s) fall outside the "
            f"long-term anchor range (long-term is flat-extrapolated there, so "
            f"medium-term alone drives the blend); {long_only_days} day(s) fall "
            "outside the medium-term range (long-term alone drives it)."
        )

    def blend(long_w: float, medium_w: float) -> list[float]:
        return _blend_risk(long_ok, medium_ok, long_risk, medium_risk, long_w, medium_w)

    print(
        "\nCycle-overlap sensitivity (diagnostic vs. the codebase's standing "
        "3:1 long:medium default -- NOT a ceiling on this score; see module "
        "docstring):"
    )
    sensitivity = {}
    for long_w, medium_w in SENSITIVITY_RATIOS:
        blended = blend(long_w, medium_w)
        score = combined_cycle_overlap_score(
            dates,
            blended,
            long_windows,
            medium_windows,
            long_weight=long_w,
            medium_weight=medium_w,
        )
        key = f"{long_w:.0f}:{medium_w:.0f}"
        sensitivity[key] = score.model_dump()
        print(
            f"  {key}  objective={score.objective:.2f}  "
            f"long_spread={score.long.spread:.2f}  "
            f"medium_spread={score.medium.spread:.2f}"
        )

    oracle_risk = blend(DEFAULT_LONG_WEIGHT, DEFAULT_MEDIUM_WEIGHT)

    dates_pl = pl.Series("date", dates, dtype=pl.Date)
    prices_pl = pl.Series("price", prices, dtype=pl.Float64)
    risk_pl = pl.Series("risk", oracle_risk, dtype=pl.Float64)

    print(
        f"\nFitting buy/sell curve on the {DEFAULT_LONG_WEIGHT:.0f}:{DEFAULT_MEDIUM_WEIGHT:.0f} "
        "blended oracle index (production search space/bounds, unmodified)..."
    )
    result = search_wide_knee_curve(
        dates_pl,
        prices_pl,
        risk_pl,
        initial_cash=INITIAL_CASH,
        frozen_weights=_PLACEHOLDER_WEIGHTS,
    )
    best = result.best
    shape = best.shape

    # search_wide_knee_curve's CurveTrialScore only carries summary fields;
    # re-run to get the full report (vs_lump_usd/vs_flat_dca_usd), same
    # inputs so this is deterministic and matches `best` exactly.
    report, _frame = run_backtest(
        dates_pl, prices_pl, risk_pl, AccumDistCurve(shape.to_nodes()), INITIAL_CASH
    )
    oracle_final_value = INITIAL_CASH + report.total_pnl

    # Derived from the SAME accounting vs_lump_pct/vs_flat_dca_pct are
    # measured against (run_backtest's lump benchmark starts at the first
    # trade day, not day 0 -- a naive lump_mark_to_market(prices, cash) call
    # here would silently disagree with the percentages reported above it).
    lump_final = oracle_final_value - report.vs_lump_usd
    flat_final = oracle_final_value - report.vs_flat_dca_usd

    print("\n=== North-star ceiling: perfect index + perfectly-fit curve ===")
    print(f"Window: {dates[0]} -> {dates[-1]}  (initial cash ${INITIAL_CASH:,.0f})")
    print(
        f"  Lump-sum (from first trade day): ${lump_final:,.0f}  "
        f"({(lump_final / INITIAL_CASH - 1) * 100:,.1f}%)  "
        "[benchmark vs_lump_pct below is measured against]"
    )
    print(
        f"  Flat DCA (from window start)   : ${flat_final:,.0f}  "
        f"({(flat_final / INITIAL_CASH - 1) * 100:,.1f}%)"
    )
    print(
        f"  Oracle-optimal SDCA : ${oracle_final_value:,.0f}  "
        f"({report.total_return_pct:,.1f}%)  "
        f"[+{best.vs_lump_pct:,.1f}% vs lump, +{best.vs_flat_dca_pct:,.1f}% vs flat DCA]"
    )
    print(
        f"  Max drawdown        : {best.max_drawdown_pct:.1f}%  "
        f"(risk_adjusted_return={best.risk_adjusted_return:.2f})"
    )
    print(f"  feasible={best.feasible}  reject_reasons={best.reject_reasons}")
    print("\nWinning buy/sell curve (the 'perfect' shape, given production search bounds):")
    for field, value in shape.model_dump().items():
        print(f"  {field}: {value}")

    tier_sheet = {
        "label": "SDCA oracle ceiling — non-causal, non-deployable north star",
        "generated_for": "Chris, 2026-09-11 request",
        "window": {"start": str(dates[0]), "end": str(dates[-1])},
        "initial_cash": INITIAL_CASH,
        "benchmarks": {
            "lump_sum_final": lump_final,
            "lump_sum_return_pct": (lump_final / INITIAL_CASH - 1) * 100.0,
            "flat_dca_final": flat_final,
            "flat_dca_return_pct": (flat_final / INITIAL_CASH - 1) * 100.0,
        },
        "oracle_optimal": {
            "final_value": oracle_final_value,
            "total_return_pct": report.total_return_pct,
            "vs_lump_pct": best.vs_lump_pct,
            "vs_flat_dca_pct": best.vs_flat_dca_pct,
            "max_drawdown_pct": best.max_drawdown_pct,
            "risk_adjusted_return": best.risk_adjusted_return,
            "feasible": best.feasible,
            "reject_reasons": list(best.reject_reasons),
            "curve_shape": shape.model_dump(),
        },
        "index_construction": {
            "method": "piecewise log-price min-max normalization between actual "
            "local price extrema inside each documented cycle window "
            "(cycle_windows.SdcaCycleWindows); non-causal by design",
            "long_term_anchors": [
                {"date": str(a.day), "price": a.price, "kind": a.kind.value} for a in long_anchors
            ],
            "medium_term_anchor_count": len(medium_anchors),
            "blend_ratio_used": f"{DEFAULT_LONG_WEIGHT:.0f}:{DEFAULT_MEDIUM_WEIGHT:.0f} (long:medium)",
            "blend_fallback": "days outside one timeframe's anchor range use the "
            "other timeframe alone rather than blending in a "
            "flat-extrapolated stale value",
            "medium_only_days": medium_only_days,
            "long_only_days": long_only_days,
            "cycle_overlap_sensitivity": sensitivity,
        },
        "frozen_weights_placeholder": {
            "note": "search_wide_knee_curve requires a SdcaCompositeWeights value "
            "for its audit-trail notes only; the oracle index above is "
            "NOT derived from this or any indicator blend",
            "value": _PLACEHOLDER_WEIGHTS.model_dump(),
        },
        "num_curve_evaluations": result.num_evaluations,
        "num_curve_feasible": result.num_feasible,
        "caveats": [
            "Non-causal: uses realized future price at every day, which no live "
            "indicator can ever have. This is a ceiling, not a strategy.",
            "Never push to the Strategy Book artifact db or settings.json.",
            "Curve search uses the same production bounds/grid as a real trial "
            "(WIDE_KNEE_SEARCH_BOUNDS/WIDE_KNEE_COARSE_GRID) -- only the index "
            "is idealized, not the curve-fitting methodology.",
        ],
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / "oracle_ceiling_result.json"
    out_path.write_text(json.dumps(tier_sheet, indent=2, default=str))
    print(f"\nTier sheet written to {out_path}")
    return tier_sheet


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-path", type=Path, default=DEFAULT_DATA_PATH)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    build_report(data_path=args.data_path, output_dir=args.output_dir)


if __name__ == "__main__":
    main()
