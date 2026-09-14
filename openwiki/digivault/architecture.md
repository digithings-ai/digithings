---
type: service-architecture
title: digivault Architecture
description: Vault design of digivault — pure core library versus thin service layer, module map, and safety invariants.
tags: [digivault, vault, markdown, architecture]
sources:
  - id: openwiki-source-a18bc9b1229d0282f121b666
    resource: repo://digivault/AGENTS.md
  - id: openwiki-source-177aa6b06017b843d46bc98a
    resource: repo://digivault/ARCHITECTURE.md
  - id: openwiki-source-bf004a9f25211e53a4b65e2d
    resource: repo://digivault/pyproject.toml
  - id: openwiki-source-88d7df185e0425784adb4684
    resource: repo://digivault/src/digivault/models.py
generated: { by: "opencode", at: "2026-09-07T22:38:58.074Z" }
verified:
  - by: openwiki/0.5.0
    at: 2026-09-09T14:37:17.158Z
---

# digivault Architecture

digivault (port 8004) manages an Obsidian-style markdown vault —
frontmatter, `[[wikilinks]]`, backlinks, tags, folder taxonomy — first
consumed by the project's own `docs/vision/`. It splits into a
**pure-Python core library** (no FastAPI, side-effect-free on import) and
a thin **service layer** (FastAPI + MCP + CLI) behind the `[service]`
extra.

## Core vs service

Core hard deps are `pydantic>=2` + `pyyaml>=6` only — `import digivault`
never pulls FastAPI, uvicorn, mcp, or typer (guarded by an import-cost
test). Service deps (FastAPI, MCP bounded `<2`, typer, Supabase/D1
clients) live in extras; auth, tracing, metrics, and error envelopes
reuse digikey + digibase without modifying them.

## Module map (selected)

| Module | Role |
|--------|------|
| `models.py` | Pydantic results: `Note`, `NoteRow`, `NoteDetail`, `VaultSearchHit`, `LintReport`, … — never bare dicts |
| `vault.py` | `Vault`: index + link graph + backlinks + tags; create/write/rename/lint ops |
| `frontmatter.py` | Round-trip-safe YAML `split`/`dump`/`set_keys` |
| `wikilinks.py` | Parse + rewrite `[[links]]`, skipping code regions |
| `local_search.py` | Filesystem keyword search (no network) |
| `supabase_store.py` / `d1_store.py` | Remote read paths (Supabase FTS, Cloudflare D1 FTS5) |
| `tool_dispatch.py` | Canonical tool names + handlers (vault-local vs runtime-only) |
| `orchestrator_tools.py` | OpenAI manifest digigraph fetches |
| `path_scopes.py` / `tenant_scope.py` | Read/write scopes, tenant corpus binding |
| `server.py`, `mcp_server.py`, `cli.py` | FastAPI, MCP transport wrapper, Typer CLI |

## Safety invariants

All write paths sandbox to the vault root (`Vault` refuses `../`
traversal and absolute escapes); frontmatter round-trips
(`split(dump(fm, body)) == (fm, body)`); wikilink rewrites mask code
spans/blocks; routes carry read vs write scopes; new vault tools register
in `tool_dispatch.py` only (no duplicate handler tables).

## Store precedence

Search and by-path fetch prefer D1 when Cloudflare credentials +
`D1_DATABASE_MAP` are set (D1 wins even with `DIGIVAULT_ROOT` set), then
local filesystem, then Supabase FTS. `digivault_get_note` is D1-only with
no fallback.
