# Architecture Decision Records (ADRs)

Short, immutable decisions. **Add a new file** with the next number: `NNNN-short-title.md`.

Use the template: [0000-template.md](0000-template.md).

Link ADRs from [docs/agent-backlog/INDEX.md](../agent-backlog/INDEX.md) when they govern ongoing work.

Current high-water mark: **0036** ([0036-digitrace-cloudflare-native-tracing.md](0036-digitrace-cloudflare-native-tracing.md), Accepted) — digitrace tracing is a Cloudflare-native pipeline: an ingest Worker and Queue, an R2 archive as the system of record, a Supabase `public` index with per-table RLS, Workers Analytics Engine aggregates, and MLflow on demand for the deep analysis. Self-hosted Langfuse is dropped (no new paid services).
