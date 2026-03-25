# AGENTS.md – Master Instructions for All Coding Agents (DigiThings, February 2026)

**This is the single source of truth for every AI coding agent (Cursor, Claude Code, Cline, etc.).**

## Core Project Context
- Read and strictly follow `DIGI.md` (vision, mission, branding, monetization).
- Read `ARCHITECTURE.md` (diagrams & interfaces) and `ROADMAP.md` (current phase).
- **DigiThings** (digithings.ai) is an open-core agentic product family; one use case is the quant workflow (“hedge fund in a box” for solo quants and small firms). The same stack supports RAG, document search, and other agent applications.
- All code must stay MCP-first, Dockerized, token-efficient, and production-hardened.

## Non-Negotiable Technical Rules
- **Data layer**: Polars only — NEVER use pandas.
- **Quant engine**: NautilusTrader (Rust core) for all backtesting, optimization, live execution.
- **Orchestration**: LangGraph with layered supervisor + sub-graph pattern only.
- **LLM routing**: LiteLLM (100+ providers, full feature passthrough, caching mandatory).
- **Memory**: Graphiti (temporal bi-model) + Neo4j/PGVector + LangGraph checkpoints.
- **Outputs**: Always structured Pydantic models.
- **Security**: Follow `SECURITY.md` exactly (loopback-only, least privilege, human gates for live trades).
- **Performance**: Backtests < 2 s for 10 M rows. Token reduction ≥ 70 % vs naive prompts.
- **Interoperability**: Every capability exposed as discoverable MCP tool.

## Workflow Rules (plan → execute → verify)
1. Always explore and plan first (never write code until you have a clear step-by-step plan).
2. Reference existing documentation before inventing anything.
3. Commit early and often with clear messages.
4. Write tests for every new feature.
5. When in doubt, ask for clarification instead of guessing.
6. For any change, update the relevant DIGIxxx.md documentation section.

## Coding Style & Boundaries
- Python 3.12+, strict typing, black/ruff compliant.
- Keep files focused and modular.
- Never touch production live-trading code without explicit human approval.
- Prefer self-healing patterns and ADDM drift detection where applicable.

## DigiKey

- Optional identity plane: **JWT + scoped API keys**; authoritative doc **[digikey/DIGIKEY.md](digikey/DIGIKEY.md)**. Python services use `digikey.integrations.service_middleware`; DigiChat exchanges via `DIGIKEY_URL` / `DIGIKEY_BFF_TOKEN`.

## Sub-folder Guidance
- In digigraph/: Follow `digigraph/DIGIGRAPH.md` strictly.
- In digiquant/: Follow `digiquant/DIGIQUANT.md` strictly. When modifying Nautilus strategies or backtest: read `digiquant/docs/NAUTILUS_NAVIGATION.md` first.
- In digiclaw/: Follow `digiclaw/DIGICLAW.md` strictly.
- In digisearch/: Follow `digisearch/DIGISEARCH.md` strictly. Use Polars for CSV parsing (never pandas).
- In digismith/: Follow `digismith/DIGISMITH.md` strictly. Keep `/v1/status` free of secrets; tracing uses the LangSmith SDK when configured.
- In digibase/: The **`digibase`** Python package is the shared error envelope and HTTP helpers. Target architecture for centralizing DB/cache access lives in **`digibase/DIGIBASE.md`** (future DigiBase **service** vs today’s **library** only).

## How to Use This File
- Agents should reference this file in every session.
- When you improve a rule, update this file and let other agents know.
- Hierarchical: sub-folders may have their own AGENTS.md for component-specific rules.

## Learned User Preferences
- When implementing work from an attached plan file, do not edit the plan file; use the plan’s existing todo list (mark items in progress in order and finish them) instead of creating duplicate todos.
- Keep `projects/` out of public git history and remotes when it holds client or confidential deployments.
- In top-level README and positioning copy, treat **DigiThings** as an open product family; quantitative finance (“hedge fund in a box”) is one application among others (RAG, search, general agents).
- For the public site starfield, keep a solid black background behind the canvas animation so Safari matches Chrome (no gray canvas tint); animate stars above that base layer.
- For DigiSearch-facing type names, drop redundant `Digi` prefixes when context already implies the module (e.g. prefer `Document`, `Chunk`, `Query`, `Result` over `DigiDocument`, `DigiChunk`, etc.).

## Learned Workspace Facts
- Local or client deployments often live under `projects/` (e.g. Sitaas); that directory is confidential and must not be pushed to public remotes.
- Session-scoped dataset blobs are intended to live in Digistore (on disk); LangGraph checkpointed workflow state should carry only lightweight refs and profiles, not full row payloads.
- **Claude Code** guidance for this repo lives in a single root file **`CLAUDE.md`** (all caps `CLAUDE`); avoid duplicate mixed-case filenames that confuse case-insensitive filesystems.

This file evolves — corrections and improvements are encouraged.