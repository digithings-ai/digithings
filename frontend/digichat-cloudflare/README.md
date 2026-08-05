# digichat on Cloudflare Containers (DEFERRED)

> **Status:** Deferred. digithings marketing chat ships on **Cloudflare Pages**
> (native digichat-ui + digivault Function) under the Workers **Free** plan.
> Containers require Workers **Paid** — do not block Phase 3 on this scaffold.
>
> Spec: `docs/superpowers/specs/2026-08-05-digichat-phase3-unification-design.md`

Optional future path if digithings upgrades to Workers Paid and wants one digichat
Node for `/embed` on digithings.ai (customer-style embeds on the marketing domain).

digithings has **no Azure**. DataTap keeps its own digichat Azure ACA.

## When Paid is available

```bash
cd frontend/digichat-cloudflare
npm install
npx wrangler secret put …
npx wrangler deploy
# then zone routes for /embed*, /api/*, /_dtchat*
```

Until then, ignore this package for digithings.ai `/chat` deploys.
