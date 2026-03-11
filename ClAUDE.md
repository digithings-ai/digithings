# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Core Project Context

**Read these first:**
- `DIGI.md` - Master vision, mission, branding, and monetization
- `ARCHITECTURE.md` - System diagrams and interfaces
- `AGENTS.md` - Non-negotiable technical rules (the single source of truth)

**Project type:** DigiThings (digithings.ai) — open-core agentic stack; one use case is the quant workflow (hedge fund in a box), others include RAG and document search.

## Repository Structure

```
digi/
├── digiclaw/          # OpenClaw runtime + gateway + heartbeat + audit
├── digigraph/         # LangGraph orchestration brain + agent families
├── digiquant/         # High-perf Nautilus + Polars + ML pipeline
├── digisearch/        # RAG, document search, MCP tools for agents
├── config/            # LiteLLM, model modes, shared config
├── docker-compose.yml # Multi-service orchestration
├── .env.example       # Environment variable template
└── tests/             # Unit + e2e tests (pytest)
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
| `make package` | Create deployment bundle |
| `pytest -v` | Run all tests from repo root with venv |
| `pytest tests/dq/test_file.py` | Run DigiQuant tests |
| `pytest tests/dg/test_file.py` | Run DigiGraph tests |

**From repo root with venv activated:**
```bash
# Activate venv (via direnv or manually)
source .venv/bin/activate

# Install dev dependencies
pip install -e digiquant[dev]
pip install -e digigraph[dev]

# Run tests
pytest -v --tb=short
pytest tests/test_file.py -k "test_name"
pytest --cov=digiquant --cov-report=html
```

**DigiQuant CLI:**
```bash
# Backtest (requires OHLCV CSV data)
digiquant backtest -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -p trade_size=1

# Optimize (grid/random/bayesian)
digiquant optimize -s bollinger_mr -S BTC-USD -d digiquant/data/BTC-USD.csv -m bayesian -n 100

# Export to target platform
digiquant export -s bollinger_mr -p period=25 -p std_dev=2.5 -o backtest_results/exports
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
| **DigiSearch** | RAG, document search | HTTP + MCP server |

### Data Flow

1. User enters idea in chat → DigiClaw
2. DigiClaw skill calls `run_digigraph_workflow` → DigiGraph
3. DigiGraph supervisor routes to appropriate sub-graph
4. Sub-graph calls DigiQuant MCP tools (run_backtest, run_optimize)
5. Results written to Graphiti memory and returned through stack

### MCP Tool Flow

- DigiGraph exposes nodes as discoverable MCP tools
- DigiQuant exposes backtest/optimize/export as MCP tools
- Agents discover and call tools dynamically at runtime
- Tool schemas are machine-readable for validation

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
| DigiSearch | 8002 | Document search, RAG |
| LiteLLM | 4000 | LLM routing (100+ providers) |
| Ollama | 11435 | Local LLM (Docker port; maps to 11434) |

**Note:** All services bind to `127.0.0.1` only for security. Use Tailscale or Cloudflare Tunnel for remote access.

## Configuration

**Environment variables (see `.env`):**
- `DIGI_LLM_MODE` - Model mode: `test` (default), `medium`, `best`
- `OPENAI_API_KEY` - OpenAI key (optional; use Ollama for free tier)
- `OLLAMA_API_KEY` - Ollama Cloud key (free tier; fastest testing)
- `OLLAMA_MODEL` - Specific model override (e.g., `ollama-cloud/qwen3.5:cloud`)
- `DIGIQUANT_URL` - DigiQuant base URL (default: `http://digiquant:8001`)
- `DIGISEARCH_URL` - DigiSearch base URL (default: `http://digisearch:8002`)
- `DIGIQUANT_DATA_DIR` - OHLCV data directory
- `AUDIT_LOG_PATH` - Audit log file path

**Configuration files:**
- `config/litellm.yaml` - LiteLLM router config (add models here)
- `config/model_modes.yaml` - Mode → model mappings
- `config/MODELS.md` - Model documentation for agents

**Model selection:**
- `test` mode: `ollama-cloud/minimax-m2.5:cloud` (minimal tokens)
- `medium` mode: `ollama-cloud/qwen3.5:cloud` (balanced)
- `best` mode: `ollama-cloud/glm-5:cloud` (largest)

## Sub-folder Documentation

- **digigraph/**: Follow `digigraph/DIGIGRAPH.md` - LangGraph orchestration
- **digiquant/**: Follow `digiquant/DIGIQUANT.md` - High-performance quant pipeline. Nautilus integration: `digiquant/docs/NAUTILUS_NAVIGATION.md`
- **digiclaw/**: Follow `digiclaw/DIGICLAW.md` - Gateway & runtime
- **digisearch/**: Follow `digisearch/DIGISEARCH.md` - RAG & document search
- **config/**: Follow `config/MODELS.md` - Model configuration

## Testing Strategy

- **Unit tests:** `make test-unit` or `pytest -m unit -v`
- **E2E tests:** `make test-e2e` (requires `docker compose up`)
- **Coverage:** `pytest --cov=digiquant --cov-report=html`
- **Test markers:** `unit`, `integration`, `e2e`, `slow`

**Test locations:**
- `tests/dq/` - DigiQuant tests
- `tests/dg/` - DigiGraph tests
- `tests/dc/` - DigiClaw tests
- `tests/test_e2e.py` - End-to-end tests

## Common Development Tasks

**Local development (no Docker):**
```bash
# One-time setup
direnv allow
pip install -e "./digiquant[nautilus]" -e ./digigraph

# Download test data
python digiquant/scripts/fetch_nautilus_test_data.py

# Start services
./scripts/run_local.sh
```

**Run workflow end-to-end:**
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

**Add new LLM model:**
1. Add entry to `config/litellm.yaml` under `model_list`
2. Add model name to appropriate list in `config/model_modes.yaml`
3. Restart stack: `docker compose up -d`

**Run heartbeat agent:**
```bash
# Docker
docker compose --profile heartbeat up -d

# Local
python -m digiclaw
```

## Getting Started

**Quick start:**
```bash
# Copy environment template and configure
cp .env.example .env
# Edit .env with your LLM keys (OpenAI or Ollama Cloud)

# Build and start all services
make up

# Test the workflow
curl -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"test-1"}'
```
