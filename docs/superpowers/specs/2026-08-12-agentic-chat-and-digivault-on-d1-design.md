# Agentic chat (#2240) + digivault's corpus on Cloudflare D1 (#2239)

**Date:** 2026-08-12
**Status:** Draft for review
**Supersedes:** the Supabase-switch approach in [#2239](https://github.com/digithings-ai/digithings/issues/2239), and the
`architecture_notes`-as-corpus-store arrangement for the two chat corpora
**Related:** [Vectorize remote index design](2026-08-11-vectorize-remote-index-design.md)

## Why these are one spec

They look separate and are not. #2240 wants the model to **locate** a document with
digisearch, then **load** it with digivault. That is unexpressible today for two
independent reasons: the model is handed an empty tool list, and digivault has no
way to fetch a note by identifier. Fixing either alone delivers nothing — fixing
only #2239 would deliver *different* fixed results through the same broken
pattern, as #2240 already notes.

## Part 1 — digivault's corpus moves to Cloudflare D1

### The decision

Owner direction, 2026-08-12: *"ideally we keep all the corpus data in the same
location to reduce dependencies. So if the vector is in Cloudflare, then digivault
storage for the digithings corpus and the OCC corpus should also be in Cloudflare
storage."*

So digivault's production read path becomes **Cloudflare D1**, symmetric with
digisearch's move to Vectorize. This *replaces* the plan to make the Supabase path
work in the container, and in doing so deletes all three blockers #2239 enumerates
rather than fixing them:

| #2239 blocker | Under D1 |
|---|---|
| Image lacks the `[supabase]` extra | Gone — D1 is plain HTTPS + `httpx`, already present |
| `entrypoint.sh` re-defaults an empty `DIGIVAULT_ROOT` | Gone — see *Backend selection* below; `DIGIVAULT_ROOT` and the boot-critical `mkdir` are left untouched |
| `CORE_SUPABASE_*` absent from the `envVars` whitelist | Replaced by `D1_*`, using the same three-site pattern `VECTORIZE_*` established |

It also removes the fourth, latent blocker: whether migration 068's 3-arg
`search_architecture_notes` RPC is applied to the production project. D1 owns its
own schema.

### Why D1 and not R2 or KV

digivault does exactly two things for chat: **keyword search** and (new)
**fetch-by-identifier**. R2 and KV give a fast exact-key `get` and no search at
all, so either would need a second system for the index — the opposite of the
stated goal. D1 is SQLite: FTS5 `MATCH` covers search, primary-key lookup covers
get. One store, one dependency, one credential.

### Verified constraints (retrieved 2026-08-12, not from memory)

| Fact | Value | Source |
|---|---|---|
| REST query API exists (no Worker binding needed) | `POST /accounts/{account_id}/d1/database/{database_id}/query`, `Authorization: Bearer <token>` | [D1 query API](https://developers.cloudflare.com/api/resources/d1/subresources/database/methods/query/) |
| Max database size | 500 MB free / 10 GB paid | [D1 limits](https://developers.cloudflare.com/d1/platform/limits/) |
| Max storage per account | 5 GB free / 1 TB paid | limits |
| Databases per account | 10 free / 50,000 paid | limits |
| Max row / string / BLOB size | 2,000,000 bytes | limits |
| Max SQL statement length | 100,000 bytes | limits |
| Max bound parameters per query | 100 | limits |
| FTS5 full-text search | Supported, incl. `fts5vocab` | [D1 SQL statements](https://developers.cloudflare.com/d1/sql-api/sql-statements/) |
| Export limitation | Not supported for databases containing virtual tables — drop, export, recreate | [import/export](https://developers.cloudflare.com/d1/best-practices/import-export-data/) |

**Fit, measured live against production Supabase on 2026-08-12** — not estimated:

| corpus | notes | mean body | largest | total |
|---|---|---|---|---|
| `clients/digithings/` | 1,279 | 854 B | 15,065 B | ~1.09 MB |
| `clients/online-compliance-center/` | 328 | 898 B | 9,740 B | 0.29 MB |

~1.4 MB of markdown against a 500 MB free database — **0.3% utilisation**, and the
largest single note is 0.75% of the 2 MB row cap. Even doubling storage for an FTS5
copy of the text leaves three orders of magnitude of headroom.

### Two databases, not one

`digithings_docs` and `occ_help`, mirroring the Vectorize index split and inheriting
its rationale verbatim: isolation becomes **structural** — an OCC query physically
cannot reach digithings notes — rather than depending on every call site passing the
right filter. Maps 1:1 onto `DIGI_TENANT_CORPUS_MAP` and onto the two Vectorize
indexes that already exist (`digithings_docs`, `occ_help`, both 384-dim, verified on
the account). The free tier allows 10 databases, so this costs nothing.

This matters more here than it did for Vectorize. Today `architecture_notes` is
anon-SELECT across all tenants and `path_prefix` is an advisory argument digigraph
injects, not an auth boundary — so a `get_note(vault_path)` tool against the shared
table would let any caller read another client's corpus. Separate databases make
that impossible by construction.

### Schema (per database)

```sql
CREATE TABLE notes (
  vault_path    TEXT PRIMARY KEY,   -- canonical, NO .md suffix
  title         TEXT NOT NULL,
  body          TEXT NOT NULL,
  frontmatter   TEXT NOT NULL,      -- JSON blob
  parent_doc    TEXT,               -- for sibling / whole-document queries later
  segment_index INTEGER,
  updated_at    TEXT NOT NULL
);
CREATE INDEX notes_parent ON notes(parent_doc, segment_index);

CREATE VIRTUAL TABLE notes_fts USING fts5(title, body, content='notes', content_rowid='rowid');
```

External-content FTS5 (`content='notes'`) avoids duplicating the text. Because sync
is a **full republish**, the index is rebuilt in the same transaction rather than
maintained by triggers — simpler, and it sidesteps trigger/`content=` drift.

`frontmatter` stays a JSON blob rather than exploded columns: the five keys #2234
carries (`segment_label`, `segment_index`, `parent_doc`, `source_url`, `page_class`)
plus `client`, `content_type`, `page_class`, `tags`, `type` are all present today,
and only `parent_doc`/`segment_index` need to be queryable — those are promoted to
real columns.

### Backend selection — presence, not a flag

Neither option offered during design review is used. digivault selects D1 **when D1
is configured**, following the precedent already set by `digisearch`'s
`_stub.py` registration-order dispatch and by `VectorizeBackend`:

1. `D1_ACCOUNT_ID` + `D1_API_TOKEN` + a database id for the corpus → `D1Store`
2. else `CORE_SUPABASE_*` set → `SupabaseStore` (unchanged; local/dev)
3. else `DIGIVAULT_ROOT` → filesystem vault (unchanged; local/offline)

This is strictly better than both options put to review: no new flag to document,
and no overloading of "`DIGIVAULT_ROOT` is empty". `entrypoint.sh` keeps its
`DATA_VAULT` default, its `mkdir -p` under `set -eu`, and its seed loop exactly as
they are — the boot hazard that made blocker 2 delicate simply never arises.

### `vault_path` normalisation

The shared key between a digisearch hit and a vault note is `vault_path`, and it is
exact — but the two existing producers disagree on the suffix: `search_local_vault`
emits it **with** `.md`, Supabase **without**. D1 stores the canonical
extension-less form, and the tool boundary strips one trailing `.md`. This is a real
translation hazard, not a hypothetical; normalising at one boundary retires it.

### Ingest

**D1 replaces Supabase as the durable note store for the chat corpora.** Owner
direction, 2026-08-12: *"I want to move everything into Cloudflare storage for all
the search and vault storage to minimize dependencies for the chat."* So Supabase
leaves the chat path entirely — not just the runtime read path, but the publish
path too.

The pipeline keeps its current shape with D1 substituted 1:1 for Supabase:

```
run_onboard.py → vault (ephemeral workdir)
                   └→ d1_sync.py        → D1        (durable note store)
                                            └→ vectorize_sync.py → Vectorize
```

`vectorize_sync.py` is repointed to read **D1** rather than Supabase. Keeping a
durable store as the vector source (rather than embedding straight from the
ephemeral workdir) preserves today's most useful property: re-embedding the corpus
does not require re-crawling a client's site.

New `scripts/d1_sync.py`, a sibling of `vectorize_sync.py`: reads the onboard
vault, writes D1, batched `INSERT OR REPLACE` inside the 100 KB statement / 100
bound-parameter caps.

### What stays in Supabase, and why it is not a chat dependency

`architecture_notes` holds three populations, counted live on 2026-08-12:

| population | rows | serves the chat? |
|---|---|---|
| `clients/digithings/` | 1,279 | yes → **moves to D1** |
| `clients/online-compliance-center/` | 328 | yes → **moves to D1** |
| root notes (`api/*`, module names) | 29 | **no** |

The 29 root notes are the legacy repo architecture vault written by
`scripts/sync_architecture_vault.py` + `scripts/gen-api-vault.ts` via
`.github/workflows/sync-architecture-vault.yml`. They are unreachable from the
chat: `DIGI_TENANT_CORPUS_MAP` (`wrangler.toml:85`) scopes both tenants to
`clients/digithings` and `clients/online-compliance-center`, and no tenant maps to
the root. That script is already on the GAPLOG retirement list, so it is left
alone here rather than migrated — moving it would expand this change without
removing a chat dependency.

`SupabaseStore` also stays in the digivault codebase as a local/dev backend. This
spec removes Supabase from the **chat's** dependency graph; it does not delete
working code.

### Cutover

1. Create the two D1 databases and apply the schema.
2. One-time backfill: 1,607 notes Supabase → D1 (a `--source supabase` mode on
   `d1_sync.py`, used once and then unused).
3. Verify counts and a sampled body/frontmatter round-trip per corpus.
4. Repoint `vectorize_sync.py` to D1; re-run and confirm vector counts unchanged.
5. Switch `docs-onboard-digithings.yml` from `CORE_SUPABASE_*` to `D1_*` secrets
   and from `sync_onboard_vault.py` to `d1_sync.py`.
6. Configure `D1_*` in the container and confirm digivault serves real notes.

Steps 1–4 are reversible; the chat keeps reading Supabase-free Vectorize
throughout, and digivault keeps serving seed stubs until step 6.

### Container wiring

Three edit sites, copying what `VECTORIZE_*` did in #2222:

- `frontend/digithings-stack-cloudflare/src/index.ts` — add `D1_ACCOUNT_ID`,
  `D1_API_TOKEN`, `D1_DATABASE_MAP` to the `envVars` whitelist **and** the `Env`
  interface. The whitelist is explicit; a `wrangler secret put` alone never reaches
  the container.
- `container/entrypoint.sh` — no change to `DIGIVAULT_ROOT` handling (see above);
  export the D1 vars only.
- `wrangler.toml` — leave `DIGIVAULT_ROOT=/data/vault` in place; the seed vault
  stays as the offline fallback.

### Prerequisite (human action)

**A Cloudflare API token with D1 edit is required.** Verified 2026-08-12: the
existing token authenticates against Vectorize (both indexes listed) but returns
`Authentication error` (code 10000) on `GET /accounts/{id}/d1/database`. Either
widen that token or mint a second one. Token creation is not something an agent
should do.

## Part 2 — the chat becomes agentic (#2240)

### The finding that reshapes this work

**digigraph already has a working multi-round tool-calling loop, and the chat path
already calls it.** `digillm.client.run_tools`
([client.py:1969](../../../digillm/src/digillm/client.py)) iterates
`for round_idx in range(max_tool_rounds)` with `tool_choice="auto"`, appends
`{"role": "assistant", "tool_calls": [...]}`, parses and executes each call,
appends each `{"role": "tool", ...}` result, and loops — streaming deltas via
`on_tool_step`. `_run_document_rag_path` invokes it at
[research.py:482](../../../digigraph/src/digigraph/graph/research.py).

The chat is non-agentic for exactly one reason: `_strip_tools_by_name` empties the
tool list five lines earlier. `tests/dg/test_nodes.py:139` already proves the
model-driven path works end to end when tools survive.

So #2240 is **"stop disabling the loop"**, not "build one". There is no LangGraph
`ToolNode`, no `create_react_agent`, and none is needed.

**Correction to the issue as filed:** #2240 states `DIGI_ALLOWED_TOOLS` decides the
production allowlist. It does not — the mounted project YAML outranks it. The
conclusion (an empty tool list) is right; the mechanism named is wrong. To be
corrected on the issue.

### Changes

1. **Delete the prefetch.** Remove the `always_retrieve_tools` block
   (research.py:403-429), `_strip_tools_by_name`, and `_format_prefetch_context`.
   Owner decision: drop entirely rather than keep-and-unstrip or gate. This is the
   only option that satisfies *"a turn needing no retrieval performs none"*, and it
   kills the flattened-transcript query problem at the root instead of treating it
   (the stopword strip in #2114 treated the symptom).
2. **Tool surface** = `digisearch`, `digivault_search_notes`, **`digivault_get_note`**
   (new). Owner decision: `get_note` keyed on `vault_path` only — the smallest
   surface that makes locate-then-load expressible, and it matches the key
   digisearch hits already carry. A whole-document `get_document(parent_doc)` is
   deliberately **not** built yet; the schema's `notes_parent` index leaves the door
   open.
3. **Round budget.** `max_tool_rounds` defaults to 5 and is currently not passed
   from `research.py`. Pass it explicitly — proposed **4** — so the ceiling is a
   decision on the record rather than a library default.
4. **Activity UI.** Emit a trace for every model-emitted tool call, including ones
   returning zero hits (today only `rag_sources` produces a span, so an empty
   search is invisible and indistinguishable from a turn that correctly retrieved
   nothing). Include the query string in the `rag_sources` payload — the digichat
   mapper already has a slot the server never fills.
5. **Prompts.** Remove *"Those tools were prefetched — do not ask to re-run them"*
   from `config/dogfood-digiproject.yaml` and
   `infra/digichat-release/config/digiproject.yaml`.
6. **Tests.** `tests/dg/test_research_prefetch.py` asserts `captured["tools"] == []`
   and must be rewritten to assert the opposite. `digigraph/ARCHITECTURE.md:397`
   documents the strip and must be updated.

### Risks

- **Latency and cost.** Up to 4 completions per chat turn where there is now
  exactly 1, plus one extra round before any retrieval happens (the cost of
  dropping prefetch). Needs measuring on the real deployment before it ships.
- **Free-tier model tool-calling reliability.** The chat profile pins a free-tier
  model; small models emit malformed tool calls more often. If reliability is poor,
  the choice is a better pinned model for this profile, not reinstating prefetch.
- **Rate limiting.** `orchestrator_invoke` is capped at 10 req/min. A
  search-then-load-N loop can reach that within one turn. Confirm the cap applies
  per-session and raise it for this path if so.
- **Profile A** (multi-image, no digisearch) never enters `_run_document_rag_path`.
  Declared **out of scope**; it keeps today's behaviour.

## The dependency graph this produces

The point of the change, stated plainly. **Before**, a chat turn's storage path
touched two vendors:

```
chat → digisearch → Vectorize        (Cloudflare)
     → digivault  → /data/vault      (baked seed stubs — the #2239 bug)
                    …intended: Supabase
publish: vault → Supabase → Vectorize
```

**After**, one vendor, and one credential pair:

```
chat → digisearch → Vectorize        (Cloudflare)
     → digivault  → D1               (Cloudflare)
publish: vault → D1 → Vectorize
```

Supabase, `psycopg`/`supabase-py`, the `[supabase]` extra, the `CORE_SUPABASE_*`
secrets, and migration 068's RPC all leave the chat's path. The container reaches
both stores the same way — HTTPS + `Authorization: Bearer` — so there is one auth
story, one failure mode, and one place to look when retrieval misbehaves.

## Non-goals

- **Deleting `SupabaseStore` or the filesystem vault.** Both remain as digivault
  backends for local/dev and offline work. This removes Supabase from the chat's
  dependency graph, not from the codebase.
- **Migrating the 29 legacy root architecture notes.** They serve no tenant and are
  already flagged for retirement; moving them would grow this change without
  removing a chat dependency.
- **A whole-document fetch tool.** `get_note` only; the `notes_parent` index leaves
  the door open.
- **Vector and keyword search sharing one query planner** — they stay independent
  tools the model composes.

## Acceptance

- An OCC chat query returns vault hits under `clients/online-compliance-center/`
  that are not `seed-*.md`.
- The model, not the framework, decides when to search and writes its own query.
- Asking "hi" performs zero retrievals.
- A locate-then-load turn is observable in the activity UI as: `digisearch` →
  `digivault_get_note(vault_path=…)` → answer.
- With D1 unconfigured, digivault falls back cleanly and says so — no silent empty
  results.
