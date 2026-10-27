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
  `digitrace/src/digitrace/config.py`) — Langfuse is only one optional OTLP
  backend there, it is fail-soft, and it still feeds LangSmith.
  `DIGITRACE_LANGFUSE_OTLP_ENDPOINT` and its aliases stay recorded as
  **retired (DIG-5136)** in
  [`digitrace/ARCHITECTURE.md`](../../digitrace/ARCHITECTURE.md), not deleted:
  removing an env name from the config would break a deployment that still
  exports it.
- `digigraph/src/digigraph/tracing.py` — it imports `digitrace.trace.traceable`,
  is a no-op with no endpoint configured, and also feeds LangSmith.
- `infra/local-proxy/Caddyfile` — see the note below.

## Follow-ups for a human (not done here, deliberately)

- **R2 bucket `digitrace-langfuse-events`** may exist on the account and may
  hold data. It was not listed for deletion, not emptied and not touched. A
  human decides whether it is empty before removing it.
- **`infra/local-proxy/Caddyfile`** still carries a `trace.digithings.localhost`
  route (documented in [`docs/LOCAL_STACK.md`](../LOCAL_STACK.md)) that proxies
  `/_langfuse/*` and `/api/public/otel` to `digitrace:8003`. That is the live
  digitrace service, not the retired Langfuse Worker, so the route is left
  alone; only its path prefix is a leftover of the old naming.
