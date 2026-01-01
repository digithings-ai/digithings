# Synthetic seed data for the self-host reference stack

Implements plan section 5 (DIG-2774). **Synthetic only**: no client data is
read, copied or derived, and no step can write outside this machine.

## Run it

    make seed-local                       # everything available
    make seed-local SEED=43               # a different deterministic seed
    make seed-local SEED_ARGS=--dry-run   # print the plan, write nothing
    make seed-local-no-r2                 # skip the Miniflare R2 objects

Or directly:

    python3 -m scripts.seed.seed_all --seed 42

Exit code is 0 only when every step that ran succeeded; steps whose backing
service is not running report `skipped` with the reason rather than
fabricating a pass.

## What each step writes

| step | target | idempotency key |
|---|---|---|
| `tenants` | `workspaces`, `workspace_members`, `documents` | `(id)` / `(workspace_id, user_id)` / `(workspace_id, date, document_key)` |
| `portfolio` | `nav_history`, `decision_log`, `portfolio_metrics` | delegated to `scripts/seed_digiquant_demo.py`, which already pins `--seed 42` |
| `digikey` | `digikey_api_keys` | `label` — an existing non-revoked row is reused, never re-minted |
| `r2` | Miniflare R2 `market-data/…` | content-addressed by `as_of`; the manifest digest is a pure function of the rows |
| `digisearch` | digisearch index via `make seed-digisearch-local` | the ingester upserts per document |
| `digigraph` | `scripts/seed/data/digigraph/*.json` | files are byte-stable for a given seed |

## Three properties, enforced in one place

`scripts/seed/deterministic.py` holds the three rules so no seeder has to
repeat them:

1. **Deterministic** — every value comes from `stable_uuid()` or
   `rng_for(seed, topic)`. Per-topic RNG streams mean adding a ticker to the
   market slice does not shift the portfolio fixtures.
2. **Synthetic** — identities use the reserved `seed.digithings.local`
   domain; prices are a seeded random walk, never fetched.
3. **No production writes** — `require_local()` refuses any host that is not
   loopback, and `r2_market.put_local()` passes `wrangler … --local`
   unconditionally.

## Known boundary

`digigraph` exposes no ingest or seed route at the tree this was written
against (measured routes are in `digigraph.load_status()`), so its fixtures
are emitted as files rather than pushed into the service. Turning that into
a real push needs a digigraph route, which is a digigraph-owner decision, not
a seeding one.
