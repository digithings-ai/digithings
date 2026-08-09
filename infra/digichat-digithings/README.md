# digithings digichat hosting

digithings **marketing** chat runs on **Cloudflare Pages** (native digichat-ui +
digivault Function). See Phase 3 ops checklist.

The `frontend/digichat-cloudflare/` Workers Paid / Containers scaffold was **removed on
2026-08-06**. It had no deploy path in the repo — Containers require Workers Paid and
digithings is on Free (see the Phase 3 design spec) — and it was the only thing pulling
`wrangler` (and five `workerd` platform binaries) into the root lockfile. The Cloudflare
account itself was not checked. It is not required for `/chat`; recover it from git history if
digithings ever adopts Workers Paid.

## Hard constraint

- digithings has **no Azure**.
- DataTap digichat ACA is **client-only** — do not use for digithings.
- **2026-08-05:** a digithings misdeploy on DataTap WebSite was torn down.

Azure ACA scripts previously in this directory were removed — do not recreate them.
