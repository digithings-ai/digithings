# digithings digichat hosting

digithings marketing chat uses **digichat → digigraph → digillm + digivault hub**.
digithings has **no Azure**. Do not use DataTap ACA for digithings.

Canonical **production** path (no laptop dependency):

```text
Browser digithings.ai/chat[/occ]
  → iframe digichat /embed (Cloudflare Worker → digichat Container)
       → digigraph https://graph.digithings.ai  (Profile A stack Container)
       → digikey   https://key.digithings.ai    (same stack Container)
            digigraph → loopback digisearch / digivault / LiteLLM
```

See [`docs/architecture/digichat-modular-frontend.md`](../../docs/architecture/digichat-modular-frontend.md)
and ADR-0018.

**Client #0 dogfood:** corpus + cutover plan live under
[`docs/projects/digithings/`](../../docs/projects/digithings/)
([plan](../../docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md)).

## Client / release installs

digithings’ production host is **Cloudflare Containers**. Clients installing
digichat themselves should use [`infra/digichat-release/`](../digichat-release/)
and [`docs/digichat/INSTALL.md`](../../docs/digichat/INSTALL.md) (Profile A or B).

## Hard constraints

- digithings has **no Azure**.
- DataTap digichat ACA is **client-only**.
- Chat UI is **digithings.ai only** — do **not** add a digiquant.io `/chat` page.
- **Production digichat:** Cloudflare Containers —
  [`frontend/digichat-cloudflare/README.md`](../../frontend/digichat-cloudflare/README.md).
  One Container serves digithings + OCC (and future) tenants.
- **Production backends:** Cloudflare Containers Profile A stack —
  [`frontend/digithings-stack-cloudflare/README.md`](../../frontend/digithings-stack-cloudflare/README.md)
  (`graph.digithings.ai` / `key.digithings.ai`). **Do not** point production
  digichat at Mac Docker or `*.trycloudflare.com` quick tunnels.
- **Dev-only:** Mac Compose (+ optional quick tunnels) below.

## Auth (Option A)

Dogfood and default installs keep root Auth.js **OFF**:

```bash
DIGICHAT_REQUIRE_ROOT_AUTH=0   # default; `/` → `/embed`
```

Public chat is the ungated embed iframe (`gateMode: ungated`). Do not enable
`DIGICHAT_DEV_AUTH` in production.

## Production — Cloudflare Containers

### digichat (BFF)

See [`frontend/digichat-cloudflare/README.md`](../../frontend/digichat-cloudflare/README.md).

1. Workers Paid on the digithings Cloudflare account.
2. Deploy digichat Worker + Container; zone routes for `/embed*`, digichat APIs, `/_dtchat*`.
3. Secrets: `AUTH_SECRET`, `DIGICHAT_EMBED_TENANTS`, `DIGIGRAPH_INTERNAL_URL`,
   `DIGIKEY_URL`, `DIGIKEY_BFF_TOKEN` via `wrangler secret put` only.

### Profile A stack (digigraph + digikey + …)

See [`frontend/digithings-stack-cloudflare/README.md`](../../frontend/digithings-stack-cloudflare/README.md).

**Human gate — infra/network:** `graph.digithings.ai` and `key.digithings.ai`
are public hostnames (JWT/BFF still required). Review before merge/deploy.

```bash
cd frontend/digithings-stack-cloudflare
npx wrangler secret put DIGIKEY_PRIVATE_KEY_PEM
npx wrangler secret put DIGIKEY_BFF_TOKEN
npx wrangler secret put GROQ_API_KEY
npx wrangler deploy
```

Retarget digichat:

```bash
cd frontend/digichat-cloudflare
printf '%s' 'https://graph.digithings.ai' | npx wrangler secret put DIGIGRAPH_INTERNAL_URL
printf '%s' 'https://key.digithings.ai'   | npx wrangler secret put DIGIKEY_URL
npx wrangler secret put DIGIKEY_BFF_TOKEN   # must match stack
```

Pages: `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN=https://digithings.ai` (same host).

### OCC corpus

Production `DIGICHAT_EMBED_TENANTS` must include OCC:

```json
"occ.digithings.ai": {
  "slug": "occ",
  "backend": {
    "type": "digigraph",
    "digisearchIndex": "occ_help",
    "vaultPathPrefix": "clients/online-compliance-center"
  }
}
```

digichat forwards `X-Digi-Corpus-Index` / `X-Digi-Vault-Prefix`; digigraph
`corpus_routing` applies them to digisearch / digivault tools.

Stack entrypoint seeds a **minimal** `occ_help` FAQ + vault notes into Chroma
**before** supervisord starts digisearch (avoids multi-process SQLite locks).
Full crawl of help.online-compliance-center.com remains **HOLD** until approval
([GAPLOG](../../docs/projects/online-compliance-center/GAPLOG.md)).

**CF secret retarget:** only after `graph.digithings.ai` / `key.digithings.ai`
healthz succeed — never Mac `*.trycloudflare.com` tunnels.

## Dev-only — Mac Compose (+ optional tunnels)

Use this for local iteration. **Not** a production dependency.

### Prefer: Profile A bundle (one stack container)

Same image as production CF backends. Replaces digikey + digigraph + digisearch +
digivault + LiteLLM + Redis as separate containers:

