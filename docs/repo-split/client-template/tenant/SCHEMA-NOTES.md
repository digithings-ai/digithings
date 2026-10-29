# Tenant schema notes

The tenant doc schema is R0's (`apps/digichat` deploy-config, checked by `config:check`).
These rules apply to every client repo's `tenant/` files and to the tenant writer that
puts them in KV. They come from the Guard review of 2026-10-29.

## 1. `access.invite` is server-only

- The invite settings (`access.invite`: mode, how the invite key is stored, cookie name,
  max age) live only on the server side of the tenant doc.
- `/api/embed/tenant-config` and every other payload that reaches a browser or client
  (embed bootstrap, devkit export, client projection) is **built from an allowlist of
  display fields**. Nothing is copied from the full doc and then stripped, so `access`
  (and `token` or `tokenEnv`) never appears in a browser-facing response, including any
  field added later.
- R0 must pin this with a test (U1/U5 work): the client projection of a doc with
  `access.invite` set carries no `access` key at all.
- **PENDING One's confirmation:** how `access.invite` stores the invite key. Two options,
  not yet chosen:
  1. the secret's env **name** (never its value); or
  2. `HMAC-SHA256(INVITE_PEPPER, key)` (Guard's proposal).
- In this template, `tenant/env/<env>.yaml` sets `gate.mode` and `secrets.inviteKey`. The
  deploy writes them into the server-only `access.invite` block in whichever form is
  confirmed.

## 2. The tenant slug is validated by the tenant writer

The tenant doc stores **only the slug**, which must match `^[a-z0-9]+(-[a-z0-9]+)*$`
(lowercase, one segment, no slash, no `..`, no encoded characters; for example `example`,
`example-b`). The doc never stores a full path. R0 builds the served path `/chat/<slug>`
with one shared helper, which U1 imports (see U5a).

The tenant writer refuses a doc when:

- the slug is a reserved house name (for example `api`, `embed`, `_dtchat`, `_digichat`,
  `_digichat-admin`, `healthz`, or any name R0 reserves later; the list lives in R0 and
  the writer reads it from there);
- the slug is already used by another tenant.

Collision and house-route checks compare **whole path segments**, not raw strings:
`/chat/abc` and `/chat/abcd` do not collide, while `/chat` and `/chat/x` overlap.

Legacy fallback (one release, until P-exit): a full `pathPrefix` of the form `/chat/<slug>` is still accepted; the slug is taken from it, any other shape is refused, the built path must be byte-identical to today's, and there is no live config migration.
If a doc has both a `slug` and a legacy `pathPrefix` and the two disagree, the doc is refused and the tenant stays closed.

## 3. Gated tenants fail closed

- If a tenant's doc is **missing, unreadable or invalid** (schema error, bad slug,
  missing or unusable invite key material), a gated tenant (`gate.mode: invite`) is
  **denied**, not served ungated and not served with defaults.
- Gated paths come from an **R0-side claims list**, seeded from today's live value, with
  the last-known-good copy of the doc as backup (see U5a). A missing doc on a claimed path
  is denied.
- Ungated (house) defaults never apply to a host or path that a gated tenant claims.
- The deny is a plain 403/404 with no tenant detail in the body. The reason goes only to
  the server log.
