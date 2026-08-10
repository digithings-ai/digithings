# digithings — client #0 (dogfood)

Public digithings.ai chat is the **same** self-hosted digichat + Profile A stack
clients install. Corpus is driven by this directory's onboard manifest.

Digi product names are always lowercase in prose.

## Locked decisions

| Topic | Decision |
|---|---|
| Chat UI | **digithings.ai only** — no digiquant.io `/chat` page |
| Crawl hosts | digithings.ai + digiquant.io (corpus sources) |
| Sinks | Dual-sink: digivault (Supabase publish) + digisearch |
| Auth | Option A — `DIGICHAT_REQUIRE_ROOT_AUTH=0`; embed `gateMode: ungated` |
| Vault | Production search via Supabase-backed digivault (no prod-only `DIGIVAULT_ROOT`) |
| Stage A | Human-owned develop→main + GHCR publish — not blocked for onboard work |

Plan: [`docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md`](../../superpowers/plans/2026-08-10-digithings-dogfood-cutover.md).

## Tree

```text
docs/projects/digithings/
  README.md
  SHOWCASE.md          # canonical “how is this chat built?” note (onboarded)
  GAPLOG.md
  digiproject.yaml     # DIGI_PROJECT_CONFIG co-located with manifest
  onboard.yaml
  sources/
    repo-docs.yaml
    openapi.yaml
  indexes/
    docs.yaml
```

## digigraph project config

Set **`DIGI_PROJECT_CONFIG`** to the committed dogfood snippet:

```bash
export DIGI_PROJECT_CONFIG=config/dogfood-digiproject.yaml
# or: docs/projects/digithings/digiproject.yaml
```

Local overrides (e.g. `config/dogfood-digiproject.local.yaml`) may stay gitignored
via `docker-compose.override.yml`.

## Embed (operator env)

```bash
DIGICHAT_REQUIRE_ROOT_AUTH=0
DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai
DIGICHAT_EMBED_TENANTS='{"digithings.ai":{"slug":"digithings","aliases":["www.digithings.ai"],"gateMode":"ungated","showByok":true,"showStatusBar":true,"layout":"page","activityDetail":"full","attribution":false,"token":"<schema-required>","backend":{"type":"digigraph"}}}'
```

digiquant.io is **crawl-only** unless a human later requests iframing digithings
chat as an embed parent.

## CI on `main` (automatic)

[`.github/workflows/docs-onboard-digithings.yml`](../../../.github/workflows/docs-onboard-digithings.yml)
runs on pushes to `main` that touch onboard sources (manifest, repo-docs /
OpenAPI globs, pipeline scripts). It dry-runs classification, then **applies**
a local vault sink and publishes via `scripts/sync_onboard_vault.py` to core
Supabase `architecture_notes` (same `production` / `CORE_SUPABASE_*` pattern as
`sync-architecture-vault.yml`). Manual runs: Actions → **Docs: onboard
digithings** (`dry-run` / `apply`, optional website crawl).

digisearch dual-sink is **not** applied from Actions (ingest needs a
server-visible path). Use the operator path below or the legacy
`docs-reindex-guide.yml` until remote ingest exists.

## First onboard (operator / local)

Dry-run (no network crawl / no sinks — validates manifest + static/repo/OpenAPI
classification):

```bash
source .venv/bin/activate
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/digithings/onboard.yaml \
  --workdir /tmp/digithings-onboard \
  --dry-run
```

Apply (needs secrets + running digivault/digisearch/digikey — see
[`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../digichat/CLIENT-DOCS-ONBOARD.md)).
Prefer this for digisearch dual-sink; vault→Supabase on `main` is covered by CI:

```bash
export DIGIVAULT_URL="${DIGIVAULT_URL:-http://127.0.0.1:8004}"
export DIGISEARCH_URL="${DIGISEARCH_URL:-http://127.0.0.1:8002}"
export DIGIKEY_URL="${DIGIKEY_URL:-http://127.0.0.1:8005}"
# DIGISEARCH_SEED_API_KEY=…  DIGIVAULT_API_KEY=… (or bearer via digikey)

python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/digithings/onboard.yaml \
  --workdir /tmp/digithings-onboard \
  --digivault-url "$DIGIVAULT_URL" \
  --sinks vault,search \
  --api-key "$DIGISEARCH_SEED_API_KEY"

# Publish local/API vault notes → Supabase architecture_notes (service role):
python scripts/sync_onboard_vault.py \
  --vault /tmp/digithings-onboard-vault \
  --dry-run   # then drop --dry-run with CORE_SUPABASE_* set
```

## Legacy (parallel during transition)

| Artifact | Status |
|---|---|
| `docs/projects/digithings-guide/` + `scripts/reindex_digithings_guide.py` | Keep until digisearch dual-sink verified; then retire |
| `scripts/sync_architecture_vault.py` | Optional parallel from `docs/vision`; retire when onboard + `sync_onboard_vault.py` cover notes |

## Profile A / Stage A

Operator GHCR pull cutover is documented in
[`infra/digichat-digithings/README.md`](../../../infra/digichat-digithings/README.md).
Until Stage A publishes stack images on `main`, use monorepo Compose build for
local/operator smoke. Do not block onboard development on GHCR 404s.

## Related

- Runbook: [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../digichat/CLIENT-DOCS-ONBOARD.md)
- Install: [`docs/digichat/INSTALL.md`](../../digichat/INSTALL.md)
- Gap log: [`GAPLOG.md`](GAPLOG.md)
