# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Project Context

**Read these first:**
- `DIGI.md` - Master vision, mission, branding, and monetization
- `ARCHITECTURE.md` - System diagrams and interfaces
- `ROADMAP.md` - Current phase and delivery plan
- `AGENTS.md` - Non-negotiable technical rules (the single source of truth)

**Project type:** Agentic "hedge-fund-in-a-box" for solo quants and small firms.

**Current phase:** Phase 0 (foundation) → Phase 1 (DigiGraph core with LangGraph) in progress.

## Repository Structure

```
digi/
├── digiclaw/          # OpenClaw runtime + gateway + chat + cron
├── digigraph/         # LangGraph orchestration brain + agent families
├── digiquant/         # High-perf Nautilus + Polars + ML pipeline
├── config/            # Shared config (LiteLLM, etc.)
├── docker-compose.yml # Multi-service orchestration
└── .env.example       # Environment variable template
```

## Non-Negotiable Technical Rules

- **Data layer:** Polars only — NEVER use pandas
- **Quant engine:** NautilusTrader (Rust core) for backtesting, optimization, live execution
- **Orchestration:** LangGraph with layered supervisor + sub-graph pattern
- **LLM routing:** LiteLLM (100+ providers, full feature passthrough, caching mandatory)
- **Memory:** Graphiti (temporal bi-model) + Neo4j/PGVector + LangGraph checkpoints
- **Outputs:** Always structured Pydantic models
- **Security:** Follow `SECURITY.md` (loopback-only, least privilege, human gates for live trades)
- **Performance:** Backtests < 2s for 10M rows; token reduction ≥ 70% vs naive prompts
- **Interoperability:** Every capability exposed as discoverable MCP tool

## Commands

| Command | Description |
|---------|-------------|
| `make build` | Build Docker images |
| `make up` | Start services (`docker compose up -d`) |
| `make down` | Stop services (`docker compose down`) |
| `make test` | Run all tests (unit + e2e if stack up) |
| `make test-unit` | Unit tests only (`pytest -m unit -v`) |
| `make test-e2e` | E2E tests (`pytest -v -m e2e`) |
| `make test-cov` | Unit tests with coverage (digigraph + digiquant) |
| `make test-cov-html` | Coverage with HTML report in `htmlcov/` |
| `pytest -v` | Run all tests from repo root with venv |
| `pytest tests/test_file.py` | Run specific test file |

**From repo root with venv activated:**
```bash
# Activate venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dev dependencies
pip install -e digiquant[dev]
pip install -e digigraph[dev]

# Run tests
pytest -v --tb=short
pytest tests/test_file.py -k "test_name"
pytest --cov=digiquant --cov-report=html
```

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    User / Chat                                  │
│              (Slack, Discord, Telegram)                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DigiClaw                                     │
│  OpenClaw runtime + Gateway + Heartbeat + Skill contract        │
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP/HTTP (run_digigraph_workflow)
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DigiGraph                                    │
│  LangGraph + Supervisor + Sub-graphs + GraphRAG + LiteLLM       │
│  - Research Supervisor                                          │
│  - Data Science Family                                          │
│  - Strategy Generator                                           │
│  - Execution Monitor                                            │
└────────────────────────────┬────────────────────────────────────┘
                             │ MCP tools
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    DigiQuant                                    │
│  NautilusTrader + Polars + VectorBT Pro + Qlib/FinRL           │
│  - run_backtest (MCP)                                           │
│  - run_optimize (MCP)                                           │
│  - run_validation (MCP)                                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    External Data & Brokers                      │
│  Polygon • IB • Alpaca • QuantConnect • TradingView            │
└─────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Primary Role | Key Technologies |
|-----------|--------------|------------------|
| **DigiClaw** | User gateway, runtime, monitoring | OpenClaw, Node.js, WebSocket |
| **DigiGraph** | Cognitive orchestration & memory | LangGraph, LiteLLM, Neo4j, Graphiti |
| **DigiQuant** | Research → backtest → live | NautilusTrader, Polars, VectorBT Pro |

### Data Flow

1. User enters idea in chat → DigiClaw
2. DigiClaw skill calls `run_digigraph_workflow` → DigiGraph
3. DigiGraph supervisor routes to appropriate sub-graph
4. Sub-graph calls DigiQuant MCP tools (run_backtest, run_optimize)
5. Results written to Graphiti memory and returned through stack

## Key Interfaces

- **DigiClaw → DigiGraph:** `POST /workflow` with `{"prompt", "session_id"}`; returns `WorkflowResult`
- **DigiGraph → DigiQuant:** MCP tools: `run_backtest`, `run_optimize`, `run_validation`
- **All data exchange:** Polars DataFrames (Arrow zero-copy)
- **All LLM outputs:** Structured Pydantic models

## Service Endpoints

| Service | Port | Purpose |
|---------|------|---------|
| DigiGraph | 8000 | LangGraph orchestration, HTTP API |
| DigiQuant | 8001 | Backtest/optimize, MCP tools |
| LiteLLM | 4000 | LLM routing (100+ providers) |
| Ollama | 11434 | Local LLM (optional, for testing) |

## Configuration

**Environment variables (see `.env.example`):**
- `OPENAI_API_KEY` - OpenAI key (or set `OLLAMA_MODEL` for local LLM)
- `OLLAMA_MODEL` - Local model (e.g., `ollama/qwen3:8b`)
- `DIGIQUANT_URL` - DigiQuant base URL (default: `http://digiquant:8001`)
- `LITELLM_CONFIG` - LiteLLM config path

**Configuration files:**
- `config/litellm.yaml` - LiteLLM router config
- `.env` - Runtime secrets (copy from `.env.example`)

## Sub-folder Documentation

- **digigraph/**: Follow `digigraph/DIGIGRAPH.md` - LangGraph orchestration
- **digiquant/**: Follow `digiquant/DIGIQUANT.md` - High-performance quant pipeline
- **digiclaw/**: Follow `digiclaw/DIGICLAW.md` - Gateway & runtime

## Testing Strategy

- **Unit tests:** `make test-unit` or `pytest -m unit -v`
- **E2E tests:** `make test-e2e` (requires `docker compose up`)
- **Coverage:** `pytest --cov=digiquant --cov-report=html`

## Common Development Tasks

**Run backtest directly (from digiquant/):**
```bash
cd digiquant
python -c "from digiquant.tools import run_backtest; print(run_backtest(...))"
```

**Run workflow end-to-end (from repo root):**
```bash
# Services must be running: make up
curl -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"test-1"}'
```

**Add new MCP tool:**
1. Implement tool handler in relevant module
2. Register with `@mcp.tool()` decorator or `register_tool()`
3. Update `DIGIxxx.md` to document the new capability

## Phase 0 Status (Completed)

- [x] Root repo structure with `docker-compose.yml`
- [x] LiteLLM config skeleton
- [x] DigiQuant HTTP server with `run_backtest`
- [x] DigiGraph HTTP server with `POST /workflow`
- [x] DigiClaw skill contract documented
- [x] Phase 0 tests passing

## Phase 1 In Progress

- [ ] Full LangGraph orchestration with layered agent families
- [ ] LiteLLM router wired into DigiGraph
- [ ] MCP exposure for research, backtest, optimize nodes
- [ ] DigiClaw custom skill integration
- [ ] Graphiti/GraphRAG stub or design

**Next action:** Wire LiteLLM into stack; expose DigiGraph nodes as MCP tools.
