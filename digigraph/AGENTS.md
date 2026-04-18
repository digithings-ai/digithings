# Agent Guide: DigiGraph

## Purpose

DigiGraph is the **orchestration hub** of DigiThings. It runs a LangGraph state machine that accepts user prompts, delegates research to DigiSearch and backtesting to DigiQuant via HTTP, and returns structured results through an OpenAI-compatible streaming API. It owns no domain logic — it coordinates verticals.

---

## Read First

In this order, before writing any code:

1. [`ARCHITECTURE.md`](ARCHITECTURE.md) — module map, data flow, all API endpoints, data models, configuration reference, integration points
2. [`../AGENTS.md`](../AGENTS.md) — non-negotiable stack-wide rules (Polars, Pydantic v2, LiteLLM, LangGraph)
3. [`../ROADMAP.md`](../ROADMAP.md) — what phase we are in; do not build Phase 2 features in a Phase 2+ PR
4. [`docs/SECURITY.md`](docs/SECURITY.md) — auth gates, code execution policy, thread API scope
5. [`../docs/agent-backlog/INDEX.md`](../docs/agent-backlog/INDEX.md) — current task queue

---

## Pre-Flight Checklist

Before making any change to `digigraph/`:

- [ ] Read the `ARCHITECTURE.md` section for the area you're touching (graph, orchestration, llm, tools, server)
- [ ] Run `pytest tests/ -m unit -k "digigraph" -v` — all tests must pass before and after
- [ ] Run `ruff check digigraph/ && ruff format --check digigraph/` — zero errors
- [ ] Confirm no new import of `digisearch` or `digiquant` Python modules (call via HTTP only)
- [ ] Confirm no hardcoded model name strings (use `get_model_for_mode()`)
- [ ] Confirm any new FastAPI route has `Depends(require_scope(...))` middleware

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **MCP-first**: Every new capability must be a discoverable tool registered in the orchestration registry. Never add logic directly to a LangGraph node.
- **No tight coupling**: DigiGraph must never import DigiSearch or DigiQuant Python packages. All vertical calls go through `POST /v1/orchestrator_invoke`.
- **State stays lean**: `WorkflowState` carries only refs and summaries. No full document bodies, no large DataFrames in state or LangGraph checkpoints. Use Digistore (`digistore.py`) for large data.
- **Tool allowlist respected**: New tools must work correctly when `ToolContext.allowed_tool_names` is set to a subset. Never bypass the allowlist check.
- **LLM routing via llm.py**: All LLM calls go through `get_client()` / `chat_completion()`. No direct `openai.chat.completions.create()` calls.
- **Never MemorySaver in production**: Default is fine for dev, but document `DIGI_CHECKPOINTER=postgres` for production.
- **No PII in spans**: DigiSmith spans must not carry raw prompts, full document bodies, or bearer tokens. See `digismith/ARCHITECTURE.md` Section 4.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digigraph" -v

# Single test file
pytest tests/digigraph/test_graph.py -v

# Full unit suite
make test-unit

# Lint
ruff check digigraph/ && ruff format --check digigraph/

# Stack smoke test (requires make up)
curl -s http://localhost:8000/health

# LLM smoke test (requires DIGI_ENABLE_DEBUG_ENDPOINTS=1)
curl http://localhost:8000/test_llm
```

---


---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
