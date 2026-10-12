# DIG-951: rc6 Probe Results — Both Questions Closed

Ran a real backtest against `nautilus_trader==2.0.0rc6` (installed to `/tmp/nt_rc6`).

## Q1: Do the stat key names survive?

**Partially.** Here is the rc6 `PortfolioStatistics` surface (from `engine.portfolio.statistics()`):

| Key in our code | rc6 status | Where it lives |
|---|---|---|
| `"Sharpe Ratio (252 days)"` | ✅ **SURVIVES** | `stats.returns["Sharpe Ratio (252 days)"]` |
| `"Max Drawdown %"` | ❌ **GONE** | Not in any stats dict |
| `"Max Drawdown"` | ❌ **GONE** | Not in any stats dict |
| `result.max_drawdown_pct` | ❌ **GONE** | Not on `BacktestResult` in rc6 |

**Max drawdown must be computed from the returns series** (the fallback code at `nautilus_runner.py:370-384` already does this — it will become the primary path).

## Q2: API surface changes

The entire `PortfolioAnalyzer` API is replaced:

| Old API (1.223.0) | New API (rc6) |
|---|---|
| `engine.portfolio.analyzer` | `engine.portfolio.statistics()` |
| `analyzer.get_performance_stats_returns()` | `stats.returns` (dict property) |
| `analyzer.get_performance_stats_pnls()` | `stats.pnls` (dict property, **nested by currency**: `{"USD": {...}}`) |
| `analyzer.get_performance_stats_general()` | `stats.general` (dict property) |
| `analyzer.returns()` | `stats.returns_series` (dict property) |
| `analyzer.realized_pnls(USD)` | Not directly available |
| `result.max_drawdown_pct` | Not available |

**`PortfolioStatistics` lives in `nautilus_trader.analysis`** (not `nautilus_trader.portfolio`).

## Migration impact

1. **`_extract_perf_stats` needs a rewrite** — the analyzer methods are gone; replace with dict property access
2. **PnL stats are nested by currency** — `stats.pnls` returns `{"USD": {...}}`, so we need to extract the currency sub-dict (the tearsheet code at `tearsheet_stats.py:131-133` already handles this pattern)
3. **Max drawdown** — must come from `stats.returns_series` (compute from cumulative returns), not from a pre-computed key
4. **Sharpe** — key name survives, just moves from `get_performance_stats_returns()["Sharpe Ratio (252 days)"]` to `stats.returns["Sharpe Ratio (252 days)"]`

## Effort estimate

- `_extract_perf_stats` rewrite: **~30-60 min** (mechanical replacement + currency unwrapping)
- Max drawdown from returns series: **already implemented as fallback** (~10 min to make it primary)
- `tearsheet_stats.py` updates: **~15 min** (same key names, just new access path)
- Testing: **~30 min** (run existing backtests against rc6)

**Total: ~1.5-2 hours.** Low risk — the shape is confirmed, the keys are mostly the same, and the max-drawdown fallback already exists.

## Recommendation

**Proceed with the migration.** The API change is mechanical, the key names mostly survive, and the max-drawdown fallback is already in place. The rc6 upgrade is viable for `digiquant`.

## Evidence

- Probe script: `/tmp/probe_rc6_stats.py`
- rc6 installed at: `/tmp/nt_rc6`
- Backtest ran successfully: 100 iterations, 0 trades (no strategy attached), portfolio statistics all NaN as expected
- `PortfolioStatistics` confirmed at `nautilus_trader.analysis.PortfolioStatistics`
- `BacktestResult` confirmed at `nautilus_trader.backtest.BacktestResult` with `stats_general`, `stats_pnls`, `stats_returns` attributes
