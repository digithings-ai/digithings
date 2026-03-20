# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DigiThings** (digithings.ai) is an open-core modular agentic stack for conversational agents that research, search, analyze, and act. Primary use case: quantitative finance ("hedge fund in a box"). Same stack supports RAG, document search, and general agent workflows.

Sub-folder docs are authoritative for each component:
- `digigraph/DIGIGRAPH.md` — orchestration brain
- `digiquant/DIGIQUANT.md` — quant engine
- `digisearch/DIGISEARCH.md` — RAG/search
- `digiclaw/DIGICLAW.md` — gateway/heartbeat/audit

Read `ARCHITECTURE.md` for system diagrams and `DIGI.md` for vision and strategy.

## Commands

### Docker (primary workflow)
```bash
make build          # docker compose build all services
make up             # docker compose up -d (stack on ports 8000/8001/8002/4000)
make down           # docker compose down
make up-heartbeat   # start with monitoring profile
```

### Tests
```bash
make test           # all tests (unit + e2e if stack is up)
make test-unit      # pytest -m unit (no stack required)
make test-e2e       # pytest -m e2e (requires stack running)
make test-cov       # coverage report

# Single test
pytest tests/path/to/test_file.py::test_name -v
pytest -m unit -k "keyword" -v
```

### Local dev (without Docker)
```bash
scripts/run_local.sh    # Start DigiGraph (18000) + DigiQuant (18001) locally
python -m digiclaw      # Run heartbeat/audit from repo root
```

### DigiQuant CLI
```bash
digiquant backtest -s <strategy> -S <symbol> -d <data.csv> -p param=value
digiquant optimize -s <strategy> -m bayesian -n 100
digiquant export -s <strategy> -o output/
```

## Architecture

### Services
| Service | Port | Purpose |
|---------|------|---------|
| DigiGraph | 8000 | LangGraph orchestration, agent workflows, OpenAI-compatible API |
| DigiQuant | 8001 | NautilusTrader backtest/optimize, strategy registry |
| DigiSearch | 8002 | RAG, document ingestion, vector search |
| LiteLLM | 4000 | LLM routing proxy (100+ providers) |
| DigiClaw | — | Heartbeat, audit, gateway (Docker profile: `heartbeat`) |

### Data flow
`User → DigiGraph (workflow) → Research node (LLM + RAG via DigiSearch) → Backtest node (DigiQuant) → WorkflowResult`

### Key patterns
- **Orchestration**: LangGraph supervisor + sub-graphs (`digigraph/src/digigraph/graph/`, `agents/`)
- **Tool discovery**: MCP registry pattern (`digigraph/orchestration/registry.py`) — every capability must be an MCP tool
- **LLM routing**: LiteLLM via `config/litellm.yaml`; model mode selected by `DIGI_LLM_MODE` env var (`test`/`medium`/`best`)
- **Structured outputs**: Pydantic v2 models everywhere (no dicts)
- **Audit**: Immutable JSONL event log (`digiclaw/audit.py`, `digiquant/audit.py`)

### Website (`website/`)
Static vanilla HTML/CSS/JS landing page — no framework. Canvas starfield animation in `main.js`. Deployed to GitHub Pages at digithings.ai.

## Non-Negotiable Rules

- **Data layer**: Polars only — never use pandas
- **Quant engine**: NautilusTrader for all backtesting and optimization
- **Orchestration**: LangGraph with layered supervisor + sub-graph pattern only
- **LLM routing**: LiteLLM (caching mandatory)
- **Outputs**: Always structured Pydantic v2 models
- **Security**: Loopback-only, least privilege, human gates before any live trade
- **Performance targets**: Backtests < 2s for 10M rows; token reduction ≥ 70% vs naive prompts
- **Python**: 3.12+, strict typing, black/ruff compliant
- **Never** touch live-trading code without explicit human approval

## Before Modifying a Component

- Read the component's own `DIGIxxx.md` first
- For Nautilus strategies/backtest changes: read `digiquant/docs/NAUTILUS_NAVIGATION.md`
- Update the relevant `DIGIxxx.md` section after any change
- Commit early and often with clear messages
