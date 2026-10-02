#!/usr/bin/env python3
"""Generic SDCA buy/sell PERIOD optimizer CLI (#4804, Plan 20).

Thin, asset-agnostic front end over
:mod:`digiquant.strategies.sdca.period_optimize`. It knows about *no*
symbol, no price file and no window: everything it searches comes from the
frozen horizon grids in the module plus the pivots the price series produced
itself (``cycle_windows.py`` forbids hand-entered dates, and so does this
script). Run it on any DCA asset:

    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/optimize_sdca_periods.py --symbol GLD-USD --horizon medium
    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/optimize_sdca_periods.py --symbol ANY-USD --horizon long \\
            --data-dir digiquant/data/price-history --split-sample --out /tmp/any_long.json

**What it prints.** The horizon's own grid (never a cross-grid contest — the
medium and long grids are different search spaces and are never ranked against
each other), the pivot counts per candidate width, the full candidate table
with every risk-adjusted metric, the winner under the frozen objective, and
the split-sample pair when ``--split-sample`` is passed.

**Frozen, not tunable here.** The objective (Sharpe primary, Calmar tie-break,
CAGR tertiary) and the time-in-market floor live in the module as
``EXPOSURE_FLOOR_PCT``; this CLI deliberately exposes **no** floor knob, so a
run cannot quietly relax the owner's ruling. A width whose pivot count falls
below ``min_peaks`` / ``min_troughs`` is dropped and reported with its reason —
the minimum is never lowered to make a grid fit.

**Ruling 2 read-layer rule (this file, not ``risk_metrics.py``).**
``risk_metrics.equity_metrics`` divides CAGR by a drawdown that is floating-point
dust (~1e-14) on a drawdown-free path and therefore reports a Calmar around
1e16. Plan 20 forbids editing ``risk_metrics.py``, so the epsilon lives at the
read layer: every Calmar printed or serialized here is ``None``/blank when
``max_drawdown_pct < CALMAR_DD_EPS_PCT``, and the raw drawdown is always shown
beside it so a blank is never mistaken for a missing metric. Selection is
unaffected — ``rank_period_scores`` consults Calmar only on an exact Sharpe tie.

No ``nautilus_trader`` import: pure Python/Polars through the sdca core.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

from digiquant.strategies.sdca.optimize import load_sdca_ohlcv
from digiquant.strategies.sdca.period_optimize import (
    DEFAULT_INITIAL_CASH,
    EXPOSURE_FLOOR_PCT,
    PeriodHorizon,
    PeriodOptimizationResult,
    PeriodScore,
    SplitSampleResult,
    confirmation_days,
    detect_pivots,
    discover_candidate_periods,
    optimize_periods,
    split_sample_check,
)
from digiquant.strategies.sdca.risk_metrics import RiskMetrics

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]

# Drawdown magnitude below which a Calmar is float dust rather than a ratio.
# 1e-9 x100% = 1e-11% peak-to-trough, i.e. 12+ orders below any real GLD/BTC
# swing. Read layer only (see the module docstring).
CALMAR_DD_EPS_PCT = 1e-9

CEILING_LABEL = (
    "CEILING: every metric here is an IN-SAMPLE CEILING on the same history the "
    "periods were fit on. The oracle buys the whole book all-in on every pinned buy "
    "date and sells all-out on every pinned sell date, so it measures PERIOD QUALITY, "
    "never achievable performance — real DCA drips and cannot buy one close. Only the "
    "split-sample read (fit on the first half, score on the unseen second half) says "
    "anything out-of-sample-ish, and both sides must be read next to this sentence."
)

OBJECTIVE_LABEL = (
    "frozen objective: maximize oracle Sharpe, tie-break Calmar, then CAGR, subject to "
    f"a time-in-market floor of {EXPOSURE_FLOOR_PCT:.1f}% of days "
    "(period_optimize.EXPOSURE_FLOOR_PCT / rank_period_scores)"
)

RISK_FREE_LABEL = (
    "risk-adjusted conventions (sdca/risk_metrics.py): simple per-day returns, "
    "annualization 252, risk-free 0, drawdown reused from walk_forward."
)

HORIZON_NAMES: tuple[str, ...] = ("medium", "long")


def horizon_by_name(name: str) -> PeriodHorizon:
    """The frozen grid for ``name`` — the only two this plan defines."""
    if name == "medium":
        return PeriodHorizon.medium()
    if name == "long":
        return PeriodHorizon.long()
    raise ValueError(f"unknown horizon {name!r}; expected one of {list(HORIZON_NAMES)}")


def default_data_path(symbol: str) -> Path:
    """Conventional cache path for ``symbol`` (``load_sdca_ohlcv``'s ``data_dir`` rule)."""
    return DIGIQUANT_ROOT / "data" / "price-history" / f"{symbol}.csv"


def load_closes(symbol: str, data_path: Path) -> tuple[list[date], list[float]]:
    """Daily closes for one symbol through the sdca loader (no bespoke fetch path)."""
    return load_sdca_ohlcv(symbols=[symbol], data_path=data_path, data_dir=None)


def calmar_or_none(max_drawdown_pct: float, calmar: float) -> float | None:
    """``calmar`` unless the drawdown is float dust — Ruling 2's read-layer epsilon."""
    if max_drawdown_pct < CALMAR_DD_EPS_PCT:
        return None
    return calmar


def fmt_opt(value: float | None, spec: str = ".4f") -> str:
    """Format an optional metric; ``None`` prints blank (never a placeholder number)."""
    return "" if value is None else format(value, spec)


def grid_label(horizon: PeriodHorizon) -> str:
    """Printable statement of ONE horizon's search space (Ruling 2 reporting rule)."""
    widths = ", ".join(str(width) for width in horizon.half_widths)
    return (
        f"horizon '{horizon.name}' OWN GRID: half-widths [{widths}] d | minima "
        f"{horizon.min_peaks} peaks / {horizon.min_troughs} troughs | confirmation "
        f"{confirmation_days(horizon)} bars (derived as max(2, min(half_widths) // 3)) | "
        "reported against this grid only — never as a cross-grid contest"
    )


def pivot_rows(
    dates: Sequence[date],
    prices: Sequence[float],
    horizon: PeriodHorizon,
) -> list[dict[str, Any]]:
    """Pivot counts per candidate width, with the drop reason when a width is skipped.

    Pivot pins are detected at the horizon's confirmation width, which depends on the
    grid and not on the candidate width, so every width in a horizon sees the SAME
    counts; the row is per width anyway, so a future grid that derives pivots per width
    cannot silently change one column.
    """
    peak_pins, trough_pins = detect_pivots(dates, prices, horizon)
    scored_widths = {
        candidate.half_width_days
        for candidate in discover_candidate_periods(dates, prices, horizon)
    }
    rows: list[dict[str, Any]] = []
    for width in horizon.half_widths:
        dropped = len(peak_pins) < horizon.min_peaks or len(trough_pins) < horizon.min_troughs
        rows.append(
            {
                "half_width_days": width,
                "n_peaks": len(peak_pins),
                "n_troughs": len(trough_pins),
                "scored": width in scored_widths,
                "dropped": dropped,
                "drop_reason": (
                    f"pivot counts {len(peak_pins)} peaks / {len(trough_pins)} troughs fall "
                    f"below the frozen minima {horizon.min_peaks} / {horizon.min_troughs}; "
                    "the minimum is never lowered to fit a grid"
                )
                if dropped
                else None,
            }
        )
    return rows


def metrics_row(
    label: str,
    metrics: RiskMetrics,
    *,
    exposure_pct: float | None,
    eligible: bool | None = None,
    rejection: str | None = None,
    n_windows: int | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """A ``score_row``-shaped row for ANY equity path.

    Used for the ``score_periods`` candidates and, with ``extra``, for a comparator
    path (lump / flat DCA) so both land in one table with one column set — a
    comparator is not a period set, so ``n_windows`` / eligibility may be ``None``.
    """
    row: dict[str, Any] = {
        "label": label,
        "half_width_days": None,
        "n_windows": n_windows,
        "n_buy_dates": None,
        "n_sell_dates": None,
        "truncated_windows": [],
        "total_return_pct": metrics.total_return_pct,
        "cagr_pct": metrics.cagr_pct,
        "sharpe": metrics.sharpe,
        "sortino": metrics.sortino,
        "calmar": calmar_or_none(metrics.max_drawdown_pct, metrics.calmar),
        "calmar_blank_reason": (
            f"max_drawdown_pct {metrics.max_drawdown_pct:.3e} < {CALMAR_DD_EPS_PCT:.0e} "
            "drawdown epsilon (float dust divisor, Ruling 2 read-layer rule)"
            if metrics.max_drawdown_pct < CALMAR_DD_EPS_PCT
            else None
        ),
        "max_drawdown_pct": metrics.max_drawdown_pct,
        "exposure_pct": exposure_pct,
        "meets_exposure_floor": None,
        "degenerate": None,
        "eligible": eligible,
        "rejection": rejection,
    }
    if extra:
        row.update(extra)
    return row


def score_row(score: PeriodScore, *, label: str | None = None) -> dict[str, Any]:
    """One candidate as a JSON-ready row: every metric, the blanked Calmar, the verdict."""
    row = metrics_row(
        label
        or (f"pm{score.half_width_days}" if score.half_width_days is not None else "no-width"),
        score.metrics.metrics,
        exposure_pct=score.exposure_pct,
        eligible=score.eligible,
        rejection=score.rejection,
        n_windows=len(score.windows),
    )
    row["half_width_days"] = score.half_width_days
    row["n_buy_dates"] = len(score.edges.buy_dates)
    row["n_sell_dates"] = len(score.edges.sell_dates)
    row["truncated_windows"] = list(score.edges.truncated_windows)
    row["meets_exposure_floor"] = score.meets_exposure_floor
    row["degenerate"] = score.degenerate
    return row


def score_columns(row: dict[str, Any]) -> list[str]:
    """Pre-formatted console cells for one candidate row (blank Calmar stays blank)."""
    return [
        str(row["label"]),
        "-" if row["n_windows"] is None else str(row["n_windows"]),
        fmt_opt(row["sharpe"], ".4f"),
        fmt_opt(row["calmar"], ".3f"),
        fmt_opt(row["sortino"], ".3f"),
        fmt_opt(row["cagr_pct"], ".2f"),
        fmt_opt(row["total_return_pct"], ".2f"),
        fmt_opt(row["max_drawdown_pct"], ".2f"),
        fmt_opt(row["exposure_pct"], ".2f"),
        "n/a" if row["eligible"] is None else ("yes" if row["eligible"] else "NO"),
        row["rejection"] or "-",
    ]


SCORE_HEADER: tuple[str, ...] = (
    "candidate",
    "wins",
    "sharpe",
    "calmar",
    "sortino",
    "cagr%",
    "total%",
    "maxdd%",
    "expo%",
    "eligible",
    "rejection",
)


def print_table(title: str, header: Sequence[str], rows: Sequence[Sequence[str]]) -> None:
    """Fixed-width console table; cells are already formatted by the caller."""
    print(title)
    widths = [
        max(len(str(header[index])), *(len(row[index]) for row in rows))
        if rows
        else len(header[index])
        for index in range(len(header))
    ]
    print("  ".join(str(cell).rjust(widths[index]) for index, cell in enumerate(header)))
    for row in rows:
        print("  ".join(str(cell).rjust(widths[index]) for index, cell in enumerate(row)))
    print("")


def print_candidate_table(title: str, rows: Sequence[dict[str, Any]]) -> None:
    """Print a candidate ladder from :func:`score_row` payloads."""
    print_table(title, SCORE_HEADER, [score_columns(row) for row in rows])


def run_horizon(
    dates: Sequence[date],
    prices: Sequence[float],
    horizon: PeriodHorizon,
    *,
    initial_cash: float = DEFAULT_INITIAL_CASH,
) -> tuple[PeriodOptimizationResult | None, str | None]:
    """Optimize one horizon; ``(None, reason)`` when discovery found no structure.

    ``optimize_periods`` raises ``ValueError`` when no candidate survives the
    minima. That is a result, not a crash: it is returned as the reason string so
    the caller can record it verbatim instead of inventing periods to fill the gap.
    """
    try:
        return optimize_periods(dates, prices, horizon, initial_cash=initial_cash), None
    except ValueError as error:
        return None, str(error)


def sharpe_ties(scores: Sequence[PeriodScore]) -> int:
    """How many adjacent ranked pairs share an EXACT Sharpe.

    Calmar only breaks an exact Sharpe tie, so this is the count of pairs where the
    reported (epsilon-blanked) Calmar could have influenced the order at all. It is
    reported so a reader can see that blanking Calmar never changed a selection.
    """
    ranked = list(scores)
    return sum(
        1 for left, right in zip(ranked, ranked[1:], strict=False) if left.sharpe == right.sharpe
    )


def split_sample_payload(result: SplitSampleResult) -> dict[str, Any]:
    """Both split-sample sides, with a null side explained rather than hidden."""
    return {
        "horizon": result.horizon.name,
        "split": result.split,
        "fit_days": result.fit_days,
        "score_days": result.score_days,
        "fit_best": score_row(result.fit_best) if result.fit_best is not None else None,
        "fit_best_absent_reason": (
            None
            if result.fit_best is not None
            else "no candidate cleared the frozen time-in-market floor on the fit half"
        ),
        "out_of_sample": (
            score_row(result.out_of_sample) if result.out_of_sample is not None else None
        ),
        "out_of_sample_absent_reason": (
            None
            if result.out_of_sample is not None
            else "no fit winner existed to carry into the unseen half"
        ),
        "out_of_sample_eligible": result.out_of_sample_eligible,
    }


def horizon_payload(
    symbol: str,
    horizon: PeriodHorizon,
    result: PeriodOptimizationResult | None,
    error: str | None,
    *,
    dates: Sequence[date],
    prices: Sequence[float],
    initial_cash: float,
) -> dict[str, Any]:
    """The full per-horizon block: grid, pivots, every candidate, the selection verdict."""
    block: dict[str, Any] = {
        "horizon": horizon.name,
        "symbol": symbol,
        "grid": horizon.model_dump(mode="json"),
        "grid_label": grid_label(horizon),
        "confirmation_days": confirmation_days(horizon),
        "exposure_floor_pct": EXPOSURE_FLOOR_PCT,
        "initial_cash": initial_cash,
        "calendar": {
            "bars": len(dates),
            "first": dates[0].isoformat(),
            "last": dates[-1].isoformat(),
        },
        "pivot_counts_per_width": pivot_rows(dates, prices, horizon),
        "discovery_error": error,
        "candidates": [],
        "selection": {
            "best": None,
            "best_absent_reason": error or "no candidate cleared the frozen time-in-market floor",
        },
        "exact_sharpe_tie_pairs": 0,
    }
    if result is None:
        return block
    rows = [score_row(score) for score in result.scores]
    block["candidates"] = rows
    block["peak_pins"] = [day.isoformat() for day in result.peak_pins]
    block["trough_pins"] = [day.isoformat() for day in result.trough_pins]
    block["selection"]["best"] = score_row(result.best) if result.best is not None else None
    if result.best is None:
        block["selection"]["best_absent_reason"] = (
            f"every scored candidate failed the frozen {EXPOSURE_FLOOR_PCT:.1f}% "
            "time-in-market floor (or was degenerate); the floor is never lowered here"
        )
        block["selection"]["rank1_ineligible_diagnostic"] = {
            "warning": (
                "NOT a selection: the highest-ranked candidate under the frozen objective "
                "while ineligible. Reported so the owner can see what the floor cost; it "
                "must never be quoted as the optimizer's best."
            ),
            "candidate": rows[0] if rows else None,
        }
    block["exact_sharpe_tie_pairs"] = sharpe_ties(result.scores)
    return block


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symbol", required=True, help="price symbol, e.g. GLD-USD or BTC-USD")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=None,
        help="OHLCV csv (default: digiquant/data/price-history/<symbol>.csv)",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="directory holding <symbol>.csv (default: the conventional price-history dir)",
    )
    parser.add_argument(
        "--horizon",
        choices=HORIZON_NAMES,
        default="medium",
        help="which frozen grid to search (reported against its own grid only)",
    )
    parser.add_argument("--out", type=Path, default=None, help="optional JSON output path")
    parser.add_argument(
        "--split-sample",
        action="store_true",
        help="also run the fit-on-first-half / score-on-unseen-half check",
    )
    parser.add_argument(
        "--initial-cash",
        type=float,
        default=DEFAULT_INITIAL_CASH,
        help=f"oracle capital (default {DEFAULT_INITIAL_CASH:.0f}; ratios are scale-free)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.data_path is not None and args.data_dir is not None:
        raise SystemExit("pass --data-path or --data-dir, not both")
    data_path = args.data_path or default_data_path(args.symbol)
    dates, prices = load_closes(args.symbol, data_path)
    horizon = horizon_by_name(args.horizon)

    print(f"{args.symbol} {dates[0]}..{dates[-1]} ({len(dates)} daily bars) from {data_path}")
    print(CEILING_LABEL)
    print(OBJECTIVE_LABEL)
    print(grid_label(horizon))
    print(RISK_FREE_LABEL)

    result, error = run_horizon(dates, prices, horizon, initial_cash=args.initial_cash)
    if result is None:
        print(f"no candidates for horizon {horizon.name!r}: {error}")
        block = horizon_payload(
            args.symbol,
            horizon,
            None,
            error,
            dates=dates,
            prices=prices,
            initial_cash=args.initial_cash,
        )
    else:
        rows = [score_row(score) for score in result.scores]
        print(
            f"pivots: {len(result.peak_pins)} peaks / {len(result.trough_pins)} troughs at "
            f"confirmation {confirmation_days(horizon)} bars (identical for every width)"
        )
        print_candidate_table("candidate table (best-first under the frozen objective):", rows)
        block = horizon_payload(
            args.symbol,
            horizon,
            result,
            None,
            dates=dates,
            prices=prices,
            initial_cash=args.initial_cash,
        )
        best = block["selection"]["best"]
        if best is None:
            print(
                f"SELECTION: none — {block['selection']['best_absent_reason']}. "
                f"See the ladder above; the highest-ranked ineligible row is a diagnostic only."
            )
        else:
            print(
                f"SELECTION: {best['label']} (sharpe {best['sharpe']:.4f}, "
                f"exposure {best['exposure_pct']:.2f}%)"
            )
        print(
            f"exact-sharpe tie pairs (the only way Calmar affects order): "
            f"{block['exact_sharpe_tie_pairs']}"
        )

    if args.split_sample:
        split = split_sample_check(dates, prices, horizon, initial_cash=args.initial_cash)
        payload = split_sample_payload(split)
        block["split_sample"] = payload
        print(
            f"split-sample ({split.split:.0%} fit): fit side on {split.fit_days} bars -> "
            f"{payload['fit_best'] and payload['fit_best']['label'] or 'NONE'} "
            f"({payload['fit_best_absent_reason'] or 'eligible'}); unseen side on "
            f"{split.score_days} bars -> "
            f"{payload['out_of_sample'] and payload['out_of_sample']['label'] or 'NONE'} "
            f"({payload['out_of_sample_absent_reason'] or 'eligible'}), "
            f"out_of_sample_eligible={split.out_of_sample_eligible}"
        )

    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(block, indent=2, default=str) + "\n")
        print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
