---
title: digiquant
type: module
status: reviewed
created: 2026-04-19
tags:
  - core
  - quant
relevance:
  - olympus
  - digichat
---
# digiquant
> The quantitative finance platform — from macro research to deployed trading strategies, powered by AI agents.

**Names (ADR-0026):** the product is digiquant. The three jobs are research, portfolio, and execution. Historical package paths (`digiquant.olympus.{atlas,hermes,kairos}`) stay until a dedicated rename PR.

## What it is

digiquant is the quantitative finance vertical within digithings. It is not a trading platform in the traditional sense — it is an AI-powered toolkit for the complete investment workflow: researching markets, constructing theses, building and testing strategies, and deploying them.

Three distinct products cover each stage of that workflow. digiquant is accessed via digigraph agent tools, a dedicated digichat interface, and a CLI — never requiring the user to write infrastructure code.

## The problem it solves

Systematic quantitative trading and AI-driven investment research have historically required either expensive institutional infrastructure (Bloomberg, FactSet, proprietary execution systems) or a research engineering team to stitch together disparate tools. The result is that rigorous, systematic investment research has been the exclusive domain of well-funded institutions and large funds.

digiquant makes this accessible to independent researchers, small funds, and individual investors by automating the infrastructure and exposing it through natural language interfaces. The full pipeline — from daily macro research through thesis construction, strategy development, backtesting, optimization, and live deployment — is available without writing infrastructure code.

## Products

Three jobs, one product. There is no second brand beside digiquant ([ADR-0026](../adr/0026-retire-olympus-atlas-hermes-kairos.md)). Package paths still use the historical names until a dedicated rename PR.

### Research

The macro research engine and the knowledge foundation everything else builds on (`digiquant.olympus.atlas`, phases A0–A4).

It runs daily research cycles across parallel layers — data ingestion, sector analysis, macro synthesis — producing a persistent, structured research library and a daily market digest. Three temporal cycles govern how that library is maintained:

- **Daily delta updates** — line-level edits to existing documents, minimizing token cost. Rather than regenerating full documents every day, the graph patches only what changed. This is the core cost optimization of the system.
- **Weekly full document regeneration** — complete rewrites to ensure coherence and catch accumulated drift.
- **Monthly lookback rollup** — synthesizes the month's deltas and weeklies into a durable archival summary.

Research is built as digigraph sub-graphs with parallel execution, batched API calls, structured Pydantic outputs at every node, and prompt caching. The delta system keeps daily operating costs predictable at scale — a key design constraint for a platform intended to run autonomously and continuously.

### Portfolio

The portfolio management orchestration layer (`digiquant.olympus.hermes`, phases H1–H9). It takes the research library and translates it into portfolio action through a structured deliberation pipeline:

1. **Research ingestion** — pulls the current research library as context.
2. **Investment thesis construction** — generates theses with explicit validity requirements and exit triggers.
3. **Asset mapping** — filters candidate assets by the user's investment profile (risk tolerance, sector preferences, geographic constraints, account type).
4. **Parallel analyst deliberation** — spawns parallel agent instances per asset, each producing a bull case, bear case, headwinds/tailwinds analysis, and a formal recommendation.
5. **Portfolio manager synthesis** — a top-level agent deliberates across all analyst outputs, aware of the full current portfolio state and user preferences, and produces a final portfolio with weights and rationale.

The portfolio graph uses PyPortfolioOpt for the quantitative math — mean-variance optimization, Black-Litterman, and Hierarchical Risk Parity — alongside LLM deliberation. Structured outputs at every node keep token costs predictable and outputs auditable. The separation between analyst agents and the portfolio manager agent mirrors institutional investment committee structures.

### Execution

The hands-on strategy building and order-intent toolkit (`digiquant.olympus.kairos`). Algorithmic trading is about identifying and seizing the exact right entry and exit window. Live venue cutover stays human-gated.

Execution operates in two modes:

