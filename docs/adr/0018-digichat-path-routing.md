# ADR 0018 — digichat on digithings.ai (path), not a separate `chat.` deploy

Status: Accepted · Amended 2026-08-05 (evening) · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned digichat as `chat.digithings.ai`. digichat should feel like part of digithings.ai, not a second product site.

Full digichat (Next.js standalone, Auth.js, Postgres, `/embed` for customers) still needs a Node host for **customer embeds** (e.g. DataTap). DigiThings **marketing** chat does not need that stack on the free Cloudflare plan.

## Decision (amended 2026-08-05 evening)

| Path | Owner | Role |
|---|---|---|
| `digithings.ai/chat` | Cloudflare Pages (`frontend/digithings-web`) | Native `@digithings/digichat-ui` + digivault Pages Function (`/api/chat`) |
| digichat `/embed` (customers) | digichat Node (DataTap Azure ACA today; DigiThings Containers **deferred**) | Customer iframe embeds |

- Marketing chat: **no iframe**, **no Workers Paid Containers** required.
- Shared UI package unifies look/feel; digithings keeps a free Pages digivault Function rather than deploying digichat Node for visitors.
- DigiThings has **no Azure**. DataTap Azure digichat is client-only.
- Do **not** use `chat.digithings.ai` as the marketing host.

### Historical notes

1. Original 0018: digichat app under `digithings.ai/chat/*` with `DIGICHAT_BASE_PATH=/chat`.
2. Midday Phase 3 amendment: `/chat` Pages shell + iframe → Containers `/embed` (blocked on Workers Paid).
3. Evening amendment: native digichat-ui + Pages Function (this revision).
4. **2026-08-06:** the deferred `frontend/digichat-cloudflare/` Containers scaffold (and its
   `Dockerfile.digichat-cloudflare`) was **deleted**. It was never deployed — no
   `digithings-digichat` Workers app was ever created, every `[[routes]]` block stayed
   commented out, and no workflow built the image — while its `wrangler` devDependency kept
   five `workerd` platform binaries in the root lockfile. Recover it from git history if
   DigiThings later adopts Workers Paid and wants one digichat Node for marketing + embeds.

## Production configuration

- Cloudflare Pages `digithings-ai`: static digithings-web + Functions; secrets `OPENROUTER_API_KEY`, `CORE_SUPABASE_*`.
- Marketing “Try Chat” → `/chat`.

## Consequences

- One domain; marketing chat stays free.
- Digithings marketing digivault path can diverge from digichat’s TypeScript digivault provider until a shared package is extracted.
- Customer digichat embeds remain on digichat Node (unchanged by this ADR).
