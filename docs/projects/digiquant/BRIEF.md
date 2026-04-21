# DigiQuant — Project Planning Brief
> For agent execution: generate GitHub Issues, Milestones, and Project Board from this document.

---

## Overview

DigiQuant is the quantitative finance toolkit module within the DigiThings platform. It is **not a standalone product** — it is a service layer that exposes capabilities as MCP tools and CLI commands, consumed by DigiGraph (the agent orchestration brain) and surfaced through DigiChat (the chat UI).

The primary use case is **interactive strategy development via chat**: a user describes a trading idea, an agent taps into DigiQuant's tools to research, build, backtest, and iterate on a strategy — no coding expertise required.

**Primary flow:**
```
User (DigiChat) → DigiGraph agent → DigiQuant MCP tools → Results back to chat
```

---

## Four-Stage Architecture

DigiQuant is organized into four sequential stages. Everything maps to one of these:

### Stage 1 — Ideation
Research and strategy discovery. Agents explore the strategy library to find candidates, understand what's available, and prompt the user with targeted questions to define a strategy for a given use case.

### Stage 2 — Construction
Building a strategy from indicator primitives. Composing indicators into strategy logic with configurable parameters. Exporting to PineScript for TradingView.

### Stage 3 — Backtesting & Optimization
Running backtests via NautilusTrader. Optimizing strategy parameters. Generating tear sheets.

### Stage 4 — Deployment
Connecting to execution venues (Interactive Brokers, Alpaca, QuantConnect) or exporting to TradingView. **This stage is out of scope for Phase 1.**

---

## Component Inventory

### 1. Strategy Library
- Structured on-disk library of strategies and indicators
- Each strategy has:
  - A **config file** (YAML or TOML) — parameters, asset universe, timeframe, tags
  - A **markdown document** — thesis, objective, use case, asset fit, limitations, conceptual explanation for agents
  - A **Python (or Rust) implementation** — actual strategy logic
- Library lives locally for built-in strategies; custom strategies stored in Supabase (digiquant project/schema)
- DigiSearch indexes the markdown documents for agent-driven exploration and semantic search
- Seed library: classic technical strategies (mean reversion, momentum, trend following, stat arb stubs)
- Grows organically over time as strategies are developed and saved

### 2. Indicator Library
- Baseline technical indicators as reusable primitives
- Do **not** re-implement from scratch — wrap `ta-lib`, `pandas-ta`, or equivalent, then expose via Polars-native interface for performance
- Indicators must be composable: an indicator output can be an input to another
- Optimized for vectorized computation (Polars + NumPy/Numba where needed)
- Exposed as MCP tools so agents can call them programmatically

### 3. Price Data Engine (migrated from Atlas)
- Migrate the existing Atlas Yahoo Finance pipeline into DigiQuant
- DigiQuant becomes the **source of truth** for price data across the platform
- Atlas taps into DigiQuant instead of maintaining its own pipeline
- Phase 1: Yahoo Finance (already exists), expand to free sources (Alpha Vantage, Twelve Data, CoinGecko for crypto)
- Price data stored in Supabase (digiquant schema — OHLCV tables per asset/timeframe)
- Background job that keeps price tables updated on a schedule
- Exposed as MCP tools: `get_price_history`, `get_latest_price`, `list_available_assets`

### 4. Backtesting Engine
- NautilusTrader as the backtesting framework (already decided)
- Wrapper layer that takes a strategy config + parameter set and runs a backtest
- Returns structured results (Pydantic v2 models) — metrics, equity curve, trade log
- Exposed as MCP tool: `run_backtest(strategy_id, params, asset, timeframe, start, end)`

### 5. Optimization Framework
- Grid search / random search / Bayesian optimization over strategy parameters
- Uses the backtesting engine internally
- Returns ranked parameter sets with performance metrics
- Exposed as MCP tool: `optimize_strategy(strategy_id, param_grid, ...)`

### 6. Tear Sheet Generator
- Takes backtest results and generates a visual performance report
- Use existing tooling as baseline (Quantstats or pyfolio-reloaded) for standard metrics
- Custom HTML/SVG layer on top for design control and Claude-generated tear sheets
- Output: HTML file (downloadable) + structured JSON metrics (for agent consumption)

### 7. PineScript Converter
- Converts a DigiQuant strategy config + indicator composition into valid PineScript v5/v6
- Output: `.pine` file the user can copy into TradingView
- Future: import PineScript from TradingView → convert to Python strategy (Phase 2)

### 8. MCP + CLI Interface
- Every DigiQuant capability exposed as an MCP tool (DigiGraph can call it)
- Also exposed as CLI commands (direct use, scripting, agent coding tools)
- OpenAPI spec generated from the MCP tool definitions
- Authentication via DigiKey (JWT + API keys, consistent with rest of DigiThings)

### 9. DigiSearch Integration
- DigiSearch indexes the strategy library markdown documents
- Enables agents to semantically search: "find me momentum strategies that work on crypto"
- Phase 1: assess whether Supabase's built-in vector search (pgvector) is sufficient — avoids a separate vector DB dependency
- If pgvector is sufficient, configure DigiSearch to use it as the backend for the strategy index

