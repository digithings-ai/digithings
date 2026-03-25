# DigiSmith – LangSmith-aligned observability

**Part of [DigiThings](https://github.com/digithings-ai/digithings) (digithings.ai).**  
Companion layer for [LangSmith](https://docs.smith.langchain.com/): shared tracing helpers and a small HTTP service for health and **non-sensitive** tracing configuration status.

## Library

- **`digismith.config`** — `tracing_enabled()`, `langsmith_host_sanitized()`, `SmithStatus` model.
- **`digismith.trace`** — `traceable(name)` decorator: applies `langsmith.traceable` only when `LANGSMITH_API_KEY` is set and `langsmith` is installed (otherwise no-op). Used by DigiGraph for LLM calls.

Install:

```bash
pip install -e "./digismith[langsmith]"   # tracing + LangSmith SDK
pip install -e "./digismith"             # HTTP service deps only
```

## HTTP service

- **`GET /health`** — liveness.
- **`GET /v1/status`** — Pydantic JSON: version, whether tracing would activate, whether `langsmith` is importable, **sanitized** LangSmith API host only. **Never** returns API keys or tokens.

Default Docker port: **8003** (`http://127.0.0.1:8003`). Optional convention for other services: `DIGISMITH_URL=http://digismith:8003` (reserved for future discovery; DigiGraph does not require it for tracing in v1).

## Environment

| Variable | Purpose |
|----------|---------|
| `LANGSMITH_API_KEY` | Enables trace export when the `langsmith` package is installed. |
| `LANGSMITH_ENDPOINT` | Optional API base URL (default `https://api.smith.langchain.com`). Host from this URL may appear in `/v1/status` (hostname only). |

## Security

Treat `/v1/status` as **public metadata** suitable for orchestrators and dashboards; it must not leak secrets. Keep keys in env or secret stores only.

## Integration

- **DigiGraph** installs `digismith[langsmith]` in the stack image and uses `digismith.trace.traceable` around chat completions. Traces still go to LangSmith via the SDK (or your configured endpoint), not through the DigiSmith HTTP process.

## Span attributes and PII (contract)

When LangSmith tracing is on, spans SHOULD carry (where known): **`workflow_id`**, **`request_id`** (mirror `X-Request-ID`), **`session_id`**, **`job_id`** / backtest job id from DigiQuant, and **tool or run name** (e.g. orchestrator tool id, `chat_completion`). Do not put raw prompts, API keys, bearer tokens, file paths outside approved workspace roots, or full document bodies into span inputs/outputs—summarize or hash when needed. **`GET /v1/status`** remains non-secret (version flags, sanitized host only); never add keys or tokens to that payload. Optional OpenTelemetry on HTTP services (via `digibase[otel]`) complements LangSmith for infra-level traces; keep the same PII rules on span attributes.
