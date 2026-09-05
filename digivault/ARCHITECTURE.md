# digivault – Architecture

`digivault` is the **Obsidian-style markdown vault service** for the digithings
monorepo. It manages the creation, storage, and maintenance of a folder of
markdown notes: YAML frontmatter, `[[wikilinks]]`, backlinks, tags, and a folder
taxonomy. The first consumer is the project's own documentation (`docs/vision/`),
migrated to a managed vault so ideation and maintenance compound instead of
drifting.

It is split into a **pure-Python core library** (no FastAPI, side-effect-free on
import) and a thin **service layer** (FastAPI + MCP + CLI) behind the `[service]`
extra.

## Non-negotiables

- Python 3.12, Pydantic v2, full type hints, ruff line-length 100.
- Core hard deps: `pydantic>=2`, `pyyaml>=6` only. `import digivault` never
  imports FastAPI, uvicorn, mcp, or typer.
- Service deps live in the `[service]` extra; auth, tracing, metrics, and error
  envelopes reuse `digikey` + `digibase` (the service does **not** modify
  `digikey`).
- Result types are Pydantic models (`Note`, `LintReport`, …), never bare dicts.
- All write paths are sandboxed to the vault root — `Vault` refuses path
  traversal (`../`) and absolute escapes.

## Module map

