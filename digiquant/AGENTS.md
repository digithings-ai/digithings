# Agent Guide: DigiQuant

## Purpose

DigiQuant is the **deterministic quant engine** of DigiThings. It owns and executes the ordered pipeline: validate → backtest → optimize → export. No other service may make performance claims (Sharpe, PnL, trade count) without a result originating from this service. It is the sole source of truth for strategy evaluation.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — full pipeline, API surface, data models, Nautilus integration notes
2. [`docs/NAUTILUS_NAVIGATION.md`](docs/NAUTILUS_NAVIGATION.md) — **required** before any Nautilus strategy or backtest change
3. [`docs/NAUTILUS_QUICK_REF.md`](docs/NAUTILUS_QUICK_REF.md) — Nautilus Actor/Bar/Order quick reference
4. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules
5. [`../ROADMAP.md`](../ROADMAP.md) — do not implement VectorBT/Qlib/FinRL until Phase 3
6. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digiquant/`:

- [ ] Read `ARCHITECTURE.md` section for the area you're touching (data, strategies, backtest, optimize, server)
- [ ] Read `docs/NAUTILUS_NAVIGATION.md` if touching any strategy, backtest runner, or Nautilus wrapper
- [ ] Run `pytest tests/ -m unit -k "digiquant" -v` — passes before and after
- [ ] Run `ruff check digiquant/ && ruff format --check digiquant/` — zero errors
- [ ] Confirm no `import pandas` outside the [pandas allowlist](#pandas-allowlist-rem-058059) below
- [ ] Confirm no live-trading path touched (broker adapters, order submission) without human gate
- [ ] Confirm `BacktestResult` Pydantic model is unchanged or versioned if modified

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **Nautilus only**: NautilusTrader is the sole backtest and live-trade engine. Do not add a second backtest path. VectorBT Pro sweeps are Phase 3.
- **Polars except at documented boundaries**: Use Polars for all new data paths. Pandas is allowed only on paths in the allowlist below (Nautilus wrangler, tearsheet Plotly bridge, legacy atlas preload script). Do not add new pandas imports without updating this table.

### Pandas allowlist (REM-058/059)

| Path | Reason | Migration |
|------|--------|-------------|
| `digiquant/nautilus_runner.py` | Nautilus `BarDataWrangler` requires pandas | None — documented boundary |
| `digiquant/tearsheet.py` | Nautilus `account_report` / `fills_report` are pandas DataFrames | Defer — Plotly quantstats bridge |
| `digiquant/tearsheet_charts.py` | Plotly/quantstats expect pandas Series for rolling stats | Defer — same as tearsheet |
| `digiquant/scripts/atlas/*.py` | Legacy ops: yfinance / pandas-ta / treasury XML (REM-058 allowlist) | Migrate per-script to Polars in [#579](https://github.com/digithings-ai/digithings/issues/579); `compute-technicals.py` Polars date fix (REM-009) |
| `digiquant/scripts/atlas/preload-history.py` | Same atlas ops family | Delegate to `scripts/preload-history.py` (Polars) when touched |
| `digiquant/strategies/bollinger_mr.py` | Nautilus strategy bar helpers | Issue backlog — migrate to stdlib `timedelta` pattern (see `rsi_momentum.py`) |
| `digiquant/strategies/macd_trend.py` | Same | Same |
| `digiquant/strategies/rsi_momentum.py` | **Migrated** — uses `datetime.timedelta` only | Done (audit PR) |

- **No perf claims without results**: Never return Sharpe, PnL, or drawdown values from anywhere except a completed `BacktestResult` or `OptimizeResult`.
- **Pipeline ordering is sacrosanct**: validate → backtest → optimize → export. Never skip validation. Never run optimize before backtest.
- **Strategies compile to Nautilus Actor**: All strategies must implement the Nautilus `Actor`/`Strategy` interface. Custom Python strategy logic goes in `strategies/`, not inline in the backtest runner.
- **ADDM drift is wired**: `GET /check_drift` accepts `current_sharpe`; `run_backtest` calls `record_sharpe()`. Heartbeat still needs product wiring to act on `drift_detected`.
- **Human gate on live trading**: Broker adapter code (`digiquant/brokers/`) must never be called from any automated path without an explicit human gate.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digiquant" -v

# Single strategy test
pytest tests/digiquant/test_strategies.py -v

# Backtest smoke test (requires data file)
digiquant backtest -s ema_cross -S BTC-USD -d digiquant/data/BTC-USD.csv -v

# Optimize smoke test
digiquant optimize -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -m grid -n 10

# Full unit suite
make test-unit

# Lint
ruff check digiquant/ && ruff format --check digiquant/
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
