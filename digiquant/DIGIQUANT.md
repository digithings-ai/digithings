# DigiQuant – High-Performance Quant Pipeline

**Purpose** (from `DIGI.md`): Research → Backtest → Optimize → Implement → Monitor engine. Zero pandas. Rust/Polars/Nautilus core.

**Design Principles**  
- **Intent-based design**: Strategy and optimization config express *what* to achieve (e.g. maximize Sharpe vs minimize drawdown); the pipeline decides *how* (which backtest path, which optimizer). Process mapping and clear role definition—who loads data, who runs backtest, who runs optimization—keep the pipeline auditable and agent-friendly.  
- **Configuration-as-Code**: Strategy, backtest, and optimization are declarative YAML (or equivalent); single source of truth, versionable, idempotent. Re-running the same config yields the same outcome; export is the only platform-specific step (Nautilus, QuantConnect, Pine, Alpaca, etc.).  
- **Asset-agnostic contract**: Downstream layers see only symbol and OHLCV (or Polars equivalents); asset-specific logic (equities vs crypto vs multi-exchange) lives in the data layer so new asset classes require no changes to strategy or backtest interfaces.

**Core Pipeline (Research → Backtest → Optimize → Implement → Monitor)**
1. Research agent (web + memory)
2. Strategy → Nautilus Actor
3. Sweeps → VectorBT Pro
4. ML signals → Qlib / FinRL / XGBoost
5. TradingView import/export (PyneCore)
6. Execution → Nautilus native IB + adapters
7. ADDM drift detection + re-optimization

**Two-Path Backtest Clarity**  
- **Event-driven (Nautilus)**: Full strategy lifecycle, realistic order handling, pre-trade risk. Use for single runs and live parity.  
- **Vectorized (VectorBT Pro)**: Fast sweeps and optimization loops over many parameter sets. Both paths consume the same strategy contract; long-term design favors a unified event bus (bar → signal → order → fill) with vectorized optimization as a dedicated fast path.

**Staged and Constrained Optimization**  
Optimization follows clear stages where applicable: e.g. foundation params first, keep top N, then add stages in order with incremental refinement. Hard constraints (min trades, max drawdown, min Sharpe) filter candidates before scoring; multi-objective (e.g. Pareto) is supported where metrics conflict. Primary metric and constraints are explicit in config so agents and humans share the same contract.

**MCP Tool Layer**  
DigiQuant exposes a thin orchestration layer to DigiGraph: run_backtest, run_optimize, run_validation (and where relevant run_baseline, load_strategy_spec). These entry points delegate to the core pipeline; agents invoke them via MCP with strategy/backtest/optimization config as resources or parameters. No need for agents to import core modules directly.

**Agent Workflow and Export**  
The canonical agent flow is: research (clarify goals, no code) → strategy source (generation or Pine retrieval) → baseline backtest → optimization and robustness checks → implementation (deploy). Each step has clear handoffs; export is a single step: strategy definition + best params → target platform artifact. Results and best params are written to Graphiti memory for persistence and audit.

**Delegated Compute and Production Readiness**  
Heavy optimization runs can be delegated to remote or batch compute (e.g. Modal or self-hosted workers) with the same config contract. Pre-trade risk (position limits, daily loss kill switch, exposure caps) is a first-class module, not bolted onto execution. Structured logging and optional metrics (fill rate, latency, PnL) support observability; defining fill/order event contracts now eases future unification with a single event bus.

**Approved Package Choices (Feb 2026)**
| Layer              | Package              | Reason |
|--------------------|----------------------|------|
| Backtest Engine    | NautilusTrader       | Rust core, live/backtest parity, 20.1k stars |
| Data               | Polars               | 20-30× faster than pandas, lazy Arrow |
| Sweeps             | VectorBT Pro         | Numba vectorized |
| ML/RL              | Qlib + FinRL         | Microsoft + AI4Finance production stacks |
| Interop            | PyneCore             | Deterministic Pine ↔ Python |

**Performance Targets**
- 10M-row backtest < 2 s
- 100k-param sweep < 30 s
- All heavy compute local/offline (token-free)

**Interfaces**
- Exposed as MCP tools to DigiGraph
- Data flows via Polars DataFrames (Arrow zero-copy)
- Results written to Graphiti memory

