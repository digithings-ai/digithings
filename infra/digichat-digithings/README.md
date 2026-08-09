# digithings digichat hosting

digithings marketing chat uses **digichat → digigraph → digillm + digivault hub**.
digithings has **no Azure**. Do not use DataTap ACA for digithings.

Canonical path:

```text
Browser digithings.ai/chat
  → iframe digichat /embed (Cloudflare Tunnel → digichat Node)
       → digigraph (DIGIGRAPH_INTERNAL_URL)
            → digillm → LiteLLM
            → digivault_hub → digivault :8004 (DIGIVAULT_URL)
```

See [`docs/architecture/digichat-modular-frontend.md`](../../docs/architecture/digichat-modular-frontend.md).

## Hard constraints

- digithings has **no Azure**.
- DataTap digichat ACA is **client-only**.
- Workers Free: no Cloudflare Containers for digichat Node — run digichat + stack on
  operator infra (Docker Compose) and expose digichat via **Cloudflare Tunnel**.

## Compose stack (operator host)

From repo root (adjust `.env`):

```bash
# Required for digithings digigraph chat (root .env)
export DIGIVAULT_URL=http://digivault:8004
# digikey BFF token + LLM keys as in root .env.example
# Newer LiteLLM images read REDIS_URL; either leave it unset *and* avoid
# passing an empty string, or enable cache Redis:
#   REDIS_URL=redis://redis:6379
#   --profile litellm-cache

docker compose --profile digichat --profile digivault --profile litellm-cache up -d --build
# digichat image CSP: pass DIGICHAT_EMBED_HOSTS as a build-arg when building digichat
```

**Local smoke (no Tunnel):** open `http://127.0.0.1:3005/embed?host=digithings.ai` or
`POST /api/chat` with `X-Embed-Host: https://digithings.ai`. That proves digichat → digigraph
→ LiteLLM (+ digivault when tools run). Public `digithings.ai/chat` still needs Tunnel + Pages.

digichat runtime embed registry (never a Docker build-arg — tokens leak in layers):

```bash
export DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai
export DIGICHAT_EMBED_TENANTS='{"digithings.ai":{"slug":"digithings","aliases":["www.digithings.ai"],"gateMode":"ungated","showByok":true,"showStatusBar":true,"layout":"page","activityDetail":"full","attribution":false,"token":"<unused-for-first-party>","backend":{"type":"digigraph"}}}'
```

Build digichat image with `DIGICHAT_EMBED_HOSTS` present so CSP `frame-ancestors` includes digithings.ai.

## Cloudflare Tunnel

1. Install `cloudflared` on the host that runs digichat (port 3005).
2. Create a tunnel; route public hostname e.g. `digichat.digithings.ai` → `http://127.0.0.1:3005`.
3. Pages (digithings-web) build env:
   - `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digichat.digithings.ai`
4. digithings-web `npm prebuild` writes `public/_headers` `frame-src` from that
   same env (see `lib/security-headers.mjs`) — no manual CSP edit per host.

## digithings.ai `/chat`

Static Pages shell (`DtNav` + iframe) loads
`${NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN}/embed?host=digithings.ai` (first-party hosts
skip embed token). The Pages Function OpenRouter digivault loop is **retired**.

## Smoke

1. Open https://digithings.ai/chat
2. Ask a vault-grounded question (e.g. what digigraph orchestrates)
3. Expect digichat activity rows from digigraph tools (digivault search) and an
   answer via digillm — not direct OpenRouter from Pages.

## Historical note

The `frontend/digichat-cloudflare/` Workers Paid Containers scaffold was removed
2026-08-06. Recover from git history only if digithings adopts Workers Paid later.
