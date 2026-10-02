#!/usr/bin/env python3
"""GOLD wiring for the generic SDCA period optimizer (#4804, Plan 20, Task 3).

Runs the medium and long horizons on the cached GLD closes, combines them
(long sells override medium buys), prices both comparators, and writes one
JSON carrying every metric, the split-sample pairs and the CEILING label:

    PYTHONPATH=digiquant/src .venv/bin/python \\
        digiquant/scripts/run_gold_period_optimization.py

Writes only ``digiquant/.scratch/gold_period_optimization.json`` (UNTRACKED).
All search machinery lives in the generic modules — this file is the gold
wiring plus the console ladder; ``optimize_sdca_periods.py`` is the same
ladder for any other symbol and carries the shared read-layer rules (the
Ruling 2 Calmar epsilon, the ceiling sentence, the table/row formatting), so
both scripts can never drift apart on how a number is presented.

**The honest frame, printed before every table.** The oracle is an IN-SAMPLE
CEILING on the same history the periods were fit on: it buys the entire book
all-in on each pinned buy date and sells all-out on each pinned sell date, so
it measures period *quality*, never achievable performance. The split-sample
read (fit periods on the first half, score on the unseen second half) is the
only out-of-sample-ish number here, and both sides are reported together.

**Nothing is tuned in this file.** The objective, the 70% time-in-market floor
and the two grids are frozen module constants. A width whose pivot count falls
below the minima is reported as dropped, and a candidate that misses the floor
is reported as ineligible: neither minimum is lowered to make a run succeed.
When nothing is eligible, the highest-ranked ineligible candidate is still
printed — labeled ``rank1 diagnostic, NOT a selection`` — so the owner can see
what the floor cost without it ever being quotable as a result.

Research-only. No engine call, no backtest, no ``nautilus_trader`` import.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path
from typing import Any

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from optimize_sdca_periods import (  # noqa: E402
    CEILING_LABEL,
    OBJECTIVE_LABEL,
    RISK_FREE_LABEL,
    fmt_opt,
    grid_label,
    horizon_by_name,
    horizon_payload,
    load_closes,
    metrics_row,
    print_candidate_table,
    run_horizon,
    score_row,
    split_sample_payload,
)

from digiquant.strategies.sdca.dca_metrics import (  # noqa: E402
    flat_dca_mark_to_market,
    lump_mark_to_market,
)
from digiquant.strategies.sdca.period_optimize import (  # noqa: E402
    DEFAULT_INITIAL_CASH,
    EXPOSURE_FLOOR_PCT,
    PeriodScore,
    combine_periods,
    score_periods,
    split_sample_check,
)
from digiquant.strategies.sdca.risk_metrics import equity_metrics  # noqa: E402

SYMBOL = "GLD-USD"
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / f"{SYMBOL}.csv"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_period_optimization.json"

SPLIT = 0.5

HOLDOUT_NOTE = (
    "in-sample by construction: this run scores the FULL cached GLD history, the same "
    "history the periods are derived from. No separate holdout segment was carved out "
    "or touched; the split-sample pair below is the only out-of-sample-ish read."
)

SOURCES = (
    DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "sdca" / "period_optimize.py",
    DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "sdca" / "risk_metrics.py",
    DIGIQUANT_ROOT / "src" / "digiquant" / "strategies" / "sdca" / "perfect_strategy.py",
    DIGIQUANT_ROOT / "scripts" / "optimize_sdca_periods.py",
    DIGIQUANT_ROOT / "scripts" / "run_gold_period_optimization.py",
)


def sha256(path: Path) -> str:
    """Full-file digest, so every number in the JSON is traceable to its inputs."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def header(symbol: str, dates: Sequence[date], data_path: Path) -> None:
    """Print the honesty frame once, above every table."""
    print(f"=== GOLD PERIOD OPTIMIZATION ({symbol}) — Plan 20 Task 3 (#4804) ===")
    print(f"{symbol} {dates[0]}..{dates[-1]} ({len(dates)} daily bars) from {data_path}")
    print(CEILING_LABEL)
    print(OBJECTIVE_LABEL)
    print(RISK_FREE_LABEL)
    print(HOLDOUT_NOTE)
    print("")


