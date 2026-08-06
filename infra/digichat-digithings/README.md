# Digithings DigiChat hosting

DigiThings **marketing** chat runs on **Cloudflare Pages** (native digichat-ui +
digivault Function). See Phase 3 ops checklist.

The `frontend/digichat-cloudflare/` Workers Paid / Containers scaffold was **removed on
2026-08-06**. It was never deployed — Containers require Workers Paid, digithings is on Free —
and it was the only thing pulling `wrangler` (and five `workerd` platform binaries) into the
root lockfile. It is not required for `/chat`; recover it from git history if digithings ever
adopts Workers Paid.

## Hard constraint

- DigiThings has **no Azure**.
- DataTap DigiChat ACA is **client-only** — do not use for DigiThings.
- **2026-08-05:** a DigiThings misdeploy on DataTap WebSite was torn down.

Azure ACA scripts previously in this directory were removed — do not recreate them.
