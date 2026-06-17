# DigiQuant
> The quantitative finance platform — from macro research to deployed trading strategies, powered by AI agents.

## What it is

DigiQuant is the quantitative finance vertical within DigiThings. It is not a trading platform in the traditional sense — it is an AI-powered toolkit for the complete investment workflow: researching markets, constructing theses, building and testing strategies, and deploying them.

Three distinct products cover each stage of that workflow. DigiQuant is accessed via DigiGraph agent tools, a dedicated DigiChat interface, and a CLI — never requiring the user to write infrastructure code.

## The problem it solves

Systematic quantitative trading and AI-driven investment research have historically required either expensive institutional infrastructure (Bloomberg, FactSet, proprietary execution systems) or a research engineering team to stitch together disparate tools. The result is that rigorous, systematic investment research has been the exclusive domain of well-funded institutions and large funds.

DigiQuant makes this accessible to independent researchers, small funds, and individual investors by automating the infrastructure and exposing it through natural language interfaces. The full pipeline — from daily macro research through thesis construction, strategy development, backtesting, optimization, and live deployment — is available without writing infrastructure code.

## Products

### Atlas

Atlas is the macro research engine and the knowledge foundation everything else builds on.

It runs daily research cycles across parallel layers — data ingestion, sector analysis, macro synthesis — producing a persistent, structured research library and a daily market digest. Three temporal cycles govern how that library is maintained:

- **Daily delta updates** — line-level edits to existing documents, minimizing token cost. Rather than regenerating full documents every day, Atlas patches only what changed. This is the core cost optimization of the system.
- **Weekly full document regeneration** — complete rewrites to ensure coherence and catch accumulated drift.
- **Monthly lookback rollup** — synthesizes the month's deltas and weeklies into a durable archival summary.

Atlas is built as DigiGraph sub-graphs with parallel execution, batched API calls, structured Pydantic outputs at every node, and prompt caching. The delta system keeps daily operating costs predictable at scale — a key design constraint for a platform intended to run autonomously and continuously.

### Hermes

Hermes is the portfolio management orchestration layer. It takes Atlas research and translates it into portfolio action through a structured deliberation pipeline:

1. **Research ingestion** — pulls the current Atlas research library as context.
2. **Investment thesis construction** — generates theses with explicit validity requirements and exit triggers.
3. **Asset mapping** — filters candidate assets by the user's investment profile (risk tolerance, sector preferences, geographic constraints, account type).
4. **Parallel analyst deliberation** — spawns parallel agent instances per asset, each producing a bull case, bear case, headwinds/tailwinds analysis, and a formal recommendation.
5. **Portfolio manager synthesis** — a top-level agent deliberates across all analyst outputs, aware of the full current portfolio state and user preferences, and produces a final portfolio with weights and rationale.

Hermes uses PyPortfolioOpt for the quantitative portfolio math — mean-variance optimization, Black-Litterman, and Hierarchical Risk Parity — alongside LLM deliberation. Structured outputs at every node keep token costs predictable and outputs auditable. The separation between analyst agents and the portfolio manager agent mirrors institutional investment committee structures.

### Kairos

Kairos is the hands-on strategy building toolkit, named after the Greek concept of the opportune moment — the recognition that algorithmic trading is fundamentally about identifying and seizing the exact right entry and exit window.

Kairos operates in two modes:

**Developer mode** — a well-documented toolkit for researchers and engineers who want direct control. Operated via CLI or coding agent (Claude Code, Cursor), with the full strategy development pipeline exposed as composable components.

**Product mode** — a DigiChat interface where a user describes a trading idea in natural language. Kairos researches the idea, derives candidate strategies, runs parallel backtests across multiple variations, optimizes parameters, and presents results with performance metrics, risk analysis, and deployment options. No code required.

The strategy development pipeline enforces a progression:

1. **VectorBT** — fast vectorized backtesting for rapid ideation. 100 strategy variations in seconds. Used for research and screening, not production validation.
2. **NautilusTrader** — final strategy validation in a Rust-core, event-driven backtesting environment that matches the live execution environment exactly.
3. **Alpaca paper trading** — realistic fills in a live market environment without capital at risk.
4. **Live deployment** — to Alpaca or QuantConnect. No skipping steps in the progression.

Multi-strategy parallel research rounds accelerate ideation at scale — Kairos can explore a broad strategy space autonomously before surfacing the most promising candidates for human review.

## How it fits in the ecosystem

DigiQuant is a vertical service that DigiGraph orchestrates. DigiGraph agents call DigiQuant tools — `run_backtest`, `optimize_strategy`, `get_price_history`, `compute_indicator` — through the standard MCP tool registry. From DigiGraph's perspective, DigiQuant is one of several vertical capabilities, alongside DigiSearch and others.

Data and state flow across the broader stack:

