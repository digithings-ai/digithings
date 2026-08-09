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

**Client #0 dogfood:** corpus + cutover plan live under
[`docs/projects/digithings/`](../../docs/projects/digithings/)
([plan](../../docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md)).

## Client / release installs

digithings’ Tunnel host is **this** operator path. Clients installing digichat
themselves should use [`infra/digichat-release/`](../digichat-release/) and
[`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md) (Profile A or B).

## Hard constraints

- digithings has **no Azure**.
- DataTap digichat ACA is **client-only**.
- Workers Free: no Cloudflare Containers for digichat Node — run digichat + stack on
  operator infra (Docker Compose) and expose digichat via **Cloudflare Tunnel**.
- Chat UI is **digithings.ai only** — do **not** add a digiquant.io `/chat` page.

## Auth (Option A)

Dogfood and default installs keep root Auth.js **OFF**:

```bash
DIGICHAT_REQUIRE_ROOT_AUTH=0   # default; `/` → `/embed`
```

Public chat is the ungated embed iframe (`gateMode: ungated`). Do not enable
`DIGICHAT_DEV_AUTH` in production.

## Compose stack (operator host)

### Today — monorepo build (until Stage A)

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
# digichat CSP: set runtime DIGICHAT_EMBED_HOSTS (and DIGICHAT_EMBED_TENANTS) on the digichat service
# Auth: DIGICHAT_REQUIRE_ROOT_AUTH=0
```

**Local smoke (no Tunnel):** open `http://127.0.0.1:3005/embed?host=digithings.ai` or
`POST /api/chat` with `X-Embed-Host: https://digithings.ai`. That proves digichat → digigraph
→ LiteLLM (+ digivault when tools run). Public `digithings.ai/chat` still needs Tunnel + Pages.

### Profile A GHCR pulls — blocked on Stage A (human)

After develop→main promotion and `Publish: service images` on `main`, migrate this
host to stock GHCR pins:

```bash
cp infra/digichat-release/.env.profile-a.example infra/digichat-release/.env.profile-a
# set AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGI_IMAGE_TAG, DIGICHAT_VERSION,
# DIGICHAT_REQUIRE_ROOT_AUTH=0, DIGICHAT_EMBED_HOSTS / TENANTS (digithings.ai only)
make digichat-profile-a-up
```

Until GHCR packages exist, pulls 404 — keep monorepo build above. Record the
`DIGI_IMAGE_TAG` pin in operator notes once Stage A verifies.

### digisearch (dual-sink)

Profile A compose does **not** start digisearch. For dogfood dual-sink smoke, run
digisearch beside the stack (`make stack-local` digisearch or Compose profile) and
point onboard `--digisearch-url` / digigraph `DIGISEARCH_URL` at it. See
[`docs/projects/digithings/README.md`](../../docs/projects/digithings/README.md).

digichat runtime embed registry (never a Docker build-arg — tokens leak in layers):

```bash
export DIGICHAT_REQUIRE_ROOT_AUTH=0
export DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai
export DIGICHAT_EMBED_TENANTS='{"digithings.ai":{"slug":"digithings","aliases":["www.digithings.ai"],"gateMode":"ungated","showByok":true,"showStatusBar":true,"layout":"page","activityDetail":"full","attribution":false,"token":"<unused-for-first-party>","backend":{"type":"digigraph"}}}'
```

Set `DIGICHAT_EMBED_HOSTS` (and/or tenant host keys) at **runtime** so CSP `frame-ancestors` includes digithings.ai — no digichat image rebuild. **Do not** add digiquant.io to embed hosts for chat (crawl-only).

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

## CSP verification (Stage 6)

| Side | Header | digithings.ai |
|---|---|---|
| Pages parent | `frame-src` ← `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` | digithings-web prebuild |
| digichat | `frame-ancestors` ← `DIGICHAT_EMBED_HOSTS` / tenants | digithings.ai, www only |

No digiquant-web `/chat` route. Future iframe parent on digiquant.io is a separate
human request.

## Smoke

1. Open https://digithings.ai/chat — no `/login` wall
2. Ask a vault-grounded question (e.g. what digigraph orchestrates)
3. Expect digichat activity rows from digigraph tools (digivault search) and an
   answer via digillm — not direct OpenRouter from Pages.

## Onboard corpus

```bash
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/digithings/onboard.yaml \
  --workdir /tmp/digithings-onboard \
  --dry-run
```

Apply + Supabase publish: see [`docs/projects/digithings/README.md`](../../docs/projects/digithings/README.md).

## Historical note

The `frontend/digichat-cloudflare/` Workers Paid Containers scaffold was removed
2026-08-06. Recover from git history only if digithings adopts Workers Paid later.
