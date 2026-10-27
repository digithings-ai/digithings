---
title: digitrace
type: module
status: reviewed
created: 2026-04-19
tags:
  - support
  - observability
---
# digitrace

> Observability for the digithings ecosystem — tracing, metrics, and status, without the overhead.

**What it is:** digitrace is the observability layer for digithings. It is the tracing path every
service uses: a thin, side-effect-free emit wrapper that sends OTLP over HTTP into a
Cloudflare-native ingest pipeline, plus a public `/v1/status` endpoint that reports ecosystem
health without leaking secrets. The Prometheus metrics helper itself lives in digibase
(`install_metrics`); digitrace's role is to drive consistent adoption of that helper across
services alongside tracing.

**Design principle:** digitrace should be invisible when working and loud when something breaks.

**The platform target (decided 2026-10-09):** the self-hosted Langfuse deployment is retired and
the tracing surface is the Cloudflare-native pipeline — see
[ADR-0036](../adr/0036-digitrace-cloudflare-native-tracing.md). In-house digitrace over OTLP is the
default; LangSmith and Langfuse-OTLP remain supported, optional integrations and are never the
default. Sources emit OTel over HTTP
into a `digitrace-ingest` Worker; a Queue feeds a consumer that writes an R2 archive (the system of
record), a Supabase `public` index with per-table RLS, and Workers Analytics Engine aggregates; the
dashboard reads through `dashboard-api`; `digitrace replay` loads a window from the archive into
MLflow 3.10+ (with the `genai` extra) for the deep analysis, on the Mac or on a scale-to-zero
Cloudflare Container. A read-only `digitrace.mcp_server` MCP server is in scope and is owned by
DIG-5141; it is not built yet.

**This supersedes the earlier zero-dependency principle.** The line "zero dependencies beyond
FastAPI and Pydantic" and the claim that digitrace needs no database, no background worker and no
queue are **retired**: digitrace now owns an ingest Worker, a Queue, a consumer and three stores.
What the principle still holds is the *invisibility* half — the emit path stays a thin wrapper, and
a service that does not configure tracing still does nothing at all.

**Cost rule (binding):** no new paid services. The analysis container is on demand and sleeps after
about 10 minutes; Workers native trace storage stays `persist: false`. The marginal bill of tracing
stays at zero by construction.

**Current state:** in-house OTel export (the default), optional LangSmith and Langfuse-OTLP
integrations, `/v1/status` endpoint returning public metadata, `/health` and `/healthz` liveness
endpoints. The Cloudflare-native pipeline is being built (DIG-2656 to DIG-2663) and is not yet in
production.

**12-month roadmap:**
- Roll the digibase `install_metrics` helper out to every service so each exposes a `/metrics` endpoint with consistent labels
- X-Request-ID correlation ID propagation across all services (digigraph, digisearch, digiquant, digikey, digibot) — enables tracing a request through the full stack
- PII redaction and a hash-and-length span payload before any data reaches the trace store
- Structured logging throughout (digisearch currently has zero structured logging)
- Grafana dashboard for operational visibility

**Open source vs. proprietary:** Entirely open. Observability infrastructure is commodity — the
stores are Cloudflare and Supabase, the analysis tool is Apache-2.0 MLflow, and the protocol is
OTLP. No proprietary tracing vendor is in the path.
