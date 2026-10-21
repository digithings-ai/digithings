# DIG-194 — trade-idea card, reprinted from the fixed fields

**Status:** reprint of the card that DIG-205 published before the two blockers landed.
Every number below is quoted from one `BacktestResult` produced by the shipped
DigiQuant engine on 2026-10-21, at `develop` tip `f11a392dd7`.

The reprint exists because the first card quoted numbers the engine did not return
and could not carry a win rate with its sample size. Both defects are fixed on
`develop` (DIG-427, DIG-428). This card is printed from the fixed contract only.

**This is not an order.** Ideas only: no broker adapter, no export, no activation
control, no paper-to-live switch.

---

## 1. The path

| Step | What ran | Real or stand-in |
| --- | --- | --- |
| Research note | The folded design note on DIG-194 (Radar market scan + Lab product read) | Real. It is this issue's own deliverable, not a substitute for it. |
| Backtest | `run_backtest("ema_cross", ["AAPL"], data_path="digiquant/data/AAPL.csv")` on nautilus_trader 1.230.0 | Real engine, real run. |
| Optimization | `run_optimize("ema_cross", ["AAPL"], param_grid=3x3 EMA grid, objective="sharpe")` | Real grid search, 9 trials, 9/9 passed constraints. |
| Trade idea | The card in section 3 | Quoted from the `BacktestResult` JSON below. Nothing typed in by hand. |

`ema_cross` is in the DigiQuant registry (`digiquant/src/digiquant/strategies/ema_cross.py`),
it is the simplest of the eleven registry strategies, and AAPL is the one symbol.
No free-form strategy language was invented in this pass.

## 2. The envelope the chat receives

The chat reads a string, not an object: `digiquant_run_backtest` returns
`result.model_dump_json(indent=2)` (`digiquant/src/digiquant/mcp_server.py:772`).
`tests/dq/test_backtest_result_json.py` asserts on that string (DIG-474 L4).
This is the JSON the card is printed from:

```json
{
  "run_id": "nautilus-0bd681d6",
  "strategy_name": "ema_cross",
  "symbols": ["AAPL"],
  "start_time": "2024-01-01T00:00:00Z",
  "end_time": "2024-12-31T00:00:00Z",
  "total_pnl": -31010.400000000023,
  "total_return_pct": -3.1010400000000025,
  "sharpe_ratio": -0.09310998448342742,
  "max_drawdown_pct": -5.11,
  "num_trades": 34,
  "per_symbol_pnl": {},
  "missing": [],
  "honest_rate": {
    "k": 0,
    "n": 34,
    "estimate": 0.0,
    "ci_lo": 0.0,
    "ci_hi": 0.10151455415332376,
    "low_sample": false,
    "refused": false,
    "schema": "1.0",
    "basis": "closed round trips (Nautilus realized PnL, one per closed position)",
    "n_unit": "closed round trips",
    "warn_floor": 30,
    "refuse_floor": 10,
    "stability": {
      "first_half": {"n": 17, "k": 0, "estimate": 0.0, "ci95": [0.0, 0.1843181350088518]},
      "second_half": {"n": 17, "k": 0, "estimate": 0.0, "ci95": [0.0, 0.1843181350088518]},
      "agree": true
    },
    "disclaimer": "Historical conditional frequencies with sample sizes. Not predictions, not advice."
  },
  "honest_rate_by_symbol": {},
  "engine_provenance": {
    "engine": "nautilus_trader",
    "resolved_version": "1.230.0",
    "pin": "nautilus_trader==1.230.0",
    "lock": {"file": "uv.lock", "sha256_12": "1848a8646a7e"},
    "arithmetic": "balance_path",
    "returns_series_verified": true
  },
  "status": "ok",
  "message": "Backtest on user OHLCV data (AAPL).",
  "success": true
}
```

`run_id` is new on every run. Every other value above is stable across re-runs of
the same code, data and parameters: four independent runs produced identical
Sharpe, drawdown, PnL, `num_trades` and `honest_rate` values, on both logging
backends.

## 3. The trade-idea card

```
=== TRADE IDEA CARD (DIG-194) ===
strategy: ema_cross   symbol: AAPL
run_id: nautilus-0bd681d6   status: ok   missing: []
window: 2024-01-01T00:00:00Z .. 2024-12-31T00:00:00Z

-- Evidence A: DigiQuant backtest (performance numbers) --
  Sharpe ratio: -0.09310998448342742
  Max drawdown: -5.11 %
  Total PnL: -31010.400000000023 USD
  Total return: -3.1010400000000025 %

-- Evidence B: closed-round-trip frequency (honesty envelope) --
  Win rate: 0.0% (0/34, n=34, 95% CI [0.0%, 10.2%])
  Basis: closed round trips (Nautilus realized PnL, one per closed position)
  Disclaimer: Historical conditional frequencies with sample sizes. Not predictions, not advice.

-- Engine provenance --
  nautilus_trader 1.230.0 (pin nautilus_trader==1.230.0, lock uv.lock 1848a8646a7e)
  arithmetic: balance_path

NOT AN ORDER. Ideas only: no broker adapter, no export, no activation.
```

