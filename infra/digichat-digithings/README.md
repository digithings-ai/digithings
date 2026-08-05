# Digithings DigiChat (Phase 3) — hosting notes

## Hard constraint — subscription ownership

**DigiThings DigiChat MUST NOT run in any DataTap Azure subscription.**

- Forbidden: **DataTap WebSite** `fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0`.
- DataTap is a client. DigiThings operators may only touch DataTap Azure for
  DataTap’s own website DigiChat ACA.
- **2026-08-05:** a misdeploy (`digithings-rg` / CAE / ACR / digichat ACA) into
  DataTap WebSite was torn down. Do not recreate DigiThings stack there.

## Product direction (locked)

- DigiChat is a **path on digithings.ai**: CF route `digithings.ai/embed*` →
  DigiThings-owned DigiChat Node; Pages `/chat` iframes that path (same-origin).
- Do **not** use `chat.digithings.ai` as the marketing embed origin.
- Leave `DIGICHAT_BASE_PATH` unset for this cutover.
- Scripts in this tree are DigiThings-subscription only; they must refuse DataTap
  accounts (`az account show`).

## Scripts

`build-image.sh`, `import-ghcr.sh`, and `apply-secrets.sh` refuse DataTap Azure
accounts. Use only after DigiThings-owned subscription is confirmed.

## Tenant / secrets shape

See `docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md`.
