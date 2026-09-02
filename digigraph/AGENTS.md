# Agent Guide: digigraph

## Purpose

digigraph is the **orchestration hub** of digithings. It runs a LangGraph state machine that accepts user prompts, delegates research to digisearch and backtesting to digiquant via HTTP, and returns structured results through an OpenAI-compatible streaming API. It owns no domain logic — it coordinates verticals.

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
- [ ] Confirm any new FastAPI route is covered by `DigiAuthMiddleware` path scopes (`digikey.integrations.service_middleware.digigraph_path_scopes`)

---

## Non-Negotiable Rules

Beyond root `AGENTS.md`:

- **MCP-first**: Every new capability must be a discoverable tool registered in the orchestration registry. Never add logic directly to a LangGraph node.
- **No tight coupling**: digigraph must never import digisearch or digiquant Python packages. All vertical calls go through `POST /v1/orchestrator_invoke`.
- **State stays lean**: `WorkflowState` carries only refs and summaries. No full document bodies, no large DataFrames in state or LangGraph checkpoints. Use digistore (`digistore.py`) for large data.
- **Tool allowlist respected**: New tools must work correctly when `ToolContext.allowed_tool_names` is set to a subset. Never bypass the allowlist check.
- **LLM routing via digillm**: All LLM calls go through `digigraph.llm_client` (`completion` / `completion_text` / `run_tools`), which wraps the `digillm` toolkit client. No direct OpenAI SDK `chat.completions.create()` calls.
- **Context compaction (#399)**: Long research transcripts use two-tier compaction in `digigraph.compaction` (tier-1 tool-result truncation + tier-2 tagged summarisation). Config: `CompactionConfig` / `DIGI_COMPACTION_*` env vars (see ARCHITECTURE §8.3.1). Store lean `_compaction_event` on `WorkflowState`; originals live in the session workspace. Do not invent a parallel graph node for compaction.
- **Never MemorySaver in production**: Default is fine for dev, but document `DIGI_CHECKPOINTER=postgres` for production.
- **Checkpointer env**: Set `DIGI_CHECKPOINTER=memory|sqlite|postgres` explicitly in prod; `memory` does not survive restarts.
- **MCP auth**: Bind MCP to loopback; set `DIGI_MCP_REQUIRE_AUTH=1` when exposing beyond localhost. The `workflow` tool refuses unauthenticated calls when auth is required.
- **No PII in spans**: digismith spans must not carry raw prompts, full document bodies, or bearer tokens. See `digismith/ARCHITECTURE.md` Section 4.

---

## Test Commands

```bash
# Unit tests (no stack required)
pytest tests/ -m unit -k "digigraph" -v

# Single test file
pytest tests/digigraph/test_graph.py -v

# Context compaction (#399)
pytest -m unit -k compaction -v

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

## Project-Mode Capabilities

When a `digiproject.yaml` (or `config.yaml`) sets `run_data_dir`, digigraph operates in **project mode**. The `project_rag` skill is activated, exposing additional tools beyond the base `search` skill.

### Full tool set (project_rag skill)

| Tool | Skill | Condition | Description |
|---|---|---|---|
| `digisearch` | search | `DIGISEARCH_URL` set | Semantic/keyword search over indexed documents |
| `digisearch_fetch_all` | search | `DIGISEARCH_URL` set | Paginated full-result fetch with filters |
| `digistore_list` | project_rag | `run_data_dir` set | List named datasets from current session |
| `digistore_profile` | project_rag | `run_data_dir` set | Inspect schema, row count, and sample rows of a dataset |
| `visualization_agent` | project_rag | `run_data_dir` set | Generate charts (ECharts JSON or PNG) from a dataset_ref |
| `analysis_agent` | project_rag | `run_data_dir` set | Statistical summaries, correlations, histograms |
| `data_prep_agent` | project_rag | `run_data_dir` set | Filter, sample, sort, export a dataset |
| `data_manipulation_agent` | project_rag | `run_data_dir` set | Merge, join, reshape, or transform datasets |
| `data_engineer_agent` | project_rag | `run_data_dir` set + `DIGI_ALLOW_CODE_EXEC=1` | Execute sandboxed Polars code for custom transformations |

### Multi-turn dataset context

When `stored_datasets` is in graph state, the research node prepends a `[Current session datasets: ...]` context block to the user message so the LLM can reference previous search results by `dataset_ref` (e.g. "chart search_1"). The state is persisted across turns when `DIGI_CHECKPOINTER` is set (default `memory`; use `sqlite` or `postgres` for cross-restart persistence).

### ECharts rendering

`visualization_agent` prefers ECharts tools (`echarts_*`) that return `echarts_option` JSON (optional SVG via Node SSR). Matplotlib-style `plot_*` tools return `image_path`. Stream `<details>` / table chrome for those results requires explicit Open WebUI opt-in (`X-Response-Format: openwebui` or `openwebui_format=true`) — not `model=digigraph-rag` alone. Frontends that consume tool results directly should handle the `echarts_option` key.

---

## More

Extension patterns, anti-patterns, and integration boundaries live in [`ARCHITECTURE.md`](ARCHITECTURE.md). Update that doc when changing interfaces or behavior.
