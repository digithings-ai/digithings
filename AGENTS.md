# AGENTS.md – Master Instructions for All Coding Agents (Digi Ecosystem, February 2026)

**This is the single source of truth for every AI coding agent (Cursor, Claude Code, Cline, etc.).**

## Core Project Context
- Read and strictly follow `DIGI.md` (vision, mission, branding, monetization).
- Read `ARCHITECTURE.md` (diagrams & interfaces) and `ROADMAP.md` (current phase).
- This is an agentic “hedge-fund-in-a-box” for solo quants and small firms.
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

## Sub-folder Guidance
- In digigraph/: Follow `digigraph/DIGIGRAPH.md` strictly.
- In digiquant/: Follow `digiquant/DIGIQUANT.md` strictly.
- In digiclaw/: Follow `digiclaw/DIGICLAW.md` strictly.

## How to Use This File
- Agents should reference this file in every session.
- When you improve a rule, update this file and let other agents know.
- Hierarchical: sub-folders may have their own AGENTS.md for component-specific rules.

This file evolves — corrections and improvements are encouraged.