# OpenWiki instructions — digithings repo

## Scope: full repository

Document every component in the monorepo. One section per component,
each with its own quickstart (where applicable), architecture / module
map, behavior guides, and API + operations reference — mirroring the
established `digismith/` pilot structure.

Components and ports:

- `digigraph` (8000) — LangGraph orchestration, OpenAI-compatible API, tool registry
- `digiquant` (8001) — NautilusTrader backtest/optimize, strategy registry, research + portfolio sub-graphs
- `digisearch` (8002) — RAG, document ingest, vector search
- `digismith` (8003) — LangSmith tracing helpers, status API ✅ done (pilot — do not regenerate unless stale)
- `digivault` (8004) — Obsidian-style markdown vault management
- `digikey` (8005) — JWT + scoped API key auth plane
- `digichat` (3005) — Next.js BFF + React chat UI
- `digiclaw` — heartbeat, audit (JSONL), gateway
- `digibase` — shared HTTP/audit **library** (Python package, not a service)
- `digillm`, `digifetch`, `digiskills` — supporting libraries
- `frontend/dashboard` — digiquant operator surface
- Repo-level: branching model, `make` targets, review/merge policy (brief — pointer to AGENTS.md, not a duplicate)

Do NOT document `projects/` (confidential). Keep each component to
3–6 pages max: quickstart, architecture, key behaviors, API + operations.
Skip exhaustive symbol inventories.

## Repo conventions the wiki must respect

- Product/module names are always lowercase (`digichat`, never DigiChat).
  See root `AGENTS.md` § Naming. (Code identifiers like `DigiChatSession`
  keep their language-idiomatic casing — do not "fix" those.)
- Non-negotiables: Pydantic v2, strict typing, ruff line length 100,
  structured errors (no silent `except`), Polars-only (never pandas),
  NautilusTrader for all backtest paths, LiteLLM for LLM routing.
- `GET /healthz` is liveness (`{"ok": true}`); component `/v1/status`
  endpoints are operator diagnostics — do not conflate them (see root
  `AGENTS.md` § Liveness vs status).
- Every claim about behavior must cite evidence (`repo://` spans).
  Do not invent endpoints, ports, or env vars.
- Never document live-trading paths beyond what source + tests show;
  flag `digikey/` auth and `digiquant/brokers/` areas as human-gate
  rather than operational how-tos.