**Developer mode** — a well-documented toolkit for researchers and engineers who want direct control. Operated via CLI or coding agent (Claude Code, Cursor), with the full strategy development pipeline exposed as composable components.

**Product mode** — a digichat interface where a user describes a trading idea in natural language. The system researches the idea, derives candidate strategies, runs parallel backtests across multiple variations, optimizes parameters, and presents results with performance metrics, risk analysis, and deployment options. No code required.

The strategy development pipeline enforces a progression:

1. **VectorBT** — fast vectorized backtesting for rapid ideation. 100 strategy variations in seconds. Used for research and screening, not production validation.
2. **NautilusTrader** — final strategy validation in a Rust-core, event-driven backtesting environment that matches the live execution environment exactly.
3. **Alpaca paper trading** — realistic fills in a live market environment without capital at risk.
4. **Live deployment** — to Alpaca or QuantConnect. No skipping steps in the progression.

Multi-strategy parallel research rounds accelerate ideation at scale — the execution graph can explore a broad strategy space autonomously before surfacing the most promising candidates for human review.

## How it fits in the ecosystem

digiquant is a vertical service that digigraph orchestrates. digigraph agents call digiquant tools — `run_backtest`, `optimize_strategy`, `get_price_history`, `compute_indicator` — through the standard MCP tool registry. From digigraph's perspective, digiquant is one of several vertical capabilities, alongside digisearch and others.

Data and state flow across the broader stack:

- **digistore** holds the research library, strategy definitions, backtest results, and portfolio state.
- **digisearch** indexes finalized research documents for semantic retrieval, so agents can pull relevant research context on demand.
- **digiclaw** runs the research and portfolio graphs on their daily and weekly schedules autonomously — digiquant's scheduled execution layer.
- **digichat** is the user-facing chat interface for querying research interactively.
- **Dashboard** (`frontend/olympus`) is the operator surface — morning read, deliberations and risk debate, portfolio/NAV tracking — and the surface where the human approval gate will be exercised once that flow ships. See [[olympus|olympus.md]]. Sub-graphs live in `digiquant.olympus` (ADR-0014, ADR-0015); product names are digiquant + research / portfolio / execution ([ADR-0026](../adr/0026-retire-olympus-atlas-hermes-kairos.md)).

## Data philosophy

Free data first, always. The internet is free and digiquant capitalizes on it. Paid API connectors exist but require user-supplied keys — digithings never pays for data on behalf of users.

Production data stack:

- **OpenBB** — aggregation layer covering approximately 100 data sources. digistore's primary data retrieval interface.
- **Twelve Data** — price history and technicals. 800 API calls per day on the free tier.
- **EdgarTools** — SEC filings and XBRL data. No rate limits. Includes an MCP server, so agents can query SEC filings directly without custom tooling.
- **FRED** — macroeconomic data from the Federal Reserve. Free, authoritative, and comprehensive.
- **CoinGecko** — cryptocurrency market data.
- **Finnhub** — news feeds and sentiment signals.
- **S3 / MinIO** — object storage for large datasets, backtest results, and research archives.

This stack provides broad coverage across equities, macro, crypto, and alternative data without a mandatory paid subscription. Users who need higher rate limits or premium data sources supply their own keys.

## Technology decisions

**NautilusTrader** — Rust-core event-driven backtesting and live execution. Used for final strategy validation and all live deployments. The Rust core eliminates Python GIL constraints and delivers execution fidelity that matches production at nanosecond resolution. Chosen because the backtesting environment and the live execution environment are the same system — there is no translation layer that introduces behavioral drift.

**VectorBT** — vectorized backtesting for rapid strategy ideation. 10–100x faster than event-driven backtesting for parameter sweeps and strategy screening. Used exclusively for research; never for production validation. The performance gap between VectorBT and NautilusTrader is the reason for the two-stage validation pipeline — use the fast tool to explore the space, use the faithful tool to validate candidates.