---

## Database (Supabase — digiquant schema)

Tables needed:
- `assets` — tracked assets with metadata
- `price_ohlcv` — partitioned by asset + timeframe
- `strategies` — custom user strategies (id, name, config_json, created_at, tags)
- `backtest_runs` — results per run (strategy_id, params, metrics_json, equity_curve_json)
- `optimization_runs` — linked to backtest_runs, ranked results

---

## Phase Plan

### Phase 1 — Foundation (Target: ~2 weeks)
**Goal: end-to-end working path from chat prompt → backtest result.**

Everything needed for a user to say "build me a mean-reversion strategy on BTC using RSI and Bollinger Bands, backtest it on the last 2 years" and get a result back through DigiChat.

**Milestones:**
1. **Data Engine** — Migrate Atlas pipeline. Supabase schema. Price update job. MCP tools for price data.
2. **Indicator Library** — Wrap ta-lib/pandas-ta. Polars interface. 10 core indicators exposed as MCP tools.
3. **Strategy Library (seed)** — File structure defined. 3–5 seed strategies documented and implemented. DigiSearch indexing configured.
4. **Backtesting (MVP)** — NautilusTrader wrapper. Single-strategy backtest via MCP tool. Structured output.
5. **Tear Sheet (MVP)** — Basic HTML tear sheet from backtest results. Quantstats baseline.
6. **MCP + CLI scaffold** — All Phase 1 tools registered. CLI commands wired. DigiGraph integration tested.
7. **DigiChat smoke test** — End-to-end: chat prompt → agent → DigiQuant tools → result in chat.

### Phase 2 — Strategy Development Loop (Target: ~4–6 weeks post Phase 1)
**Goal: interactive, iterative strategy development via chat.**

- Parameter optimization via MCP tool
- Strategy saving to Supabase (custom strategies)
- Tear sheet improvements (custom design layer)
- PineScript export (basic conversion for indicator-based strategies)
- TradingView PineScript import → Python conversion (experimental)
- Expand price data sources (Alpha Vantage, crypto)
- DigiSearch semantic search over strategy library (assess pgvector)

### Phase 3 — Agentic Strategy Research (Longer term)
**Goal: agents autonomously research opportunities and propose/build strategies.**

- Atlas integration: Atlas identifies macro opportunities → DigiQuant agent builds a strategy to capitalize
- Example: Atlas flags oil supply disruption → DigiQuant agent proposes long oil futures or VIX trade, builds and backtests it
- Self-iterating strategy agent: runs optimization rounds, evaluates results, proposes improvements
- Multi-strategy portfolio construction
- Broker connections: Alpaca first (simplest API), then Interactive Brokers, then QuantConnect

---

## Technical Decisions

| Decision | Choice | Rationale |
|---|---|---|
| Language | Python (primary), Rust via NautilusTrader | Ecosystem fit, open source. Rust-core perf where it counts (backtest execution) |
| Dataframe | Polars only — no pandas | Performance, memory efficiency, required for optimization rounds |
| Backtesting | NautilusTrader | Already decided. Rust-core, institutional grade |
| Indicators | ta-lib / pandas-ta wrapped with Polars interface | Don't reinvent the wheel; wrap and optimize |
| Database | Supabase (digiquant schema) | Already used in DigiThings, MCP connector available, free tier, pgvector built in |
| Vector search | Supabase pgvector (assess first) | Avoids external vector DB dependency if sufficient |
| Strategy format | YAML/TOML config + Markdown doc + Python impl | Machine-readable config, human/agent-readable docs, typed implementation |
| Tear sheets | Quantstats baseline + custom HTML layer | Don't maintain a metrics library; customize the presentation layer |
| Auth | DigiKey (JWT + API keys) | Consistent with rest of DigiThings |

---

## Issue Labels (suggest creating these in GitHub)

- `stage:ideation` `stage:construction` `stage:backtest` `stage:deployment`
- `component:data-engine` `component:indicator-lib` `component:strategy-lib` `component:backtest` `component:optimization` `component:tearsheet` `component:pinescript` `component:mcp-cli` `component:digisearch`
- `phase:1` `phase:2` `phase:3`
- `priority:critical` `priority:high` `priority:medium` `priority:low`
- `complexity:S` `complexity:M` `complexity:L` `complexity:XL`
- `type:migration` `type:feature` `type:integration` `type:infra` `type:research`

---

## Phase 1 Issues (Detailed)

### Milestone: Data Engine

**[MIGRATION] Migrate Atlas price pipeline into DigiQuant**
- Priority: Critical | Complexity: M | Phase: 1
- Move Yahoo Finance ingestion job from Atlas into `digiquant/data/`
- Create Supabase `digiquant` schema with `assets` and `price_ohlcv` tables
- Atlas updated to call DigiQuant data MCP tools instead of its own pipeline
- Background scheduler for price updates

