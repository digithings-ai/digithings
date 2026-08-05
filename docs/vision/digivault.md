---
title: digivault
type: module
status: reviewed
created: 2026-06-15
tags:
  - support
  - knowledge-vault
relevance:
  - digigraph
---
# digivault
> The knowledge-vault layer — every note, link, and tag in a managed Obsidian-style markdown vault.

## What it is

digivault manages an Obsidian-style vault: a folder of markdown notes with YAML
frontmatter, `[[wikilinks]]`, backlinks, tags, and a folder taxonomy. It creates,
stores, and maintains that vault — building the link graph, rewriting inbound
links when a note is renamed, and validating the whole vault for unresolved
links, missing frontmatter, and orphans.

It ships as a pure-Python core library plus a thin service (FastAPI + MCP + CLI),
so the same vault semantics power CI documentation checks, ad-hoc scripts, and
agent tool calls through digigraph.

## The problem it solves

Documentation rots. Cross-references break silently, frontmatter drifts, and
there is no cheap way to ask "what links here?" or "which notes are about X?".
Teams either adopt a heavyweight wiki or let a folder of markdown decay. digivault
makes a plain folder of markdown a first-class, queryable, self-validating
knowledge base — the ideation and maintenance surface compounds instead of
drifting.

## How it fits in the ecosystem

digivault is a vertical service that digigraph orchestrates: the hub fetches its
tools via `POST /v1/orchestrator_tools` and invokes them via
`POST /v1/orchestrator_invoke`, so agents can search the vault by tag, fetch
backlinks, lint, and create notes. It reuses digikey for JWT auth
(`digivault:read` / `digivault:write`) and digismith for tracing.

It is complementary to two other modules:

- **[[digistore|digistore]]** owns *where bytes live* (storage backend
  abstraction). digivault owns *how knowledge is organized and traversed*
  (frontmatter, wikilinks, backlinks, taxonomy). digivault would sit above
  digistore, not replace it.
- **[[digisearch|digisearch]]** indexes content for semantic retrieval.
  digivault can feed it: a managed vault is a clean ingestion source, and
  digivault's tags/links add structure digisearch can exploit later.

The first consumer is the project's own documentation (`docs/vision/`), migrated
to a managed vault so ideation and maintenance of all docs run through one tool.

## Capabilities — Current

Shipped:

- Round-trip-safe YAML frontmatter parse/serialize
- Wikilink parsing (`[[note]]`, `[[note#heading|alias]]`, `![[embed]]`), code-aware
- Vault index with backlinks and a tag index
- Maintenance ops: create note, rename (rewrites every inbound `[[link]]`),
  set frontmatter, reindex
- Lint: unresolved links, missing required frontmatter, tag-taxonomy violations,
  orphans (driven by a `.digivault.yml` manifest)
- FastAPI service (port 8004, profile `digivault`) behind digikey JWT
- MCP server (`python -m digivault.mcp_server`) and a `digivault` CLI

## Capabilities — 12-month roadmap

- Migrate `docs/vision/` (and then the wider docs tree) to a managed vault, with
  `make vault-check` validating wikilinks and frontmatter in CI
- Generated backlink sections / maps-of-content per note
- digisearch ingestion of vault notes with tag- and link-aware metadata
- digistore-backed storage so a vault can live on Supabase/S3, not just local disk
- Bidirectional Obsidian compatibility (open the same vault in the Obsidian app)

## Open source vs. proprietary

**Open (MIT/Apache):** the entire digivault module — core library, service, MCP
server, and CLI. It is open-core infrastructure for organizing knowledge; any
proprietary value lives in the *content* of a given vault, not in digivault.
