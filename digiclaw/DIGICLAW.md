# DigiClaw – Gateway & Runtime Layer

**Part of [DigiThings](https://github.com/digithings-ai/digithings) (digithings.ai).**  
**Purpose** (from root `DIGI.md`): Persistent multi-channel interface, execution gateway, and self-governing runtime built on OpenClaw (180k+ stars, Feb 2026).

**When we set up OpenClaw:** Phase 1 (week of Mar 2 → Mar 20). Phase 0 only defined the skill contract (`digiclaw/skills/README.md`); the OpenClaw runtime, Docker service, and `run_digigraph_workflow` skill implementation are part of Phase 1 “DigiClaw custom skill integration” (see `ROADMAP.md`). OpenClaw integration remains deferred.

**Phase 3 (current):** Heartbeat and audit run without OpenClaw. Use `python -m digiclaw` from repo root, or `docker compose --profile heartbeat up`, to run the heartbeat agent every 30 min (health checks + audit log). See **HEARTBEAT.md** and **ROADMAP.md** Phase 3.

**Core Responsibilities**
- Channel adapters (Slack, Discord, Telegram, WhatsApp)
- Session & queue management
- Heartbeat/cron agents (HEARTBEAT.md driven)
- One custom MCP skill that calls DigiGraph
- Hardened security (loopback-only, Tailscale, least-privilege)

**Tech Stack**
- OpenClaw latest (post-CVE-2026-25253 hardened)
- Node.js Gateway + Docker Compose base
- WebSocket control plane

**Interfaces with Other Components**
- Calls `DigiGraph` via MCP/HTTP (see `digigraph/DIGIGRAPH.md`)
- Receives results for user chat & persistent Markdown workspace
- Triggers self-healing via `DigiQuant` monitoring agents

**Deployment for Clients**
One-command: `docker compose up` → fully isolated VM or container recommended.

Full security & hardening spec → root `SECURITY.md`.

---

## Phase 3 implementation (heartbeat + audit)

- **`digiclaw/audit.py`** — `audit_log(event_type, agent_id, payload)` appends JSONL to `AUDIT_LOG_PATH` (default: `digiquant/results/audit/events.jsonl`). Redacts common secret keys.
- **`digiclaw/heartbeat_runner.py`** — One cycle: ping DigiGraph and DigiQuant `/health`, log result via `audit_log("heartbeat", ...)`. Reads `HEARTBEAT.md` path from `DIGI_WORKSPACE`.
- **Run:** `python -m digiclaw` from repo root (env: `DIGIGRAPH_URL`, `DIGIQUANT_URL`, `AUDIT_LOG_PATH`). Or Docker: `docker compose --profile heartbeat up`.
- **HEARTBEAT.md** (repo root) — Checklist for the agent; heartbeat runner runs health checks, then calls DigiQuant `/check_drift` and triggers `/run_optimize` when ADDM reports drift (stub returns no drift by default).

---

## MCP entrypoints (hub-only vs vertical)

Skills can target different MCP surfaces depending on deployment:

| Pattern | When to use | Tools / flows |
|--------|-------------|----------------|
| **Hub-only** | Default chatops; single policy surface | OpenClaw skill calls **DigiGraph** MCP/HTTP (`run_digigraph_workflow`, `chat`, orchestrator tools). DigiSearch/DigiQuant tool **definitions** are served by each vertical (`POST /v1/orchestrator_tools`); DigiGraph invokes `POST /v1/orchestrator_invoke`. **`DIGI_HUB_MODE=federated`** adds delegate tool names (`digiquant_pipeline_delegate`, `digisearch_research_delegate`) to the LLM surface; `legacy` keeps the same vertical invoke path for core search/pipeline tools without those aliases. |
| **Direct vertical MCP** | Power users, split blast radius, standalone DigiQuant/DigiSearch | Register MCP servers for **DigiQuant** (`digiquant_run_pipeline`, backtest, optimize, …) and/or **DigiSearch** (`digisearch_query`, `digisearch_research_turn` when `digisearch[agent]` is installed) in addition to or instead of the hub. |

Use **hub-only** when you want one DigiKey allowlist and trace stream. Use **direct vertical MCP** when a client should call DigiSearch or DigiQuant without loading the full DigiGraph tool surface. Never expose long-lived service tokens to browser clients; gateway holds credentials.