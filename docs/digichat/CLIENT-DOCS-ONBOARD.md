# Client docs onboard

Operator runbook for the offline **docs onboard** pipeline under
`scripts/docs_onboard/`. Turns a client website URL into documentation-focused
digivault notes and/or a digisearch index so Profile A digichat → digigraph →
digivault (and/or digisearch) can ground answers on that client's docs.

Digi module names are always lowercase in prose. This is an **ops workflow**,
not a Digi peer module and not a digichat fork.

## What this is / is not

| Is | Is not |
|---|---|
| Offline job beside the stack (`scripts/docs_onboard/`) | A Digi service or peer package |
| Shared multi-client scripts + per-client manifests | Client logic baked into digichat |
| Writes `DIGIVAULT_ROOT` and/or digisearch via ingest | Live crawl tools inside digigraph |
| Orthogonal to Pick 1 (runtime CSP) and Pick 2 (GHCR Profile A) | Part of the digichat Node image |

Pipeline order:

```text
scrape_site → classify_pages → fetch_docs
  → [ingest_static / ingest_openapi / ingest_repo?]
  → [write_vault_notes?] → [write_search_index?]
  → [d1_sync.py → D1?]
```

Website crawl remains the primary discovery path. Manifest extensions:

| Field | Purpose |
|---|---|
| `static_sources` | YAML globs → `PageClass.repo_doc` |
| `openapi_sources` | OpenAPI/Swagger JSON → `PageClass.openapi` |
| `repo_source` | Local path or GitHub `{owner}/{repo}` + globs → `repo_doc` |
| `sinks: [vault, search]` | Dual-sink (dogfood digithings) |
| `vault_url` / `--digivault-url` | Upsert via digivault `POST /v1/notes?overwrite` |

Dogfood client #0: [`docs/projects/digithings/`](../projects/digithings/).
## Prerequisites

- Python 3.12+ and a repo venv (`source .venv/bin/activate`).
- Editable installs for transport + sinks:

```bash
pip install -e ./digifetch -e ./digivault -e "./digisearch[dev]"
```

- A client (or example) manifest under `docs/projects/<client>/onboard.yaml`
  (or private `projects/<client>/`).
- For the **vault** sink: a writable vault root (`--vault-root` or `DIGIVAULT_ROOT`).
- For the **search** sink: digisearch reachable + digikey API key
  (`DIGISEARCH_SEED_API_KEY` / `--api-key`), same pattern as
  `scripts/seed_digisearch_local.py`.

OCR for scanned PDFs is owned by **digisearch** (`DIGISEARCH_OCR_ENABLED=true` and
`digisearch[ocr]`) — do not enable OCR inside the onboard scripts.

## Example run

Example public dogfood manifest:
[`docs/projects/example-docs-client/onboard.yaml`](../projects/example-docs-client/onboard.yaml).
Client #0 (digithings.ai):
[`docs/projects/digithings/onboard.yaml`](../projects/digithings/onboard.yaml).

Dry-run (no crawl network when `--dry-run`; validates static/openapi/repo):

```bash
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/digithings/onboard.yaml \
  --workdir /tmp/digithings-onboard \
  --dry-run
```

Replace `seed_url` / hosts with a real allowlisted docs host for live smoke.

```bash
export DIGIVAULT_ROOT="${DIGIVAULT_ROOT:-/tmp/demo-vault}"
mkdir -p "$DIGIVAULT_ROOT"

python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/example-docs-client/onboard.yaml \
  --workdir /tmp/example-onboard \
  --vault-root "$DIGIVAULT_ROOT" \
  --sinks vault,search \
  --digisearch-url "${DIGISEARCH_URL:-http://127.0.0.1:8002}" \
  --digikey-url "${DIGIKEY_URL:-http://127.0.0.1:8005}" \
  --api-key "${DIGISEARCH_SEED_API_KEY}"
```

Production digithings path prefers `--digivault-url` (filesystem vault on the
operator digivault) then `scripts/d1_sync.py` to publish the vault into Cloudflare
D1 (`clients/digithings`'s `notes` table + FTS5 index; `--dry-run` first — reads
and counts, writes nothing, needs no credentials). Do **not** point public
digivault search at an unpublished local `DIGIVAULT_ROOT` only — that splits the
brain from the D1 corpus digivault actually serves in production.

#### Operator apply

- Exit `0` on success; exit `2` if any sink reported errors (JSON `OnboardResult`
  still prints to stdout).
- Leaf scripts (`scrape_site.py`, `classify_pages.py`, …) are runnable alone with
  the same flag subset for debugging.

