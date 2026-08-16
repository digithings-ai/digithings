---
title: "digigraph — API reference"
type: reference
status: generated
created: 2026-08-10
tags:
  - api
  - core
relevance:
  - digigraph
---
# digigraph — API reference

> A declarative graph decides what runs next — profile in, path out.

**Role:** Orchestration · LangGraph state machine · **Tier:** core

## Overview
A LangGraph state machine routes each request to the right sub-graph — quant research, retrieval, or chat — through conditional edges keyed on the request profile and the run's state. DIGI_SUPERVISOR=1 adds an entry node that stamps the run and enforces a recursion budget; it does not pick the branch, and unset, requests enter the research graph directly.

Speaks the OpenAI API so existing clients work unchanged; LiteLLM handles routing, caching, and checkpointed state across hops.

## Authentication
Endpoints accept a digikey-issued RS256 JWT in `Authorization: Bearer`. When no JWKS is configured the service runs in passthrough mode (dev/test only). `/healthz` and `/v1/status` are auth-exempt.

- `digigraph:workflow` — POST /workflow + debug routes (default fallback)
- `digigraph:chat` — /v1/chat/completions, /v1/models, /v1/model-info
- `digigraph:mcp` — /threads/*, /files/* (when enabled)

## Run locally
```bash
docker compose up -d digigraph
```

```bash
uvicorn digigraph.server:app
```

MCP: `FastMCP streamable-http (workflow, chat, thread_state, list_orchestrator_tools)`

## Configuration
- `DIGIQUANT_URL`: digiquant base URL (defaults to the compose service URL).
- `DIGISEARCH_URL`: digisearch base URL; empty disables retrieval.
- `DIGIKEY_JWKS_URL`: JWT public-key (JWKS) endpoint.
- `OPENAI_API_BASE`: LiteLLM proxy base URL.
- `DIGI_LLM_MODE` (default `test`): Model tier: test / medium / best.
- `DIGI_CHECKPOINTER` (default `memory`): LangGraph state backend: memory / sqlite / postgres / none.
- `DIGI_ENABLE_THREAD_API` (default `0`): Gate /threads/* and /files/*.
- `DIGI_ENABLE_DEBUG_ENDPOINTS` (default `0`): Gate /test_llm and /v1/debug/*.

## Endpoints

Base URL: `$DIGIGRAPH_URL` (the service URL from docker-compose.yml).

### GET /healthz
Liveness probe. Auth-exempt; always 200.

auth: none

Response example:
```json
{ "ok": true }
```

```bash
curl $DIGIGRAPH_URL/healthz
```

### GET /v1/status
Public, secret-free project status.

auth: none · rate: 30/min/IP

Response example:
```json
{
  "service": "digigraph",
  "project_name": "demo",
  "agents_enabled": true,
  "llm_mode": "test",
  "mcp_enabled": true,
  "workflow_profile": "default"
}
```

```bash
curl $DIGIGRAPH_URL/v1/status
```

### POST /workflow
Run the full research + backtest graph (digiclaw custom skill).

auth: digigraph:workflow (optional) · rate: 10/min/IP

Request:
- `prompt` (string) — required: The user request to route through the supervisor.
- `session_id` (string): Conversation/session correlation id.
- `allowed_tools` (string[]): Tool allowlist override for this run.
- `digi_bearer` (string): JWT forwarded downstream to digisearch/digiquant.

Response:
- `success` (boolean): Whether the workflow completed.
- `message` (string): Human-readable summary or full RAG answer.
- `backtest_result` (object | null): digiquant BacktestResult, if a backtest ran.
- `rag_sources` (object[] | null): Aggregated digisearch citations.

```bash
curl -X POST $DIGIGRAPH_URL/workflow \
  -H "Authorization: Bearer $JWT" -H "content-type: application/json" \
  -d '{"prompt": "Backtest a momentum strategy on AAPL"}'
```

```python
import os, httpx

r = httpx.post(
    f"{os.environ['DIGIGRAPH_URL']}/workflow",
    headers={"Authorization": f"Bearer {os.environ['DIGI_JWT']}"},
    json={"prompt": "Backtest a momentum strategy on AAPL"},
    timeout=120,
)
print(r.json()["message"])
```

```typescript
const r = await fetch(`${process.env.DIGIGRAPH_URL}/workflow`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${process.env.DIGI_JWT}`,
    "content-type": "application/json",
  },
  body: JSON.stringify({ prompt: "Backtest a momentum strategy on AAPL" }),
});
const { message } = await r.json();
```

### POST /v1/chat/completions
OpenAI-compatible chat. Set stream:true for SSE (events: tool_call, content, done).

auth: digigraph:chat (optional) · rate: 10/min/IP

Request:
- `model` (string): Model id; default "digigraph-rag".
- `messages` ({role,content}[]) — required: Chat messages.
- `stream` (boolean): Stream tokens as SSE.

```bash
curl -X POST $DIGIGRAPH_URL/v1/chat/completions \
  -H "Authorization: Bearer $JWT" -H "content-type: application/json" \
  -d '{"model":"digigraph-rag","messages":[{"role":"user","content":"hi"}]}'
```

```python
import os
from openai import OpenAI
client = OpenAI(base_url=os.environ["DIGIGRAPH_URL"] + "/v1", api_key=os.environ["DIGI_JWT"])
resp = client.chat.completions.create(
    model="digigraph-rag",
    messages=[{"role": "user", "content": "hi"}],
)
```

### GET /v1/models
OpenAI-style model list.

auth: digigraph:chat (optional) · rate: 30/min/IP

```bash
curl $DIGIGRAPH_URL/v1/models -H "Authorization: Bearer $JWT"
```

## MCP tools
- `workflow(prompt, thread_id?)` — Run the full research + backtest graph; returns a JSON WorkflowResult.
- `chat(message, thread_id?, model?)` — Single-turn chat via /v1/chat/completions.
- `thread_state(thread_id)` — Return the LangGraph checkpoint state for a thread.
- `list_orchestrator_tools()` — List registered orchestrator tool names.
- `list_orchestrator_tools_detailed()` — Tool manifest: name, tags, dynamic_schema flag.

## Stack
LangGraph, FastAPI, LiteLLM, Pydantic, Polars, OpenAI SDK

## Related
digiquant, digisearch, digichat

## Links
- [Source](https://github.com/digithings-ai)

See also [[digigraph]].
