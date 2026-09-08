---
type: behavior-guide
title: digiquant Strategies and Backtest
description: digiquant strategy registry and backtest semantics — registration, aliases, backtest caching, optimize, export, and result models.
tags: [digiquant, strategies, backtest, optimize]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-f049bd9504f8ed6c09ceb7ff
    resource: repo://digiquant/ARCHITECTURE.md
  - id: openwiki-source-006c18858eab61ec613abd4e
    resource: repo://digiquant/src/digiquant/backtest.py
  - id: openwiki-source-89fea6ce6379fad0eacf70ee
    resource: repo://digiquant/src/digiquant/models.py
  - id: openwiki-source-03367345d67d7d6162b06fce
    resource: repo://digiquant/src/digiquant/strategy_aliases.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digiquant Strategies and Backtest

Performance numbers come only from completed result models. This page
covers how strategies register, how names resolve, and what each pipeline
stage computes — the pipeline ordering itself lives in
[Architecture](/openwiki/digiquant/architecture.md).

## Registry and aliases

Six Nautilus strategies ship in `strategies/` (`ema_cross`,
`ema_cross_long`, `ema_cross_trailing`, `rsi_momentum`, `bollinger_mr`,
`macd_trend`), plus the SDCA engine (`btc_sdca`) and the `m2_liquidity`
runtime-path pattern. All implement the Nautilus Actor/Strategy
interface; `register(..., aliases=...)` enrolls each name. The canonical
alias map (`strategy_aliases.STRATEGY_ALIASES`, `resolve_strategy_name`)
folds user-facing names (`ema`, `s`, `mean_reversion_tech`,
`momentum_tech` → `ema_cross`; `mean_reversion_stat_arb` →
`bollinger_mr`); optimize param-spec keys may differ (`btc_sdca` →
`sdca`) via `PARAM_SPEC_NAMES`. One alias dict — never a second private
one.

## Backtest

`run_backtest(strategy_name, symbols, data_path|data_dir, ...)` requires
an explicit data source (no defaults), rejects unknown strategies and
empty symbol lists, and caches in memory by strategy/symbols/params/data
hash — skipped when a tearsheet path is set, disabled via
`DIGIQUANT_BACKTEST_CACHE=false`. Results are `BacktestResult`
(`run_id`, strategy, symbols, window, PnL, return %, Sharpe, drawdown,
trade count, per-symbol PnL, `ok|partial|error` status). Success records
Sharpe into ADDM history.

## Optimize and export

`run_optimize(...)` evaluates param sets (grid, random, bayesian, or
explicit `param_grid`) subject to `OptimizationConstraints` (min trades /
Sharpe / return, max drawdown, trade-frequency band), returning
`OptimizeResult` with `best_params` and the best trial's `BacktestResult`.
SDCA walk-forward uses the same path with objective `vs_flat_dca_pct`
under a capital-deployed floor and drawdown cap. `ExportResult` targets
`nautilus | tradingview | alpaca | quantconnect` with an artifact path.

## Human gate

Broker adapters and any order-submission path stay human-gated; no
automated caller may invoke them. Tearsheets and publish flows
(`--push-supabase`) are operator steps after real Nautilus runs — never
from agent environments, never with fabricated metrics.
