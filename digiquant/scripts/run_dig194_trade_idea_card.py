#!/usr/bin/env python3
"""DIG-194 proof of concept: research note → backtest → optimize → trade idea.

Prints the trade-idea card and the raw envelopes the card quotes. Every number on
the card comes from a ``BacktestResult`` / ``OptimizeResult`` this script produced;
nothing is typed in by hand.

Usage (from the repository root, with the digiquant venv on the path):

    .venv/bin/python digiquant/scripts/run_dig194_trade_idea_card.py \
        --data-path digiquant/data/AAPL.csv --out-dir /tmp/dig194

Why a script and not a chat reply: the card is only worth publishing if anybody
can re-run it and get the same numbers. This is the re-run.
"""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from nautilus_trader.common.component import set_logging_pyo3

from digiquant.backtest import run_backtest
from digiquant.optimize import run_optimize
from digiquant.stats.honesty import format_honest_rate

# The Nautilus Rust logger can only be initialised once per process: a second
# engine run in the same process panics with "attempted to set a logger after the
# logging system was already initialized". The optimization step runs nine engine
# runs in one process, so the Python logging backend is selected before the first
# engine run. It changes where the log lines go, not the numbers: a single-run card
# produced with the Rust backend and the same card produced with the Python backend
# carry identical Sharpe, drawdown, PnL and honest_rate values.
set_logging_pyo3(True)

#: The one strategy in the DigiQuant registry this POC uses.
STRATEGY = "ema_cross"

#: The one symbol this POC uses.
SYMBOL = "AAPL"

#: The grid the optimization step searches. Nine trials, 3x3.
PARAM_GRID = [
    {"fast_ema_period": fast, "slow_ema_period": slow}
    for fast in (5, 8, 10)
    for slow in (15, 20, 25)
]


def _card_lines(result, out_dir: Path) -> list[str]:
    """Render the trade-idea card from one BacktestResult.

    Every value printed here is read off ``result``. The win rate is read off
    ``result.honest_rate`` (its own k and n) and never off ``num_trades``.
    """
    block = result.honest_rate
    if block is None:
        rate_text = "REFUSED — no realized-PnL series on this run"
    else:
        rate_text = format_honest_rate(
            block.k, block.n, warn=block.warn_floor, refuse=block.refuse_floor
        )
    provenance = result.engine_provenance
    lines = [
        "=== TRADE IDEA CARD (DIG-194) ===",
        f"strategy: {result.strategy_name}   symbol: {', '.join(result.symbols)}",
        f"run_id: {result.run_id}   status: {result.status}   missing: {result.missing}",
        f"window: {result.start_time} .. {result.end_time}",
        "",
        "-- Evidence A: DigiQuant backtest (performance numbers) --",
        f"  Sharpe ratio: {result.sharpe_ratio}",
        f"  Max drawdown: {result.max_drawdown_pct} %",
        f"  Total PnL: {result.total_pnl} USD",
        f"  Total return: {result.total_return_pct} %",
        "",
        "-- Evidence B: closed-round-trip frequency (honesty envelope) --",
        f"  Win rate: {rate_text}",
        f"  Basis: {block.basis if block else 'n/a'}",
        f"  Disclaimer: {block.disclaimer if block else 'n/a'}",
        "",
        "-- Engine provenance --",
        f"  {provenance.engine} {provenance.resolved_version} (pin {provenance.pin}, "
        f"lock {provenance.lock.file} {provenance.lock.sha256_12})",
        f"  arithmetic: {provenance.arithmetic}",
        "",
        "NOT AN ORDER. Ideas only: no broker adapter, no export, no activation.",
    ]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "backtest_envelope.json").write_text(result.model_dump_json() + "\n")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-path", default="digiquant/data/AAPL.csv")
    parser.add_argument("--out-dir", default=str(Path(tempfile.gettempdir()) / "dig194-card"))
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)

    result = run_backtest(STRATEGY, [SYMBOL], data_path=args.data_path, full_tearsheet=True)
    for line in _card_lines(result, out_dir):
        print(line)

    print()
    print("=== OPTIMIZATION (9 trials, objective sharpe) ===")
    optimized = run_optimize(
        STRATEGY,
        [SYMBOL],
        param_grid=PARAM_GRID,
        method="grid",
        objective="sharpe",
        data_path=args.data_path,
        max_workers=args.workers,
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "optimize_envelope.json").write_text(optimized.model_dump_json() + "\n")
    print(optimized.model_dump_json())


if __name__ == "__main__":
    main()
