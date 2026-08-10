# ADR 0018 — digichat on digithings.ai (path), not a separate `chat.` deploy

Status: Accepted · Amended 2026-08-10 (Cloudflare Containers multi-tenant) · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned digichat as `chat.digithings.ai`. digichat should feel like part of digithings.ai, not a second product site.

Full digichat (Next.js standalone, Auth.js, Postgres, `/embed`) needs a Node host. digithings marketing chat must use the digithings stack: digichat → digigraph → digillm + digivault hub — not a proprietary OpenRouter Pages Function. Multiple marketing chats (digithings, OCC, …) must share one digichat process.

## Decision (amended 2026-08-10)

| Path | Owner | Role |
|---|---|---|
| `digithings.ai/chat` | Cloudflare Pages shell | iframe → `/embed?host=digithings.ai` |
| `digithings.ai/chat/occ` | Cloudflare Pages shell | iframe → `/embed?host=occ.digithings.ai` |
| `digithings.ai/embed*`, digichat APIs, `/_dtchat*` | Worker → **one** digichat Container | BFF; tenants via `DIGICHAT_EMBED_TENANTS` |
| digigraph + digillm + digivault + digikey | Profile A / Compose (reachable URL) | Chat brain + vault tools |

- digithings has **no Azure**. DataTap Azure digichat is client-only.
- Do **not** use `chat.digithings.ai` as the marketing path host; public URLs stay under `digithings.ai/chat…`.
- **Preferred:** Cloudflare Containers (Workers Paid) — see [`frontend/digichat-cloudflare/`](../../frontend/digichat-cloudflare/README.md).
- **Fallback:** operator Compose + Tunnel (`digichat.digithings.ai`) if Paid is unavailable.
- Pages Function OpenRouter digivault loop is **retired** (410).
- New marketing chats = new Pages `/chat/<slug>` + embed-tenant row — **not** a new Container.

### Historical notes

1. Original 0018: digichat app under `digithings.ai/chat/*` with `DIGICHAT_BASE_PATH=/chat`.
2. Midday Phase 3: `/chat` Pages shell + iframe → Containers `/embed` (blocked on Workers Paid).
3. Evening 2026-08-05: native digichat-ui + Pages digivault Function (free plan).
4. 2026-08-06: `frontend/digichat-cloudflare/` Containers scaffold deleted (#1949).
5. 2026-08-09: digigraph cutover — marketing chat iframes digichat digigraph backend.
6. **2026-08-10:** Containers scaffold restored for multi-tenant digithings + OCC on one Node (#2073).

## Production configuration

- Cloudflare Pages `digithings-ai`: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai`; `_headers` `frame-src` allows that origin.
- digichat Container: `DIGICHAT_EMBED_HOSTS`, `DIGICHAT_EMBED_TENANTS` (digithings + occ → `digigraph`); `DIGIGRAPH_INTERNAL_URL`, digikey BFF secrets.
- digigraph stack: Profile A / Compose; `DIGIVAULT_URL`, LiteLLM / digillm.
- Runbook: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

## Consequences

- One digichat process for all digithings.ai marketing chats.
- digithings chat uses digigraph + digillm + digivault modules only.
- Client embeds (Foundry) stay on digichat Node unchanged.
- digichat Node backends are only `digigraph` and `foundry`.
- Containers require Workers Paid; digigraph is not packed into the digichat image.

## See also

- Modular frontend + adapters: [`docs/architecture/digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md)
- OCC: [`docs/projects/online-compliance-center/README.md`](../projects/online-compliance-center/README.md)