### What each line obeys

- **Sharpe, max drawdown, total PnL and total return** come from one balance path.
  `engine_provenance.arithmetic` says `balance_path`: the four numbers cannot
  disagree with each other, because they are derived from the same balance series.
- **The win rate is a frequency, not a performance number, and it is labelled
  separately.** It carries `k`, `n` and the Wilson 95% interval, so no bare
  percentage is printed. `n=34` clears the warn floor of 30, so the block is not
  marked low sample and the estimate is published.
- **`num_trades` is never used as a denominator.** The denominator on the card is
  `honest_rate.n` (34 closed round trips), which the block carries with its own
  numerator. `num_trades` happens to be 34 as well — since DIG-1808 it counts
  closed round trips, the same population — but the card does not derive the rate
  from it.
- **The stability split** is carried: first half 0/17, second half 0/17, the two
  Wilson intervals overlap, so `agree` is true. The rate is not a first-half
  artefact.
- **The disclaimer** travels with the number, in the words of
  `digiquant/src/digiquant/stats/honesty.py`.

### The optimization step

Nine trials over `fast_ema_period` 5/8/10 by `slow_ema_period` 15/20/25, objective
Sharpe, 9/9 passed constraints:

```json
{
  "run_id": "optimize-172d2d5c",
  "strategy_name": "ema_cross",
  "symbols": ["AAPL"],
  "best_params": {"fast_ema_period": 8, "slow_ema_period": 25},
  "best_backtest": {
    "run_id": "nautilus-adc8c174",
    "total_pnl": -28353.199999999953,
    "total_return_pct": -2.8353199999999954,
    "sharpe_ratio": -0.07837497762647883,
    "max_drawdown_pct": -4.844280000000005,
    "num_trades": 34,
    "honest_rate": {"k": 0, "n": 34, "estimate": 0.0, "ci_lo": 0.0, "ci_hi": 0.10151455415332376,
                    "low_sample": false, "refused": false},
    "status": "ok"
  },
  "num_evaluations": 9,
  "status": "ok",
  "message": "grid optimization (9/9 passed constraints)."
}
```

**The optimized parameters are still a losing configuration.** The grid search
returned the least-bad of nine trials, not a good strategy. The card says so rather
than letting the optimizer's "best" label carry an implication it does not support.

## 4. What this run is, and what it is not

This is **not** evidence that EMA crossover works on AAPL. Every one of the 34
closed round trips was a loss, the return is negative, and the best grid point is
still negative. The run is evidence that the honesty contract works: the engine
publishes one balance-path Sharpe, one drawdown, one PnL, and a win rate that
cannot be printed without its sample size and interval.

The earlier note in this issue recorded `OrderRejected` events
(`SHORT SELLING not permitted on a CASH account`) in the engine log for this
strategy. The same rejection is still there in the current run: 191 `OrderRejected`
events on the same data. The arithmetic on the card is unaffected by that, but it
is the reason the demo is presented as a contract test rather than as a strategy
result — 34 closed round trips, all of them long, all of them losers.

The harness runs on the Python logging backend, so it does not print those
rejections. The count above comes from the same backtest run on the Rust logging
backend; the numbers are identical either way.

## 5. How to reproduce it

```sh
uv sync --frozen --package digiquant --extra nautilus
cp /path/to/digiquant/data/AAPL.csv digiquant/data/AAPL.csv   # local, git-ignored
.venv/bin/python digiquant/scripts/run_dig194_trade_idea_card.py \
    --data-path digiquant/data/AAPL.csv
```

The harness (`digiquant/scripts/run_dig194_trade_idea_card.py`) prints the card,
writes both envelopes as JSON, and needs no hand-written number. It selects the
Python logging backend before the first engine run: the Nautilus Rust logger can
only be initialised once per process, and the optimization step runs nine engine
runs in one process. The logging backend changes where the log lines go, not the
numbers.

## 6. Boundaries held

No live orders, no broker adapter, no export, no activate control, no paper-to-live
switch, no second backtester. This branch is not merged to `develop` or `main`.
No file listed as off-limits was edited: `apps/dashboard-api/src/index.ts`,
`DEPLOYMENT.md` and `digiquant/ARCHITECTURE.md` are untouched.
