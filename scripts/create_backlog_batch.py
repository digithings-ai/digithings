#!/usr/bin/env python3
"""
create_backlog_batch.py — Batch-create the DigiThings 12-month backlog.

Creates ~57 GitHub issues covering all module roadmap items, assigns them to
the correct module project board, and prints a TSV for set_project_fields.sh.

Usage:
    python3 scripts/create_backlog_batch.py [--module MODULE] [--dry-run]

Options:
    --module MODULE   Only create issues for one module (e.g. digiquant, digigraph)
    --dry-run         Print what would be created without making API calls
"""

import argparse
import subprocess
import sys
import time

REPO = "digithings-ai/digithings"
OWNER = "digithings-ai"

# Component → project number mapping (from project_routing.json)
PROJECT_MAP = {
    "root":       1,
    "digiquant":  2,
    "digigraph":  3,
    "digisearch": 4,
    "digichat":   5,
    "digikey":    6,
    "digismith":  7,
    "digiclaw":   8,
    "digibase":   9,
}

# ── Issue definitions ──────────────────────────────────────────────────────────
# Each dict:
#   component, type, risk, priority, complexity, model, title, labels_extra, body
# ──────────────────────────────────────────────────────────────────────────────

ISSUES = [

    # ── Cross-cutting epics (Project #1 — digithings) ─────────────────────────

    dict(
        component="root", type="feat", risk="med", priority="high", complexity="L",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:L", "priority:high"],
        title="[Epic] DigiLink — connection and translation layer",
        body="""\
## Goal
Establish DigiLink as a first-class module that serves as the universal connection layer for DigiThings — both internally between modules (standardised HTTP/gRPC) and externally to any protocol a client needs (REST, MCP, CLI, Docker, webhooks). Every DigiThings capability is defined once and exposed through multiple protocol adapters derived from that single definition.

## Why this epic
Currently each module exposes its own REST API independently with no shared translation layer. Adding MCP support, a CLI, or a desktop AI connector requires manual work per module. DigiLink eliminates this by generating adapters from a central capability registry.

## Sub-tasks (in digisearch / digigraph project boards)
- [ ] DigiLink module scaffold — capability registry and adapter framework
- [ ] MCP adapter generation from OpenAPI specs
- [ ] CLI wrapper auto-generation from REST endpoints
- [ ] Desktop AI connector library (Claude Desktop, Cursor, Windsurf)
- [ ] Webhook/event connector for async integrations

## Acceptance Criteria
- [ ] Every DigiThings capability is reachable via REST, MCP tool, and CLI without per-module adapter code
- [ ] Adding a new module requires only registering it in DigiLink — no new adapter code
- [ ] Claude Desktop can call DigiQuant backtest tools via MCP
- [ ] `docs/vision/digilink.md` reflects implementation state

## Documentation to Update
- [ ] `docs/vision/digilink.md`
- [ ] `ARCHITECTURE.md`
""",
    ),

    dict(
        component="root", type="feat", risk="low", priority="high", complexity="L",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:L", "priority:high"],
        title="[Epic] DigiStore — standalone storage abstraction module",
        body="""\
## Goal
Extract and build DigiStore as a proper standalone module — the unified storage abstraction layer for the entire DigiThings ecosystem. Currently DigiStore exists only as a thin session/dataset cache inside DigiGraph. The standalone module provides one interface over SQLite (local dev), Postgres/Supabase (production), and S3/MinIO (file storage), with OpenBB as the data retrieval layer underneath.

## Sub-tasks (tracked separately)
- [ ] DigiStore standalone module scaffold (new top-level module)
- [ ] Backend registry: SQLite, Postgres/Supabase, S3/MinIO
- [ ] OpenBB integration as data retrieval layer
- [ ] Dockerized local dev stack

## Acceptance Criteria
- [ ] DigiStore is a standalone Python package importable independently of DigiGraph
- [ ] SQLite, Supabase, and MinIO backends all work via the same interface
- [ ] DigiGraph's existing Digistore functionality migrated without regression
- [ ] `docs/vision/digistore.md` reflects implementation state

## Documentation to Update
- [ ] `docs/vision/digistore.md`
- [ ] `ARCHITECTURE.md`
""",
    ),

    dict(
        component="root", type="feat", risk="high", priority="critical", complexity="XL",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:XL", "priority:critical"],
        title="[Epic] DigiKey — SSO federation and org/project membership",
        body="""\
## Goal
Extend DigiKey beyond API key management to a full identity platform: SSO federation (Microsoft OIDC/SAML, Google OIDC), organization and project membership model, and resource-level JWT claims that encode which specific indexes, sub-graphs, and data views a user can access.

## Why now
Enterprise client onboarding (e.g. a company using Microsoft) requires employees to log in with corporate credentials. DigiChat's adaptive UI requires fine-grained JWT scopes. DigiSearch's per-user result filtering requires resource-level claims.

## Sub-tasks (in digikey project board)
- [ ] Microsoft OIDC/SAML SSO integration
- [ ] Google OIDC integration
- [ ] Organization and project membership API
- [ ] Resource-level JWT claims (index and sub-graph access scopes)
- [ ] JWT revocation — jti blocklist in Redis
- [ ] Scheduled JWKS rotation with zero-downtime overlap

## Acceptance Criteria
- [ ] An enterprise user can log in with their Microsoft account and receive a DigiKey JWT
- [ ] The JWT contains their org ID, project ID, and allowed resource list
- [ ] DigiSearch filters results based on JWT claims without code changes per client
- [ ] `docs/vision/digikey.md` reflects implementation state

## Documentation to Update
- [ ] `docs/vision/digikey.md`
- [ ] `digikey/ARCHITECTURE.md`
""",
    ),

    dict(
        component="root", type="feat", risk="med", priority="high", complexity="XL",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:XL", "priority:high"],
        title="[Epic] DigiClaw — OpenClaw integration and autonomous agent scheduling",
        body="""\
## Goal
Build out DigiClaw from its current heartbeat/audit MVP into the always-on agent orchestration layer: OpenClaw runtime integration, agent definition schema, cron/continuous scheduling, and the Atlas daily cycle running automatically without manual execution.

## Sub-tasks (in digiclaw project board)
- [ ] OpenClaw runtime integration
- [ ] Agent definition schema and registry
- [ ] Cron and continuous scheduling
- [ ] Atlas daily cycle automation — DigiClaw scheduled job
- [ ] Strategy performance monitor agent
- [ ] ADDM — Adaptive Drift Detection Monitor (rewrite from stub)
- [ ] DigiClaw dashboard — agent status and audit log viewer

## Acceptance Criteria
- [ ] Atlas daily delta, weekly full-gen, and monthly rollup run automatically on schedule
- [ ] A new agent can be defined in a YAML file and scheduled without code changes
- [ ] Audit log captures every autonomous action with timestamp and outcome
- [ ] `docs/vision/digiclaw.md` reflects implementation state

## Documentation to Update
- [ ] `docs/vision/digiclaw.md`
- [ ] `digiclaw/ARCHITECTURE.md`
""",
    ),

    dict(
        component="root", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[Epic] digithings.ai and digiquant.io — live website demos",
        body="""\
## Goal
Deploy two embedded DigiChat instances — one on digithings.ai (platform overview, DigiThings docs indexed, 3-question free tier) and one on digiquant.io (investment profiling entry flow, paywall into Kairos). Both showcase BYOK model selection and the DigiThings modularity story.

## Sub-tasks (in digichat and digisearch project boards)
- [ ] digithings-guide index — DigiThings docs indexed and live
- [ ] digithings.ai demo instance — 3-question free tier, model selector
- [ ] digiquant.io investment profiling entry flow

## Acceptance Criteria
- [ ] A visitor to digithings.ai can ask 3 questions about DigiThings without an API key
- [ ] BYOK input allows continuing with their own key
- [ ] digiquant.io investment profiling saves a user profile to DigiStore
- [ ] Both demos are live and monitored

## Documentation to Update
- [ ] `website/` and `digichat/` deployment configs
""",
    ),

    # ── DigiQuant (Project #2) ─────────────────────────────────────────────────

    dict(
        component="digiquant", type="feat", risk="high", priority="critical", complexity="XL",
        model="opus", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:feature", "complexity:XL", "priority:critical", "stage:ideation"],
        title="[FEATURE] Migrate Atlas research cycles to DigiGraph sub-graphs",
        body="""\
## Goal
Rebuild Atlas from manual instruction files and scripts into a deterministic DigiGraph sub-graph execution graph. The result: a reliable, scheduled Atlas pipeline with parallel research layer execution (data → sector → macro), batched API calls, Pydantic structured outputs at every node, and prompt caching to minimise cost.

## From scratch
YES — current Atlas is ad-hoc scripts requiring manual execution and backfilling. A full DigiGraph implementation is needed, not a refactor.

## Acceptance Criteria
- [ ] Atlas sub-graph runs without manual intervention when triggered
- [ ] Research executes in parallel across data, sector, and macro layers
- [ ] All LLM calls use structured outputs (Pydantic v2 models)
- [ ] Prompt caching enabled on all repeated-context calls
- [ ] Daily Digest generated fresh; other documents delta-patched
- [ ] Sub-graph can be scheduled via DigiClaw
- [ ] `digiquant/ARCHITECTURE.md` and `digigraph/ARCHITECTURE.md` updated

## Files affected (new)
- `digigraph/src/digigraph/graph/atlas/__init__.py`
- `digigraph/src/digigraph/graph/atlas/research.py`
- `digigraph/src/digigraph/graph/atlas/models.py`
- `digigraph/src/digigraph/graph/atlas/prompts.py`

## Dependencies
None — this is the foundation for Hermes, Kairos, and DigiClaw Atlas runner.

## Parallelizable: NO — blocks Hermes (#8), Atlas runner (#47)
## Model: opus — complex orchestration, parallel sub-graph design
""",
    ),

    dict(
        component="digiquant", type="feat", risk="med", priority="high", complexity="M",
        model="sonnet", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Atlas delta update system — line-level document patching",
        body="""\
## Goal
Implement the delta update system for Atlas research documents: rather than regenerating entire documents daily, agents produce line-level edit instructions (append/replace/delete at specific locations). This minimises token spend while keeping the research library current.

## From scratch
YES — new capability, no existing implementation.

## Acceptance Criteria
- [ ] Delta instruction format defined (Pydantic v2 model): operation, location, content
- [ ] Delta application is idempotent — re-applying the same delta is safe
- [ ] Full document regeneration still works when triggered (weekly cadence)
- [ ] Delta documents are NOT indexed by DigiSearch (only resolved final state)
- [ ] Unit tests for delta application edge cases (insert, replace, delete, append)

## Files affected (new)
- `digigraph/src/digigraph/graph/atlas/delta.py`
- `tests/dg/test_atlas_delta.py`

## Dependencies: Atlas sub-graphs (#6)
## Parallelizable: NO — part of Atlas migration sequence
## Model: sonnet
""",
    ),

    dict(
        component="digiquant", type="feat", risk="high", priority="critical", complexity="XL",
        model="opus", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:feature", "complexity:XL", "priority:critical"],
        title="[FEATURE] Hermes portfolio deliberation pipeline",
        body="""\
## Goal
Build the Hermes deliberation pipeline as DigiGraph sub-graphs: a multi-agent system that takes Atlas research, constructs investment theses, maps them to acceptable assets (filtered by user profile), runs parallel analyst agents per asset (bull/bear/headwinds/tailwinds), deliberates with a portfolio manager agent, and produces a final portfolio weight output.

## From scratch
YES — Hermes does not exist yet. Full build.

## Acceptance Criteria
- [ ] Thesis layer: Atlas research → structured investment theses with validity requirements and exit triggers
- [ ] Asset mapping: thesis → acceptable assets filtered by user investment profile (Pydantic v2)
- [ ] Analyst agents: parallel execution, one per asset, structured recommendation output
- [ ] Portfolio manager: sequential deliberation with each analyst, aware of full portfolio state
- [ ] Final output: portfolio weights with rationale (Pydantic v2 `PortfolioOutput` model)
- [ ] PyPortfolioOpt used for quantitative math (mean-variance, HRP)
- [ ] Structured outputs at every node; batching where possible
- [ ] Human approval gate before any allocation change is acted upon
- [ ] `digiquant/ARCHITECTURE.md` updated

## Files affected (new)
- `digigraph/src/digigraph/graph/hermes/__init__.py`
- `digigraph/src/digigraph/graph/hermes/thesis.py`
- `digigraph/src/digigraph/graph/hermes/analyst.py`
- `digigraph/src/digigraph/graph/hermes/portfolio_manager.py`
- `digigraph/src/digigraph/graph/hermes/models.py`
- `digiquant/src/digiquant/portfolio_math.py`

## Dependencies: Atlas sub-graphs (#6)
## Parallelizable: NO — depends on Atlas
## Model: opus — multi-agent orchestration, financial logic
""",
    ),

    dict(
        component="digiquant", type="feat", risk="med", priority="high", complexity="L",
        model="sonnet", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:feature", "complexity:L", "priority:high"],
        title="[FEATURE] Kairos strategy exploration DigiChat interface",
        body="""\
## Goal
Build the Kairos product-mode interface: a DigiChat experience where a user describes a trading idea and Kairos researches (tapping Atlas research + Hermes recommendations), derives candidate strategies, sends them through VectorBT sweep rounds, refines with NautilusTrader, and presents results. Multi-strategy parallel research rounds at scale.

## From scratch
YES — the product interface does not exist. Current Kairos is developer-facing CLI/scripts only.

## Acceptance Criteria
- [ ] User can describe a strategy idea in natural language via DigiChat
- [ ] Kairos sub-graph retrieves relevant Atlas research and Hermes recommendations
- [ ] VectorBT runs parameter sweep (multiple variations in parallel)
- [ ] Top candidates passed to NautilusTrader for final backtest validation
- [ ] Results (metrics, equity curve link) returned to DigiChat
- [ ] Strategy saved to DigiStore (Supabase) on user approval
- [ ] `digiquant/ARCHITECTURE.md` updated

## Files affected (new)
- `digigraph/src/digigraph/graph/kairos/__init__.py`
- `digigraph/src/digigraph/graph/kairos/research.py`
- `digigraph/src/digigraph/graph/kairos/sweep.py`
- `digichat/src/components/kairos/` (frontend components)

## Dependencies: Atlas migration (#6), VectorBT integration (#13)
## Parallelizable: PARTIAL — backend sub-graph and frontend can run in parallel after spec
## Model: sonnet
""",
    ),

    dict(
        component="digiquant", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:integration", "complexity:M", "priority:high"],
        title="[INTEGRATION] OpenBB as DigiStore data retrieval layer",
        body="""\
## Goal
Integrate OpenBB SDK as the data aggregation layer beneath DigiStore. OpenBB unifies ~100 free data sources (price, fundamentals, macro, crypto, news, options) under one SDK. DigiStore wraps OpenBB for retrieval and persists results to Supabase/S3 for caching.

## Acceptance Criteria
- [ ] OpenBB installed and configured in `digiquant/`
- [ ] `DigiStoreOpenBBAdapter` wraps OpenBB calls with DigiStore caching
- [ ] At minimum: price history, fundamental data (EdgarTools), macro (FRED), crypto (CoinGecko)
- [ ] Cached data served from Supabase; only fetches fresh when cache is stale
- [ ] Unit tests with mocked OpenBB responses
- [ ] `digiquant/ARCHITECTURE.md` updated (data stack section)

## Files affected (new)
- `digiquant/src/digiquant/data/openbb_adapter.py`
- `tests/dq/test_openbb_adapter.py`

## Dependencies: None — independent
## Parallelizable: YES — independent of other roadmap items
## Model: sonnet
""",
    ),

    dict(
        component="digiquant", type="feat", risk="med", priority="high", complexity="M",
        model="opus", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Live strategy deployment — Alpaca and QuantConnect connectors",
        body="""\
## Goal
Build deployment connectors that take a validated Kairos strategy (passed NautilusTrader backtest + Alpaca paper trading) and deploy it to live execution on Alpaca or QuantConnect. Includes mandatory paper → live gate with human approval.

## Non-negotiables
- Human approval gate REQUIRED before any live deployment — non-bypassable
- No live-trading path touched without this gate
- Audit trail via DigiClaw for every deployment action

## Acceptance Criteria
- [ ] `AlpacaDeployment` and `QuantConnectDeployment` classes implement `DeploymentBase`
- [ ] Paper trading validation step mandatory before live deployment option appears
- [ ] Human approval gate: deployment cannot proceed without explicit human sign-off in DigiChat
- [ ] DigiClaw audit log captures every deployment action
- [ ] `digiquant/ARCHITECTURE.md` updated

## Files affected (new)
- `digiquant/src/digiquant/deployment/__init__.py`
- `digiquant/src/digiquant/deployment/alpaca.py`
- `digiquant/src/digiquant/deployment/quantconnect.py`
- `digiquant/src/digiquant/deployment/base.py`

## Dependencies: None — independent of Atlas/Hermes
## Parallelizable: YES
## Model: opus — live trading code, human gate required
""",
    ),

    dict(
        component="digiquant", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[INFRA] VectorBT integration for fast strategy ideation sweeps",
        body="""\
## Goal
Add VectorBT as the fast strategy ideation layer alongside NautilusTrader. VectorBT is 10-100x faster for parameter sweeps — use it for exploring many strategy variations quickly during Kairos research rounds. NautilusTrader remains for final validation and live execution.

## Acceptance Criteria
- [ ] VectorBT installed in `digiquant/` dev dependencies
- [ ] `StrategySweepper` class runs multi-parameter sweeps via VectorBT
- [ ] Results returned as Pydantic v2 `SweepResult` model (top N candidates by Sharpe)
- [ ] Sweep results feed into NautilusTrader validation for top candidates only
- [ ] Unit tests for sweep with synthetic price data
- [ ] `digiquant/ARCHITECTURE.md` updated (two-track backtesting section)

## Files affected (new)
- `digiquant/src/digiquant/sweep.py`
- `tests/dq/test_sweep.py`

## Dependencies: None — independent
## Parallelizable: YES
## Model: sonnet
""",
    ),

    dict(
        component="digiquant", type="feat", risk="med", priority="medium", complexity="S",
        model="sonnet", milestone="Phase 2 — Strategy Development Loop",
        labels_extra=["type:feature", "complexity:S", "priority:medium"],
        title="[FEATURE] digiquant.io investment profiling entry flow",
        body="""\
## Goal
Build the digiquant.io free-tier entry experience: a structured investment profiling chat that collects user preferences (risk tolerance, time horizon, asset classes, investment goals), saves the profile to DigiStore, and shows what Atlas/Hermes could produce for their profile. Paywall trigger: "Ready to build your first strategy? Start with Kairos."

## Acceptance Criteria
- [ ] Investment profiling sub-graph collects profile via structured DigiChat conversation
- [ ] User profile saved to DigiStore (Supabase) as `InvestmentProfile` Pydantic model
- [ ] Sample Atlas research summary shown relevant to their stated interests
- [ ] Paywall trigger rendered at end of free flow
- [ ] Free tier: no API key required (cheap model, limited tokens)
- [ ] Profile persists across sessions for returning users

## Files affected
- `digigraph/src/digigraph/graph/subgraphs/investment_profiling.py` (new)
- `digichat/src/components/profiling/` (new)

## Dependencies: Hermes (#8)
## Parallelizable: NO
## Model: sonnet
""",
    ),

    # ── DigiGraph (Project #3) ─────────────────────────────────────────────────

    dict(
        component="digigraph", type="fix", risk="high", priority="critical", complexity="M",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:critical"],
        title="[SECURITY] DigiGraph security hardening — IMPROVEMENT_PLAN Phase 1",
        body="""\
## Goal
Close the 8 critical security gaps identified in `docs/IMPROVEMENT_PLAN_V2.md` Phase 1. These are blocking — none of the public-facing deployments (digithings.ai, digiquant.io) should go live until these are resolved.

## Items to fix
1. API key timing attack — constant-time comparison (1-line fix)
2. Path traversal — resolve-first pattern in `path_utils.py` (new util, 4 callsites)
3. OData filter injection — grammar validator or raw-filter allowlist in DigiSearch
4. Session ID length limit — 1 line in DigiGraph
5. DigiSearch stub explicit error — show "no_backend_configured" not fake results
6. CORS default — require explicit allowlist, not `["*"]`
7. Data directory traversal in DigiQuant — 4 lines
8. Sandbox `execute_python.py` — gate behind env var or subprocess sandbox

## Acceptance Criteria
- [ ] All 8 items resolved
- [ ] Regression tests for each security fix
- [ ] `make score` passes Security ≥ 8 on all three services
- [ ] `docs/IMPROVEMENT_PLAN_V2.md` Phase 1 marked complete

## Files affected
- `digigraph/src/digigraph/path_utils.py` (new)
- `digigraph/src/digigraph/server.py` (CORS, session limit)
- `digisearch/src/digisearch/server.py` (OData, stub error)
- `digiquant/src/digiquant/` (data dir traversal)

## Dependencies: None — independent, highest priority
## Parallelizable: NO — security fixes should be reviewed together
## Model: opus
""",
    ),

    dict(
        component="digigraph", type="feat", risk="med", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Investor document builder sub-graph",
        body="""\
## Goal
Build a proprietary DigiGraph sub-graph that takes an investment thesis, selected assets, and user context, and produces a formal investor document: executive summary, thesis statement, asset analysis, risk factors, and recommended allocation. Output: structured Pydantic model + formatted markdown.

## Acceptance Criteria
- [ ] Sub-graph registered in DigiGraph tool registry
- [ ] Accepts: thesis (str), assets (list), user_context (dict)
- [ ] Produces: `InvestorDocument` Pydantic v2 model with all required sections
- [ ] Formatted markdown output suitable for export to PDF
- [ ] Unit tests with mocked LLM responses
- [ ] Schema validates — no free-form output where structured is expected

## Files affected (new)
- `digigraph/src/digigraph/graph/subgraphs/investor_doc.py`
- `tests/dg/test_investor_doc.py`

## Dependencies: None — independent sub-graph
## Parallelizable: YES — independent of Atlas/Hermes
## Model: sonnet
""",
    ),

    dict(
        component="digigraph", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Scholarly article synthesis sub-graph",
        body="""\
## Goal
Build a sub-graph that ingests scholarly articles (PDFs or URLs), extracts key findings, and synthesises them into a structured research note saved to the DigiStore research library. Feeds the Atlas knowledge base with academic-quality content.

## Acceptance Criteria
- [ ] Sub-graph accepts: list of article URLs or file paths
- [ ] Uses DigiSearch PDF parser for ingestion
- [ ] Produces: `ResearchNote` Pydantic v2 model (title, key findings, methodology, implications, citations)
- [ ] Saves to DigiStore research library with proper metadata
- [ ] Registered as a DigiGraph tool
- [ ] Unit tests with sample article fixture

## Files affected (new)
- `digigraph/src/digigraph/graph/subgraphs/article_synthesis.py`
- `tests/dg/test_article_synthesis.py`

## Dependencies: DigiSearch PDF parsing (already exists), DigiStore
## Parallelizable: YES — alongside investor_doc sub-graph
## Model: sonnet
""",
    ),

    dict(
        component="digigraph", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Exploration agent sub-graph — exhaustive index search",
        body="""\
## Goal
Build a fast, cheap exploration agent sub-graph that exhaustively searches a DigiSearch index to uncover every relevant piece of information before synthesis. Uses a cheap/fast model (e.g. Haiku) with quick iterations. The "deep search" pattern — analogous to Perplexity's deep research mode.

## Acceptance Criteria
- [ ] Sub-graph accepts: query (str), index_name (str), max_iterations (int, default 10)
- [ ] Uses cheap model (configurable, default haiku/flash)
- [ ] Iteratively refines search queries based on what's been found
- [ ] Returns: `ExplorationResult` — ranked findings with source references
- [ ] Registered as a DigiGraph tool callable by other sub-graphs
- [ ] Cost guard: stops at max_iterations or when coverage metric plateaus
- [ ] Unit tests

## Files affected (new)
- `digigraph/src/digigraph/graph/subgraphs/exploration.py`
- `tests/dg/test_exploration.py`

## Dependencies: DigiSearch (already exists)
## Parallelizable: YES
## Model: sonnet
""",
    ),

    dict(
        component="digigraph", type="feat", risk="med", priority="medium", complexity="L",
        model="opus", milestone=None,
        labels_extra=["type:research", "complexity:L", "priority:medium"],
        title="[FEATURE] Graphiti graph memory integration",
        body="""\
## Goal
Integrate Graphiti (temporal knowledge graph) as an optional persistent memory backend for DigiGraph. Enables cross-session knowledge accumulation — agents remember what they learned, who said what, and how the world has changed over time. Particularly valuable for Atlas (remembering past research conclusions) and Hermes (tracking thesis evolution).

## Acceptance Criteria
- [ ] Graphiti installed as optional dependency (`digigraph[memory]`)
- [ ] `GraphitiMemory` implements `MemoryBase` interface
- [ ] Activated via `DIGI_MEMORY_BACKEND=graphiti` env var
- [ ] DigiGraph nodes can read/write to the knowledge graph
- [ ] No regression when Graphiti is not configured (graceful fallback)
- [ ] `digigraph/ARCHITECTURE.md` updated

## Files affected (new)
- `digigraph/src/digigraph/memory/__init__.py`
- `digigraph/src/digigraph/memory/graphiti.py`
- `digigraph/src/digigraph/memory/base.py`

## Dependencies: None — independent
## Parallelizable: YES
## Model: opus — novel architecture pattern
""",
    ),

    dict(
        component="digigraph", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[FEATURE] Remote MCP enumeration — discover external MCP servers at runtime",
        body="""\
## Goal
Extend the DigiGraph tool registry to enumerate and integrate external MCP servers at runtime. A DigiGraph instance can discover tools from any MCP server pointed at it via config, making the tool registry open and extensible without code changes.

## Acceptance Criteria
- [ ] `DIGI_MCP_SERVERS` env var accepts comma-separated MCP server URLs
- [ ] At startup, DigiGraph enumerates tools from each configured MCP server
- [ ] Enumerated tools appear in the tool registry alongside built-in tools
- [ ] Tool calls are proxied to the correct MCP server transparently
- [ ] `digigraph/ARCHITECTURE.md` updated

## Files affected
- `digigraph/src/digigraph/orchestration/registry.py` (extend)
- `digigraph/src/digigraph/orchestration/mcp_client.py` (new)

## Dependencies: None — independent
## Parallelizable: YES
## Model: sonnet
""",
    ),

    dict(
        component="digigraph", type="feat", risk="low", priority="medium", complexity="S",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:S", "priority:medium"],
        title="[FEATURE] OpenAI Responses API support",
        body="""\
## Goal
Add support for the OpenAI Responses API (stateful conversations, built-in tools, file search) as an alternative completion backend in DigiGraph's LLM layer. Enables richer integrations for clients using the Responses API natively.

## Acceptance Criteria
- [ ] `ResponsesAPIClient` implements the `LLMClient` interface in `llm.py`
- [ ] Activated via `DIGI_LLM_BACKEND=responses_api` env var
- [ ] Existing `get_client()` / `chat_completion()` API unchanged
- [ ] Graceful fallback to standard chat completions if not configured
- [ ] Unit tests with mocked Responses API

## Files affected
- `digigraph/src/digigraph/llm.py` (extend)
- `tests/dg/test_llm_backends.py` (extend)

## Dependencies: None — independent
## Parallelizable: YES
## Model: sonnet
""",
    ),

    # ── DigiSearch (Project #4) ────────────────────────────────────────────────

    dict(
        component="digisearch", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[FEATURE] Expand vector backend registry — Qdrant, Weaviate, LanceDB",
        body="""\
## Goal
Add three new vector store backends to DigiSearch's pluggable registry: Qdrant (high-performance, self-hostable), Weaviate (strong built-in hybrid search), and LanceDB (columnar + vector, excellent for local use). Each implements the existing `BackendBase` interface.

## Acceptance Criteria
- [ ] `QdrantBackend`, `WeaviateBackend`, `LanceDBBackend` all implement `BackendBase`
- [ ] Backend selected via `DIGI_VECTOR_BACKEND=qdrant|weaviate|lancedb` env var
- [ ] Each backend passes the shared backend test suite (`tests/ds/test_backends.py`)
- [ ] Docker Compose service definitions added for Qdrant and Weaviate (optional profiles)
- [ ] `digisearch/ARCHITECTURE.md` updated (backend registry section)

## Files affected
- `digisearch/src/digisearch/backends/qdrant.py` (new)
- `digisearch/src/digisearch/backends/weaviate.py` (new)
- `digisearch/src/digisearch/backends/lancedb.py` (new)

## Dependencies: None — extend existing backend registry
## Parallelizable: YES — each backend is independent
## Model: sonnet
""",
    ),

    dict(
        component="digisearch", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Selective indexing — draft/final state tracking from DigiStore",
        body="""\
## Goal
Implement selective indexing rules: DigiSearch only indexes finalized documents from DigiStore, not delta patches, drafts, or intermediate agent outputs. Re-index is triggered when a document transitions to final state. This prevents delta noise from polluting the search index.

## Acceptance Criteria
- [ ] `DocumentState` enum: DRAFT, FINAL defined in DigiStore
- [ ] DigiSearch indexer only processes documents with state=FINAL
- [ ] Re-index triggered on DRAFT→FINAL transition (event or polling)
- [ ] Delta patch files explicitly excluded from indexing
- [ ] Integration test: create draft → index → verify not found → finalize → verify found

## Files affected
- `digisearch/src/digisearch/indexer.py` (extend)
- `digistore/src/digistore/models.py` (DocumentState enum — new)

## Dependencies: DigiStore standalone module (#57)
## Parallelizable: NO
## Model: sonnet
""",
    ),

    dict(
        component="digisearch", type="feat", risk="med", priority="high", complexity="M",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Index access control via DigiKey JWT scopes",
        body="""\
## Goal
Add JWT-based access control to DigiSearch: the JWT issued by DigiKey contains which indexes the user is allowed to query and what document-level filters apply. DigiSearch enforces this without per-client code changes.

## Acceptance Criteria
- [ ] DigiSearch reads `index:<name>` scopes from the validated JWT
- [ ] Requests for an index the user lacks scope for return 403 (not 404)
- [ ] Document-level filter applied when JWT contains filter rules (e.g. department=engineering)
- [ ] No regression for unauthenticated/internal calls
- [ ] Unit tests for scope enforcement
- [ ] `digisearch/ARCHITECTURE.md` updated

## Files affected
- `digisearch/src/digisearch/server.py` (extend auth middleware)
- `digisearch/src/digisearch/auth.py` (new)
- `tests/ds/test_access_control.py` (new)

## Dependencies: DigiKey resource-level JWT claims (#37)
## Parallelizable: NO
## Model: opus — security-sensitive
""",
    ),

    dict(
        component="digisearch", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:integration", "complexity:M", "priority:high"],
        title="[INTEGRATION] DigiQuant research library indexing — Atlas documents",
        body="""\
## Goal
Configure DigiSearch to index finalized Atlas research documents from DigiStore, enabling the Kairos exploration agent and DigiChat to semantically search the research library.

## Acceptance Criteria
- [ ] Atlas finalised documents trigger DigiSearch re-index via DigiStore event
- [ ] Research library searchable via `search_strategies()` MCP tool
- [ ] Correct metadata filtering: query by date, doc_type, sector, asset_class
- [ ] Integration test: finalize an Atlas doc → verify searchable in DigiSearch
- [ ] `digiquant/ARCHITECTURE.md` updated (DigiSearch integration section)

## Dependencies: Atlas migration (#6), DigiStore (#57), Selective indexing (#24)
## Parallelizable: NO
## Model: sonnet
""",
    ),

    dict(
        component="digisearch", type="feat", risk="low", priority="medium", complexity="S",
        model="sonnet", milestone=None,
        labels_extra=["type:infra", "complexity:S", "priority:medium"],
        title="[INFRA] digithings-guide index — DigiThings docs indexed for digithings.ai demo",
        body="""\
## Goal
Deploy the digithings-guide DigiSearch index (already defined in `docs/projects/digithings-guide/`) so the digithings.ai chat demo can answer questions about DigiThings from the actual documentation.

## Acceptance Criteria
- [ ] `docs/projects/digithings-guide/` index deployed and populated
- [ ] All `docs/`, `ARCHITECTURE.md`, ADRs, vision docs, module READMEs indexed
- [ ] Semantic search returns relevant results for queries like "what does DigiQuant do?"
- [ ] Index auto-updates when docs change (CI hook or scheduled DigiClaw job)

## Files affected
- `docs/projects/digithings-guide/indexes/docs.yaml` (extend sources)
- DigiSearch deployment config

## Dependencies: None — independent
## Parallelizable: YES
## Model: sonnet
""",
    ),

    # ── DigiChat (Project #5) ──────────────────────────────────────────────────

    dict(
        component="digichat", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Model selector settings panel — multi-provider BYOK",
        body="""\
## Goal
Build a model selector settings panel in DigiChat where users configure their LLM provider connections: API key input, provider selection, and optional OAuth for providers requiring it. Stored per user in DigiStore. LiteLLM handles the translation — this is pure frontend + config plumbing.

## Acceptance Criteria
- [ ] Settings panel accessible from DigiChat UI
- [ ] Supports: OpenAI, Anthropic, Gemini, Ollama (local), and a generic "custom" provider
- [ ] API key stored encrypted in DigiStore per user (never in localStorage)
- [ ] Provider selection persists across sessions
- [ ] Model selection dropdown populated based on configured provider's available models
- [ ] Existing BYOK flow migrated to use this panel
- [ ] `digichat/ARCHITECTURE.md` updated

## Files affected
- `digichat/src/components/model-selector/` (new components)
- `digichat/src/app/api/settings/` (new API routes)

## Dependencies: None — extend existing BYOK flow
## Parallelizable: YES — pure frontend
## Model: sonnet
""",
    ),

    dict(
        component="digichat", type="feat", risk="med", priority="high", complexity="M",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Microsoft SSO and Google OIDC login via DigiKey",
        body="""\
## Goal
Add SSO login options to DigiChat using DigiKey as the identity broker. Users from Microsoft-tenant organizations log in with their corporate account; general users log in with Google. DigiKey issues a JWT with org/project membership and resource scopes.

## Acceptance Criteria
- [ ] "Login with Microsoft" and "Login with Google" buttons in DigiChat
- [ ] Auth flow: DigiChat → DigiKey SSO endpoint → corporate IdP → DigiKey JWT → DigiChat session
- [ ] JWT scopes drive visible tools/indexes (adaptive UI — see #30)
- [ ] Existing email/password and API key login unaffected
- [ ] `digichat/ARCHITECTURE.md` updated

## Files affected
- `digichat/src/auth.ts` (extend)
- `digichat/src/app/api/auth/` (extend)

## Dependencies: DigiKey Microsoft OIDC (#34)
## Parallelizable: NO — depends on DigiKey SSO
## Model: opus
""",
    ),

    dict(
        component="digichat", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Adaptive UI — scope-driven tool and index visibility",
        body="""\
## Goal
Make DigiChat's UI adapt to the user's DigiKey JWT scopes: tools, indexes, and sub-graphs not in the user's scope simply don't appear — not locked, not visible. A free user sees the public demo; an enterprise user sees their org's indexes and tools.

## Acceptance Criteria
- [ ] JWT scopes read on login and stored in client session (no JWT exposure to frontend)
- [ ] Tool/connection panel only renders items matching user's scopes
- [ ] Scope changes (e.g. plan upgrade) reflected on next login without code changes
- [ ] Unit tests for scope-to-visibility mapping logic
- [ ] `digichat/ARCHITECTURE.md` updated

## Files affected
- `digichat/src/lib/scopes.ts` (new)
- `digichat/src/components/sidebar/` (extend)
- `digichat/src/app/api/me/` (new — returns user scope summary)

## Dependencies: DigiKey resource-level JWTs (#37)
## Parallelizable: NO — depends on DigiKey
## Model: sonnet
""",
    ),

    dict(
        component="digichat", type="feat", risk="low", priority="medium", complexity="S",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:S", "priority:medium"],
        title="[FEATURE] digithings.ai demo — docs indexed, 3-question free tier",
        body="""\
## Goal
Deploy the digithings.ai DigiChat demo instance: DigiThings own docs indexed, 3 free questions with a cheap model (Haiku/Flash), BYOK to continue, model selector visible, sample questions displayed.

## Acceptance Criteria
- [ ] Visitor can ask 3 questions without any API key
- [ ] Token/question counter visible and enforced
- [ ] Sample questions shown: "What is DigiThings?", "What does DigiQuant do?", "How do I deploy DigiThings?"
- [ ] BYOK prompt shown after 3rd question with provider options
- [ ] digithings-guide index (#27) live and powering responses
- [ ] Deployment config committed and documented

## Dependencies: digithings-guide index (#27)
## Parallelizable: NO
## Model: sonnet
""",
    ),

    dict(
        component="digichat", type="feat", risk="low", priority="medium", complexity="S",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:S", "priority:medium"],
        title="[FEATURE] Conversation history and session management UI",
        body="""\
## Goal
Build conversation history UI: users can see past conversations, resume them, rename them, and delete them. Already stored in Postgres via Drizzle — this is the frontend and retrieval API work.

## Acceptance Criteria
- [ ] Sidebar shows conversation list ordered by last activity
- [ ] Click to resume a past conversation (full message history loaded)
- [ ] Rename and delete conversations
- [ ] Search/filter conversations by keyword
- [ ] Conversations grouped by date (Today, Yesterday, Last 7 days)
- [ ] `digichat/ARCHITECTURE.md` updated

## Files affected
- `digichat/src/components/history/` (new)
- `digichat/src/app/api/conversations/` (extend)

## Dependencies: None — data already exists in Postgres
## Parallelizable: YES
## Model: sonnet
""",
    ),

    # ── DigiKey (Project #6) ───────────────────────────────────────────────────

    dict(
        component="digikey", type="feat", risk="high", priority="critical", complexity="L",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:L", "priority:critical"],
        title="[FEATURE] Microsoft OIDC/SAML SSO integration",
        body="""\
## Goal
Add Microsoft identity provider support to DigiKey. Enterprise clients using Microsoft tenants can log in with their corporate credentials. DigiKey maps the Microsoft identity to a DigiThings project/org and issues a JWT with appropriate scopes.

## From scratch
YES — SSO infrastructure does not exist in DigiKey.

## Acceptance Criteria
- [ ] Microsoft OIDC authorization code flow implemented in DigiKey
- [ ] SAML 2.0 support for orgs using SAML (optional, configurable)
- [ ] Identity mapped to DigiThings project via `DIGI_SSO_TENANT_MAP` config
- [ ] JWT issued with org_id, project_id, and resource scopes from org config
- [ ] Token exchange: Microsoft token → DigiKey JWT (same `token_exchange` endpoint)
- [ ] Unit tests with mocked Microsoft OIDC responses
- [ ] `digikey/ARCHITECTURE.md` updated

## Files affected (new)
- `digikey/src/digikey/sso/__init__.py`
- `digikey/src/digikey/sso/microsoft.py`
- `digikey/src/digikey/sso/base.py`

## Dependencies: None — foundation for Google OIDC (#35) and DigiChat SSO
## Parallelizable: NO — blocks DigiChat SSO login
## Model: opus — security-critical identity path
""",
    ),

    dict(
        component="digikey", type="feat", risk="high", priority="high", complexity="M",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Google OIDC integration",
        body="""\
## Goal
Add Google OIDC as a second SSO provider in DigiKey, using the SSO framework established by the Microsoft integration. General users (not enterprise) can log in with their Google account.

## Acceptance Criteria
- [ ] Google OIDC authorization code flow implemented using `sso/base.py`
- [ ] Google identity mapped to DigiThings user (personal account, no org mapping required)
- [ ] JWT issued with user_id and default tier scopes
- [ ] Unit tests
- [ ] `digikey/ARCHITECTURE.md` updated

## Files affected (new)
- `digikey/src/digikey/sso/google.py`

## Dependencies: Microsoft SSO (#34) — SSO base framework
## Parallelizable: NO — sequential after Microsoft
## Model: opus
""",
    ),

    dict(
        component="digikey", type="feat", risk="high", priority="critical", complexity="L",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:L", "priority:critical"],
        title="[FEATURE] Organization and project membership API",
        body="""\
## Goal
Build the organization and project membership data model and API in DigiKey. A user belongs to one or more organizations; each org has one or more projects; each project has a set of resource permissions. This is the foundation for resource-level JWTs and multi-tenant isolation.

## From scratch
YES — DigiKey currently has users and API keys but no org/project concept.

## Acceptance Criteria
- [ ] Database schema: `orgs`, `projects`, `org_members`, `project_members` tables
- [ ] REST API: CRUD for orgs, projects, and memberships (admin-only)
- [ ] `GET /v1/me` returns user's org and project memberships
- [ ] Org/project IDs included in issued JWTs
- [ ] Unit tests for membership API
- [ ] `digikey/ARCHITECTURE.md` updated

## Files affected (new)
- `digikey/src/digikey/org.py`
- `digikey/src/digikey/db_schema.py` (extend)
- `tests/dk/test_org.py`

## Dependencies: None — foundation for resource-level JWTs
## Parallelizable: NO — needed before resource-level JWTs
## Model: opus
""",
    ),

    dict(
        component="digikey", type="feat", risk="high", priority="critical", complexity="M",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:critical"],
        title="[FEATURE] Resource-level JWT claims — index and sub-graph access scopes",
        body="""\
## Goal
Extend DigiKey's JWT issuance to include resource-level claims: which specific DigiSearch indexes, which DigiGraph sub-graphs, and what data-filter rules apply to this user. Downstream services (DigiSearch, DigiGraph, DigiChat) read these claims to enforce access without per-client code changes.

## Acceptance Criteria
- [ ] JWT payload includes `resources` claim: `{indexes: [...], subgraphs: [...], filters: {...}}`
- [ ] Resources derived from org/project configuration (not hardcoded)
- [ ] DigiSearch enforces `indexes` claim (see #25)
- [ ] DigiGraph enforces `subgraphs` claim on tool invocation
- [ ] JWT size remains reasonable (< 8KB) — pagination or reference tokens if needed
- [ ] Unit tests for resource claim generation and enforcement
- [ ] `digikey/ARCHITECTURE.md` updated

## Files affected
- `digikey/src/digikey/jwt_issue.py` (extend)
- `digikey/src/digikey/scopes.py` (extend)
- `tests/dk/test_resource_claims.py` (new)

## Dependencies: Org membership (#36)
## Parallelizable: NO
## Model: opus
""",
    ),

    dict(
        component="digikey", type="fix", risk="high", priority="critical", complexity="M",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:critical"],
        title="[SECURITY] JWT revocation — jti blocklist in Redis",
        body="""\
## Goal
Implement JWT revocation via a jti (JWT ID) blocklist stored in Redis. Currently there is no way to invalidate an issued JWT before it expires — this is a known security gap. Any compromised token is valid until expiry.

## Acceptance Criteria
- [ ] Every issued JWT includes a unique `jti` claim
- [ ] `POST /v1/revoke` endpoint adds jti to Redis blocklist with TTL matching token expiry
- [ ] All token verification middleware checks blocklist before accepting
- [ ] Redis connection is optional with graceful fallback (log warning, no hard failure) for dev
- [ ] `DIGI_REDIS_URL` env var controls Redis connection
- [ ] Unit tests for revocation flow
- [ ] `digikey/ARCHITECTURE.md` updated (security section)

## Files affected (new)
- `digikey/src/digikey/revocation.py`
## Files affected (modify)
- `digikey/src/digikey/jwt_verify.py`
- `digikey/src/digikey/server.py`

## Dependencies: None — independent security fix
## Parallelizable: YES — independent of SSO work
## Model: opus — security-critical
""",
    ),

    dict(
        component="digikey", type="fix", risk="med", priority="high", complexity="M",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[SECURITY] Scheduled JWKS rotation with zero-downtime overlap",
        body="""\
## Goal
Implement scheduled JWKS key rotation that maintains a transition period where both old and new keys are valid. Currently JWKS rotates on restart, causing all existing JWTs to become invalid immediately — a production availability risk.

## Acceptance Criteria
- [ ] Key rotation schedule configurable via `DIGI_JWKS_ROTATION_DAYS` (default: 30)
- [ ] During rotation: both old and new key in JWKS endpoint for `DIGI_JWKS_OVERLAP_HOURS` (default: 24)
- [ ] New JWTs issued with new key immediately; old JWTs validated against old key during overlap
- [ ] Rotation can be triggered manually via admin API
- [ ] Unit tests for overlap window behavior
- [ ] `digikey/ARCHITECTURE.md` updated

## Files affected
- `digikey/src/digikey/crypto_keys.py` (extend)
- `digikey/src/digikey/server.py` (extend)

## Dependencies: None — independent
## Parallelizable: YES
## Model: opus
""",
    ),

    # ── DigiSmith (Project #7) ─────────────────────────────────────────────────

    dict(
        component="digismith", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Prometheus /metrics endpoint rollout to all services",
        body="""\
## Goal
Roll out Prometheus `/metrics` endpoints to all DigiThings services using the shared `digibase.metrics` instrumentation. Consistent labels across all services enable unified dashboards.

## Acceptance Criteria
- [ ] `/metrics` endpoint live on: DigiGraph, DigiQuant, DigiSearch, DigiKey, DigiSmith, DigiClaw
- [ ] Consistent metric labels: `service`, `version`, `environment`
- [ ] Request duration histogram, request count, and error rate per route
- [ ] `digibase/src/digibase/metrics.py` utility used by all (no per-service duplicate)
- [ ] Docker Compose Prometheus scrape config updated
- [ ] `digismith/ARCHITECTURE.md` updated

## Files affected
- `digibase/src/digibase/metrics.py` (extend)
- Each service's `server.py` (add metrics mount)

## Dependencies: None
## Parallelizable: YES — each service independently
## Model: sonnet
""",
    ),

    dict(
        component="digismith", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] X-Request-ID correlation ID propagation across all services",
        body="""\
## Goal
Propagate X-Request-ID headers through all service-to-service calls so a single user request can be traced end-to-end through DigiChat → DigiGraph → DigiSearch/DigiQuant → DigiKey. Uses the existing `digibase.http` outbound header utilities.

## Acceptance Criteria
- [ ] All incoming requests assign or pass through an X-Request-ID
- [ ] All outbound HTTP calls from any service include the X-Request-ID
- [ ] Request ID appears in all log lines for that request
- [ ] Correlation ID visible in DigiSmith `/v1/status` for active requests
- [ ] Integration test: single request traced through 3 service hops

## Files affected
- `digibase/src/digibase/http.py` (extend middleware)
- All service `server.py` files (add middleware)

## Dependencies: None — independent
## Parallelizable: YES
## Model: sonnet
""",
    ),

    dict(
        component="digismith", type="feat", risk="low", priority="high", complexity="S",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:S", "priority:high"],
        title="[FEATURE] PII redaction middleware before LangSmith tracing",
        body="""\
## Goal
Add PII redaction middleware in DigiSmith that strips sensitive fields (API keys, email addresses, personal identifiers) from trace data before it reaches LangSmith. Required before enabling LangSmith in production.

## Acceptance Criteria
- [ ] `PiiRedactor` strips: email patterns, API key patterns (`dgk_live_*`, `sk-*`), phone numbers
- [ ] Redaction applied to all span inputs/outputs before LangSmith submission
- [ ] Configurable: additional patterns via `DIGI_PII_PATTERNS` env var
- [ ] No-op when LangSmith not configured
- [ ] Unit tests: verify redaction on known PII patterns, no-op on clean data

## Files affected (new)
- `digismith/src/digismith/redaction.py`
- `digismith/src/digismith/trace.py` (extend)

## Dependencies: None — independent
## Parallelizable: YES
## Model: sonnet
""",
    ),

    dict(
        component="digismith", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[FEATURE] Structured logging throughout DigiSearch",
        body="""\
## Goal
Add structured JSON logging throughout DigiSearch — currently it has zero structured logging. Every significant operation (parse, chunk, embed, index, query) should emit a structured log entry with request_id, operation, duration, and outcome.

## Acceptance Criteria
- [ ] All DigiSearch modules use `structlog` or Python `logging` with JSON formatter
- [ ] Log entries include: timestamp, level, service, request_id, operation, duration_ms, outcome
- [ ] No sensitive data (document content, user queries) in logs at INFO level
- [ ] Log level configurable via `DIGI_LOG_LEVEL` env var
- [ ] `digisearch/ARCHITECTURE.md` updated

## Files affected
- `digisearch/src/digisearch/` (all files — add logging)

## Dependencies: X-Request-ID propagation (#41) for request_id
## Parallelizable: YES
## Model: sonnet
""",
    ),

    # ── DigiClaw (Project #8) ──────────────────────────────────────────────────

    dict(
        component="digiclaw", type="feat", risk="med", priority="high", complexity="L",
        model="opus", milestone=None,
        labels_extra=["type:infra", "complexity:L", "priority:high"],
        title="[INFRA] OpenClaw runtime integration",
        body="""\
## Goal
Integrate the OpenClaw runtime as the agent execution engine beneath DigiClaw. OpenClaw handles the actual agent loop, tool calling, and session management. DigiClaw wraps it with scheduling, agent definitions, audit logging, and tool provisioning.

## From scratch
YES — DigiClaw currently has no OpenClaw integration.

## Acceptance Criteria
- [ ] OpenClaw installed as DigiClaw dependency
- [ ] `OpenClawRuntime` class wraps OpenClaw with DigiClaw's agent definition schema
- [ ] An agent can be launched with: definition file, tool list, and schedule config
- [ ] Agent output captured and written to JSONL audit log
- [ ] `digiclaw/ARCHITECTURE.md` updated with integration architecture

## Files affected (new)
- `digiclaw/src/digiclaw/openclaw/__init__.py`
- `digiclaw/src/digiclaw/openclaw/runtime.py`
- `digiclaw/src/digiclaw/openclaw/adapter.py`

## Dependencies: None — foundation for all other DigiClaw tasks
## Parallelizable: NO — blocks agent registry and scheduler
## Model: opus — novel architecture integration
""",
    ),

    dict(
        component="digiclaw", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Agent definition schema and registry",
        body="""\
## Goal
Define the schema for DigiClaw agent definitions (YAML files) and build the registry that loads, validates, and manages them. An agent definition specifies: what the agent does, which tools/sub-graphs it has access to, its schedule, and its output sink.

## Acceptance Criteria
- [ ] `AgentDefinition` Pydantic v2 schema: name, description, tools, schedule, output_sink
- [ ] YAML files in `digiclaw/agents/` auto-loaded on startup
- [ ] Registry validates all definitions against schema on load
- [ ] `digiclaw agents list` CLI command shows registered agents
- [ ] Unit tests for schema validation and registry loading

## Files affected (new)
- `digiclaw/src/digiclaw/agents/__init__.py`
- `digiclaw/src/digiclaw/agents/schema.py`
- `digiclaw/src/digiclaw/agents/registry.py`
- `digiclaw/agents/` (example definitions directory)

## Dependencies: OpenClaw integration (#44)
## Parallelizable: NO
## Model: sonnet
""",
    ),

    dict(
        component="digiclaw", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] Cron and continuous scheduling",
        body="""\
## Goal
Build the scheduling layer for DigiClaw: agents can be scheduled on a cron expression, run continuously (24/7 with configurable sleep between iterations), or triggered by events. The scheduler manages agent lifecycle: start, stop, pause, resume.

## Acceptance Criteria
- [ ] Cron schedule parsed from agent definition YAML (standard cron syntax)
- [ ] Continuous mode: agent loops with configurable `interval_seconds`
- [ ] Scheduler survives service restart (pending jobs re-queued)
- [ ] `digiclaw schedule status` CLI shows next run times
- [ ] Agent runs are isolated — one run's failure doesn't affect next scheduled run
- [ ] Unit tests for cron expression parsing and run scheduling

## Files affected (new)
- `digiclaw/src/digiclaw/scheduler.py`
- `tests/dc/test_scheduler.py`

## Dependencies: Agent registry (#45)
## Parallelizable: NO
## Model: sonnet
""",
    ),

    dict(
        component="digiclaw", type="feat", risk="med", priority="critical", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:critical"],
        title="[FEATURE] Atlas daily cycle automation — DigiClaw scheduled job",
        body="""\
## Goal
Define and deploy the Atlas daily cycle as a DigiClaw scheduled job: delta updates at 06:00 UTC daily, full regeneration weekly (configurable), monthly rollup on the 1st. Eliminates manual Atlas execution entirely.

## Acceptance Criteria
- [ ] `digiclaw/agents/atlas_daily.yaml` agent definition with correct schedule
- [ ] Agent triggers the Atlas DigiGraph sub-graph via MCP/API call
- [ ] Run result (success/failure, documents updated, token cost) written to audit log
- [ ] Alert triggered (via DigiSmith or webhook) if run fails 2x consecutively
- [ ] Integration test: trigger agent manually, verify Atlas sub-graph runs

## Files affected (new)
- `digiclaw/agents/atlas_daily.yaml`
- `digiclaw/src/digiclaw/jobs/atlas_daily.py`

## Dependencies: Scheduler (#46) + Atlas DigiGraph migration (#6)
## Parallelizable: NO
## Model: sonnet
""",
    ),

    dict(
        component="digiclaw", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[FEATURE] Strategy performance monitor agent",
        body="""\
## Goal
Build a DigiClaw agent that continuously monitors live strategy performance against backtest baseline. Detects statistically significant P&L drift, Sharpe degradation, or execution anomalies and files a GitHub issue or sends an alert.

## Acceptance Criteria
- [ ] `digiclaw/agents/strategy_monitor.yaml` agent definition (continuous, 1hr interval)
- [ ] Fetches live performance metrics from deployed strategy (Alpaca API)
- [ ] Compares rolling Sharpe, win rate, and max drawdown vs. backtest baseline
- [ ] Drift threshold configurable per strategy in the definition file
- [ ] On threshold breach: writes alert to audit log + creates GitHub issue via `gh` CLI
- [ ] Unit tests for drift detection logic

## Files affected (new)
- `digiclaw/agents/strategy_monitor.yaml`
- `digiclaw/src/digiclaw/jobs/strategy_monitor.py`

## Dependencies: Scheduler (#46)
## Parallelizable: YES — after scheduler
## Model: sonnet
""",
    ),

    dict(
        component="digiclaw", type="feat", risk="high", priority="medium", complexity="L",
        model="opus", milestone=None,
        labels_extra=["type:feature", "complexity:L", "priority:medium"],
        title="[FEATURE] ADDM — Adaptive Drift Detection Monitor (rewrite from stub)",
        body="""\
## Goal
Rewrite the ADDM stub (currently returns `drift_detected=false` always) into a real drift detection system. ADDM monitors two kinds of drift: strategy performance drift (vs. backtest baseline) and agent output quality drift (outputs changing character over time, indicating model behaviour change).

## From scratch
YES — current ADDM is a stub. Full implementation needed.

## Acceptance Criteria
- [ ] Statistical drift detection: Page-Hinkley test or CUSUM on rolling performance metrics
- [ ] Agent output quality drift: embedding distance between recent outputs and historical baseline
- [ ] `DriftReport` Pydantic v2 model: drift_type, severity, metric, threshold, recommendation
- [ ] ADDM runs as a DigiClaw agent (scheduled, after each monitored run)
- [ ] Unit tests with synthetic drift scenarios
- [ ] `digiclaw/ARCHITECTURE.md` updated (ADDM section)

## Files affected
- `digiclaw/src/digiclaw/addm.py` (rewrite)
- `tests/dc/test_addm.py` (new)

## Dependencies: Scheduler (#46)
## Parallelizable: YES — after scheduler
## Model: opus — statistical methods, novel detection logic
""",
    ),

    # ── DigiBase (Project #9) ──────────────────────────────────────────────────

    dict(
        component="digibase", type="chore", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:infra", "complexity:M", "priority:medium"],
        title="[CHORE] Extend OTel wiring — all services emit OpenTelemetry traces",
        body="""\
## Goal
Extend DigiBase's optional OTel wiring so that all services emit OpenTelemetry traces when `DIGI_OTEL_ENDPOINT` is configured. Enables integration with Jaeger, Tempo, or any OTLP-compatible backend.

## Acceptance Criteria
- [ ] All services import and initialise OTel from `digibase.otel` (no per-service setup)
- [ ] Spans cover: incoming HTTP requests, LLM calls, DigiSearch queries, DigiKey exchanges
- [ ] Service name and version in resource attributes
- [ ] Zero overhead when `DIGI_OTEL_ENDPOINT` is not set
- [ ] Docker Compose OTel Collector config added (optional profile)

## Files affected
- `digibase/src/digibase/otel.py` (extend)
- Each service `server.py` (add OTel init)

## Dependencies: None — independent
## Parallelizable: YES — per service
## Model: sonnet
""",
    ),

    # ── DigiLink (tracked in digigraph project for now) ────────────────────────

    dict(
        component="digigraph", type="feat", risk="med", priority="high", complexity="XL",
        model="opus", milestone=None,
        labels_extra=["type:infra", "complexity:XL", "priority:high"],
        title="[INFRA] DigiLink module scaffold — capability registry and adapter framework",
        body="""\
## Goal
Scaffold DigiLink as a new top-level DigiThings module. DigiLink is the connection and translation layer: a central capability registry where every DigiThings capability is registered once and exposed via multiple protocol adapters (REST, MCP, CLI, Docker, webhooks).

## From scratch
YES — DigiLink does not exist yet.

## Architecture
```
Capability definition (OpenAPI schema / function signature)
    ↓  DigiLink registry
REST  ·  MCP tool  ·  CLI command  ·  Docker entrypoint  ·  Webhook
```

## Acceptance Criteria
- [ ] `digilink/` top-level Python package with `pyproject.toml`
- [ ] `CapabilityRegistry` — registers capabilities with name, schema, handler
- [ ] REST adapter: FastAPI router auto-generated from registered capabilities
- [ ] Docker entrypoint pattern: each capability callable as a container
- [ ] At least one DigiQuant capability registered and accessible via REST + CLI
- [ ] `docs/vision/digilink.md` updated to reflect implementation state
- [ ] `ARCHITECTURE.md` updated

## Files affected (new)
- `digilink/` (new top-level module)
- `digilink/src/digilink/__init__.py`
- `digilink/src/digilink/registry.py`
- `digilink/src/digilink/adapters/rest.py`

## Dependencies: None — new module, but MCP adapter depends on this
## Parallelizable: NO — foundation for all DigiLink sub-tasks
## Model: opus — novel module architecture
""",
    ),

    dict(
        component="digigraph", type="feat", risk="low", priority="high", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:high"],
        title="[FEATURE] DigiLink — MCP adapter generation from OpenAPI specs",
        body="""\
## Goal
Build the MCP adapter in DigiLink that auto-generates MCP tool definitions from registered capability schemas (OpenAPI). Any DigiThings capability registered in DigiLink becomes callable via Claude Desktop, Cursor, or any MCP client.

## Acceptance Criteria
- [ ] `McpAdapter` reads capability registry and emits MCP tool definitions
- [ ] MCP server serves generated tool list at `/mcp/tools`
- [ ] Tool calls are proxied to the capability handler
- [ ] Integration test: DigiQuant `run_backtest` callable via MCP protocol
- [ ] `docs/vision/digilink.md` updated

## Files affected (new)
- `digilink/src/digilink/adapters/mcp.py`
- `tests/dl/test_mcp_adapter.py`

## Dependencies: DigiLink scaffold (#53)
## Parallelizable: NO — sequential after scaffold
## Model: sonnet
""",
    ),

    dict(
        component="digigraph", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[FEATURE] DigiLink — CLI wrapper auto-generation from REST endpoints",
        body="""\
## Goal
Build the CLI adapter in DigiLink that auto-generates Click/Typer CLI commands from registered capabilities. Every DigiThings capability becomes callable as a terminal command without per-module CLI maintenance.

## Acceptance Criteria
- [ ] `CliAdapter` generates Click commands from capability registry
- [ ] Commands follow `digithings <capability> [args]` structure
- [ ] `--help` works for all generated commands
- [ ] Integration test: `digithings run-backtest --strategy ema_cross --asset BTC ...`
- [ ] `docs/vision/digilink.md` updated

## Files affected (new)
- `digilink/src/digilink/adapters/cli.py`

## Dependencies: DigiLink scaffold (#53)
## Parallelizable: YES — parallel with MCP adapter after scaffold
## Model: sonnet
""",
    ),

    dict(
        component="digigraph", type="feat", risk="low", priority="medium", complexity="M",
        model="sonnet", milestone=None,
        labels_extra=["type:feature", "complexity:M", "priority:medium"],
        title="[FEATURE] DigiLink — desktop AI connector library (Claude Desktop, Cursor, Windsurf)",
        body="""\
## Goal
Build pre-packaged connector configurations for the major desktop AI apps (Claude Desktop, Cursor, Windsurf) that users can drop in to connect to a DigiThings instance with one config file. Built on the MCP adapter (#54).

## Acceptance Criteria
- [ ] `digilink/connectors/claude-desktop-config.json` — ready to paste into Claude Desktop settings
- [ ] `digilink/connectors/cursor-config.json` — Cursor MCP config
- [ ] `digilink/connectors/windsurf-config.json` — Windsurf MCP config
- [ ] `make generate-connectors` command auto-generates all configs with correct DigiThings URL
- [ ] Connector configs documented in `docs/vision/digilink.md`

## Files affected (new)
- `digilink/connectors/` directory
- `digilink/src/digilink/connectors/generator.py`

## Dependencies: DigiLink MCP adapter (#54)
## Parallelizable: YES — after MCP adapter
## Model: sonnet
""",
    ),

    # ── DigiStore (tracked separately, scaffold first) ─────────────────────────

    dict(
        component="digigraph", type="feat", risk="med", priority="high", complexity="L",
        model="sonnet", milestone=None,
        labels_extra=["type:infra", "complexity:L", "priority:high"],
        title="[INFRA] DigiStore standalone module scaffold",
        body="""\
## Goal
Extract DigiStore from DigiGraph and build it as a proper standalone Python module — the unified storage abstraction layer for the entire DigiThings ecosystem. Backends: SQLite (local dev), Postgres/Supabase (production), S3/MinIO (file/blob storage).

## From scratch
YES — DigiStore currently exists only as a thin session/dataset cache inside DigiGraph. This is a new standalone module.

## Acceptance Criteria
- [ ] `digistore/` top-level Python package with `pyproject.toml`
- [ ] `BackendBase` interface: `get`, `put`, `delete`, `list`, `query`
- [ ] `SqliteBackend` — fully functional for local dev, zero config
- [ ] `PostgresBackend` (Supabase) — async, connection pooling
- [ ] `S3Backend` / `MinioBackend` — for file/blob storage
- [ ] Backend selected via `DIGI_STORE_BACKEND` env var
- [ ] DigiGraph's existing Digistore functionality migrated without regression
- [ ] Dockerized local dev stack: SQLite + MinIO + Postgres
- [ ] Unit tests for all backends (SQLite real; Postgres/S3 mocked)
- [ ] `docs/vision/digistore.md` updated

## Files affected (new)
- `digistore/` (new top-level module)
- `digistore/src/digistore/__init__.py`
- `digistore/src/digistore/backends/`
- `digistore/src/digistore/models.py`

## Files affected (modify)
- `digigraph/src/digigraph/digistore.py` → migrate to import from `digistore`

## Dependencies: None — but DigiSearch selective indexing depends on this
## Parallelizable: NO — blocks DigiSearch (#24) and OpenBB integration (#10)
## Model: sonnet
""",
    ),
]


