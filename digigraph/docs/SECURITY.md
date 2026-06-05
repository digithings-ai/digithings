# DigiGraph security notes

DigiGraph is intended to run **loopback-first** alongside other DigiThings services. Harden deployments that listen on non-local interfaces.

## Authentication

- **DigiKey (required for protected routes):** Set **`DIGIKEY_JWKS_URL`** or **`DIGIKEY_PUBLIC_KEY_PEM`**. Non-exempt routes require **`Authorization: Bearer <RS256 JWT>`** with scopes per path (e.g. `digigraph:chat` for `/v1/chat/completions`, `digigraph:workflow` for `/workflow`). Without verifier configuration, protected routes return **503** `auth_not_configured`. Legacy static **`DIGI_API_KEY`** is **not** supported on DigiGraph.
- **Per-thread secrecy**: Thread IDs are not secret tokens. Anyone who can call the API can probe `GET /threads/{id}/state` when the thread API is enabled. Do not expose DigiGraph to untrusted networks without a gateway that binds sessions to authenticated users.

## Opt-in HTTP surfaces

These are **disabled by default** (HTTP 404) unless explicitly enabled:

| Env | Effect |
|-----|--------|
| `DIGI_ENABLE_DEBUG_ENDPOINTS=1` | `GET /test_llm`, `GET /v1/debug/*` |
| `DIGI_ENABLE_THREAD_API=1` | `GET/POST /threads/*`, `GET /files/*` |

Docker Compose defaults both to **`0`** (secure-by-default). Set `DIGI_ENABLE_DEBUG_ENDPOINTS=1` and/or `DIGI_ENABLE_THREAD_API=1` in `.env` for local debugging.

## Tool allowlist

Orchestrator tools (RAG, delegate agents) can be restricted:

1. Request body `allowed_tools` on `POST /workflow` or `POST /v1/chat/completions`, or header `X-Allowed-Tools: name1,name2`.
2. Project YAML `agents.allowed_tools: [digisearch, ...]`.
3. Env `DIGI_ALLOWED_TOOLS` (comma-separated).

Precedence: explicit request list → project config → env → unrestricted (all registered tools).

## Code execution

`data_engineer_agent` / `execute_python_on_datasets` uses Python `exec()` when **`DIGI_ALLOW_CODE_EXEC=true`**. This is **not** a capability sandbox — restricted globals only block casual misuse.

**Policy (REM-012):** Default is **disabled** (fail closed). Do not enable in production without a container/subprocess sandbox design review. See `digigraph/tools/analytics/execute_python.py` module docstring.

## CORS

`DIGI_ALLOWED_ORIGINS` controls browser CORS. Default origins are local dev only. For internet-facing UIs, set an explicit allowlist instead of `*`-style patterns.

## Research corpus & citations

- Ingest only content you are licensed to index (uploaded PDFs, open-access works, metadata from APIs such as Crossref). Do not use DigiGraph or DigiSearch to circumvent paywalls or to reproduce full text without rights.
- `ResearchBrief` must cite **tool-returned** `source_id` values; operators should treat uncited model text as non-evidence.

## Streaming implementation

`POST /v1/chat/completions` with `stream: true` runs the LangGraph workflow in a **worker thread** and forwards events over SSE. There is no cancellation token or backpressure contract today; prefer short workflows or non-streaming calls for strict latency budgets. See `digigraph/ARCHITECTURE.md` (streaming) for details.
