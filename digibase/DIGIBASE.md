# DigiBase — shared library today, data-plane service (roadmap)

This document covers two related things:

| Name | What it is | Status |
|------|------------|--------|
| **`digibase`** | Python package: HTTP correlation headers, FastAPI error envelope, audit redaction helpers, optional OTel wiring | **Shipped** — see [README.md](README.md) |
| **DigiBase** | First-party **data-plane** HTTP service: central place for **managed data access** (credentials, routing, quotas, audit) | **Not shipped** — architecture target |

Operators and contributors should treat **DigiBase (service)** as the long-term way to **centralize data operations** so application services do not each own raw connection strings, cache topology, or cross-cutting data policy.

## Why a DigiBase service

Today, DigiChat, DigiGraph (checkpoints), DigiKey, DigiSearch (embeddings cache), and LiteLLM (proxy cache) each can point at different stores using env-specific URLs. That is fine for v1 local dev and small deployments. As footprint grows, operators need:

- **One place to rotate credentials** and scope them per tenant / service (aligned with [digikey/DIGIKEY.md](../digikey/DIGIKEY.md)).
- **Consistent audit** for who touched which logical dataset (not necessarily row-level — policy TBD).
- **Optional multi-backend routing** (single Postgres, Supabase, Azure Database, etc.) without rewriting every consumer.
- **Cache and queue policy** in one layer (namespaces, TTL caps, rate limits) instead of ad hoc Redis URLs in six containers.

DigiBase does **not** replace domain logic: DigiSearch still owns RAG pipelines; DigiQuant still owns Nautilus; DigiGraph still owns orchestration. DigiBase **mediates durable and shared ephemeral data access** where the platform chooses to centralize.

## Scope: what would route through DigiBase (target)

**Likely in scope** for a first data-plane release:

1. **OLTP-style Postgres** — DigiChat conversation storage, DigiKey identity store links, DigiGraph **checkpoint** URI indirection (service resolves to a real `postgresql://…` internally), other small relational payloads the monorepo already puts in Postgres.
2. **Shared cache credentials** — central issue of Redis (or compatible) **connection handles** or namespaced keys for: embedding cache hints, optional cross-service idempotency keys, rate-limit buckets (where not already inlined). *LiteLLM* may keep speaking Redis/LiteLLM-native config initially; DigiBase could still **distribute** `REDIS_URL` or short-lived tokens to approved services.
3. **Object/blob refs** — optional signed URLs or internal paths for Digistore-like artifacts if we move from “everyone mounts the same volume” to “everyone asks DigiBase for a scoped read/write handle.”

**Explicitly delicate / phased:**

- **LLM response cache** — LiteLLM remains the **semantic** owner of prompt cache behavior; DigiBase would at most **supply** infrastructure (Redis URL, key prefix, quota), not re-implement LiteLLM caching.
- **Vector index (Chroma, pgvector, etc.)** — DigiSearch keeps retrieval algorithms; DigiBase might broker **connection policy** and **tenant-isolated index names** so DigiSearch does not embed long-lived secrets in env everywhere.
- **Huge quant datasets** — still primarily **Digistore / Parquet on disk** or vertical-specific stores; DigiBase is for **platform** data planes, not a replacement for tick data lakes.

## Security model (sketch)

- **No browser** talks to DigiBase with DB superuser strings. BFFs and Python services use **DigiKey-scoped** service tokens (or mTLS in hardened deployments).
- **digibase** (library) continues to standardize **`X-Request-ID`** and error JSON; DigiBase (service) would echo the same patterns for its own HTTP API.
- **Audit**: emit structured events (aligned with DigiClaw JSONL style) for connection issuance, policy denials, and admin changes — details to be specified when the service is scoped.

## Phasing (proposal)

| Phase | Outcome |
|-------|---------|
| **0 (now)** | Direct `DATABASE_URL` / `REDIS_URL` per service; `digibase` library everywhere for HTTP errors and correlation. |
| **1** | DigiBase **Postgres gateway**: logical DB names / tenant routing; DigiChat and DigiKey migrate first consumers; Compose gains optional `digibase` service. |
| **2** | **Cache namespace** API + Redis credential brokering; consumers opt in per feature flag. |
| **3** | **Artifact / object** handles; optional vector **metadata** routing (not replacing DigiSearch’s internal store). |

Each phase should remain **optional**: operators who want only direct Postgres keep using `DIGICHAT_DATABASE_URL` and friends until they opt into the broker.

## Relation to this repo

- **`digibase/` Python package** — install and import as today; no breaking rename.
- **Future `digibase` HTTP service** — new module or sibling package (name TBD: e.g. `digibase-server`, `digibase-plane`) so the **library** stays lightweight for `pip install digibase` on Lambdas and workers.

Authoritative stack diagram updates: [ARCHITECTURE.md](../ARCHITECTURE.md). Chat-specific persistence today: [DIGICHAT.md](../DIGICHAT.md).
