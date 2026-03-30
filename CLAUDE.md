# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**DigiThings** (digithings.ai) is an open-core modular agentic stack for conversational agents that research, search, analyze, and act. Primary use case: quantitative finance ("hedge fund in a box"). Same stack supports RAG, document search, and general agent workflows.

Sub-folder docs are authoritative for each component:
- `digigraph/DIGIGRAPH.md` — orchestration brain
- `digiquant/DIGIQUANT.md` — quant engine
- `digisearch/DIGISEARCH.md` — RAG/search
- `digismith/DIGISMITH.md` — LangSmith-aligned observability (library + status API)
- `digiclaw/DIGICLAW.md` — gateway/heartbeat/audit
- `digibase/DIGIBASE.md` — shared HTTP/audit **library** (`digibase` package) + **DigiBase data-plane** roadmap (Postgres/cache broker)

Read `ARCHITECTURE.md` for system diagrams and `DIGI.md` for vision and strategy.

## Commands

### Docker (primary workflow)
```bash
make build          # docker compose build all services
make up             # docker compose up -d (stack on ports 8000/8001/8002/8003/4000/8005 DigiKey)
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

### Linting & formatting
```bash
ruff check .            # lint (line-length 100, target py312)
ruff format .           # format
```

### Local dev (without Docker)
```bash
scripts/run_local.sh    # Start DigiGraph (18000) + DigiQuant (18001) locally; PYTHONPATH includes digismith/src
make stack-local        # Full local stack (all services, no Docker)
make stack-local-stop   # Stop local stack
python -m digiclaw      # Run heartbeat/audit from repo root
```

### DigiChat (Next.js)
```bash
make digichat-dev       # Start DigiChat dev server
npm run lint            # ESLint (run from digichat/)
npm run test            # Vitest (run from digichat/)
npm run db:migrate      # Run Drizzle migrations
npm run db:seed         # Seed database
npm run db:create-key -- <tenant_slug> <key_name>  # Create machine API key
```

### Other useful targets
```bash
make test-cov-html      # HTML coverage report (output: htmlcov/)
make openapi-digigraph  # Generate OpenAPI schema to docs/openapi/
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
| DigiSmith | 8003 | LangSmith tracing helpers (library); health + `/v1/status` in Docker |
| LiteLLM | 4000 | LLM routing proxy (100+ providers) |
| DigiKey | 8005 | Optional API keys + JWT exchange (`digikey/DIGIKEY.md`) |
| DigiClaw | — | Heartbeat, audit, gateway (Docker profile: `heartbeat`) |

### Data flow
`User → DigiGraph (workflow) → Research node (LLM + RAG via DigiSearch) → Backtest node (DigiQuant) → WorkflowResult`

### Key patterns
- **Orchestration**: LangGraph supervisor + sub-graphs (`digigraph/src/digigraph/graph/`, `agents/`)
- **Tool discovery**: MCP registry pattern (`digigraph/orchestration/registry.py`) — every capability must be an MCP tool. Two kinds: builtins (`digigraph/orchestration/builtin.py`) and verticals that expose `POST /v1/orchestrator_tools`
- **LLM routing**: LiteLLM via `config/litellm.yaml` (Compose: `docker.litellm.ai/berriai/litellm:main-stable`); DigiGraph Bearer from `LITELLM_PROXY_API_KEY` or `OPENAI_API_KEY`; model mode from `DIGI_LLM_MODE` (`test`/`medium`/`best`)
- **Checkpointing**: LangGraph checkpoint backend set via `DIGI_CHECKPOINTER` env (`memory` | `sqlite` | `postgres`)
- **Structured outputs**: Pydantic v2 models everywhere (no dicts)
- **Audit**: Immutable JSONL event log (`digiclaw/audit.py`, `digiquant/audit.py`)
- **DigiSearch naming**: Drop redundant `Digi` prefix for entity names (e.g., `Document` not `DigiDocument`)
- **DigiSmith tracing**: Span attributes must include `workflow_id`, `request_id`, `session_id`. Never include raw prompts, API keys, or full doc bodies in spans. `GET /v1/status` is public — keep it secret-free.

### Website (`website/`)
Static vanilla HTML/CSS/JS landing page — no framework. Canvas starfield animation in `main.js`. Deployed to GitHub Pages at digithings.ai.

### DigiChat (`digichat/`)
**Production** Next.js + React chat + BFF for DigiGraph (Auth.js OIDC, machine API keys, optional Postgres). Docker Compose profile `digichat`. See **`DIGICHAT.md`**. Legacy static demo: `website/digichat/` — refresh published assets with **`make website-digichat-build`** (Vite output in `dist/`, synced by `npm run build:site`; GitHub Actions runs the same before Pages deploy).

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

- Read the component's own `DIGIxxx.md` first (including `digismith/DIGISMITH.md` for observability)
- For Nautilus strategies/backtest changes: read `digiquant/docs/NAUTILUS_NAVIGATION.md`
- Update the relevant `DIGIxxx.md` section after any change
- Commit early and often with clear messages
- `projects/` is confidential — never push to public remotes
