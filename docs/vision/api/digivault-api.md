---
title: "digivault — API reference"
type: reference
status: generated
created: 2026-08-10
tags:
  - api
  - support
relevance:
  - digivault
---
# digivault — API reference

> A folder of markdown notes, served over HTTP — frontmatter, wikilinks and backlinks.

**Role:** Markdown vault · wikilinks · backlinks · **Tier:** support

## Overview
An Obsidian-style vault service: it manages a folder of markdown notes with YAML frontmatter, wikilinks, tags and a folder taxonomy, and answers over HTTP rather than asking callers to walk the filesystem.

Routes cover listing, reading and creating notes, renaming with backlink repair, backlink and tag lookups, and a lint report. Two more — orchestrator_tools and orchestrator_invoke — expose the vault to digigraph as callable tools. Runs behind the `digivault` compose profile, so it is opt-in rather than up by default.

## Authentication
DigiAuthMiddleware with a per-path scope map: digivault:read for reads and for both orchestrator routes, digivault:write for mutations. /v1/orchestrator_invoke is gated at read because most of its tools are reads — the one mutating tool re-checks digivault:write in the handler, so a read-only caller cannot reach it through the shared endpoint.


## Run locally
```bash
docker compose --profile digivault up -d digivault   # opt-in profile, not up by default
digivault lint --root ./docs/vision
```

## Configuration
- `DIGIVAULT_ROOT` (default `/data/vault`): Vault directory. Unset, the routes that read the filesystem answer 503 rather than guessing a path; /v1/orchestrator_tools still returns its static manifest.
- `DIGIKEY_JWKS_URL` (default `http://digikey:8005/.well-known/jwks.json`): Where the middleware fetches the public half to verify tokens.
- `DIGIKEY_ISSUER` (default `http://digikey:8005`): Expected token issuer.
- `DIGIKEY_AUDIENCE` (default `digi-ecosystem`): Expected token audience.

## Public interface
- `GET /v1/notes` — List notes in the vault.
- `GET /v1/notes/{name}` — Read one note — body plus parsed YAML frontmatter.
- `POST /v1/notes` — Create a note. Requires digivault:write.
- `PATCH /v1/notes/{name}/frontmatter` — Update frontmatter in place.
- `POST /v1/notes/{name}/rename` — Rename a note and repair the wikilinks pointing at it.
- `GET /v1/notes/{name}/backlinks` — Every note linking to this one.
- `GET /v1/tags/{tag}` — Notes carrying a tag.
- `GET /v1/lint` — Vault health: broken wikilinks, missing frontmatter, taxonomy drift.
- `POST /v1/orchestrator_tools` — Tool manifest, so digigraph can discover what the vault offers.
- `POST /v1/orchestrator_invoke` — Invoke one of those tools by name.

## Notes
- The vault is a folder of markdown files — YAML frontmatter, wikilinks, tags, folder taxonomy. There is no database; the filesystem is the store.
- Its first consumer is this repository's own docs/vision/, which scripts/gen-api-vault.ts generates from the same module registry this page is built from.

## Stack
FastAPI, Pydantic, PyYAML

## Related
digigraph, digisearch, digibase

## Links
- [Source](https://github.com/digithings-ai)

See also [[digivault]].
