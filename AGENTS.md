# AGENTS.md

Single source of truth for every AI coding agent working in this repo (Claude Code, Cursor, GitHub Copilot, and others driven by `agents.yml`).

## What this project is

**DigiThings** (digithings.ai) is an open-core modular agentic stack for chat-driven workflows, RAG, and domain apps. Flagship vertical is quantitative finance; the same stack powers RAG, document search, and general agent workflows.

Before taking any non-trivial action, read:

1. [docs/VISION.md](docs/VISION.md) — strategic direction and decisions.
2. [ARCHITECTURE.md](ARCHITECTURE.md) — system diagram, service topology, interaction flows.
3. [ROADMAP.md](ROADMAP.md) — current phase and upcoming work.
4. The target component's `ARCHITECTURE.md` and `AGENTS.md`.

## Non-negotiable technical rules

- **Data layer:** Polars only. Never use pandas.
- **Quant engine:** NautilusTrader for all backtest/optimize/live paths.
- **Orchestration:** LangGraph, supervisor + sub-graph pattern only.
- **LLM routing:** LiteLLM. Caching is mandatory.
- **Structured outputs:** Pydantic v2 everywhere, never raw dicts across service boundaries.
- **Security:** Follow [SECURITY.md](SECURITY.md) exactly — loopback-only defaults, least privilege, human gates for every live trade. The [STRIDE threat model](SECURITY.md#threat-model) enumerates the actors, assets, and controls you are expected to respect.
- **Performance targets:** Backtests < 2 s for 10 M rows; token reduction ≥ 70 % vs naive prompts.
- **Python:** 3.12+, strict typing, ruff-compliant (line length 100).
- **MCP-first:** every capability exposed as a discoverable tool.
- **No orphan code:** every code change must trace to a GitHub Issue on [Project #1](https://github.com/orgs/digithings-ai/projects/1). Use a `task/<N>-<slug>` branch (via `make task ISSUE=N`) or add `Fixes #<N>` / `Closes #<N>` to the PR body. Enforced by `.github/workflows/pr-linkage.yml`. See the epic at #34 for rationale.
- **`housekeeping` label:** issues labeled `housekeeping` are exempt from project-field requirements (Phase/Area/Kind/Priority/Model in `scripts/project_fields.tsv`). Use only for trivial chores — dependency bumps, typo fixes, README-only updates — that do not require tracking on the board.
- **Agent surface is generated:** the skills, subagents, and slash commands under `.claude/`, the Cursor rules at `.cursor/rules/digithings.mdc`, and `.github/copilot-instructions.md` are **all generated** by `scripts/agents_init.py` from `agents.yml` + `agents/sources/`. Edit the sources, run `make agents-init`, then commit. CI drift-checks via `scripts/agents_init.py --check`.

## Workflow (plan → execute → verify)

1. Explore and plan before writing code.
2. Reference existing docs instead of inventing new structure.
3. Make small, focused commits with conventional messages.
4. Write real tests for every new feature (no smoke stubs; no "assert True").
5. Update the relevant `{component}/ARCHITECTURE.md` after any interface or behavior change.
6. When in doubt, ask rather than guess.

## PR scoring gate

Every PR must self-score with `make score` and meet the thresholds below before merge. Rubrics live in [docs/scoring/](docs/scoring/).

| Dimension | Minimum | Rubric |
|-----------|---------|--------|
| Security | ≥ 8 / 10 | [docs/scoring/SECURITY.md](docs/scoring/SECURITY.md) |
| Quality | ≥ 8 / 10 | [docs/scoring/QUALITY.md](docs/scoring/QUALITY.md) |
| Optimization | ≥ 7 / 10 | [docs/scoring/OPTIMIZATION.md](docs/scoring/OPTIMIZATION.md) |
| Accuracy | ≥ 9 / 10 | [docs/scoring/ACCURACY.md](docs/scoring/ACCURACY.md) |

End-to-end workflow: [docs/agents/AGENT_WORKFLOW.md](docs/agents/AGENT_WORKFLOW.md).

## Always requires human review

- Any change to auth, JWT, or cryptography code.
- Any change touching broker adapters or live-trading paths.
- Score below threshold on any dimension.
- New external service dependency or infrastructure change.
- Novel architectural decisions not covered by existing `ARCHITECTURE.md` files or an ADR.

## Doc-only auto-merge

Doc-only PRs on allowlisted paths may enable the `automerge-docs` label. Policy: [docs/agent-backlog/AUTOMERGE.md](docs/agent-backlog/AUTOMERGE.md). `SECURITY.md`, `.github/workflows/`, and any source-tree changes are excluded.

## Component pointers

Each component has its own `ARCHITECTURE.md` (reference) and `AGENTS.md` (pre-flight checklist + extension patterns). Read both.

- **digigraph/** — LangGraph orchestration brain.
- **digiquant/** — NautilusTrader quant engine. For Nautilus strategy/backtest work, also read `digiquant/docs/NAUTILUS_NAVIGATION.md`.
- **digisearch/** — RAG and document search. Use Polars for CSV parsing.
- **digichat/** — Next.js BFF + chat UI. Follow Next.js conventions; strict TypeScript.
- **digikey/** — JWT + scoped API keys. Python services integrate via `digikey.integrations.service_middleware`.
- **digismith/** — Tracing helpers + `/v1/status`. Keep `/v1/status` secret-free. See "Liveness vs status" below for the `/healthz` vs `/v1/status` contract.
- **digiclaw/** — Heartbeat, audit, MCP skill → DigiGraph.
- **digibase/** — Shared HTTP/audit library.

## Liveness vs status

Every FastAPI service exposes **two** diagnostic endpoints with distinct
contracts. Do not merge them.

- **`GET /healthz`** — liveness probe. Auth-exempt, rate-limit-exempt,
  secret-free. Always returns HTTP 200 with `{"ok": true}`. Intended for
  load balancers, Kubernetes liveness probes, and Docker healthchecks.
  Must not depend on downstream services, databases, or LLMs.
- **`GET /v1/status`** (DigiSmith) — human-readable diagnostic surface.
  Still public and secret-free, but may report tracing configuration,
  SDK availability, and non-sensitive versioning. Intended for operators
  and on-call debugging. Load balancers should **not** probe this path.

The legacy `/health` route remains on every service for back-compat, but
new integrations should target `/healthz`.

## Agent operations (backlog, playbooks, skills)

- **Backlog:** [GitHub Project](https://github.com/orgs/digithings-ai/projects/1); local mechanics in [docs/agent-backlog/](docs/agent-backlog/).
- **Playbooks:** [docs/agents/PLAYBOOK.md](docs/agents/PLAYBOOK.md), [docs/agents/COMPONENT_ROUTING.md](docs/agents/COMPONENT_ROUTING.md).
- **Agent capabilities** (subagents, skills, slash commands): declared in [`agents.yml`](agents.yml), authored under [`agents/sources/`](agents/sources/), regenerated into `.claude/` by `make agents-init`. See [`agents/sources/README.md`](agents/sources/README.md) for layout and the per-tool catalogue.
- **Skill templates** (per-IDE copies): [docs/agent-skills/README.md](docs/agent-skills/README.md).
- **Link checker:** `make doc-check` (also runs in CI).

## Workspace facts

- `projects/` is confidential. Contains client pilots (e.g. SITAAS). Never push to public remotes.
- Session-scoped dataset blobs live in Digistore (on disk). LangGraph checkpointed workflow state must carry only lightweight refs and profiles, not full row payloads.
- Root `CLAUDE.md` is Claude Code's canonical guide. Do not create per-component `CLAUDE.md` redirect stubs.
- DigiSearch type names drop the `Digi` prefix when context implies the module (`Document`, `Chunk`, `Query`, `Result`).

## When this file changes

Hand-edit `agents.yml` first (it's the single source of truth). Then run `make agents-init` to regenerate `.cursor/rules/digithings.mdc` and `.github/copilot-instructions.md`. This file and `CLAUDE.md` are authoritative — `agents.yml` + generated surfaces should reference them, not duplicate them.