def print_pivot_table(name: str, rows: Sequence[dict[str, Any]]) -> None:
    """Pivot counts per candidate width (identical per width; see pivot_rows docstring)."""
    print(f"{name} pivots per candidate width:")
    for row in rows:
        mark = "scored" if row["scored"] else "DROPPED"
        print(
            f"  pm{row['half_width_days']:<4} {row['n_peaks']:>4} peaks / "
            f"{row['n_troughs']:>4} troughs  {mark}"
            + (f" — {row['drop_reason']}" if row["drop_reason"] else "")
        )
    print("")


def print_selection(name: str, block: dict[str, Any]) -> None:
    """The verdict for one horizon (or the combination), with the reason spelled out."""
    best = block["selection"]["best"]
    if best is not None:
        print(
            f"{name} SELECTION: {best['label']} — sharpe {best['sharpe']:.4f} | calmar "
            f"{fmt_opt(best['calmar'], '.3f') or '(blank: dd < eps)'} | cagr "
            f"{best['cagr_pct']:.2f}% | exposure {best['exposure_pct']:.2f}%"
        )
        return
    print(f"{name} SELECTION: NONE — {block['selection']['best_absent_reason']}")
    diagnostic = block["selection"].get("rank1_ineligible_diagnostic")
    if diagnostic and diagnostic.get("candidate"):
        row = diagnostic["candidate"]
        print(
            f"  rank1 diagnostic (NOT a selection): {row['label']} — sharpe {row['sharpe']:.4f}"
            f" | calmar {fmt_opt(row['calmar'], '.3f') or '(blank: dd < eps)'} | cagr "
            f"{row['cagr_pct']:.2f}% | maxdd {row['max_drawdown_pct']:.2f}% | exposure "
            f"{row['exposure_pct']:.2f}% | {row['rejection']}"
        )
    print("")


def rank1(rows: Sequence[dict[str, Any]]) -> dict[str, Any] | None:
    """Highest-ranked candidate row, whatever its eligibility (diagnostics only)."""
    return rows[0] if rows else None


def diagnostic_score(
    dates: Sequence[date],
    prices: Sequence[float],
    windows: Sequence[Any],
    *,
    label: str,
    half_width_days: int | None,
    exposure_floor_pct: float,
    initial_cash: float,
) -> dict[str, Any]:
    """Score a NON-selected window set (a floor-failing rank-1, a combined diagnostic).

    Every such row carries the ``diagnostic`` warning so it can never be mistaken for
    a selection in the JSON, in the console, or in a Task-4 chart.
    """
    score = score_periods(
        dates,
        prices,
        windows,
        exposure_floor_pct=exposure_floor_pct,
        initial_cash=initial_cash,
        half_width_days=half_width_days,
    )
    row = score_row(score, label=label)
    row["diagnostic"] = (
        "NOT a selection: this window set does not clear the frozen time-in-market floor "
        "and therefore may not be quoted as the optimizer's best."
    )
    return row


def comparators(prices: Sequence[float], initial_cash: float) -> dict[str, dict[str, Any]]:
    """``lump_mark_to_market`` + ``flat_dca_mark_to_market`` on the same calendar.

    Both are invested on every bar from day 0 (lump deploys at the first close; flat
    DCA spends ``cash / (n - i) > 0`` on bar 0), so ``exposure_pct`` is exactly 100.0
    for both — that is a property of the two paths, not an assumption.
    """
    paths = {
        "lump_mark_to_market": lump_mark_to_market,
        "flat_dca_mark_to_market": flat_dca_mark_to_market,
    }
    out: dict[str, dict[str, Any]] = {}
    for name, build in paths.items():
        values = build(prices, initial_cash)
        out[name] = metrics_row(
            name,
            equity_metrics(values),
            exposure_pct=100.0,
            eligible=None,
            rejection=None,
            extra={
                "comparator": True,
                "exposure_basis": "invested on every bar from day 0 by construction",
            },
        )
    return out


