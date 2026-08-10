# digichat Phase 3 — digithings ops checklist

## Hostname / hosting (locked — amended)

- **Visitor chat:** `digithings.ai/chat` — Cloudflare Pages (`frontend/digithings-web`) native `DigiChatSession` + digivault **Pages Function** (`functions/api/chat.ts`).
- **No Containers / no iframe** for digithings marketing chat (Workers Free plan).
- digithings has **no Azure**. Do **not** use DataTap’s digichat ACA. Do **not** use `chat.digithings.ai` as the marketing host.
- Customer digichat embeds (DataTap) continue on digichat `/embed` — out of scope here.

## Hard constraint — Azure

**digithings digichat MUST NOT run in any Azure subscription.**

## digithings marketing chat = Pages (free)

1. Confirm Pages project `digithings-ai` secrets:
   - `OPENROUTER_API_KEY`
   - `CORE_SUPABASE_URL`
   - `CORE_SUPABASE_ANON_KEY`
2. Deploy digithings-web (build mirrors `frontend/digithings-web/functions` → repo-root `functions/`).
3. No `NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN` required for `/chat`.
4. Optional deferred: Workers Paid + `frontend/digichat-cloudflare/` if later promoting to Containers.
   *Superseded 2026-08-06 — that scaffold was deleted unused; see ADR-0018 historical note 4.*

### Local

```bash
cp frontend/digithings-web/.dev.vars.example frontend/digithings-web/.dev.vars
# fill OPENROUTER_API_KEY, CORE_SUPABASE_URL, CORE_SUPABASE_ANON_KEY
```

## Smoke

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://digithings.ai/chat
curl -s -o /dev/null -w '%{http_code}\n' -X POST https://digithings.ai/api/chat \
  -H 'content-type: application/json' \
  -d '{"messages":[{"role":"user","content":"ping"}]}'
# expect 200 stream (or 503 if secrets missing — fix Pages secrets)
```

Browser: landing quick-ask → `/chat` seeded turn; BYOK panel.

## Merge gate for #1868

`/chat` native UI + `/api/chat` Function present; iframe/`ChatEmbedShell` gone; build script mirrors Functions. Containers deploy is **not** required.
