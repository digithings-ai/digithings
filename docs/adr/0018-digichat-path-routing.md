# ADR 0018 — digichat on digithings.ai (path), not a separate `chat.` deploy

Status: Accepted · Amended 2026-08-10 (Cloudflare Containers multi-tenant + Profile A stack) · Amended 2026-10-22 (the `/chat` cutover: the app under `/chat`, DIG-5121) · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned digichat as `chat.digithings.ai`. digichat should feel like part of digithings.ai, not a second product site.

Full digichat (Next.js standalone, Auth.js, Postgres, `/embed`) needs a Node host. digithings marketing chat must use the digithings stack: digichat → digigraph → digillm + digivault hub — not a proprietary OpenRouter Pages Function. Multiple marketing chats (digithings, OCC, …) must share one digichat process.

## Decision (amended 2026-08-10)

| Path | Owner | Role |
|---|---|---|
| `digithings.ai/chat` | Worker → **one** digichat Container (the app, built with `basePath: /chat`) | the digichat app itself; `/embed?host=digithings.ai` stays reachable as a compatibility route (amendment 2026-10-22, note 8) |
| `digithings.ai/chat/occ` | Cloudflare Pages shell | iframe → `/embed?host=occ.digithings.ai` |
| `digithings.ai/embed*`, digichat APIs, `/_dtchat*` | Worker → **one** digichat Container | BFF; tenants via `DIGICHAT_EMBED_TENANTS` |
| `graph.digithings.ai` | Worker → **one** Profile A stack Container | digigraph (chat brain) |
| `key.digithings.ai` | same stack Container | digikey (JWT / BFF) |
| `search.digithings.ai` | same stack Container | digisearch `:8002` (JWT `digisearch:query`; public Worker route) |
| digivault + LiteLLM | loopback inside stack Container | vault / LLM router — **not** published hostnames |

- digisearch in-container callers still use `http://127.0.0.1:8002`; the process binds `0.0.0.0:8002` so the Worker can proxy (`wrangler.toml` search route comments, #4071).
- digithings has **no Azure**. DataTap Azure digichat is client-only.
- Do **not** use `chat.digithings.ai` as the marketing path host; public URLs stay under `digithings.ai/chat…`.
- **Preferred digichat host:** Cloudflare Containers (Workers Paid) — [`apps/digichat-cloudflare/`](../../apps/digichat-cloudflare/README.md).
- **Preferred backends:** Cloudflare Containers Profile A stack — [`apps/digithings-stack-cloudflare/`](../../apps/digithings-stack-cloudflare/README.md). Production must **not** depend on Mac Docker or `*.trycloudflare.com` quick tunnels.
- **Dev-only:** operator Mac Compose (+ optional quick tunnels) for local iteration.
- **Fallback (no Paid):** operator Compose + named Tunnel if Workers Paid is unavailable.
- Pages Function OpenRouter digivault loop is **retired** (410).
- New marketing chats = new Pages `/chat/<slug>` + embed-tenant row — **not** a new Container.
- **Human gate:** publishing `graph.` / `key.` / `search.` hostnames is new network exposure (`search.digithings.ai` is owner-approved for CI web grounding, #4063); secrets only via `wrangler secret put`.

### Historical notes

1. Original 0018: digichat app under `digithings.ai/chat/*` with `DIGICHAT_BASE_PATH=/chat`.
2. Midday Phase 3: `/chat` Pages shell + iframe → Containers `/embed` (blocked on Workers Paid).
3. Evening 2026-08-05: native digichat-ui + Pages digivault Function (free plan).
4. 2026-08-06: `apps/digichat-cloudflare/` Containers scaffold deleted (#1949).
5. 2026-08-09: digigraph cutover — marketing chat iframes digichat digigraph backend.
6. **2026-08-10:** Containers scaffold restored for multi-tenant digithings + OCC on one Node (#2073).
7. **2026-08-10 (evening):** Profile A backends (digigraph + digikey + digisearch + digivault + LiteLLM) move to a second Cloudflare Container (`digithings-stack`) so production digichat has no laptop dependency (#2078).
8. **2026-10-22:** the `/chat` cutover (DIG-5121, GitHub #1252) — the digichat **app** is served under `digithings.ai/chat*` by the digichat Worker, and the Container is built with `DIGICHAT_BASE_PATH=/chat`: the shape of the original decision (note 1). `/chat/occ` stays a Pages shell behind the invite gate. The legacy routes stay declared as a **compatibility window**: `/embed*` stays for good (the OCC shell iframe and the marketing site point at `digithings.ai/embed?host=…`), while the legacy `/api/*` spellings (`/api/chat*`, `/api/embed*`, `/api/byok*`, `/api/plan-proof*`, `/api/health`) are the pre-cutover spelling of `/chat/api/*` and are reviewed once the cutover is live. The change reaches production with the digichat deploy lane (DIG-5120) and Chris's approval of the production environment.

## Production configuration

- Cloudflare Pages `digithings-ai`: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai`; `_headers` `frame-src` allows that origin.
- digichat Container: `DIGICHAT_EMBED_HOSTS`, `DIGICHAT_EMBED_TENANTS` (digithings + occ → `digigraph` with OCC `digisearchIndex: occ_help` + `vaultPathPrefix`); `DIGIGRAPH_INTERNAL_URL=https://graph.digithings.ai`, `DIGIKEY_URL=https://key.digithings.ai`, digikey BFF secrets.
- Profile A stack Container: see [`apps/digithings-stack-cloudflare/`](../../apps/digithings-stack-cloudflare/README.md).
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
