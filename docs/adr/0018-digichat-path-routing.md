# ADR 0018 — DigiChat served on digithings.ai (path), not a separate `chat.` deploy

Status: Accepted · Amended 2026-08-05 · Supersedes the `chat.digithings.ai` subdomain decision in [ADR-0002](0002-domain-unification.md)

## Context

ADR-0002 planned DigiChat as `chat.digithings.ai` — a separate production deployment target. In practice this reads as "DigiChat has its own pipeline / its own site," which is not desired: DigiChat should be part of the digithings.ai surface, with a single web presence.

DigiChat is, however, a **stateful Next.js standalone server** (`output: "standalone"`, a Dockerfile running `node server.js`): NextAuth sessions, a Postgres/Drizzle database, streaming LLM responses through its BFF, and an `/embed` route. It therefore **cannot** be a static page under the Cloudflare-Pages static digithings.ai — it needs a DigiThings-owned server runtime (never DataTap Azure).

## Decision (amended 2026-08-05)

Split marketing chrome from DigiChat app surface on the same hostname:

| Path | Owner | Role |
|---|---|---|
| `digithings.ai/chat` | Cloudflare Pages (`frontend/digithings-web`) | Marketing shell: `DtNav` + iframe |
| `digithings.ai/embed` (+ DigiChat `/api` / `/_dtchat` assets as routed) | Cloudflare Worker → DigiThings DigiChat **Container** | DigiChat app / embed target |


- Iframe is **same-origin**: `src=https://digithings.ai/embed?host=https://digithings.ai`.
- DigiChat runs with **`DIGICHAT_BASE_PATH` unset** and **`DIGICHAT_ASSET_PREFIX=/_dtchat`** so DigiChat static assets do not collide with Pages `/_next`.
- DigiChat runs on **Cloudflare Containers** (DigiThings CF account). DigiThings has **no Azure**. DataTap Azure DigiChat ACA is client-only.
- Do **not** use `chat.digithings.ai` as the marketing embed origin.

### Historical note (original 0018 text)

The first revision routed the full DigiChat app under `digithings.ai/chat/*` with `DIGICHAT_BASE_PATH=/chat`. Phase 3 unification keeps visitor URL `/chat` as the Pages shell and moves the DigiChat surface to `/embed` so the shell can embed without reclaiming `/chat` for the Node app.

## Production configuration (Cloudflare + env)

- Cloudflare Pages: digithings-web static export; `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai`.
- Cloudflare route: `digithings.ai/embed*`, DigiChat APIs, and `/_dtchat*` → DigiChat Container Worker ([`frontend/digichat-cloudflare/`](../frontend/digichat-cloudflare/README.md)).
- DigiChat Container: digivault env + digithings tenant; stub `AUTH_SECRET`; no Postgres required for embed-only; no Azure.
- Marketing "Try Chat" link points at `/chat`.

## Consequences

- One domain, one visitor-facing website; DigiChat is a path-routed DigiThings service, not a second product site and not DataTap infrastructure.
- DigiChat still requires a DigiThings-owned Node host (auth + DB + streaming) — stack service, not a Pages Function.
- Merge of the CF Function delete must wait until `https://digithings.ai/embed` is live.
