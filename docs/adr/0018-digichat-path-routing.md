# ADR 0018 — digichat on digithings.ai (path), not a separate `chat.` deploy

Status: Accepted · Amended 2026-08-10 (Cloudflare Containers multi-tenant + Profile A stack) · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned digichat as `chat.digithings.ai`. digichat should feel like part of digithings.ai, not a second product site.

Full digichat (Next.js standalone, Auth.js, Postgres, `/embed`) needs a Node host. digithings marketing chat must use the digithings stack: digichat → digigraph → digillm + digivault hub — not a proprietary OpenRouter Pages Function. Multiple marketing chats (digithings, OCC, …) must share one digichat process.

## Decision (amended 2026-08-10)

| Path | Owner | Role |
|---|---|---|
| `digithings.ai/chat` | Cloudflare Pages shell | iframe → `/embed?host=digithings.ai` |
| `digithings.ai/chat/occ` | Cloudflare Pages shell | iframe → `/embed?host=occ.digithings.ai` |
| `digithings.ai/embed*`, digichat APIs, `/_dtchat*` | Worker → **one** digichat Container | BFF; tenants via `DIGICHAT_EMBED_TENANTS` |
| `graph.digithings.ai` | Worker → **one** Profile A stack Container | digigraph (chat brain) |
| `key.digithings.ai` | same stack Container | digikey (JWT / BFF) |
| digisearch + digivault + LiteLLM | loopback inside stack Container | RAG / vault / LLM router |

- digithings has **no Azure**. DataTap Azure digichat is client-only.
- Do **not** use `chat.digithings.ai` as the marketing path host; public URLs stay under `digithings.ai/chat…`.
- **Preferred digichat host:** Cloudflare Containers (Workers Paid) — [`frontend/digichat-cloudflare/`](../../frontend/digichat-cloudflare/README.md).
- **Preferred backends:** Cloudflare Containers Profile A stack — [`frontend/digithings-stack-cloudflare/`](../../frontend/digithings-stack-cloudflare/README.md). Production must **not** depend on Mac Docker or `*.trycloudflare.com` quick tunnels.
- **Dev-only:** operator Mac Compose (+ optional quick tunnels) for local iteration.
- **Fallback (no Paid):** operator Compose + named Tunnel if Workers Paid is unavailable.
- Pages Function OpenRouter digivault loop is **retired** (410).
- New marketing chats = new Pages `/chat/<slug>` + embed-tenant row — **not** a new Container.
- **Human gate:** publishing `graph.` / `key.` hostnames is new network exposure; secrets only via `wrangler secret put`.

### Historical notes

1. Original 0018: digichat app under `digithings.ai/chat/*` with `DIGICHAT_BASE_PATH=/chat`.
2. Midday Phase 3: `/chat` Pages shell + iframe → Containers `/embed` (blocked on Workers Paid).
3. Evening 2026-08-05: native digichat-ui + Pages digivault Function (free plan).
4. 2026-08-06: `frontend/digichat-cloudflare/` Containers scaffold deleted (#1949).
5. 2026-08-09: digigraph cutover — marketing chat iframes digichat digigraph backend.
6. **2026-08-10:** Containers scaffold restored for multi-tenant digithings + OCC on one Node (#2073).
7. **2026-08-10 (evening):** Profile A backends (digigraph + digikey + digisearch + digivault + LiteLLM) move to a second Cloudflare Container (`digithings-stack`) so production digichat has no laptop dependency (#2078).

## Production configuration

- Cloudflare Pages `digithings-ai`: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai`; `_headers` `frame-src` allows that origin.
- digichat Container: `DIGICHAT_EMBED_HOSTS`, `DIGICHAT_EMBED_TENANTS` (digithings + occ → `digigraph` with OCC `digisearchIndex: occ_help` + `vaultPathPrefix`); `DIGIGRAPH_INTERNAL_URL=https://graph.digithings.ai`, `DIGIKEY_URL=https://key.digithings.ai`, digikey BFF secrets.
- Profile A stack Container: see [`frontend/digithings-stack-cloudflare/`](../../frontend/digithings-stack-cloudflare/README.md).
- Runbook: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

## Consequences

- One digichat process for all digithings.ai marketing chats.
- digithings chat uses digigraph + digillm + digivault modules only.
- Client embeds (Foundry) stay on digichat Node unchanged.
- digichat Node backends are only `digigraph` and `foundry`.
- Containers require Workers Paid; digigraph is **not** packed into the digichat image — it is a sibling stack Container.
- Mac Compose is **dev-only**; production cutover retargets digichat secrets away from quick tunnels.

## See also

- Modular frontend + adapters: [`docs/architecture/digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md)
- OCC: [`docs/projects/online-compliance-center/README.md`](../projects/online-compliance-center/README.md)
