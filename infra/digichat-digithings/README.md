# Digithings DigiChat hosting — DEPRECATED for Azure

DigiThings DigiChat runs on **Cloudflare Containers**, not Azure.

See [`frontend/digichat-cloudflare/README.md`](../../frontend/digichat-cloudflare/README.md)
and [`docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md`](../../docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md).

## Hard constraint

- DigiThings has **no Azure**.
- DataTap DigiChat ACA is **client-only** — do not use for DigiThings.
- **2026-08-05:** a DigiThings misdeploy on DataTap WebSite was torn down.

Scripts in this directory (`build-image.sh`, `import-ghcr.sh`, `apply-secrets.sh`)
targeted Azure ACA and must **not** be used for DigiThings. Prefer Cloudflare
Containers deploy from `frontend/digichat-cloudflare`.
