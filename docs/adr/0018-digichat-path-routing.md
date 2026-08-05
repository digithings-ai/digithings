# ADR 0018 — DigiChat on digithings.ai (path), not a separate `chat.` deploy

Status: Accepted · Amended 2026-08-05 (evening) · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned DigiChat as `chat.digithings.ai`. DigiChat should feel like part of digithings.ai, not a second product site.

Full DigiChat (Next.js standalone, Auth.js, Postgres, `/embed` for customers) still needs a Node host for **customer embeds** (e.g. DataTap). DigiThings **marketing** chat does not need that stack on the free Cloudflare plan.

## Decision (amended 2026-08-05 evening)

| Path | Owner | Role |
|---|---|---|
| `digithings.ai/chat` | Cloudflare Pages (`frontend/digithings-web`) | Native `@digithings/digichat-ui` + digivault Pages Function (`/api/chat`) |
| DigiChat `/embed` (customers) | DigiChat Node (DataTap Azure ACA today; DigiThings Containers **deferred**) | Customer iframe embeds |

- Marketing chat: **no iframe**, **no Workers Paid Containers** required.
- Shared UI package unifies look/feel; digithings keeps a free Pages digivault Function rather than deploying DigiChat Node for visitors.
- DigiThings has **no Azure**. DataTap Azure DigiChat is client-only.
- Do **not** use `chat.digithings.ai` as the marketing host.

### Historical notes

1. Original 0018: DigiChat app under `digithings.ai/chat/*` with `DIGICHAT_BASE_PATH=/chat`.
2. Midday Phase 3 amendment: `/chat` Pages shell + iframe → Containers `/embed` (blocked on Workers Paid).
3. Evening amendment: native digichat-ui + Pages Function (this revision).

Deferred scaffold: [`frontend/digichat-cloudflare/`](../frontend/digichat-cloudflare/README.md) if DigiThings later adopts Workers Paid and wants one DigiChat Node for marketing + embeds.

## Production configuration

- Cloudflare Pages `digithings-ai`: static digithings-web + Functions; secrets `OPENROUTER_API_KEY`, `CORE_SUPABASE_*`.
- Marketing “Try Chat” → `/chat`.

## Consequences

- One domain; marketing chat stays free.
- Digithings marketing digivault path can diverge from DigiChat’s TypeScript digivault provider until a shared package is extracted.
- Customer DigiChat embeds remain on DigiChat Node (unchanged by this ADR).
