---
title: "digitrace — API reference"
type: reference
status: generated
created: 2026-10-02
tags:
  - api
  - support
relevance:
  - digitrace
---
# digitrace — API reference

> Correlation IDs across every hop — and prompts logged by length, never by text.

**Role:** Observability · spans · correlation IDs · **Tier:** support

## Overview
Structured logging, Prometheus metrics and OpenTelemetry spans thread through every request, so a multi-hop run is traceable.

Audit events record a prompt's length and its IDs, never the prompt itself — tail events.jsonl and check. In-house digitrace over OTLP is the default export; optional LangSmith and Langfuse-OTLP integrations are never the default and run a regex PII redactor on the way out.

## Authentication
Status and metrics are public diagnostics. Tracing is a library wrapper, not an HTTP surface.


## Run locally
```bash
docker compose up -d digitrace
```

```bash
uvicorn digitrace.server:app
```

## Configuration
- `OTEL_EXPORTER_OTLP_ENDPOINT` / `DIGI_OTEL_ENDPOINT` / `DIGITRACE_OTLP_ENDPOINT`: Enable OTel HTTP export when set — the in-house digitrace ingest is the default destination.
- `LANGSMITH_API_KEY`: Opt into the optional LangSmith integration; absent (the default) = no vendor leg.
- `LANGSMITH_ENDPOINT` (default `https://api.smith.langchain.com`): LangSmith API base for that optional integration (host shown in /v1/status only when configured).
- `LANGFUSE_HOST` / `LANGFUSE_OTLP_ENDPOINT`: Opt into the optional Langfuse-OTLP integration; absent (the default) = no vendor leg.

## Endpoints

Base URL: `$DIGITRACE_URL` (the service URL from docker-compose.yml).

### GET /v1/status
Tracing configuration diagnostic (operator-facing; secret-free).

auth: none

Response example:
```json
{
  "version": "0.1.0",
  "tracing_configured": true,
  "langsmith_sdk_installed": false,
  "langsmith_host": null,
  "request_id": "...",
  "langfuse_configured": false,
  "otel_export_configured": true,
  "dual_export": false,
  "export_backend": "otel",
  "langfuse_host": null
}
```

```bash
curl $DIGITRACE_URL/v1/status
```

### GET /metrics
Prometheus metrics (text/plain 0.0.4).

auth: none

## Public interface
- `from digitrace.trace import traceable` — @traceable("name") opens an OTel span per call when an OTLP endpoint is set (in-house digitrace by default) and, when the optional LangSmith integration is configured, wraps with langsmith.traceable too. Otherwise a no-op. PII is redacted from the LangSmith leg's span inputs/outputs.
- `from digitrace.config import tracing_enabled` — Returns True when at least one export leg is configured.

## Notes
- Span attributes SHOULD include workflow_id, request_id, session_id, job_id.
- Spans MUST NOT include raw prompts/completions, secrets, or full document bodies.

## Stack
OpenTelemetry (in-house digitrace default), optional LangSmith / Langfuse-OTLP, Prometheus, FastAPI

## Related
digigraph, digibot, digibase

## Links
- [Source](https://github.com/digithings-ai)

See also [[digitrace]].