- **DigiStore** holds the research library, strategy definitions, backtest results, and portfolio state.
- **DigiSearch** indexes finalized research documents for semantic retrieval, so agents can pull relevant research context on demand.
- **DigiClaw** runs Atlas and Hermes on their daily and weekly schedules autonomously — DigiQuant's scheduled execution layer.
- **DigiChat** is the user-facing interface for Kairos product mode and for querying Atlas research interactively.
- **Olympus** (`frontend/olympus`) is the dedicated dashboard for the trio — Atlas's "Morning Read", Hermes's deliberations and risk debate, and portfolio/NAV tracking — and the surface where the human approval gate will be exercised once Hermes ships (see Current state below). See [olympus.md](olympus.md). Atlas, Hermes, and Kairos run inside DigiQuant as `digiquant.olympus` (ADR-0014, ADR-0015).

## Data philosophy

Free data first, always. The internet is free and DigiQuant capitalizes on it. Paid API connectors exist but require user-supplied keys — DigiThings never pays for data on behalf of users.

Production data stack:

- **OpenBB** — aggregation layer covering approximately 100 data sources. DigiStore's primary data retrieval interface.
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

**PyPortfolioOpt** — portfolio optimization math. Mean-variance, Black-Litterman, and Hierarchical Risk Parity are implemented here and called by Hermes during portfolio construction.

**Polars only** — no pandas anywhere in the pipeline. Polars' lazy evaluation and columnar execution model handle financial time series data efficiently. The constraint is non-negotiable: pandas is a dependency target, not a data processing tool.

**Schema-first outputs** — every node in every DigiGraph sub-graph that DigiQuant uses produces a structured Pydantic v2 output. Claude's structured outputs API enforces schema compliance at generation time. The Instructor library handles retry logic on schema violations. YAML config files define guardrails for strategy parameters, risk limits, and deployment gates. This makes every intermediate state auditable and every output predictable.

**Paper trading gate** — the progression is internal simulator → Alpaca paper → live. No step is skippable. Alpaca paper trading uses a free account with realistic fill simulation in a live market environment. This gate exists because backtesting, even on NautilusTrader, cannot fully replicate live market microstructure.

## Current state

The DigiQuant engine is operational with six registered strategies:

- EMA cross variants (multiple parameter configurations)
- RSI momentum
- Bollinger Band mean-reversion
- MACD trend-following

Three optimization engines are available: grid search, random search, and Bayesian optimization.

Five export targets are supported: NautilusTrader, TradingView PineScript, Alpaca, QuantConnect, and JSON.

Atlas exists as instruction files and manual scripts. The research methodology is defined and has been run manually, but it is not yet a deterministic DigiGraph execution graph with scheduled autonomous execution.

Hermes and Kairos product interfaces are not yet built. The portfolio optimization math (PyPortfolioOpt) is integrated; the deliberation pipeline and the DigiChat interface are roadmap items.

## 12-month roadmap

**Months 1–3 — Atlas to DigiGraph**
Migrate the Atlas research methodology from instruction files to deterministic, parallel DigiGraph sub-graph execution. Wire in DigiClaw for scheduled daily, weekly, and monthly cycle triggers. Deliver the first autonomous daily digest.

**Months 3–6 — Hermes deliberation pipeline**
Build the full Hermes pipeline as DigiGraph sub-graphs: thesis construction, parallel analyst agents, portfolio manager synthesis, PyPortfolioOpt integration. Deliver portfolio output with weights and rationale driven by Atlas research.

**Months 4–7 — Kairos DigiChat interface**
Build the Kairos product-mode DigiChat interface for strategy exploration. Users describe a trading idea; Kairos returns backtest results, optimization curves, and deployment options. Integrate VectorBT → NautilusTrader progression into the interface.

**Months 5–8 — OpenBB integration**
Integrate OpenBB as DigiStore's primary data retrieval layer. Replace ad-hoc data fetching across Atlas, Hermes, and Kairos with a single OpenBB-backed interface. Expand data source coverage.

**Months 7–10 — Strategy library expansion**
Run Kairos parallel research rounds autonomously to expand the strategy library beyond the current six strategies. Systematic coverage across asset classes, time frames, and market regimes.

**Months 8–11 — Live deployment**
Live strategy deployment to Alpaca and QuantConnect. Full paper-to-live progression enforced by the deployment gate. Human approval required before any live capital commitment.

**Months 10–12 — digiquant.io entry flow**
Build the digiquant.io investment profiling entry flow. Free tier gives access to Atlas research and basic backtesting. Paywall gates access to Hermes portfolio management and Kairos strategy building. This is the consumer-facing monetization surface for DigiQuant.

## Open source vs. proprietary

DigiQuant follows the DigiThings open-core model. The infrastructure layer is open; the intelligence layer is proprietary.

**Open source:**
- DigiQuant engine and CLI
- NautilusTrader integration and adapter layer
- Backtesting framework and VectorBT integration
- Data connectors (OpenBB, Twelve Data, EdgarTools, FRED, CoinGecko, Finnhub)
- Strategy definition schema and export targets
- Optimization engine implementations (grid, random, Bayesian)

**Proprietary:**
- Atlas research sub-graphs and the delta patching system
- Hermes deliberation pipeline and the analyst agent prompting system
- Kairos strategy library (the accumulated output of research rounds)
- Specific strategy implementations with tuned parameters
- Execution layer and deployment gate logic
- digiquant.io investment profiling and paywall infrastructure