def combined_block(
    dates: Sequence[date],
    prices: Sequence[float],
    medium_rows: Sequence[dict[str, Any]],
    long_rows: Sequence[dict[str, Any]],
    medium_windows: Sequence[Any],
    long_windows: Sequence[Any],
    *,
    initial_cash: float,
) -> dict[str, Any]:
    """Combine the two horizons with the module's precedence and report the verdict.

    ``combine_periods`` emits long peaks, medium peaks, long troughs, medium troughs,
    and ``SdcaCycleWindows.kind_on`` returns the first match — so **long sells override
    medium buys** on a shared date.
    """
    combined = combine_periods(medium_windows, long_windows)
    block: dict[str, Any] = {
        "precedence": (
            "combine_periods order = long peaks, medium peaks, long troughs, medium "
            "troughs; SdcaCycleWindows.kind_on returns the first match, so LONG SELLS "
            "OVERRIDE MEDIUM BUYS on a shared date (flat = the conservative read of an "
            "ambiguous pin, matching the oracle's own sell-beats-buy rule)"
        ),
        "inputs": {
            "medium": rank1(medium_rows)["label"] if rank1(medium_rows) else None,
            "long": rank1(long_rows)["label"] if rank1(long_rows) else None,
        },
        "n_windows": len(combined.windows),
        "n_peaks": len(combined.peaks()),
        "n_troughs": len(combined.troughs()),
        "selection": {
            "best": None,
            "best_absent_reason": (
                "both horizons returned no eligible candidate under the frozen "
                f"{EXPOSURE_FLOOR_PCT:.1f}% time-in-market floor, so there is no selected "
                "medium/long set to combine; nothing here is a selection"
            ),
        },
        "windows": [window.model_dump(mode="json") for window in combined.windows],
    }
    block["rank1_ineligible_diagnostic"] = diagnostic_score(
        dates,
        prices,
        combined.windows,
        label="combined(rank1)",
        half_width_days=None,
        exposure_floor_pct=EXPOSURE_FLOOR_PCT,
        initial_cash=initial_cash,
    )
    return block


def combined_split_sample(
    dates: Sequence[date],
    prices: Sequence[float],
    medium_fit_windows: Sequence[Any],
    long_fit_windows: Sequence[Any],
    *,
    split: float,
    initial_cash: float,
) -> dict[str, Any]:
    """Fit-half medium+long rank-1 windows, scored on the unseen half (diagnostic).

    ``split_sample_check`` is per-horizon by design, so the combined pair is assembled
    here from the same two fit halves at the same ``int(len(dates) * split)`` index the
    module uses — the arithmetic is duplicated verbatim rather than re-derived.
    """
    split_at = int(len(dates) * split)
    combined = combine_periods(medium_fit_windows, long_fit_windows)
    out_of_sample = diagnostic_score(
        dates[split_at:],
        prices[split_at:],
        combined.windows,
        label="combined(rank1)",
        half_width_days=None,
        exposure_floor_pct=EXPOSURE_FLOOR_PCT,
        initial_cash=initial_cash,
    )
    return {
        "note": (
            "assembled in this wiring script from the two fit halves at the module's own "
            f"split index int(len(dates) * {split}) = {split_at}; split_sample_check is "
            "per-horizon by design"
        ),
        "split": split,
        "fit_days": split_at,
        "score_days": len(dates) - split_at,
        "fit_windows": len(combined.windows),
        "out_of_sample": out_of_sample,
        "out_of_sample_eligible": bool(out_of_sample["eligible"]),
    }


