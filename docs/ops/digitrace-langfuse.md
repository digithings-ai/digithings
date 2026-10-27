# digitrace Langfuse — retired, never deployed

**Status: retired. Removed from the tree (DIG-5136). Never ran in production.**

Self-hosted **Langfuse** (Web + Worker on Cloudflare Containers, with external
ClickHouse, Redis and Postgres) was the Phase 1 hosting plan for digitrace
([#4930](https://github.com/digithings-ai/digithings/issues/4930)). It was
**never deployed**: the Worker `digitrace-langfuse` was never created on the
Cloudflare account, so no runbook step below (or in this file's history) was
ever executed against production.

The tracing decision is now "Cloudflare-native ingest + on-demand MLflow",
recorded in [ADR-0036](../adr/0036-digitrace-cloudflare-native-tracing.md); the
design review is
[`docs/reviews/digitrace-tracing-architecture-review.md`](../reviews/digitrace-tracing-architecture-review.md).

## What was removed

- `apps/digitrace-langfuse/` — the Worker, its `wrangler.toml`, its
  `docker-compose.local.yml` (ClickHouse + Redis) and its tests.
- `infra/docker/Dockerfile.digitrace-langfuse-web` and
  `infra/docker/Dockerfile.digitrace-langfuse-worker`.
- The deploy job (`scripts/deploy/langfuse.sh`), the `langfuse` entry in
  `scripts/deploy/workers.tsv`, the CI path filters, the worker-build matrix
  entry, the self-host contract entries (services, env, secrets, bindings) and
  the parity-baseline surface entries.
- `scripts/smoke_digitrace_langfuse_otlp.sh`.

## What deliberately stayed

- The digitrace tracing code itself (`digitrace/src/digitrace/trace.py`,
  `digitrace/src/digitrace/config.py`) — the OTLP leg and the LangSmith leg are
  both still there and fail-soft. What went with this app is the *Langfuse
  naming*: `DIGITRACE_LANGFUSE_OTLP_ENDPOINT`, `LANGFUSE_OTLP_ENDPOINT`,
  `LANGFUSE_HOST` / `LANGFUSE_URL` and the `langfuse-otlp` export backend were
  removed, not merely marked retired. The OTLP leg exports to the in-house
  digitrace ingest via `DIGI_OTEL_ENDPOINT` / `DIGITRACE_OTLP_ENDPOINT` /
  `OTEL_EXPORTER_OTLP_ENDPOINT`; see
  [`digitrace/ARCHITECTURE.md`](../../digitrace/ARCHITECTURE.md).
- `digigraph/src/digigraph/tracing.py` — it imports `digitrace.trace.traceable`,
  is a no-op with no endpoint configured, and also feeds LangSmith.
- `infra/local-proxy/Caddyfile` — see the note below.

## Follow-ups for a human (not done here, deliberately)

- **R2 bucket `digitrace-langfuse-events`** does **not** exist on the account
  (`wrangler r2 bucket info` → code 10006, checked 2026-10-27). The app was never
  deployed, so no bucket was ever created and there is nothing to empty or delete.
- **`infra/local-proxy/Caddyfile`** still carries a `trace.digithings.localhost`
  route (documented in [`docs/LOCAL_STACK.md`](../LOCAL_STACK.md)) that proxies
  to `digitrace:8003`. That is the live digitrace service, not the retired
  Langfuse Worker. The `/_langfuse/*` path prefixes in its comment were a
  leftover of the old naming and have been corrected to the routes digitrace
  actually serves (`/health`, `/healthz`, `/v1/status`).
