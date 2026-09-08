---
type: quickstart
title: digithings Quickstart
description: Task-routing map for the digithings wiki — which section answers which question — plus the digismith tracing quickstart.
tags: [digithings, quickstart, routing]
verified:
  - by: openwiki/0.5.0
    at: 2026-09-07T22:38:58.074Z
sources:
  - id: openwiki-source-4b2266e051b2270b6ec5aa4f
    resource: repo://BRANCHING.md
  - id: openwiki-source-72050835d3541ab62444987d
    resource: repo://digiclaw/AGENTS.md
  - id: openwiki-source-deb1497ccdcada935084b098
    resource: repo://digigraph/AGENTS.md
  - id: openwiki-source-5a73d428d9c326b6be1e4770
    resource: repo://digikey/AGENTS.md
  - id: openwiki-source-3cca7b16d985d38458390d9a
    resource: repo://digiquant/AGENTS.md
  - id: openwiki-source-d16d9586117b95e03b7f1549
    resource: repo://digisearch/AGENTS.md
  - id: openwiki-source-9a612bb5c480c0f9c10eeafd
    resource: repo://digismith/AGENTS.md
  - id: openwiki-source-5c7b6be6bf0bcff60bbd689d
    resource: repo://digismith/Dockerfile
  - id: openwiki-source-e502a2c67cf187dc015ba472
    resource: repo://digismith/src/digismith/config.py
  - id: openwiki-source-01a7f90e3c3e6e8ce426b71e
    resource: repo://digismith/src/digismith/server.py
  - id: openwiki-source-c00fdd1354f900a1d45b111a
    resource: repo://digismith/src/digismith/trace.py
  - id: openwiki-source-a18bc9b1229d0282f121b666
    resource: repo://digivault/AGENTS.md
  - id: openwiki-source-a49bd70bd0f6d776441b838b
    resource: repo://docs/agents/CODE_REVIEW_POLICY.md
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
---

# digithings Quickstart

Route yourself to the right section, then run that component's own
quickstart. Every component quickstart follows the same shape — start the
service, verify with health/status curls, run the unit gates — per its
`AGENTS.md`.

## Where do I go for…

| Question | Start here |
|----------|------------|
| Run the hub, call a workflow, stream chat | [digigraph Quickstart](/openwiki/digigraph/quickstart.md) |
| Backtest / optimize a strategy | [digiquant Quickstart](/openwiki/digiquant/quickstart.md) |
| Ingest docs, run RAG queries | [digisearch Quickstart](/openwiki/digisearch/quickstart.md) |
| Add LangSmith tracing, check trace status | [digismith quickstart](#digismith-tracing) (below) |
| Work with the markdown vault | [digivault Quickstart](/openwiki/digivault/quickstart.md) |
| Issue keys, exchange JWTs | [digikey Quickstart](/openwiki/digikey/quickstart.md) |
| Run the chat UI | [digichat Quickstart](/openwiki/digichat/quickstart.md) |
| Heartbeat, audit log, schedules | [digiclaw Quickstart](/openwiki/digiclaw/quickstart.md) |
| Shared helpers (errors, metrics, OTel, audit) | [digibase Library Guide](/openwiki/digibase/library-guide.md) |
| LLM client, fetch engine, skill compiler | [digillm](/openwiki/libraries/digillm.md), [digifetch](/openwiki/libraries/digifetch.md), [digiskills](/openwiki/libraries/digiskills.md) |
| Operator views (research, portfolio, tearsheet) | [Dashboard Architecture](/openwiki/dashboard/architecture.md) |
| Branches, make targets, review/merge rules | [Repo Workflow](/openwiki/repo/workflow.md) |

## Stack-wide verify

```bash
make stack-local     # host backends (8000–8003, 8005) or: make up
curl -s http://localhost:8000/healthz   # digigraph
curl -s http://localhost:8001/healthz   # digiquant
curl -s http://localhost:8002/health    # digisearch
curl -s http://localhost:8003/healthz   # digismith
curl -s http://localhost:8005/healthz   # digikey
pytest tests/ -m unit -k "digigraph or digiquant or digisearch or digismith or digikey" -v
```

## digismith tracing

digismith gives you optional LangSmith tracing through one decorator, plus
a tiny HTTP service (port 8003) that reports whether tracing is configured.
Nothing here requires a key to try: without configuration everything is a
safe no-op.

### 1. Add tracing to a function

Install with the LangSmith extra and decorate:

```python
from digismith.trace import traceable

@traceable("chat_completion")
def chat_completion(...): ...
```

- With `LANGSMITH_API_KEY` set and the `langsmith` package installed, calls
  emit LangSmith spans scrubbed by the built-in PII redactor.
- Without either, the decorator returns your function unchanged — no
  wrapper, no overhead, tests stay green.

Gate optional behavior at runtime with `tracing_enabled()`, which re-reads
the environment on every call:

```python
from digismith.config import tracing_enabled

if tracing_enabled():
    ...
```

### 2. Run the status service

From the repo root with Docker Compose:

```bash
docker compose build digismith
docker compose up digismith
```

Or directly (from `digismith/`):

```bash
uvicorn digismith.server:app --host 0.0.0.0 --port 8003
```

The image installs `digismith[langsmith]` and serves
`digismith.server:app` on port 8003, published on the host as
`127.0.0.1:8003`.

### 3. Verify it

```bash
curl -s http://localhost:8003/healthz    # {"ok": true} — liveness
curl -s http://localhost:8003/v1/status  # tracing diagnostic
```

`GET /healthz` answers "is the process up". `GET /v1/status` answers "is
tracing configured", returning `tracing_configured`,
`langsmith_sdk_installed`, the sanitized `langsmith_host`, and an echoed
`request_id` — never any secret. To enable tracing, set `LANGSMITH_API_KEY`
(and optionally `LANGSMITH_ENDPOINT`) in `.env` and restart; `/v1/status`
will flip `tracing_configured` to true.

### 4. Run the tests and lint

```bash
pytest tests/ -m unit -k "digismith" -v
ruff check digismith/ && ruff format --check digismith/
```

### Where next

- [digismith Architecture](/openwiki/digismith/architecture.md) — library
  vs service, conditional-tracing pattern, consumer boundaries.
- [Tracing and Redaction](/openwiki/digismith/tracing-and-redaction.md) —
  decorator semantics, config helpers, PII patterns, `DIGI_PII_PATTERNS`.
- [Status API and Operations](/openwiki/digismith/status-api-and-operations.md) —
  health, status, metrics, CORS, OTel, container wiring.
