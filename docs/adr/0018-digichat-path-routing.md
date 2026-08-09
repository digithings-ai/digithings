# ADR 0018 — digichat on digithings.ai (path), not a separate `chat.` deploy

Status: Accepted · Amended 2026-08-09 (digigraph cutover) · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned digichat as `chat.digithings.ai`. digichat should feel like part of digithings.ai, not a second product site.

Full digichat (Next.js standalone, Auth.js, Postgres, `/embed`) needs a Node host. digithings marketing chat must use the digithings stack: digichat → digigraph → digillm + digivault hub — not a proprietary OpenRouter Pages Function.

## Decision (amended 2026-08-09)

| Path | Owner | Role |
|---|---|---|
| `digithings.ai/chat` | Cloudflare Pages shell (`frontend/digithings-web`) | `DtNav` + iframe → digichat `/embed` |
| digichat Node | Operator host + Cloudflare Tunnel (`digichat.digithings.ai`) | BFF; `backend.type: digigraph` for digithings |
| digigraph + digillm + digivault | Same operator Compose stack | Sole digithings chat brain + vault tool |

- digithings has **no Azure**. DataTap Azure digichat is client-only.
- Do **not** use `chat.digithings.ai` as the marketing path host; public URL stays `digithings.ai/chat`.
- Tunnel hostname may be `digichat.digithings.ai` (or equivalent) pointing at digichat Node.
- Pages Function OpenRouter digivault loop is **retired** (410).
- Workers Free: digichat Node is **not** Cloudflare Containers — Compose on operator infra + Tunnel.

### Historical notes

1. Original 0018: digichat app under `digithings.ai/chat/*` with `DIGICHAT_BASE_PATH=/chat`.
2. Midday Phase 3: `/chat` Pages shell + iframe → Containers `/embed` (blocked on Workers Paid).
3. Evening 2026-08-05: native digichat-ui + Pages digivault Function (free plan).
4. 2026-08-06: `frontend/digichat-cloudflare/` Containers scaffold deleted.
5. **2026-08-09:** digigraph cutover — marketing chat iframes digichat digigraph backend; digivault only via digigraph hub.

## Production configuration

- Cloudflare Pages `digithings-ai`: static digithings-web; `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digichat.digithings.ai`; `_headers` `frame-src` allows that origin.
- digichat Node: `DIGICHAT_EMBED_HOSTS`, `DIGICHAT_EMBED_TENANTS` with digithings → `digigraph`; digikey/upstream auth; `DIGIGRAPH_INTERNAL_URL`.
- digigraph: `DIGIVAULT_URL`, LiteLLM / digillm.
- Runbook: [`infra/digichat-digithings/README.md`](../../infra/digichat-digithings/README.md).

## Consequences

- One public path (`/chat`); digichat Node is the BFF.
- digithings chat uses digigraph + digillm + digivault modules only.
- Client embeds (Foundry) stay on digichat Node unchanged.
- digichat Node backends are only `digigraph` and `foundry`.

## See also

- Modular frontend + adapters: [`docs/architecture/digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md)
