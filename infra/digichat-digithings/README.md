# Digithings DigiChat hosting

DigiThings **marketing** chat runs on **Cloudflare Pages** (native digichat-ui +
digivault Function). See Phase 3 ops checklist.

[`frontend/digichat-cloudflare/`](../../frontend/digichat-cloudflare/README.md) is a
**deferred** Workers Paid / Containers option — not required for `/chat`.

## Hard constraint

- DigiThings has **no Azure**.
- DataTap DigiChat ACA is **client-only** — do not use for DigiThings.
- **2026-08-05:** a DigiThings misdeploy on DataTap WebSite was torn down.

Azure ACA scripts previously in this directory were removed — do not recreate them.
