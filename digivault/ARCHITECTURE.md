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
| `digivault/models.py` | Pydantic v2 result models: `Note`, `LinkRef`, `ValidationIssue`, `LintReport`, `VaultConfig`, `NoteRow` (validated Supabase notes-table row; used by `SupabaseStore.list_notes` and `scripts/vectorize_sync.py` — not the same shape as `Note`, hence the distinct name), `VaultSearchHit` (shared ranked-hit shape for both `SupabaseStore.search` and `D1Store.search`), `NoteDetail` (one note whole: body + frontmatter together — what a by-path fetch returns). |
| `digivault/frontmatter.py` | Round-trip-safe YAML frontmatter `split` / `dump` / `set_keys` (PyYAML). `split(dump(fm, body)) == (fm, body)`. |
| `digivault/wikilinks.py` | Parse `[[note]]`/`[[note#h\|alias]]`/`![[embed]]`; `rewrite_target` / `map_targets` rewrite links while skipping code spans/blocks. |
| `digivault/vault.py` | `Vault` — load a directory (or any store via `Vault.from_sources`), build the note index + link graph + backlinks + tag index; maintenance ops (`create_note`, `write_note(..., overwrite=True)` for idempotent upserts, `rename` with inbound-link rewrite, `set_frontmatter`, `reindex`, `lint`). |
| `digivault/local_search.py` | Filesystem keyword search for `digivault_search_notes` when `DIGIVAULT_ROOT` is set (Profile A / client vaults). Optional `path_prefix` filter for multi-tenant corpora. Query tokens drop common English stopwords so full-prompt prefetch does not score every note. Returns `VaultSearchHit` rows; no network. |
| `digivault/supabase_store.py` | `SupabaseStore` — read a vault out of Supabase (`architecture_notes`/`knowledge_notes`) and reconstruct it via `Vault.from_sources`; FTS `search` via the `search_architecture_notes` RPC (optional `path_prefix`; migration 068). Optional `[supabase]` extra, lazily imported. |
| `digivault/d1_errors.py` | `D1StoreError(RuntimeError)` — isolated in its own module so it stays importable even if importing `d1_store.py` fails (mirrors `digisearch`'s `vectorize_errors.py`). |
| `digivault/d1_store.py` | `D1Store` — read-only Cloudflare D1 REST-API client for one corpus's note database: FTS5 `search`, `get_note` (by exact `vault_path`), paginated `list_notes`. One database per corpus, so `path_prefix` isolation for `search`/`list_notes` is a SQL filter, while a by-path fetch is scoped by which database `server.py` opens at all (see `_open_d1_store`). `normalize_vault_path`, `build_fts_match`, and `resolve_path_prefix` also live here — the last is public (no leading underscore) specifically so `server.py`'s by-path route can call it too, sharing the "a non-`None` prefix that normalizes to empty is rejected, not silently treated as unscoped" rule instead of reimplementing it (a #2239 review found the by-path route's own reimplementation got this wrong). Credentials are constructor args, never read from the environment inside this class — `server.py` reads env. |
| `digivault/path_scopes.py` | digikey scope policy: reads need `digivault:read`, writes `digivault:write`. `POST /v1/notes/by-path` is scoped `digivault:read` despite being POST — it's a read (body carries `vault_path`/`path_prefix`), not a mutation; the carve-out matches on method as well as path, so a hypothetical future non-POST verb on the same literal path is not silently read-scoped. |
| `digivault/orchestrator_tools.py` | OpenAI-style tool manifest fetched by digigraph via `POST /v1/orchestrator_tools`: tag search, backlinks, lint, create-note, `digivault_search_notes` (D1 when configured; else local vault when `DIGIVAULT_ROOT` set; else Supabase FTS), and `digivault_get_note` (load one note whole by `vault_path` for locate-then-load after a search hit). `digivault_get_note` is D1-only, same as its `POST /v1/notes/by-path` backing route (Task 2), and `/v1/orchestrator_invoke` now dispatches it through the same `_fetch_note_by_path` helper the route uses (Task 3) — one enforcement point for the `path_prefix` authorization boundary across both surfaces. **Not yet usable from digigraph in production**: `builtin.py`'s tenant-context injection (`_handle_digivault_search`, `builtin.py:227`) only covers `digivault_search_notes`, and no tool is registered for `digivault_get_note` in digigraph's orchestrator registry at all — the model cannot call it as a chat tool until digigraph adds both. The dispatch branch itself refuses (`ok=False`) rather than defaulting to an unscoped read when `path_prefix` is absent, so this is a capability gap, not a safety gap. `digivault_search_notes`'s `path_prefix` argument is a search filter, not an enforced boundary — digigraph only fills it in when the model omits it (`builtin.py`'s `_handle_digivault_search`), so a model-supplied value is not checked against the caller's own scope (digigraph #2265). |
| `digivault/server.py` | FastAPI app: `/healthz`, `/v1/status`, note CRUD, lint, backlinks, tags, orchestrator endpoints, `POST /v1/notes/by-path` (`digivault_search_notes` and the by-path fetch prefer D1 when `D1_ACCOUNT_ID`/`D1_API_TOKEN`/`D1_DATABASE_MAP` are set — D1 wins even when `DIGIVAULT_ROOT` is also set, see below — otherwise `digivault_search_notes` falls back to local filesystem search, then `SupabaseStore.search`). |
| `digivault/mcp_server.py` | `python -m digivault.mcp_server` — vault tools over MCP (streamable HTTP, default `127.0.0.1:8766`). |
| `digivault/cli.py` | `digivault init|lint|reindex|new-note`. |

## Public API (core)

```python
from digivault import (
    Vault, VaultError, VaultConfig,
    Note, LinkRef, LintReport, ValidationIssue,
    parse_links, rewrite_target,
    split_frontmatter, dump_frontmatter, set_keys,
)

vault = Vault("docs/vision")
vault.list_notes()              # -> list[Note] (with backlinks)
vault.backlinks("digigraph")    # -> tuple[str, ...]
vault.search_by_tag("module")   # -> list[Note]
vault.create_note("kairos", frontmatter={"title": "Kairos"}, body="see [[digiquant]]")
vault.rename("atlas", "atlas-research")   # rewrites every inbound [[atlas]]
report = vault.lint()           # -> LintReport(ok, note_count, issues)
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
- **Vault root:** `DIGIVAULT_ROOT` (required for any note route; routes return
  503 when unset). The vault is re-read from disk per request — small docs vault,
  correctness over caching.
- **Note upsert:** `POST /v1/notes` accepts `overwrite: true` (and optional
  `frontmatter`) so docs_onboard can idempotently upsert via
  `Vault.write_note(..., overwrite=True)`. Default `overwrite: false` preserves
  create-only behavior.
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
  1. If D1 is configured (`D1_ACCOUNT_ID` + `D1_API_TOKEN` +
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
     No `path_prefix` at all (the common case: `always_retrieve_tools` calls
     this tool on every chat turn with none, #2265) returns
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
  `limit` is clamped to `[1, 50]` regardless of caller input. An empty-ish
  caller-supplied `path_prefix` (`""`, `"/"`, ...) is coalesced to `None`
  ("no prefix") before it reaches any backend — `D1Store.search` deliberately
  raises `ValueError` for a non-`None` prefix that normalizes to empty (a
  caller bug, not an isolation boundary to skip), so this coalescing is load-
  bearing for the D1 path, not just cosmetic.
  **`path_prefix` here is a filter, not an authorization boundary** — unlike
  the by-path route's `403` check, nothing on this path verifies that the
  caller (or the model calling this tool on the caller's behalf) is entitled
  to the prefix it supplies; `digivault:read` scope is all `orchestrator_invoke`
  requires, and the prefix arrives as an ordinary tool-call argument the model
  chooses. Tenant isolation for search depends entirely on whoever calls this
  tool (digigraph) always attaching the right prefix — #2265 tracks that
  digigraph's `always_retrieve_tools` currently attaches none. digivault's own
  half of that is only to fail honestly (`ok=False`, above) rather than silently
  search unscoped; it cannot itself authenticate a `path_prefix` it did not
  choose. The Supabase path is the same
  RPC the digithings.ai chat widget calls directly today
  ([ADR-0018](../docs/adr/0018-digichat-path-routing.md), epic #1248) — wiring
  it into digivault's own orchestrator surface lets digigraph reproduce that
  grounding once the widget is cut over to the digichat gateway. Verified live
  against the core Supabase project (2026-07-01): the RPC returns all eight
  fields `VaultSearchHit` requires, for the query "What does digigraph
  orchestrate?" — top hit was the `digigraph` note at rank 0.49.

## Design decisions

- **Core/service split.** The vault semantics are useful as a library (CI doc
  linting, scripts, other services); FastAPI is an optional delivery surface.
- **Re-read per request.** A documentation vault is small; recomputing the index
  from disk avoids a whole class of cache-coherency bugs. If a large vault ever
  needs it, add an explicit cache behind `reindex`.
- **Storage is pluggable (filesystem + Supabase).** digivault owns *how knowledge
  is organized and traversed* (frontmatter, wikilinks, backlinks, taxonomy). The
  on-disk `Vault(root)` is the default; `Vault.from_sources` builds the same index
  from any `(rel_path, text)` source, and `supabase_store.SupabaseStore` reads a
  vault out of Postgres (`architecture_notes` / `knowledge_notes`, #1087) — read-only,
  reconstructed via `dump_frontmatter`, served to agents through the anon key.
  `digistore` (when it ships) will own *where bytes live* beneath this; the two
  remain complementary — digivault sits above digistore, not replacing it.
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
| `CORE_SUPABASE_URL` (or `SUPABASE_URL`) + `CORE_SUPABASE_ANON_KEY` (or `CORE_SUPABASE_SERVICE_KEY` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`) | Fallback for `digivault_search_notes` only when neither D1 nor `DIGIVAULT_ROOT` is configured — `SupabaseStore.from_env` credentials (ADR-0022 naming). Requires the `digivault[supabase]` extra installed. |
| `D1_ACCOUNT_ID` + `D1_API_TOKEN` + `D1_DATABASE_MAP` | Cloudflare account id, API token, and a JSON object `{"<vault-prefix>": "<database id>"}` mapping each corpus's vault prefix to its D1 database. All three must be set for `_d1_configured()` to be true. When configured, D1 is authoritative for both `digivault_search_notes` and `POST /v1/notes/by-path` — it wins over `DIGIVAULT_ROOT` (the #2239 fix). Read only in `server.py` (`_open_d1_store`), never inside `D1Store`. **`D1_DATABASE_MAP` must not contain a `""` key** — `_open_d1_store` raises `D1StoreError` at config-read time if it does, regardless of which prefix was requested: a `""` entry would map every prefix that normalizes to empty (`None`, `""`, `"/"`, `"///"`, `"   "`, `".md"`) to a real database, which is precisely the cross-tenant fail-open the by-path route's `resolve_path_prefix` check exists to refuse (#2239 review). |

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
`test_supabase_store.py`'s convention. `test_d1_store.py` runs `D1Store`'s real
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
