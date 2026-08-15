# digigraph security notes

digigraph is intended to run **loopback-first** alongside other digithings services. Harden deployments that listen on non-local interfaces.

## Authentication

- **digikey (required for protected routes):** Set **`DIGIKEY_JWKS_URL`** or **`DIGIKEY_PUBLIC_KEY_PEM`**. Non-exempt routes require **`Authorization: Bearer <RS256 JWT>`** with scopes per path (e.g. `digigraph:chat` for `/v1/chat/completions`, `digigraph:workflow` for `/workflow`). Without verifier configuration, protected routes return **503** `auth_not_configured`. Legacy static **`DIGI_API_KEY`** is **not** supported on digigraph.
- **Per-thread secrecy**: Thread IDs are not secret tokens. Anyone who can call the API can probe `GET /threads/{id}/state` when the thread API is enabled. Do not expose digigraph to untrusted networks without a gateway that binds sessions to authenticated users.

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

## Tool-choice requirement

A second, independent gate — `agents.require_tool_calls` — forces `tool_choice="required"` for deployments that must never answer from parametric knowledge alone (e.g. OCC's retrieval dependency). **Scope:** it is wired into exactly one call site — `research_node`'s document-RAG path (`_run_document_rag_path`, reached only when the request is in document mode AND `DIGISEARCH_URL` is configured). It does not reach quant-mode requests or document-mode requests with no digisearch configured (Profile A's shipped default): both fall back to a tools-free `completion_text()` call that this gate cannot affect. Because that fall-through is a policy no-op rather than a refusal, `research_node` emits a `logger.warning` when `require_tool_calls` is set and the request takes the quant/augmented path — the gate still fails open there, but no longer silently. The sub-agent runners under `digigraph/src/digigraph/agents/*` have neither enforcement nor a warning. Central enforcement is tracked in #2384. Its precedence is the OPPOSITE of the allowlist above, deliberately: project config / `DIGI_REQUIRE_TOOL_CALLS` win over a request-level or `X-Require-Tool-Calls` value trying to turn it off — a request can only raise the requirement, never lower one the deployment already mandated. Unlike the allowlist (bounded by the tool registry, so a full override can't expand what's callable), this flag has no such ceiling, and `/v1/chat/completions` is reachable by callers outside digichat's control — a full override here would let any caller defeat an operator's mandatory tool-forcing policy with one field or header. See `digigraph/src/digigraph/tool_policy.require_tool_calls_for_workflow`.

**Spend amplification:** forcing `tool_choice="required"` reliably exhausts all `max_tool_rounds` completions instead of returning after one — a ~4-5x LLM-spend multiplier any caller with plain `digigraph:chat` scope can opt into per request via the same body field / header, independent of whether the deployment itself mandates the gate. `server.py`'s `_enforce_require_tool_calls_budget` meters this with a second, stricter per-IP rate limit (default 3 req/min, `DIGI_REQUIRE_TOOL_CALLS_RATE_LIMIT_MAX`) on top of the general 10 req/min `/v1/chat/completions` limit — either can 429 the request. The same budget also applies to `POST /workflow`'s `WorkflowRequest.require_tool_calls` (body field only — no header there), since it reaches the identical `tool_choice="required"` path via `require_tool_calls_for_workflow` and is reachable by the same `digigraph:workflow` scope granted alongside `digigraph:chat` in the default BFF session scopes.

## Code execution

`data_engineer_agent` / `execute_python_on_datasets` runs user code in a **subprocess** with static rejection of `import os`, `open(`, `exec(`, etc. when **`DIGI_ALLOW_CODE_EXEC=true`**. This is not a full capability sandbox — treat as dev-only.

**Policy (REM-012):** Default is **disabled** (fail closed). Production requires container isolation review in addition to subprocess. See `digigraph/tools/analytics/execute_python.py`.

## CORS

`DIGI_ALLOWED_ORIGINS` controls browser CORS. Default origins are local dev only. For internet-facing UIs, set an explicit allowlist instead of `*`-style patterns.

## Research corpus & citations

- Ingest only content you are licensed to index (uploaded PDFs, open-access works, metadata from APIs such as Crossref). Do not use digigraph or digisearch to circumvent paywalls or to reproduce full text without rights.
- `ResearchBrief` must cite **tool-returned** `source_id` values; operators should treat uncited model text as non-evidence.

## Streaming implementation

`POST /v1/chat/completions` with `stream: true` runs the LangGraph workflow in a **worker thread** and forwards events over SSE. There is no cancellation token or backpressure contract today; prefer short workflows or non-streaming calls for strict latency budgets. See `digigraph/ARCHITECTURE.md` (streaming) for details.
