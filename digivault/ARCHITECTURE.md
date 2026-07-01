# DigiVault – Architecture

`digivault` is the **Obsidian-style markdown vault service** for the DigiThings
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
| `digivault/models.py` | Pydantic v2 result models: `Note`, `LinkRef`, `ValidationIssue`, `LintReport`, `VaultConfig`. |
| `digivault/frontmatter.py` | Round-trip-safe YAML frontmatter `split` / `dump` / `set_keys` (PyYAML). `split(dump(fm, body)) == (fm, body)`. |
| `digivault/wikilinks.py` | Parse `[[note]]`/`[[note#h\|alias]]`/`![[embed]]`; `rewrite_target` / `map_targets` rewrite links while skipping code spans/blocks. |
| `digivault/vault.py` | `Vault` — load a directory (or any store via `Vault.from_sources`), build the note index + link graph + backlinks + tag index; maintenance ops (`create_note`, `rename` with inbound-link rewrite, `set_frontmatter`, `reindex`, `lint`). |
| `digivault/supabase_store.py` | `SupabaseStore` — read a vault out of Supabase (`architecture_notes`/`knowledge_notes`) and reconstruct it via `Vault.from_sources`; FTS `search` via the `search_architecture_notes` RPC. Optional `[supabase]` extra, lazily imported. |
| `digivault/path_scopes.py` | DigiKey scope policy: reads need `digivault:read`, writes `digivault:write`. |
| `digivault/orchestrator_tools.py` | OpenAI-style tool manifest fetched by DigiGraph via `POST /v1/orchestrator_tools`: tag search, backlinks, lint, create-note, and `digivault_search_notes` (Supabase FTS). |
| `digivault/server.py` | FastAPI app: `/healthz`, `/v1/status`, note CRUD, lint, backlinks, tags, orchestrator endpoints (`digivault_search_notes` dispatches to `SupabaseStore.search`, independent of the local-filesystem vault). |
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
- **Auth:** DigiKey JWT via `DigiAuthMiddleware`; `digivault:read` for GET
  routes and discovery, `digivault:write` for mutations and `orchestrator_invoke`.
  `/healthz`, `/v1/status`, `/metrics`, OpenAPI are auth-exempt.
- **Vault root:** `DIGIVAULT_ROOT` (required for any note route; routes return
  503 when unset). The vault is re-read from disk per request — small docs vault,
  correctness over caching.
- **Hub:** DigiGraph discovers tools via `POST /v1/orchestrator_tools` and
  executes via `POST /v1/orchestrator_invoke`.
- **Rate limiting:** per-IP sliding window (in-process `deque` + lock), mirrors
  `digisearch/server.py`. `/v1/orchestrator_invoke`: 10/min; `/v1/orchestrator_tools`:
  30/min; everything else except `/healthz`: 30/min default. Reads the IP from
  `X-Forwarded-For` (first hop) or `request.client.host`; `DIGI_DISABLE_RATE_LIMIT=1`
  disables it (tests); TestClient traffic (`client.host == "testclient"`) is
  exempt so the unit suite doesn't need the env var. Exceeding the limit returns
  429 with `code: rate_limit_exceeded` and a `Retry-After` header.
- **`digivault_search_notes`** is the one orchestrator tool that bypasses
  `DIGIVAULT_ROOT` entirely — it queries the Supabase-mirrored vault via
  `SupabaseStore.search` (the `search_architecture_notes` RPC, anon-key,
  read-only) and returns 503 only if `CORE_SUPABASE_URL`/`CORE_SUPABASE_ANON_KEY`
  are unset. This is the same RPC the digithings.ai chat widget calls directly
  today ([ADR-0018](../docs/adr/0018-digichat-path-routing.md), epic #1248) —
  wiring it into DigiVault's own orchestrator surface lets DigiGraph reproduce
  that grounding once the widget is cut over to the DigiChat gateway.

## Design decisions

- **Core/service split.** The vault semantics are useful as a library (CI doc
  linting, scripts, other services); FastAPI is an optional delivery surface.
- **Re-read per request.** A documentation vault is small; recomputing the index
  from disk avoids a whole class of cache-coherency bugs. If a large vault ever
  needs it, add an explicit cache behind `reindex`.
- **Storage is pluggable (filesystem + Supabase).** DigiVault owns *how knowledge
  is organized and traversed* (frontmatter, wikilinks, backlinks, taxonomy). The
  on-disk `Vault(root)` is the default; `Vault.from_sources` builds the same index
  from any `(rel_path, text)` source, and `supabase_store.SupabaseStore` reads a
  vault out of Postgres (`architecture_notes` / `knowledge_notes`, #1087) — read-only,
  reconstructed via `dump_frontmatter`, served to agents through the anon key.
  `digistore` (when it ships) will own *where bytes live* beneath this; the two
  remain complementary — DigiVault sits above DigiStore, not replacing it.
- **Wikilinks, not standard links.** The vault speaks Obsidian `[[...]]`. The
  repo's `scripts/check_doc_links.py` validates only `[text](path)` links, so
  DigiVault owns wikilink validation via `lint` (wired into `make vault-check`
  when the docs migrate).

## Environment variables

| Var | Purpose |
|-----|---------|
| `DIGIVAULT_ROOT` | Path to the managed vault directory (required for note routes). |
| `DIGIVAULT_MCP_HOST` | MCP bind host (default `127.0.0.1`). |
| `DIGIKEY_JWKS_URL` / `DIGIKEY_ISSUER` / `DIGIKEY_AUDIENCE` / `DIGIKEY_PUBLIC_KEY_PEM` | DigiKey JWT verification (shared convention). |
| `DIGI_DISABLE_RATE_LIMIT` | `1`/`true`/`yes` disables the per-IP rate limiter (shared convention with DigiSearch/DigiGraph; tests only). |
| `CORE_SUPABASE_URL` (or `SUPABASE_URL`) + `CORE_SUPABASE_ANON_KEY` (or `CORE_SUPABASE_SERVICE_KEY` / `SUPABASE_ANON_KEY` / `SUPABASE_SERVICE_ROLE_KEY`) | Required only for `digivault_search_notes` — `SupabaseStore.from_env` credentials (ADR-0022 naming). Requires the `digivault[supabase]` extra installed. |

## Testing

`tests/dv/` — `@pytest.mark.unit`, deterministic, filesystem via `tmp_path`.
Core tests (frontmatter, wikilinks, vault) need only `pydantic` + `pyyaml`.
Service and CLI tests `pytest.importorskip` their extras so the suite stays green
without `digivault[service]` installed. CI (`.github/workflows/test-digivault.yml`)
installs `digibase` + `digikey` + `digivault[service]` and runs the full set.
`digivault_search_notes` tests fake `SupabaseStore` directly (constructor takes
any `SupabaseClientProtocol`) — the real `supabase` package (`[supabase]` extra)
is never required to run the suite, matching `test_supabase_store.py`'s convention.

## Monorepo integration

Registered in `pytest.ini`, `scripts/ci_paths.yaml` (→ `ci.yml`),
`.github/workflows/test-digivault.yml`, `docker-compose.yml` (profile
`digivault`, port 8004), root `ARCHITECTURE.md` topology, `README.md`, and
`CLAUDE.md`. Human follow-ups: `CODEOWNERS`, `scripts/commit_helper.sh`
`VALID_COMPONENTS`, `scripts/project_routing.json`.