```bash
# Stop the heavy monorepo stack if it is already up (port clash on 8000/8005/3005)
docker compose --profile digichat --profile digivault --profile litellm-cache down

cp infra/digichat-release/.env.profile-a-bundle.example \
   infra/digichat-release/.env.profile-a-bundle
# AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGICHAT_VERSION, GROQ_API_KEY, …
make digichat-profile-a-bundle-up
```

Details: [`frontend/digithings-stack-cloudflare/README.md`](../../frontend/digithings-stack-cloudflare/README.md)
(local `docker run` / compose). digiquant, digismith HTTP, and Ollama stay off.

### Monorepo build (full N-container stack)

Only when you need digiquant / observability / per-service rebuilds:

```bash
export DIGIVAULT_URL=http://digivault:8004
# digikey BFF token + LLM keys as in root .env.example

docker compose --profile digichat --profile digivault --profile litellm-cache up -d --build
```

**Local smoke (no Tunnel):** open `http://127.0.0.1:3005/embed?host=digithings.ai` or
`http://127.0.0.1:3005/embed?host=occ.digithings.ai` or
`POST /api/chat` with `X-Embed-Host: https://digithings.ai`.

### Quick tunnels (dev only — never production)

If you temporarily need the Cloudflare digichat Container to reach Mac
digigraph/digikey during bring-up, `cloudflared tunnel --url http://127.0.0.1:8000`
style quick tunnels may be used **locally only**. Production digichat secrets
must point at `graph.digithings.ai` / `key.digithings.ai`, not `*.trycloudflare.com`.

### Profile A GHCR pulls — local / client install

After GHCR packages exist on `main`:

```bash
cp infra/digichat-release/.env.profile-a.example infra/digichat-release/.env.profile-a
# set AUTH_SECRET, DIGIKEY_BFF_TOKEN, DIGI_IMAGE_TAG, DIGICHAT_VERSION,
# DIGICHAT_REQUIRE_ROOT_AUTH=0, DIGICHAT_EMBED_HOSTS / TENANTS
make digichat-profile-a-up
```

### digisearch (dual-sink) on Compose

Profile A compose does **not** start digisearch. For local dual-sink smoke, run
digisearch beside the stack and point digigraph `DIGISEARCH_URL` at it. Production
CF stack includes digisearch in-process.

digichat runtime embed registry (never a Docker build-arg — tokens leak in layers):

```bash
export DIGICHAT_REQUIRE_ROOT_AUTH=0
export DIGICHAT_EMBED_HOSTS=digithings.ai,www.digithings.ai,occ.digithings.ai
export DIGICHAT_EMBED_TENANTS='{"digithings.ai":{"slug":"digithings","aliases":["www.digithings.ai"],"gateMode":"ungated","showByok":true,"showStatusBar":true,"layout":"page","llmAccess":"free_then_byok","activityDetail":"full","attribution":false,"token":"<unused-for-first-party>","backend":{"type":"digigraph"}},"occ.digithings.ai":{"slug":"occ","gateMode":"ungated","showByok":true,"showStatusBar":true,"layout":"page","activityDetail":"full","title":"OCC help assistant","welcome":"Ask about Online Compliance Center policies, procedures, and help articles.","attribution":false,"token":"<unused-for-first-party>","backend":{"type":"digigraph","digisearchIndex":"occ_help","vaultPathPrefix":"clients/online-compliance-center"}}}'
```

OCC uses virtual host `occ.digithings.ai` (no DNS) for `/chat/occ` — see
[`docs/projects/online-compliance-center/README.md`](../../docs/projects/online-compliance-center/README.md).

## digithings.ai `/chat` and `/chat/occ`

Static Pages shells (`DtNav` + iframe) load
`${NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN}/embed?host=digithings.ai` or
`…?host=occ.digithings.ai` — **one** digichat Node/Container, two tenants.
The Pages Function OpenRouter digivault loop is **retired**.

## CSP verification

| Side | Header | digithings.ai |
|---|---|---|
| Pages parent | `frame-src` ← `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` | digithings-web prebuild |
| digichat | `frame-ancestors` ← `DIGICHAT_EMBED_HOSTS` / tenants | digithings.ai, www, occ.digithings.ai |

## Smoke

1. `curl -sf https://graph.digithings.ai/healthz` and `https://key.digithings.ai/healthz`
2. Open https://digithings.ai/chat — no `/login` wall
3. Ask a vault-grounded question; expect digigraph tool activity
4. OCC: https://digithings.ai/chat/occ — activity should show digisearch against `occ_help`

## Onboard corpus

```bash
python scripts/docs_onboard/run_onboard.py \
  --manifest docs/projects/digithings/onboard.yaml \
  --workdir /tmp/digithings-onboard \
  --dry-run
```

OCC full apply waits on crawl approval (GAPLOG). CF stack ships a static seed.

## Historical note

Containers scaffold lives at `frontend/digichat-cloudflare/` (#2073).
Profile A stack Container: `frontend/digithings-stack-cloudflare/` (#2078).
Earlier digichat-only deletion (#1949) assumed Workers Free forever; Paid unlocks
same-hostname digichat without a separate Tunnel hostname.
