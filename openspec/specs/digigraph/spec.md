# DigiGraph — Spec

**Port:** 8000  
**Role:** LangGraph orchestration brain — MCP tool router, OpenAI-compatible API, multi-turn thread manager.

## Capabilities

- OpenAI-compatible `/v1/chat/completions` endpoint (streaming + non-streaming)
- `/v1/models` model catalogue
- Stateful conversation threads (`/threads/*`) backed by LangGraph checkpointer
- File upload/retrieval (`/files/*`)
- LangGraph supervisor graph routing work to sub-graphs and MCP tools
- LiteLLM routing with caching for all LLM calls

## Invariants

- LangGraph supervisor + sub-graph pattern only — no raw chain calls
- LiteLLM caching is always enabled
- `/healthz` returns `{"ok": true}` with no downstream checks; auth-exempt
- All capabilities exposed as discoverable MCP tools

## Public API

| Method | Path | Description |
|--------|------|-------------|
| POST | `/v1/chat/completions` | OpenAI-compat chat (streaming) |
| GET | `/v1/models` | Available model list |
| POST | `/threads` | Create a new thread |
| GET | `/threads/{id}` | Fetch thread state |
| POST | `/workflow` | Direct workflow invocation |
| POST | `/files` | Upload file |
| GET | `/healthz` | Liveness probe |

## Extension Pattern

Add a new capability as an MCP tool registered with the supervisor graph. Never add raw HTTP endpoints that bypass the graph.
