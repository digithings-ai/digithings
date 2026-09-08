---
type: quickstart
title: digigraph Quickstart
description: Run digigraph locally, call the workflow and chat endpoints, and run the unit suite.
tags: [digigraph, quickstart]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-deb1497ccdcada935084b098
    resource: repo://digigraph/AGENTS.md
  - id: openwiki-source-480f9d807ff1b9a39c50e94a
    resource: repo://digigraph/src/digigraph/mcp_server.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digigraph Quickstart

digigraph (port 8000) is the orchestration hub. A working setup pairs it
with reachable verticals (digisearch, digiquant) and an LLM upstream
(LiteLLM on 4000 or any OpenAI-compatible base).

## 1. Start

```bash
make stack-local     # host backends incl. digigraph on :8000
# or: make up        # full Docker Compose stack
```

LLM calls need a provider key in `.env` (e.g. `GROQ_API_KEY`); JWT
exchange for protected routes goes through digikey on :8005.

## 2. Verify

```bash
curl -s http://localhost:8000/healthz
curl -s -X POST http://localhost:8000/workflow \
  -H 'Content-Type: application/json' \
  -d '{"prompt": "hello"}'
```

With `DIGI_ENABLE_DEBUG_ENDPOINTS=1`, `GET /test_llm` smoke-tests the LLM
path. The MCP server runs separately: `python -m digigraph.mcp_server`
(streamable-http :8766) or `--stdio` for Claude Desktop.

## 3. Gates

```bash
pytest tests/ -m unit -k "digigraph" -v
ruff check digigraph/ && ruff format --check digigraph/
```

## Where next

- [digigraph Architecture](/openwiki/digigraph/architecture.md) — hub
  roles, graph, registry, boundaries.
- [digigraph Workflow and Tools](/openwiki/digigraph/workflow-and-tools.md) —
  nodes, allowlist, digistore, compaction.
- [digigraph API and Operations](/openwiki/digigraph/api-and-operations.md) —
  endpoints, auth, MCP, policy flags.