def main() -> int:
    dates, prices = load_closes(SYMBOL, DATA_PATH)
    header(SYMBOL, dates, DATA_PATH)

    horizon_blocks: dict[str, dict[str, Any]] = {}
    rank1_windows: dict[str, Sequence[Any]] = {}
    split_blocks: dict[str, dict[str, Any]] = {}
    fit_rank1_windows: dict[str, Sequence[Any]] = {}

    for name in ("medium", "long"):
        horizon = horizon_by_name(name)
        result, error = run_horizon(dates, prices, horizon, initial_cash=DEFAULT_INITIAL_CASH)
        block = horizon_payload(
            SYMBOL,
            horizon,
            result,
            error,
            dates=dates,
            prices=prices,
            initial_cash=DEFAULT_INITIAL_CASH,
        )
        horizon_blocks[name] = block

        rows = block["candidates"]
        print(grid_label(horizon))
        print_pivot_table(name, block["pivot_counts_per_width"])
        print_candidate_table(
            f"{name} candidate table (best-first under the frozen objective):", rows
        )
        print_selection(name, block)
        print(
            f"{name} exact-sharpe tie pairs (the only way Calmar can affect the order): "
            f"{block['exact_sharpe_tie_pairs']}"
        )
        print("")

        split = split_sample_check(dates, prices, horizon, split=SPLIT)
        split_blocks[name] = split_sample_payload(split)
        print(
            f"{name} split-sample ({SPLIT:.0%} fit): fit side {split.fit_days} bars -> "
            f"{(split_blocks[name]['fit_best'] or {}).get('label', 'NONE')} "
            f"({split_blocks[name]['fit_best_absent_reason'] or 'eligible'}); unseen side "
            f"{split.score_days} bars -> "
            f"{(split_blocks[name]['out_of_sample'] or {}).get('label', 'NONE')} "
            f"({split_blocks[name]['out_of_sample_absent_reason'] or 'eligible'}), "
            f"eligible={split.out_of_sample_eligible}"
        )
        if result is not None:
            top: PeriodScore | None = result.scores[0] if result.scores else None
            if result.best is not None:
                rank1_windows[name] = result.best.windows
            elif top is not None:
                rank1_windows[name] = top.windows

        # Diagnostic pair: the fit half's own rank-1 (floor-failing here) carried onto
        # the unseen half. This is the informative read when the floor leaves the
        # module's pair null, and it is labeled a diagnostic so it is never a selection.
        split_at = int(len(dates) * SPLIT)
        fit_result, fit_error = run_horizon(
            dates[:split_at], prices[:split_at], horizon, initial_cash=DEFAULT_INITIAL_CASH
        )
        fit_top: PeriodScore | None = (
            (fit_result.best or fit_result.scores[0])
            if fit_result is not None and (fit_result.best or fit_result.scores)
            else None
        )
        if fit_top is not None:
            fit_rank1_windows[name] = fit_top.windows
            fit_label = f"pm{fit_top.half_width_days}@fit"
            out_row = diagnostic_score(
                dates[split_at:],
                prices[split_at:],
                fit_top.windows,
                label=f"{fit_label}->unseen",
                half_width_days=fit_top.half_width_days,
                exposure_floor_pct=EXPOSURE_FLOOR_PCT,
                initial_cash=DEFAULT_INITIAL_CASH,
            )
            fit_row = score_row(fit_top, label=fit_label)
            fit_row["diagnostic"] = "NOT a selection: misses the frozen floor on the fit half."
            split_blocks[name]["diagnostic_pair"] = {
                "warning": (
                    "diagnostic only: neither side is a selection (both miss the frozen "
                    "floor). The pair exists so the out-of-sample read is visible instead "
                    "of null."
                ),
                "fit_rank1": fit_row,
                "out_of_sample": out_row,
                "out_of_sample_eligible": bool(out_row["eligible"]),
                "acted_dates_out_of_sample": (out_row["n_buy_dates"] or 0)
                + (out_row["n_sell_dates"] or 0),
            }
            print(
                f"  diagnostic pair (NOT a selection): fit rank1 {fit_label} -> unseen sharpe "
                f"{fmt_opt(out_row['sharpe'], '.4f')} | exposure "
                f"{fmt_opt(out_row['exposure_pct'], '.2f')}% | acted dates "
                f"{split_blocks[name]['diagnostic_pair']['acted_dates_out_of_sample']} | "
                f"{out_row['rejection'] or 'eligible'}"
            )
        elif fit_error:
            split_blocks[name]["diagnostic_pair"] = {"error": fit_error}
            print(f"  diagnostic pair unavailable: {fit_error}")
        print("")

    medium_windows = rank1_windows.get("medium", ())
    long_windows = rank1_windows.get("long", ())
    combined = combined_block(
        dates,
        prices,
        horizon_blocks["medium"]["candidates"],
        horizon_blocks["long"]["candidates"],
        medium_windows,
        long_windows,
        initial_cash=DEFAULT_INITIAL_CASH,
    )
    print("COMBINED (medium + long, long sells override medium buys):")
    print(
        f"  windows {combined['n_windows']} "
        f"({combined['n_peaks']} peaks / {combined['n_troughs']} troughs) from "
        f"{combined['inputs']['medium']} + {combined['inputs']['long']}"
    )
    print_candidate_table(
        "combined candidate table:",
        [combined["rank1_ineligible_diagnostic"]],
    )
    print_selection("combined", combined)
    print(combined["precedence"])
    print("")

    comparator_rows = comparators(prices, DEFAULT_INITIAL_CASH)
    print("comparators on the same calendar (dca_metrics, risk_metrics conventions):")
    print_candidate_table(
        "lump / flat comparator table:",
        [comparator_rows[name] for name in ("lump_mark_to_market", "flat_dca_mark_to_market")],
    )
    print(
        "read the ladder against these: an oracle ceiling may beat lump/flat and still be "
        "unachievable — the ceiling sentence above is the binding caveat."
    )
    print("")

    combined_split = (
        combined_split_sample(
            dates,
            prices,
            fit_rank1_windows.get("medium", ()),
            fit_rank1_windows.get("long", ()),
            split=SPLIT,
            initial_cash=DEFAULT_INITIAL_CASH,
        )
        if fit_rank1_windows.get("medium") and fit_rank1_windows.get("long")
        else {
            "note": "a fit half produced no candidate at all, so no combined pair exists",
            "out_of_sample": None,
            "out_of_sample_eligible": False,
        }
    )
    split_blocks["combined"] = combined_split
    print(
        "combined split-sample: fit side "
        f"{combined_split.get('fit_days')} bars / {combined_split.get('fit_windows')} windows "
        f"-> unseen side {(combined_split.get('out_of_sample') or {}).get('label', 'NONE')} "
        f"(sharpe "
        f"{fmt_opt((combined_split.get('out_of_sample') or {}).get('sharpe'), '.4f') or 'n/a'}"
        f", exposure "
        f"{fmt_opt((combined_split.get('out_of_sample') or {}).get('exposure_pct'), '.2f')}%), "
        f"eligible={combined_split.get('out_of_sample_eligible')}"
    )
    print("")
    print(CEILING_LABEL)

    payload = {
        "issue": 4804,
        "plan": 20,
        "task": 3,
        "kind": "gold-period-optimization",
        "symbol": SYMBOL,
        "data_path": str(DATA_PATH),
        "data_sha256": sha256(DATA_PATH),
        "source_sha256": {path.name: sha256(path) for path in SOURCES},
        "calendar": {
            "first": dates[0].isoformat(),
            "last": dates[-1].isoformat(),
            "bars": len(dates),
        },
        "ceiling_label": CEILING_LABEL,
        "objective_label": OBJECTIVE_LABEL,
        "risk_conventions_label": RISK_FREE_LABEL,
        "holdout_note": HOLDOUT_NOTE,
        "exposure_floor_pct": EXPOSURE_FLOOR_PCT,
        "initial_cash": DEFAULT_INITIAL_CASH,
        "split": SPLIT,
        "cross_grid_contest": False,
        "horizons": horizon_blocks,
        "combined": combined,
        "split_sample": split_blocks,
        "comparators": comparator_rows,
        "sharpe_tie_pairs": {
            name: horizon_blocks[name]["exact_sharpe_tie_pairs"] for name in horizon_blocks
        },
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"wrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