| Module | Responsibility |
|--------|----------------|
| `digivault/models.py` | Pydantic v2 result models: `Note`, `LinkRef`, `ValidationIssue`, `LintReport`, `VaultConfig`, `NoteRow` (shared list-notes shape — not the same shape as `Note`, hence the distinct name — returned by both `SupabaseStore.list_notes` and `D1Store.list_notes`. `scripts/vectorize_sync.py` reads only `D1Store.list_notes` since #2239 repointed it from Supabase to D1; `SupabaseStore.list_notes` now has exactly one caller, `scripts/d1_sync.py --from-supabase`'s one-time backfill), `VaultSearchHit` (shared ranked-hit shape for both `SupabaseStore.search` and `D1Store.search`), `NoteDetail` (one note whole: body + frontmatter together — what a by-path fetch returns; also carries `segment_label` as its own top-level field, mirrored by `D1Store.get_note` out of `frontmatter["segment_label"]` — there is no dedicated D1 column for it, unlike `segment_index` — because the original Task 3 brief documented `{vault_path, title, body_markdown, frontmatter, segment_label}` as the returned shape and a consumer reading `segment_label` at that top level would otherwise find nothing, #2239 review). |
| `digivault/frontmatter.py` | Round-trip-safe YAML frontmatter `split` / `dump` / `set_keys` (PyYAML). `split(dump(fm, body)) == (fm, body)`. |
| `digivault/wikilinks.py` | Parse `[[note]]`/`[[note#h\|alias]]`/`![[embed]]`; `rewrite_target` / `map_targets` rewrite links while skipping code spans/blocks. |
| `digivault/vault.py` | `Vault` / `FilesystemStore` — load a directory (or any store via `Vault.from_sources`), build the note index + link graph + backlinks + tag index; maintenance ops (`create_note`, `write_note(..., overwrite=True)` for idempotent upserts, `prune_children(parent_doc, keep_names, subdir)` for scoped docs_onboard convergence, `rename` with inbound-link rewrite, `set_frontmatter`, `reindex`, `lint`, `neighbors`). `FilesystemStore` is the explicit filesystem `VaultStore` name (#1142); `Vault` remains the public type. |
| `digivault/store.py` | `VaultStore` protocol (#1142) — `list_notes`, `read_text`, `backlinks`, `search_by_tag`, `neighbors`, `reindex`, `create_note`, `set_frontmatter`, `rename`. Implemented by `FilesystemStore` and `PostgresStore`. |
| `digivault/postgres_store.py` | `PostgresStore` — read/write `knowledge_notes` filtered by a `vault` namespace column; backlinks/tags/neighbors from the `wikilinks`/`tags` columns (no markdown parse at serve time). `reindex` pages with `.order("vault_path").range(...)` until a short page so PostgREST's max-rows cap cannot silently drop notes. `rename` inserts the destination (never upsert) so a collision cannot overwrite an existing `(vault, vault_path)`. `from_env` requires a service-role key — anon keys are refused because migration 118 enables RLS with no anon policy. Optional `[supabase]` extra, lazily imported via `from_env`. |
| `digivault/local_search.py` | Filesystem keyword search for `digivault_search_notes` when `DIGIVAULT_ROOT` is set (Profile A / client vaults). Optional `path_prefix` filter for multi-tenant corpora. Query tokens drop common English stopwords so a broad, question-shaped query does not score every note. Returns `VaultSearchHit` rows; no network. |
| `digivault/supabase_store.py` | `SupabaseStore` — read a vault out of Supabase (`architecture_notes`/`knowledge_notes`) and reconstruct it via `Vault.from_sources`; FTS `search` via the `search_architecture_notes` RPC (optional `path_prefix`; migration 068). Optional `[supabase]` extra, lazily imported. |
| `digivault/d1_errors.py` | `D1StoreError(RuntimeError)` — isolated in its own module so it stays importable even if importing `d1_store.py` fails (mirrors `digisearch`'s `vectorize_errors.py`). |
| `digivault/d1_store.py` | `D1Store` — read-only Cloudflare D1 REST-API client for one corpus's note database: FTS5 `search`, `get_note` (by exact `vault_path`), paginated `list_notes`. One database per corpus, so `path_prefix` isolation for `search`/`list_notes` is a SQL filter, while a by-path fetch is scoped by which database `server.py` opens at all (see `_open_d1_store`). `normalize_vault_path`, `build_fts_match`, and `resolve_path_prefix` also live here — the last is public (no leading underscore) specifically so `server.py`'s by-path route can call it too, sharing the "a non-`None` prefix that normalizes to empty is rejected, not silently treated as unscoped" rule instead of reimplementing it (a #2239 review found the by-path route's own reimplementation got this wrong). Credentials are constructor args, never read from the environment inside this class — `server.py` reads env. `query()` (the one call site every read/write goes through, including `scripts/d1_sync.py`'s schema init/upsert/FTS rebuild) retries up to `MAX_ATTEMPTS` (3) with exponential backoff plus jitter on a transport error or a status `_is_retryable_status` accepts — 429, 5xx, and (deliberately, see its docstring) 401, verified transient against a live cutover that hit three of them in one session. Every other status (400/403/404/422/other 4xx) fails on the first attempt. Backoff is delivered through an injectable `sleep` constructor arg (default `time.sleep`), mirroring `http_post`'s DI so tests never really sleep. Retrying writes too is safe only because they're idempotent by construction: the schema DDL is `CREATE ... IF NOT EXISTS`, the upsert is `ON CONFLICT(vault_path) DO UPDATE`, and the FTS rebuild fully re-derives the index rather than appending. |
| `digivault/path_scopes.py` | digikey scope policy: reads need `digivault:read`, writes `digivault:write`. `POST /v1/notes/by-path` is scoped `digivault:read` despite being POST — it's a read (body carries `vault_path`/`path_prefix`), not a mutation; the carve-out matches on method as well as path, so a hypothetical future non-POST verb on the same literal path is not silently read-scoped. |
| `digivault/tenant_scope.py` | `enforce_tenant_path_prefix` — binds a caller-supplied `path_prefix` to the tenant named in their verified JWT (`request.state.digi_auth.tenant_slug`) via `DIGI_TENANT_CORPUS_MAP`, server-side, in digivault itself. `digivault:read`/`digivault:write` prove a caller may use these routes at all, not which corpus they're entitled to; this closes that gap for a caller that talks to digivault directly, bypassing digigraph entirely (found in CodeRabbit's review of promotion PR #2293) — complementary to, and independent of, digigraph's own #2265 fix (below), which protects the model → digigraph leg but has no visibility into a direct caller of this API. No-op when `DIGI_TENANT_CORPUS_MAP` is genuinely unset (single-tenant deployments); fails closed (`403`) once it is set. `TenantCorpusMapError` distinguishes "unset" from "set but unusable" (bad JSON, or every entry individually malformed) — the latter is `503`, never silently treated as unset (a second CodeRabbit finding, on this module's own PR #2298). |
| `digivault/orchestrator_tools.py` | OpenAI-style tool manifest fetched by digigraph via `POST /v1/orchestrator_tools`. Tool **names** re-export from `tool_dispatch.py` (canonical). Manifest covers tag search, backlinks, lint, create-note, `digivault_search_notes` (D1 when configured; else local vault when `DIGIVAULT_ROOT` set; else Supabase FTS), and `digivault_get_note` (load one or more notes whole by `vault_path` / `vault_paths` for locate-then-load after a search hit; D1-only, no filesystem/Supabase fallback — every call 503s on a non-D1 deployment). Singular `vault_path` keeps the original single-`NoteDetail` response shape. Plural `vault_paths` (max 20 after dedup; oversized batches return `ok=False`) returns `{"notes": [...], "errors": {...}}` with per-path errors — `ok=True` even when every path failed, so a partial batch remains usable. `/v1/orchestrator_invoke` dispatches vault-local tools through `tool_dispatch.dispatch_vault_tool` and `digivault_get_note` through the same `_fetch_note_by_path` helper `POST /v1/notes/by-path` uses (Task 3) — one enforcement point for the `path_prefix` authorization boundary across both surfaces, including normalizing a present-but-blank `path_prefix` ("", "/", "   ", ".md") to the same `ok=False` refusal as an omitted one rather than letting it fall through to a raised `HTTPException(400)` (#2239 review). **Now wired end-to-end from digigraph**: both tools are registered in digigraph's orchestrator registry (`orchestration/builtin.py`) and bundled in the `digivault` skill, so the model can call `digivault_get_note` as well as `digivault_search_notes`. `_handle_digivault_search` and `_handle_digivault_get_note` both overwrite the `path_prefix` argument from `ToolContext.vault_path_prefix` unconditionally before invoking — a model-supplied `path_prefix` is always discarded, not merely defaulted when the model omits it — so a model cannot select another tenant's corpus (#2265, closed by #2240). With no context prefix (an unmapped tenant slug), `path_prefix` is passed through as `None`; both dispatch branches refuse with `ok=False` rather than falling back to an unscoped read on the D1 path (D1 has no unscoped mode). `digivault_get_note`'s manifest entry declares `path_prefix` as a required parameter for the same reason `POST /v1/notes/by-path` does — the server handler requires it either way, so leaving it undeclared would only hide the requirement without buying any isolation (#2239 review). digivault's own server (`tenant_scope.py`, above) now also rejects a mismatched `path_prefix` outright once `DIGI_TENANT_CORPUS_MAP` is configured, independent of whether digigraph's overwrite ran first — two layers, not one. |
| `digivault/tool_dispatch.py` | **Canonical vault tool routing (#1188).** Owns every digivault tool name (`DISPATCH_TOOL_NAMES`), the vault-local handler table (`VAULT_HANDLERS` for tag / backlinks / lint / create-note), and MCP registration (`register_mcp_tools`). `mcp_server` and `server.orchestrator_invoke` both route vault-local tools through `dispatch_vault_tool` — no duplicate handler tables. Runtime-only tools (`digivault_search_notes`, `digivault_get_note`) claim into the same table via `register_runtime_handler` from `server.py` so `dispatch_tool_names()` equals the full canonical set once the HTTP app is loaded. MCP discovery (`mcp_tool_names()`) equals the vault-local handler set. |
| `digivault/server.py` | FastAPI app: `/healthz`, `/v1/status`, note CRUD, lint, backlinks, tags, orchestrator endpoints, `POST /v1/notes/by-path` (`digivault_search_notes` and the by-path fetch prefer D1 when the shared Cloudflare credential pair (`CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN`, falling back to legacy `VECTORIZE_*`/`D1_*` names — see `_d1_credentials`) plus `D1_DATABASE_MAP` are set — D1 wins even when `DIGIVAULT_ROOT` is also set, see below — otherwise `digivault_search_notes` falls back to local filesystem search, then `SupabaseStore.search`). |
| `digivault/mcp_server.py` | `python -m digivault.mcp_server` — thin transport wrapper; tools register exclusively via `tool_dispatch.register_mcp_tools` (streamable HTTP, default `127.0.0.1:8766`). |
| `digivault/cli.py` | `digivault init|lint|reindex|new-note`. |

## Public API (core)

```python
from digivault import (
    Vault, FilesystemStore, VaultStore, VaultError, VaultConfig,
    Note, LinkRef, LintReport, ValidationIssue,
    parse_links, rewrite_target,
    split_frontmatter, dump_frontmatter, set_keys,
)

vault = FilesystemStore("docs/vision")  # or Vault(...) — same filesystem backend
vault.list_notes()              # -> list[Note] (with backlinks)
vault.backlinks("digigraph")    # -> tuple[str, ...]
vault.neighbors("digigraph")    # -> tuple[str, ...]  (outlinks ∪ backlinks)
vault.search_by_tag("module")   # -> list[Note]
vault.create_note("execution", frontmatter={"title": "execution"}, body="see [[digiquant]]")
vault.rename("research", "research-research")   # rewrites every inbound [[research]]
report = vault.lint()           # -> LintReport(ok, note_count, issues)

# Postgres-backed knowledge vault (migration 118; needs digivault[supabase]):
# from digivault.postgres_store import PostgresStore
# store = PostgresStore.from_env(vault="finance")
```

## Service topology

- **Port 8004**, host-loopback-bound, under the dedicated `digivault` Compose
  profile (not part of the always-on `core` stack).
- **Auth:** digikey JWT via `DigiAuthMiddleware`; `digivault:read` for GET
  routes, discovery, and `orchestrator_invoke` (most orchestrator tools are
  reads); `digivault:write` for mutating note routes. `orchestrator_invoke`'s
  one mutating tool (`digivault_create_note`) enforces `digivault:write` itself
  in the handler (`_require_tool_scope`, keyed on the requested tool name) since
  the shared endpoint can't scope by path alone. `/healthz`, `/v1/status`,
  `/metrics`, OpenAPI are auth-exempt.
- **Vault root:** `DIGIVAULT_ROOT` (required for filesystem-backed note routes;
  those return 503 when unset). **Exception:** `POST /v1/notes/by-path` is D1-only
  and opens D1 directly (`_fetch_note_by_path`) — it needs no `DIGIVAULT_ROOT` at
  all. Single HTTP requests build a fresh vault for cross-process filesystem
  correctness. `POST /v1/notes/batch` opens it once and applies its writes and
  stale-child pruning incrementally, so bulk ingest is linear rather than
  rescanning the corpus for every note.
- **Note upsert:** `POST /v1/notes` accepts `overwrite: true` (and optional
  `frontmatter`) so docs_onboard can idempotently upsert via
  `Vault.write_note(..., overwrite=True)`. Default `overwrite: false` preserves
  create-only behavior.
- **Scoped child prune:** `POST /v1/notes/prune-children` is write-scoped and removes
  only stale `{parent_doc}__*` segment notes with matching `parent_doc` frontmatter
  inside the requested subdirectory. docs_onboard invokes it after writing the current
  children and hub, making structural re-ingests converge without exposing a general
  recursive-delete or MCP capability (#2190).
- **By-path fetch:** `POST /v1/notes/by-path` loads one note whole (body +
  frontmatter, as `NoteDetail`) by its exact `vault_path`, from D1 only — there
  is no filesystem/Supabase fallback for this route. `path_prefix` in the
  request body is an **enforced authorization boundary**, not an advisory
  filter: with two client corpora sharing this deployment, a caller scoped to
  one prefix gets `403` if `vault_path` falls outside it, and `404` if the note
  doesn't exist. A `path_prefix` that is present but normalizes to empty
  (`""`, `"/"`, `"///"`, `"   "`, `".md"`) is `400`, not treated as "no prefix" —
  a #2239 review found the original check (`if prefix and ...`) failed open on
  exactly this input, and demonstrated that with a `""` key present in
  `D1_DATABASE_MAP` (now refused outright, see the env var table below) every
  one of those inputs returned another corpus's note with `200`. `path_prefix`
  is a **required** field (`422` if omitted) for the same underlying reason:
  with the `""` key forbidden, an omitted `path_prefix` can never resolve to a
  corpus, so "omitting it means unscoped" is not a real third state — it would
  only ever `503` at request time. Rejected up front at the schema boundary
  instead (#2239 review). Returns `503` if D1 isn't
  configured for the resolved prefix, or if D1 itself fails at query time
  (transport error, expired token) — that failure is caught around the
  `get_note` call itself, not just around opening the store, so it surfaces as
  `503` rather than an unhandled `500`. Scoped `digivault:read` (see
  `path_scopes.py`) even though it's a POST — and only for `POST`; the scope
  carve-out checks method too.
- **Hub:** digigraph discovers tools via `POST /v1/orchestrator_tools` and
  executes via `POST /v1/orchestrator_invoke`.
- **Rate limiting:** per-IP sliding window (in-process `deque` + lock), mirrors
  `digisearch/server.py`. `/v1/orchestrator_invoke`: 10/min; `/v1/orchestrator_tools`:
  30/min; everything else except `/healthz`: 30/min default. Reads the IP from
  `X-Forwarded-For` (first hop) or `request.client.host`; `DIGI_DISABLE_RATE_LIMIT=1`
  disables it (tests); TestClient traffic (`client.host == "testclient"`) is
  exempt so the unit suite doesn't need the env var. Exceeding the limit returns
  429 with `code: rate_limit_exceeded` and a `Retry-After` header.
- **`digivault_search_notes` search precedence:**
  1. If D1 is configured (the shared Cloudflare credential pair —
     `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN`, falling back to legacy
     `VECTORIZE_*` then `D1_*` names, see `_d1_credentials` — plus
     `D1_DATABASE_MAP` all set) → `D1Store.search` (FTS5, Cloudflare D1 REST
     API). **D1 wins even when `DIGIVAULT_ROOT` is also set** — this is the
     #2239 fix: production sets `DIGIVAULT_ROOT=/data/vault` pointing at baked
     seed stubs, and those stubs must never shadow the real D1-backed corpus.
     `path_prefix` selects which corpus's database `_open_d1_store` opens (via
     `D1_DATABASE_MAP`, a JSON object of `{"<vault-prefix>": "<database id>"}`);
     there is no "search across every corpus" mode — one prefix, one database,
     by construction, and `D1_DATABASE_MAP` may not carry a `""` entry to fake
     one (`_open_d1_store` refuses it at config-read time; see the env var
     table below — `orchestrator_invoke` validates the map's shape via
     `_load_d1_database_map` unconditionally, before even looking at
     `path_prefix`, so a malformed map is always `503`, never masked by the
     no-`path_prefix` case below). A prefix with no matching entry is `503`.
     No `path_prefix` at all is reached only when the caller has no mapped
     tenant corpus: digigraph's `_handle_digivault_search` (`builtin.py`)
     overwrites `path_prefix` from `ToolContext.vault_path_prefix`
     unconditionally before invoking (#2265, closed by #2240), so a `None`
     here means "no tenant is mapped for this session," not "the model
     omitted it." This branch still refuses rather than falling back to an
     unscoped read, returning
     `OrchestratorInvokeResponse(ok=False, error="path_prefix is required when
     the D1 backend is configured")` — HTTP `200`, not a raised `400`: digigraph's
     `invoke_digivault_tool` calls `raise_for_status()`, whose `str()` drops the
     response body, so a raised `400` would reach the model as a bare status
     code instead of this sentence — mirrors the `query is required` case just
     above it. A `D1StoreError` raised from inside the `.search()` call itself
     (transport failure, expired token) is `503`, not an unhandled `500`.
  2. Else if `DIGIVAULT_ROOT` is set → filesystem keyword search via
     `local_search.search_local_vault` over that vault (Profile A / client
     volumes; no Supabase required). Optional `path_prefix` isolates client
     subdirs (e.g. `clients/online-compliance-center`).
  3. Else → Supabase FTS via `SupabaseStore.search` (the
     `search_architecture_notes` RPC — always the 3-arg form from migration
     068, with `path_prefix` null when unset; anon-key, read-only); returns
     503 only if
     `CORE_SUPABASE_URL`/`CORE_SUPABASE_ANON_KEY` are unset.
  `limit` is clamped to `[1, 50]` regardless of caller input. A **present**
  `path_prefix` that normalizes to empty (`""`, `"/"`, `"   "`, `"///"`,
  `".md"`) is a **400 at parse time**, before any backend is selected —
  omitting the key (or sending `null`) is the only way to search without a
  prefix. This replaced an earlier coalesce-to-`None`, which treated "the
  caller sent a prefix that means nothing" and "the caller asked for no
  scoping" as the same request and so silently disabled scoping on every
  backend (#2359). `D1Store.search` and `resolve_path_prefix` still raise
  `ValueError` on the same input one layer down — deliberate defense in
  depth, not the primary guard.
  **Two independent enforcement layers now cover `path_prefix`, not one.**
  Layer 1, in digigraph: as of #2240, `_handle_digivault_search` overwrites
  `path_prefix` from `ToolContext.vault_path_prefix` unconditionally,
  discarding whatever the model supplied, closing the original #2265 gap
  (digigraph's since-deleted `always_retrieve_tools` prefetch calling this
  tool with no prefix at all) on digigraph's side — this protects the model →
  digigraph leg. Layer 2, in digivault itself (`tenant_scope.py`'s
  `enforce_tenant_path_prefix`, wired into both this branch and the by-path
  family via `_fetch_note_by_path`): closes a gap CodeRabbit's review of
  promotion PR #2293 found regardless of digigraph's own fix — `digivault:read`
  scope alone proves a caller may use these routes at all, but carries no
  tenant identity, so any caller holding it could name *any* prefix in
  `D1_DATABASE_MAP`, not just the corpus their own credential was issued for.
  Layer 1 alone leaves a caller that talks to digivault directly (any holder
  of a `digivault:read`-scoped JWT hitting this endpoint or
  `/v1/notes/by-path` itself, bypassing digigraph entirely) unprotected —
  Layer 2 closes that residual gap, server-side, independent of whether
  digigraph's own overwrite ran first. Layer 2 reads
  `request.state.digi_auth.tenant_slug` (the same verified claim
  `_require_tool_scope` already reads `.scopes` off of — `digikey` populates
  it on every token its own `/v1/oauth/token` issues; see `tenant_scope.py`'s
  module docstring for a known, tracked residual dependency on that claim's
  trustworthiness, #2303) and checks it against `DIGI_TENANT_CORPUS_MAP`
  (the same env var digigraph's own `corpus_routing.py` reads, parsed
  independently here so digivault stays installable standalone). It is a
  no-op when that map is genuinely unset — single-tenant deployments (local
  dev, a self-hosted single-vault install) see no behavior change — and fails
  closed once it is set: a tenant absent from the map, or a `path_prefix`
  that doesn't match the map's entry for that tenant, is refused with `403`.
  Checked once, before the D1/local-vault/Supabase precedence branch below —
  not only on the D1 path (a second CodeRabbit finding on this same fix's own
  PR #2298: the first version left the other two backends unchecked) — so it
  applies uniformly regardless of which backend a given deployment actually
  uses. **Unset is not the same as broken**: a *non-empty* but unparseable or
  entirely-empty-after-filtering `DIGI_TENANT_CORPUS_MAP` raises
  `TenantCorpusMapError`, surfaced as `503` rather than silently falling
  back to the "map unset, no enforcement" no-op — otherwise an operator who
  turned multi-tenant binding on and typo'd it would see every request pass
  through unscoped with no signal anything was wrong, mirroring the same
  "some set, not all, is unambiguously an error" discipline `_d1_configured()`
  already applies to the D1 credential trio above. The Supabase path is the same
  RPC the digithings.ai chat widget calls directly today
  ([ADR-0018](../docs/adr/0018-digichat-path-routing.md), epic #1248) — wiring
  it into digivault's own orchestrator surface lets digigraph reproduce that
  grounding once the widget is cut over to the digichat gateway. Verified live
  against the core Supabase project (2026-07-01): the RPC returns all eight
  fields `VaultSearchHit` requires, for the query "What does digigraph
  orchestrate?" — top hit was the `digigraph` note at rank 0.49.

## Design decisions

- **Canonical tool dispatch (#1188).** Vault MCP / orchestrator tool names and
  vault-local handlers live in `tool_dispatch.py`. Both `mcp_server` (discovery +
  invoke) and `server.orchestrator_invoke` (vault-local branch) route through
  `VAULT_HANDLERS` / `dispatch_vault_tool` — do not add a parallel `@mcp.tool` or
  if/elif table. `orchestrator_tools.py` re-exports the name constants and owns
  only the OpenAI manifest. Runtime-only tools (`digivault_search_notes`,
  `digivault_get_note`) claim into the same table from `server.py` so
  `dispatch_tool_names() == DISPATCH_TOOL_NAMES` after the HTTP app loads.
  MCP `digivault_search_tag` projects a slim JSON **array** of
  `{name, title, rel_path}` (pre-#3041 contract); orchestrator invoke keeps the
  shared handler’s `{"notes": [...]}` envelope.

  ```
  digigraph / MCP client
        │
        ├─ MCP tools/list ──────────► mcp_server ──register_mcp_tools──► VAULT_HANDLERS
        │                                      │
        ├─ MCP tools/call ─────────────────────┴──► dispatch_vault_tool
        │
        ├─ POST /v1/orchestrator_tools ──► orchestrator_tools (manifest; names from tool_dispatch)
        │
        └─ POST /v1/orchestrator_invoke
                 ├─ search_notes / get_note ──► server.py (D1 / tenant) + register_runtime_handler
                 └─ tag / backlinks / lint / create_note ──► dispatch_vault_tool
  ```

- **Core/service split.** The vault semantics are useful as a library (CI doc
  linting, scripts, other services); FastAPI is an optional delivery surface.
- **Fresh request index, incremental write batch.** A standalone HTTP request
  rebuilds its index from disk, avoiding a cross-process cache-coherency contract.
  Within a `POST /v1/notes/batch` request, `Vault.write_note` and
  `Vault.prune_children` update the in-memory link and parent-child indexes
  incrementally. This keeps bulk ingest linear while preserving a fresh index at
  the next request boundary.
- **Storage is pluggable (filesystem + Postgres + Supabase read path).** digivault
  owns *how knowledge is organized and traversed* (frontmatter, wikilinks,
  backlinks, taxonomy). The on-disk `Vault` / `FilesystemStore` is the default
  `VaultStore` (#1142). `PostgresStore` serves `knowledge_notes` filtered by the
  `vault` namespace column, building the link graph from stored `wikilinks` /
  `tags` (no markdown parse at serve time; migration 118). Table uniqueness is
  `(vault, vault_path)` only — duplicate filename stems in different directories
  are legal, matching the filesystem vault's `_duplicates` / `duplicate_note`
  lint (#3603). It pages `reindex` like `SupabaseStore.list_notes` (deterministic
  `vault_path` order + `.range()` until a short page, default 500) so a vault
  larger than PostgREST's row cap is indexed exactly once. `rename` inserts the
  new `(vault, vault_path)` and fails on unique-constraint conflict without
  modifying the source or the existing destination (#3606). `from_env` takes only
  `CORE_SUPABASE_SERVICE_KEY` / `SUPABASE_SERVICE_ROLE_KEY` (and rejects a JWT
  whose `role` is not `service_role`); an anon-key-only configuration is a
  config error, not an empty vault.
  `Vault.from_sources` still builds the same index from any `(rel_path, text)`
  source, and `supabase_store.SupabaseStore` remains the read-only FTS path for
  `architecture_notes` / legacy callers (#1087) — reconstructed via
  `dump_frontmatter`, served through the anon key. `digistore` (when it ships)
  will own *where bytes live* beneath this; the two remain complementary —
  digivault sits above digistore, not replacing it.
- **Wikilinks, not standard links.** The vault speaks Obsidian `[[...]]`. The
  repo's `scripts/check_doc_links.py` validates only `[text](path)` links, so
  digivault owns wikilink validation via `lint` (wired into `make vault-check`
  when the docs migrate).

## Environment variables

| Var | Purpose |
|-----|---------|
| `DIGIVAULT_ROOT` | Path to the managed vault directory (required for note routes). When set, `digivault_search_notes` searches this local vault first. |
| `DIGIVAULT_MCP_HOST` | MCP bind host (default `127.0.0.1`). |
| `DIGIKEY_JWKS_URL` / `DIGIKEY_ISSUER` / `DIGIKEY_AUDIENCE` / `DIGIKEY_PUBLIC_KEY_PEM` | digikey JWT verification (shared convention). |
| `DIGI_DISABLE_RATE_LIMIT` | `1`/`true`/`yes` disables the per-IP rate limiter (shared convention with digisearch/digigraph; tests only). |
| `CORE_SUPABASE_URL` (or `SUPABASE_URL`) + `CORE_SUPABASE_ANON_KEY` (or `CORE_SUPABASE_SERVICE_KEY` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`) | Fallback for `digivault_search_notes` only when neither D1 nor `DIGIVAULT_ROOT` is configured — `SupabaseStore.from_env` credentials (ADR-0022 naming). Requires the `digivault[supabase]` extra installed. `PostgresStore.from_env` does **not** accept the anon key: set `CORE_SUPABASE_SERVICE_KEY` or `SUPABASE_SERVICE_ROLE_KEY`. Migration 118 makes `knowledge_notes` service-role-only; an anon client would look like an empty vault. |
| `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` + `D1_DATABASE_MAP` | Cloudflare account id, API token, and a JSON object `{"<vault-prefix>": "<database id>"}` mapping each corpus's vault prefix to its D1 database. `CLOUDFLARE_ACCOUNT_ID`/`CLOUDFLARE_API_TOKEN` are canonical (wrangler's own conventional names, #2239 credential rename — the same pair Vectorize uses, see digisearch/ARCHITECTURE.md); each falls back to the legacy `VECTORIZE_ACCOUNT_ID`/`VECTORIZE_API_TOKEN`, then `D1_ACCOUNT_ID`/`D1_API_TOKEN`, names when unset (`_d1_credentials`), so the rename is zero-downtime — no coordinated secret rotation required before deploy. All three (the resolved account id, the resolved token, and `D1_DATABASE_MAP`) must be set for `_d1_configured()` to be true. When configured, D1 is authoritative for both `digivault_search_notes` and `POST /v1/notes/by-path` — it wins over `DIGIVAULT_ROOT` (the #2239 fix). Read only in `server.py` (`_open_d1_store`), never inside `D1Store`. A partial-config error names the canonical var (e.g. `CLOUDFLARE_ACCOUNT_ID`), not whichever legacy alias happened to be left unset — the credential is resolved to one value before the guard runs. **`D1_DATABASE_MAP` must not contain a `""` key** — `_open_d1_store` raises `D1StoreError` at config-read time if it does, regardless of which prefix was requested: a `""` entry would map every prefix that normalizes to empty (`None`, `""`, `"/"`, `"///"`, `"   "`, `".md"`) to a real database, which is precisely the cross-tenant fail-open the by-path route's `resolve_path_prefix` check exists to refuse (#2239 review). |
| `DIGI_TENANT_CORPUS_MAP` | Optional. Same env var digigraph's `corpus_routing.py` reads (a JSON object keyed by tenant slug, each value carrying `vaultPathPrefix`/`vault_path_prefix` among sibling keys digivault ignores) — parsed independently by `tenant_scope.py` rather than imported from the digigraph package, so digivault stays installable standalone. Binds every caller-supplied `path_prefix` — checked once, before the D1/local-vault/Supabase precedence branch, so all three backends are covered uniformly — to the tenant named in the caller's verified JWT (`request.state.digi_auth.tenant_slug`, set by `DigiAuthMiddleware`, already installed here). Genuinely unset — the default, e.g. local dev, a self-hosted single-vault install — this is a no-op; every existing single-tenant deployment is unaffected. Set, it fails closed: a `path_prefix` that doesn't match the map's entry for the caller's tenant, or a tenant absent from the map entirely, is `403`. **Set but unparseable, non-object, or every entry individually malformed is `503`**, not silently treated as unset — `TenantCorpusMapError` keeps a config typo from disabling enforcement without telling anyone, mirroring `D1_DATABASE_MAP`'s own "some set, not all, is always an error" discipline above. Closes a gap CodeRabbit's review of promotion PR #2293 found: `digivault:read` alone let any caller name any prefix in `D1_DATABASE_MAP`, not just their own corpus's — digigraph's own #2265 fix only protects the model → digigraph leg, not a caller hitting this API directly. |

## Testing

`tests/dv/` — `@pytest.mark.unit`, deterministic, filesystem via `tmp_path`.
Core tests (frontmatter, wikilinks, vault) need only `pydantic` + `pyyaml`.
Service and CLI tests `pytest.importorskip` their extras so the suite stays green
without `digivault[service]` installed. CI (`.github/workflows/test-digivault.yml`)
installs `digibase` + `digikey` + `digivault[service]` and runs the full set.
`digivault_search_notes` tests cover all three paths: D1-path tests fake
`_open_d1_store`; local-root searches exercise `local_search` against a
`tmp_path` vault; Supabase-path tests fake `SupabaseStore` directly
(constructor takes any `SupabaseClientProtocol`) — the real `supabase` package
(`[supabase]` extra) is never required to run the suite, matching
`test_supabase_store.py`'s convention. `test_vault_store.py` fakes PostgREST
`max-rows` truncation so `PostgresStore.reindex` pagination, cross-page
backlinks/tags/`get_note`/`read_text`, rename collisions beyond page one, and
service-role-only `from_env` are covered without a network (#3606). `test_d1_store.py` runs `D1Store`'s real
SQL against an in-memory SQLite/FTS5 connection rather than canned fixtures, so
a regression in the SQL text itself fails the test. `POST /v1/notes/by-path`
tests cover the 403 (out-of-prefix), 404 (absent note), 503 (D1 unconfigured or
a runtime `D1StoreError` from `.get_note()` itself, e.g. a transport failure),
400 (a `path_prefix` present but normalizing to empty — parametrized over `""`,
`"/"`, `"///"`, `"   "`, `".md"`, each asserting the fake store is never even
opened), and 200 paths, plus a `TestClient` request proving the route isn't
shadowed by `GET /v1/notes/{name}`. `digivault_search_notes`'s D1 branch has
its own `ok=False` (no `path_prefix` while D1 is configured, with a well-formed
map) and 503 (malformed `D1_DATABASE_MAP` regardless of `path_prefix`,
misconfigured prefix, or a runtime `D1StoreError` from `.search()` itself) tests,
and `_load_d1_database_map`/`_open_d1_store` have dedicated tests for the
`D1_DATABASE_MAP` `""`-key guard. `POST /v1/notes/by-path`'s `path_prefix` being a
required field is covered by a `pydantic.ValidationError` test (422 boundary).

## Monorepo integration

Registered in `pytest.ini`, `scripts/ci_paths.yaml` (→ `ci.yml`),
`.github/workflows/test-digivault.yml`, `docker-compose.yml` (profile
`digivault`, port 8004), root `ARCHITECTURE.md` topology, `README.md`, and
`CLAUDE.md`. Human follow-ups: `CODEOWNERS`, `scripts/commit_helper.sh`
`VALID_COMPONENTS`, `scripts/project_routing.json`.