### digithings.ai CI (`main`)

Corpus refresh for client #0 is automated by
[`.github/workflows/docs-onboard-digithings.yml`](../../.github/workflows/docs-onboard-digithings.yml)
on relevant pushes to `main` (and `workflow_dispatch`). The Action dry-runs
classification, then on apply writes a filesystem vault (`--sinks vault`) and runs
`scripts/d1_sync.py` to publish that vault into Cloudflare D1 (`clients/digithings`)
under the `production` environment — the same dry-run/apply CI shape as
[`sync-architecture-vault.yml`](../../.github/workflows/sync-architecture-vault.yml),
though that pipeline is a separate, still-Supabase-backed corpus
(`architecture_notes`) unrelated to this D1 publish.

digisearch dual-sink remains an **operator / local** step (or legacy
`docs-reindex-guide.yml` on `develop`): Actions runners cannot post
server-visible paths to a remote digisearch `/ingest`. Optional website crawl
is a dispatch input (`crawl: true`), not the default push path.

### digisearch path modes

`POST /ingest` `source` must be a **server-visible filesystem path** (never a raw
URL without a sandboxed fetch path in digisearch).

1. **Host digisearch** (`make stack-local`): workdir on the host; posted `source`
   is the host path.
2. **Compose digisearch:** mount the workdir into the digisearch container (e.g.
   `/data/onboard`) and pass `--source-prefix /data/onboard` (or
   `DIGISEARCH_ONBOARD_REMOTE_PREFIX`) so posted paths match the container FS.

## Profile A volume path

Profile A digivault typically mounts a Compose volume at `/data/vault`. Point
`--vault-root` / `DIGIVAULT_ROOT` at that same root so onboard notes land where
`digivault_search_notes` reads them.

digivault's search precedence is **D1 → local filesystem → Supabase FTS**: D1
wins only when `_d1_configured()` is true — resolved account ID, resolved API
token, **and** `D1_DATABASE_MAP` are all set (even over a `DIGIVAULT_ROOT` set
for local iteration). Partial D1 configuration raises `D1StoreError` rather
than falling back. Otherwise `DIGIVAULT_ROOT`, when set, searches the local
filesystem; Supabase FTS is the last-resort fallback. See
[`digivault/ARCHITECTURE.md`](../../digivault/ARCHITECTURE.md).

Attach/mount details for one-shot Compose jobs are deferred (Pick 3 later /
Pick 2 soft-depend) — MVP runs the scripts beside the stack as an operator job.

## Smoke checks

1. **Unit (no network):**

```bash
pytest tests/dv/test_local_search.py tests/scripts/docs_onboard -m unit -v
```

2. **Vault sink:** after a vault-only run, start digivault with the same
   `DIGIVAULT_ROOT` and invoke `digivault_search_notes` for a phrase from an
   ingested note.

3. **Search sink:** query digisearch for the configured `digisearch_index` and
   confirm `metadata.source_url` on ingested docs.

4. **Profile A chat (after Pick 2 stack is up):** ask digichat a question that
   only the onboarded docs answer.

## Module roles (do not blur)

| Module | Owns |
|---|---|
| **digifetch** | HTTP fetch/download transport |
| **digisearch** | Parse, OCR, chunk, embed, index |
| **digivault** | Notes, graph, agent tools; local search when `DIGIVAULT_ROOT` set |
| **scripts/docs_onboard** | Crawl orchestration, classification, workdir, sink writers |
| **docs/projects/\<client\>** | Seed URL, allow hosts, sinks, index name, path prefixes |

## Related

- Ops index: [`docs/ops/CLIENT_PIPELINES.md`](../ops/CLIENT_PIPELINES.md)
- Plan: [`docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md`](../superpowers/plans/2026-08-10-digithings-dogfood-cutover.md)
- Client #0: [`docs/projects/digithings/`](../projects/digithings/)
- Client #1 (OCC): [`docs/projects/online-compliance-center/`](../projects/online-compliance-center/)
- OCC chat: [`docs/superpowers/plans/2026-08-10-occ-client-chat.md`](../superpowers/plans/2026-08-10-occ-client-chat.md)
- Fit (picks 1–3): [`docs/architecture/digichat-self-host-picks-fit.md`](../architecture/digichat-self-host-picks-fit.md)
- Install: [`docs/digichat/INSTALL.md`](INSTALL.md)
- Release overlays: [`infra/digichat-release/README.md`](../../infra/digichat-release/README.md)
