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
- **Checkpointer env**: Set `DIGI_CHECKPOINTER=memory|sqlite|postgres` explicitly in prod; `memory` does not survive restarts.
- **MCP auth**: Bind MCP to loopback; set `DIGI_MCP_REQUIRE_AUTH=1` when exposing beyond localhost. The `workflow` tool refuses unauthenticated calls when auth is required.
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

## SITAAS / Project-Mode Capabilities

When a `digiproject.yaml` (or `config.yaml`) sets `run_data_dir`, DigiGraph operates in **project mode**. The `sitaas_rag` skill is activated, exposing additional tools beyond the base `search` skill.

### Full tool set (sitaas_rag skill)

| Tool | Skill | Condition | Description |
|---|---|---|---|
| `digisearch` | search | `DIGISEARCH_URL` set | Semantic/keyword search over indexed documents |
| `digisearch_fetch_all` | search | `DIGISEARCH_URL` set | Paginated full-result fetch with filters |
| `digistore_list` | sitaas_rag | `run_data_dir` set | List named datasets from current session |
| `digistore_profile` | sitaas_rag | `run_data_dir` set | Inspect schema, row count, and sample rows of a dataset |
| `visualization_agent` | sitaas_rag | `run_data_dir` set | Generate charts (ECharts JSON or PNG) from a dataset_ref |
| `analysis_agent` | sitaas_rag | `run_data_dir` set | Statistical summaries, correlations, histograms |
| `data_prep_agent` | sitaas_rag | `run_data_dir` set | Filter, sample, sort, export a dataset |
| `data_manipulation_agent` | sitaas_rag | `run_data_dir` set | Merge, join, reshape, or transform datasets |
| `data_engineer_agent` | sitaas_rag | `run_data_dir` set + `DIGI_ALLOW_CODE_EXEC=1` | Execute sandboxed Polars code for custom transformations |

### Multi-turn dataset context

When `stored_datasets` is in graph state, the research node prepends a `[Current session datasets: ...]` context block to the user message so the LLM can reference previous search results by `dataset_ref` (e.g. "chart search_1"). The state is persisted across turns when `DIGI_CHECKPOINTER` is set (default `memory`; use `sqlite` or `postgres` for cross-restart persistence).

### ECharts rendering

`visualization_agent` returns ECharts option JSON when the request includes `X-Response-Format: openwebui` or uses the `sitaas-rag` model endpoint. Without this header, it falls back to a PNG path. The frontend must handle the `echarts_option` key in the tool result to render the chart.

---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
