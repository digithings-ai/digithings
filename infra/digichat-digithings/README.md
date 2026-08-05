# Digithings DigiChat (Phase 3) — hosting notes

## Hard constraint — subscription ownership

**DigiThings DigiChat MUST NOT run in any DataTap Azure subscription.**

- Forbidden: **DataTap WebSite** `fc64972f-8c1e-46f1-a2b0-bd2407c0cdf0`.
- DataTap is a client. DigiThings operators may only touch DataTap Azure for
  DataTap’s own website DigiChat ACA.
- **2026-08-05:** a misdeploy (`digithings-rg` / CAE / ACR / digichat ACA) into
  DataTap WebSite was torn down. Do not recreate DigiThings stack there.

## Product direction (owner)

- Prefer DigiChat as a **path on the DigiThings website**, with `/chat` embedding
  that path with config.
- **Pause** building a separate `chat.digithings.ai` ACA until DigiThings-owned
  hosting is decided.
- Do **not** provision DigiThings DigiChat Azure resources from this tree until
  a DigiThings-owned subscription (or website-path host) is confirmed via
  `az account show` (name/id must not be DataTap*).

## Scripts

`build-image.sh`, `import-ghcr.sh`, and `apply-secrets.sh` refuse to run when
the active Azure account name matches DataTap. They are for DigiThings-owned
infra only, if/when Azure hosting is chosen.

## Tenant / secrets shape

See `docs/superpowers/rollout/2026-08-05-digichat-phase3-ops-checklist.md`.
Digivault secrets stay as env vars / secret refs; tenant JSON holds env **name**
refs only.
