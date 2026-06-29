---
title: "digismith — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - support
relevance:
  - digismith
---
# digismith — API reference

> Correlation IDs across every span; PII redacted before logs hit disk.

**Role:** Observability · spans · PII redaction · **Tier:** support

## Overview
Structured logging, Prometheus metrics, and OpenTelemetry spans thread through every request so a multi-hop run is traceable end to end.

PII is redacted before anything is written, with optional LangSmith trace export.

## Authentication
Status and metrics are public diagnostics. Tracing is a library wrapper, not an HTTP surface.


## Run locally
```bash
docker compose up -d digismith
```

```bash
uvicorn digismith.server:app
```

## Configuration
- `LANGSMITH_API_KEY`: Enable LangSmith trace export; absent = no-op.
- `LANGSMITH_ENDPOINT` (default `https://api.smith.langchain.com`): LangSmith API base (host shown in /v1/status).
- `OTEL_EXPORTER_OTLP_ENDPOINT`: Enable OTel HTTP export when set.

## Endpoints

Base URL: `$DIGISMITH_URL` (the service URL from docker-compose.yml).

### GET /v1/status
Tracing configuration diagnostic (operator-facing; secret-free).

auth: none

Response example:
```json
{
  "version": "0.1.0",
  "tracing_configured": true,
  "langsmith_sdk_installed": true,
  "langsmith_host": "api.smith.langchain.com",
  "request_id": "..."
}
```

```bash
curl $DIGISMITH_URL/v1/status
```

### GET /metrics
Prometheus metrics (text/plain 0.0.4).

auth: none

## Public interface
- `from digismith.trace import traceable` — @traceable("name") wraps a function with langsmith.traceable when LANGSMITH_API_KEY is set; otherwise a no-op. PII is redacted from span inputs/outputs.
- `from digismith.config import tracing_enabled` — Returns True when tracing is configured (key set + SDK importable).

## Notes
- Span attributes SHOULD include workflow_id, request_id, session_id, job_id.
- Spans MUST NOT include raw prompts/completions, secrets, or full document bodies.

## Stack
LangSmith, OpenTelemetry, Prometheus, FastAPI

## Related
digigraph, digiclaw, digibase

## Links
- [Source](https://github.com/digithings-ai)

See also [[digismith]].