def create_issue(issue: dict, dry_run: bool = False) -> str | None:
    component = issue["component"]
    title = issue["title"]
    body = issue["body"]
    risk = issue["risk"]
    labels_extra = issue.get("labels_extra", [])
    milestone = issue.get("milestone")

    base_labels = f"agent-task,component:{component},risk:{risk}"
    if labels_extra:
        base_labels += "," + ",".join(labels_extra)

    cmd = [
        "gh", "issue", "create",
        "--repo", REPO,
        "--title", title,
        "--label", base_labels,
        "--body", body,
    ]
    if milestone:
        cmd += ["--milestone", milestone]

    if dry_run:
        print(f"  DRY RUN: {title[:70]}")
        print(f"  Labels: {base_labels}")
        return None

    print(f"  Creating: {title[:70]}...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ERROR: {result.stderr.strip()}", file=sys.stderr)
        return None

    url = result.stdout.strip()
    print(f"  → {url}")
    return url


def add_to_project(url: str, component: str, dry_run: bool = False) -> None:
    project_num = PROJECT_MAP.get(component, 1)
    if dry_run:
        print(f"  DRY RUN: add to project #{project_num}")
        return
    result = subprocess.run(
        ["gh", "project", "item-add", str(project_num),
         "--owner", OWNER, "--url", url],
        capture_output=True, text=True
    )
    if result.returncode == 0:
        print(f"  → Project #{project_num}")
    else:
        print(f"  WARN: could not add to project #{project_num}: {result.stderr.strip()[:80]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--module", help="Only create issues for this component")
    parser.add_argument("--dry-run", action="store_true", help="Print without creating")
    args = parser.parse_args()

    issues = ISSUES
    if args.module:
        issues = [i for i in ISSUES if i["component"] == args.module]
        print(f"Filtered to {len(issues)} issues for component: {args.module}")

    print(f"Creating {len(issues)} issues {'(DRY RUN)' if args.dry_run else ''}...")
    tsv_rows = []
    created = []

    for i, issue in enumerate(issues, 1):
        print(f"\n[{i}/{len(issues)}] {issue['component']}")
        url = create_issue(issue, dry_run=args.dry_run)

        if url:
            add_to_project(url, issue["component"], dry_run=args.dry_run)
            issue_num = url.rsplit("/", 1)[-1]
            created.append((issue_num, url, issue["title"]))

            # Map priority label to project field value
            priority_map = {
                "priority:critical": "P0",
                "priority:high": "P1",
                "priority:medium": "P2",
                "priority:low": "P3",
            }
            prio_field = "P2"
            for lbl in issue.get("labels_extra", []):
                if lbl in priority_map:
                    prio_field = priority_map[lbl]
                    break

            kind = "Epic" if "[Epic]" in issue["title"] else "Task"
            area = issue["component"].capitalize() if issue["component"] != "root" else "Cross-cutting"
            model = issue.get("model", "sonnet")
            tsv_rows.append(f"{issue_num}\t\t{area}\t{kind}\t{prio_field}\t{model}")

            # Small delay to avoid rate limiting
            if not args.dry_run:
                time.sleep(0.5)

    print(f"\n\n{'='*60}")
    print(f"Created {len(created)} issues.")

    if tsv_rows:
        print("\nTSV rows for set_project_fields.sh:")
        print("issue\tphase\tarea\tkind\tpriority\tmodel")
        for row in tsv_rows:
            print(row)

    return 0


if __name__ == "__main__":
    sys.exit(main())