**[FEATURE] MCP tools: price data**
- Priority: Critical | Complexity: S | Phase: 1
- `get_price_history(asset, timeframe, start, end)` → DataFrame
- `get_latest_price(asset)` → latest OHLCV row
- `list_available_assets()` → tracked assets list
- All return Pydantic v2 models

---

### Milestone: Indicator Library

**[FEATURE] Core indicator library — Polars interface**
- Priority: Critical | Complexity: M | Phase: 1
- Wrap ta-lib or pandas-ta; expose via Polars Series/DataFrame interface
- Minimum set: RSI, MACD, Bollinger Bands, EMA, SMA, ATR, Stochastic, OBV, VWAP, ROC
- Each indicator: typed inputs, typed outputs, parameter validation

**[FEATURE] MCP tools: indicators**
- Priority: High | Complexity: S | Phase: 1
- `compute_indicator(asset, timeframe, indicator, params)` → series output
- `list_indicators()` → available indicators with param schemas

---

### Milestone: Strategy Library (seed)

**[INFRA] Strategy library file structure**
- Priority: Critical | Complexity: S | Phase: 1
- Define directory structure: `digiquant/strategies/<category>/<strategy_name>/`
- Each strategy: `config.yaml`, `README.md`, `strategy.py`
- Document the spec for config schema and markdown format
- Agents must be able to read and understand both files

**[FEATURE] Seed strategy implementations (5)**
- Priority: High | Complexity: M | Phase: 1
- RSI Mean Reversion
- Bollinger Band Breakout
- EMA Crossover (trend following)
- MACD Momentum
- Dual Moving Average
- Each with full config + markdown doc + Python implementation

**[INTEGRATION] DigiSearch indexing for strategy library**
- Priority: Medium | Complexity: M | Phase: 1
- Assess Supabase pgvector as the index backend (prefer to avoid external vector DB)
- Configure DigiSearch to index strategy README.md files
- MCP tool: `search_strategies(query)` → ranked strategy matches

---

### Milestone: Backtesting (MVP)

**[FEATURE] NautilusTrader backtest wrapper**
- Priority: Critical | Complexity: L | Phase: 1
- Wrapper that accepts: strategy_id, param overrides, asset, timeframe, start/end dates
- Pulls price data from DigiQuant data engine
- Runs backtest, captures: equity curve, trade log, performance metrics
- Returns structured Pydantic v2 `BacktestResult` model

**[FEATURE] MCP tool: run_backtest**
- Priority: Critical | Complexity: S | Phase: 1
- `run_backtest(strategy_id, params, asset, timeframe, start, end)` → BacktestResult
- Saves result to Supabase `backtest_runs` table
- Streams progress updates (for DigiChat to show live feedback)

---

### Milestone: Tear Sheet (MVP)

**[FEATURE] HTML tear sheet from backtest results**
- Priority: High | Complexity: M | Phase: 1
- Input: BacktestResult model
- Use Quantstats for metric computation (Sharpe, Sortino, max drawdown, CAGR, win rate, etc.)
- Output: standalone HTML file (downloadable via DigiChat)
- Standard sections: summary metrics, equity curve chart, monthly returns heatmap, drawdown chart

---

### Milestone: MCP + CLI Scaffold

**[INFRA] DigiQuant MCP server setup**
- Priority: Critical | Complexity: M | Phase: 1
- FastAPI + MCP server following DigiThings patterns (see DigiQuant ARCHITECTURE.md)
- Register all Phase 1 tools
- Auth via DigiKey
- Port: 8001 (consistent with docker-compose.yml)

**[INFRA] CLI commands**
- Priority: Medium | Complexity: S | Phase: 1
- CLI wrapping all MCP tools for direct use
- `digiquant backtest run ...`
- `digiquant data update ...`
- `digiquant strategy list / search ...`

**[INTEGRATION] DigiGraph agent integration**
- Priority: Critical | Complexity: M | Phase: 1
- Register DigiQuant MCP tools with DigiGraph
- End-to-end test: chat prompt → DigiGraph calls DigiQuant tool → result returned to DigiChat
- Smoke test script in `tests/e2e/`

---

## Notes for Agent Executing This Brief

1. Read `ARCHITECTURE.md`, `AGENTS.md`, and `digiquant/ARCHITECTURE.md` before touching any code.
2. Follow existing DigiThings patterns: Pydantic v2 models, Polars only (no pandas), ruff linting, mypy strict.
3. All new capabilities must be exposed as both MCP tools and CLI commands.
4. Store all results in Supabase under the `digiquant` schema — not in local files except for the strategy library source.
5. Phase 1 issues are ordered by dependency: Data Engine → Indicator Library → Strategy Library → Backtest → Tear Sheet → MCP/CLI → Integration test.
6. Create the label taxonomy above before creating issues.
7. Assign Phase 1 issues to the Phase 1 milestone. Create Phase 2 and Phase 3 milestones as placeholders with issues in backlog state.
8. Priority ordering within Phase 1: Data Engine and MCP scaffold first (everything else depends on them), then Indicator Library and Backtest wrapper in parallel, then Strategy Library, then Tear Sheet, then integration test last.