**PyPortfolioOpt** — portfolio optimization math. Mean-variance, Black-Litterman, and Hierarchical Risk Parity are implemented here and called during portfolio construction.

**Polars only** — no pandas anywhere in the pipeline. Polars' lazy evaluation and columnar execution model handle financial time series data efficiently. The constraint is non-negotiable: pandas is a dependency target, not a data processing tool.

**Schema-first outputs** — every node in every digigraph sub-graph that digiquant uses produces a structured Pydantic v2 output. Claude's structured outputs API enforces schema compliance at generation time. The Instructor library handles retry logic on schema violations. YAML config files define guardrails for strategy parameters, risk limits, and deployment gates. This makes every intermediate state auditable and every output predictable.

**Paper trading gate** — the progression is internal simulator → Alpaca paper → live. No step is skippable. Alpaca paper trading uses a free account with realistic fill simulation in a live market environment. This gate exists because backtesting, even on NautilusTrader, cannot fully replicate live market microstructure.

## Current state

The digiquant engine is operational with six registered strategies:

- EMA cross variants (multiple parameter configurations)
- RSI momentum
- Bollinger Band mean-reversion
- MACD trend-following

Three optimization engines are available: grid search, random search, and Bayesian optimization.

Five export targets are supported: NautilusTrader, TradingView PineScript, Alpaca, QuantConnect, and JSON.

The research methodology is defined and has been run as scheduled digigraph sub-graphs. The portfolio deliberation pipeline and the execution/digichat interface continue to mature; live venue cutover stays human-gated.

## 12-month roadmap

**Months 1–3 — Research graph**
Migrate research methodology from instruction files to deterministic, parallel digigraph sub-graph execution. Wire in digiclaw for scheduled daily, weekly, and monthly cycle triggers. Deliver the first autonomous daily digest.

**Months 3–6 — Portfolio deliberation pipeline**
Build the full portfolio pipeline as digigraph sub-graphs: thesis construction, parallel analyst agents, portfolio manager synthesis, PyPortfolioOpt integration. Deliver portfolio output with weights and rationale driven by research.

**Months 4–7 — Execution digichat interface**
Build the product-mode digichat interface for strategy exploration. Users describe a trading idea and get backtest results, optimization curves, and deployment options. Integrate VectorBT → NautilusTrader progression into the interface.

**Months 5–8 — OpenBB integration**
Integrate OpenBB as digistore's primary data retrieval layer. Replace ad-hoc data fetching across research, portfolio, and execution with a single OpenBB-backed interface. Expand data source coverage.

**Months 7–10 — Strategy library expansion**
Run parallel research rounds autonomously to expand the strategy library beyond the current six strategies. Systematic coverage across asset classes, time frames, and market regimes.

**Months 8–11 — Live deployment**
Live strategy deployment to Alpaca and QuantConnect. Full paper-to-live progression enforced by the deployment gate. Human approval required before any live capital commitment.

**Months 10–12 — digiquant.io entry flow**
Build the digiquant.io investment profiling entry flow. Free tier gives access to research and basic backtesting. Paywall gates access to portfolio management and strategy building. This is the consumer-facing monetization surface for digiquant.

## Open source vs. proprietary

digiquant follows the digithings open-core model. The infrastructure layer is open; the intelligence layer is proprietary.

**Open source:**
- digiquant engine and CLI
- NautilusTrader integration and adapter layer
- Backtesting framework and VectorBT integration
- Data connectors (OpenBB, Twelve Data, EdgarTools, FRED, CoinGecko, Finnhub)
- Strategy definition schema and export targets
- Optimization engine implementations (grid, random, Bayesian)

**Proprietary:**
- Research sub-graphs and the delta patching system
- Portfolio deliberation pipeline and the analyst agent prompting system
- Strategy library (the accumulated output of research rounds)
- Specific strategy implementations with tuned parameters
- Execution layer and deployment gate logic
- digiquant.io investment profiling and paywall infrastructure