**No-Go Rules**
- Never use pandas
- Never duplicate existing engines
- All strategies must compile to Nautilus Actor

---

## Phase 2 implementation (complete)

- **Data layer** (`digiquant/data/`): Polars-only. `load_ohlcv_csv()`, `generate_synthetic_ohlcv()`, `list_symbols_from_dir()`. Standard columns: timestamp, open, high, low, close, volume, symbol.
- **Strategy Repository**: `digiquant/strategies/` — registry of Nautilus wrappers and custom strategies. See [docs/NAUTILUS_STRATEGIES.md](docs/NAUTILUS_STRATEGIES.md) for full Nautilus catalog. Available strategies: `ema_cross`, `ema_cross_long`, `ema_cross_trailing` (Nautilus wrappers); `rsi_momentum`, `bollinger_mr`, `macd_trend` (custom). Aliases: `mean_reversion_tech`, `momentum_tech` → ema_cross; `momentum_energy` → rsi_momentum; `mean_reversion_stat_arb` → bollinger_mr. Unknown strategy falls back to `ema_cross`. For Nautilus navigation and integration details, see [docs/NAUTILUS_NAVIGATION.md](docs/NAUTILUS_NAVIGATION.md) and [docs/NAUTILUS_QUICK_REF.md](docs/NAUTILUS_QUICK_REF.md).
- **Backtest**: `run_backtest()` runs Nautilus when `nautilus_trader` is installed (optional dep: `digiquant[nautilus]`). **Requires** `data_path` (single CSV) or `data_dir` (directory with `{symbol}.csv` files). OHLCV CSV: timestamp, open, high, low, close, volume (optional symbol). Bar period inferred from timestamp deltas. Set `DIGIQUANT_DATA_DIR` env for default data dir. Fails if data unavailable. Maps to `BacktestResult`. Pass `tearsheet_path` to generate an interactive HTML visualization (entries/exits, equity, drawdown, stats); requires `plotly>=6.3.1` (`digiquant[visualization]`). Relative paths resolve under `backtest_results/` (gitignored).
- **Optimize**: `run_optimize()` — grid, random, or Bayesian optimization; returns `OptimizeResult` (best_params, best_backtest). HTTP `POST /run_optimize`. **Methods**: `grid` (default), `random`, `bayesian` (Optuna; `pip install digiquant[optimize]`). **Auto-inference**: when `param_grid` is None, `infer_param_grid(strategy_name)` from `strategy_specs.py` yields ranges per strategy. **Constraints**: `OptimizationConstraints` (min_trades, max_drawdown_pct, min_sharpe, min_return_pct, min/max_trades_per_year) filter candidates before scoring. Use `generate_param_grid(param_specs, base_params)` for manual grids.
- **Export**: `run_export()` — writes JSON artifact for target (nautilus | tradingview | alpaca | quantconnect). Raises `ValueError` for unsupported target. HTTP `POST /run_export`.
- **CLI** (primary interface): `python -m digiquant` or `digiquant` after install. Commands: `backtest`, `optimize`, `export`. No fallbacks; raises on failure. Example:
  ```bash
  digiquant backtest -s bollinger_mr -S BTC-USD -d data/BTC-USD.csv -p trade_size=1
  digiquant optimize -s bollinger_mr -S BTC-USD -d data/BTC-USD.csv -m bayesian -n 100 -p trade_size=1
  digiquant export -s bollinger_mr -p period=25 -p std_dev=2.5 -p trade_size=1 -o backtest_results/exports
  ```
- **Pipeline**: `POST /run_pipeline` — backtest → optimize → export in one call.
- **Sweep**: `run_sweep()` — loop over param_grid calling backtest (VectorBT Pro later).
- **Broker adapters** (`digiquant/brokers/`): `BrokerAdapter` protocol; `IBAdapterStub`, `AlpacaAdapterStub`, `QuantConnectAdapterStub` (raise NotImplementedError).
- **TradingView** (`digiquant/tradingview.py`): `export_to_pine()` / `import_from_pine()` stubs for PyneCore.
- **ADDM**: `digiquant/addm.check_drift()` stub. Full drift detection in later phase.
- **Not yet**: VectorBT Pro fast sweeps, Qlib/FinRL ML, full PyneCore; MCP tool exposure (DigiGraph still calls HTTP).