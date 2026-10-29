# Tenant schema notes

The tenant doc schema is R0's (`apps/digichat` deploy-config, checked by `config:check`).
These rules apply to every client repo's `tenant/` files and to the tenant writer that
puts them in KV. They come from the Guard review of 2026-10-29.

## 1. `access.invite` is server-only

- The invite settings (`access.invite`: mode, the secret **name** of the invite key,
  cookie name, max age) live only on the server side of the tenant doc.
- They are **stripped** from `/api/embed/tenant-config` and from every other payload that
  reaches a browser or client (embed bootstrap, devkit export, client projection).
- R0 must pin this with a test (U1/U5 work): the client projection of a doc with `access.invite` set carries no
  `access` key at all.
- In this template, `tenant/env/<env>.yaml` sets `gate.mode` and `secrets.inviteKey` (a
  name, never a value). The deploy writes them into the server-only `access.invite` block.

## 2. `chrome.pathPrefix` is validated by the tenant writer

The tenant writer refuses a doc unless `chrome.pathPrefix`:

- is a lowercase slug path: `^/[a-z0-9]+(-[a-z0-9]+)*$` (one segment, no trailing slash,
  no `..`, no uppercase, no encoded characters);
- does not collide with another tenant's `pathPrefix` (exact match or either one a
  prefix of the other);
- does not overlap a house route: `/chat`, `/api`, `/embed`, `/_dtchat`, `/_digichat`,
  `/_digichat-admin`, `/healthz` and any route R0 adds later. The list lives in R0, not here,
  and the writer reads it from there.

A tenant served under the shared chat page uses a sub-path R0 assigns (for example
`/chat/<slug>`); it never claims a house route itself.

## 3. Gated tenants fail closed

- If a tenant's doc is **missing, unreadable or invalid** (schema error, bad
  `pathPrefix`, missing invite secret name or value), a gated tenant (`gate.mode: invite`)
  is **denied**, not served ungated and not served with defaults.
- Ungated (house) defaults never apply to a host or path that a gated tenant claims.
- The deny is a plain 403/404 with no tenant detail in the body. The reason goes only to
  the server log.
