# Tenant schema notes

The tenant doc schema is R0's (`apps/digichat` deploy-config, checked by `config:check`).
These rules apply to every client repo's `tenant/` files and to the tenant writer that
puts them in KV. They come from the Guard review of 2026-10-29 and use the field names of
U5a (R0 draft PR #6680, `apps/digichat/src/lib/deploy-config/tenant-chrome.ts`).

## 0. Field names: tenant doc → flat R0 registry row

The tenant doc (`tenant/digichat.yaml`, R0 `DeploymentSchema`) nests the chat fields
under `chrome`; the flat R0 registry row (`DIGICHAT_EMBED_TENANTS` entry,
`EmbedTenantConfig`) carries them at the top level. R0's loader maps one onto the other:

| Tenant doc                         | Registry row  | Meaning                                                    |
| ---------------------------------- | ------------- | ---------------------------------------------------------- |
| `slug`                             | `slug`        | the tenant's own slug (corpus map, claims)                 |
| `chrome.slug`                      | `chatSlug`    | the tenant chat slug; R0 serves it at `/chat/<slug>`        |
| `chrome.pathPrefix` (legacy)       | `pathPrefix`  | legacy full path `/chat/<slug>`, one release (see §2)      |
| `chrome.productChat`               | `productChat` | boolean; a tenant product chat. Omitted: not one           |
| `access` (incl. `access.invite`)   | `access`      | server-only access block (see §1)                          |

New docs write `chrome.slug` only. Neither the doc nor the row ever stores a built path.

`chrome.slug` needs an R0 that includes U5a: R0's `ChromeSchema` is strict, so an R0
without #6680 refuses the key (`config:check`: unrecognized key `slug`). Until #6680 is on
R0 `develop`, `make test`'s R0 schema check is an expected failure (`xfail(strict=True)`)
on a checkout with Node deps; without them it skips locally and fails in CI. After it lands,
`make bump SHA=<develop sha with U5a>`.
`make bump` past U5a must also remove that `xfail` marker from `test_tenant_doc_passes_the_r0_schema` (strict: the bump makes it XPASS, which fails the run).

Product-chat safe default (U5a #6680): a new `chrome.productChat` row gets the premium
meter on, the tokens-per-minute limit on and the model picker off. The example tenant
keeps that default and writes no opt-out. The opt-out fields are `models.allowPicker: true`,
`models.premiumMeter: false` and `guardrails.tpmLimit: false` (`models.occPicker` is a
legacy alias of `allowPicker`). A client repo that needs legacy-row behaviour must write
these explicitly; R0 never applies them to a new row. With the limit on, R0 refuses a
`chrome.productChat` row unless it sets a positive whole-number `guardrails.tokensPerMinute`
(`deployment` or `user`) or opts out with `guardrails.tpmLimit: false`. The example tenant
writes `guardrails.tokensPerMinute.deployment` as an example value; each client sets its own.

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
- As of U5a (#6680), `access.invite` stays server-only and outside the browser allowlist:
  `toEmbedClientConfig` has no `access` branch, and a row with an invalid `access` block is
  refused without echoing it. #6680 types only `cookieName`, `label` and `maxAgeDays` and
  passes the rest through, because the key's storage shape is **still pending One**.
  Do not write a key field into `access.invite` until One confirms the shape.

## 2. The tenant slug is validated by the tenant writer

The tenant doc stores **only the chat slug**, at `chrome.slug` (registry row: `chatSlug`),
which must match `^[a-z0-9]+(-[a-z0-9]+)*$` (R0 `TENANT_PATH_SLUG`; lowercase, one
segment, no slash, no `..`, no encoded characters; for example `example`, `example-b`).
The doc never stores a full path. R0 builds the served path `/chat/<slug>`
(`tenantChatPath`) with the shared helper in §3.

The tenant writer refuses a doc when:

- the slug is a reserved house name (for example `api`, `embed`, `_dtchat`, `_digichat`,
  `_digichat-admin`, `healthz`, or any name R0 reserves later; the list lives in R0 and
  the writer reads it from there);
- the slug is already used by another tenant (rows of the same tenant may share it).

The writer runs R0's `validateTenantChatSlug(chrome.slug, { tenant, others })` with every
other tenant's claim before it stores a doc.

Collision and house-route checks compare **whole path segments**, not raw strings:
`/chat/abc` and `/chat/abcd` do not collide, while `/chat` and `/chat/x` overlap.

Legacy fallback (one release, until P-exit): a full `chrome.pathPrefix` (row: `pathPrefix`) of the form `/chat/<slug>` is still accepted; the slug is taken from it (`resolveTenantChatSlug`), any other shape is refused, the built path must be byte-identical to today's, and there is no live config migration.
If a doc has both `chrome.slug` and a legacy `chrome.pathPrefix` (row: `chatSlug` and `pathPrefix`) and the two disagree, the doc is refused and the tenant stays closed.

## 3. Gated tenants fail closed

The shared path helper is U5a's (R0 draft PR #6680,
`apps/digichat/src/lib/deploy-config/tenant-chrome.ts`): `TENANT_PATH_SLUG`,
`HOUSE_ROUTE_SEGMENTS`, `tenantChatPath`, `tenantChatSlugFromPath`, `pathsOverlap`,
`validateTenantChatSlug`, `resolveTenantChatSlug`, `gatedTenantClaims` and
`classifyTenantChatPath`. The Worker gate (U1) imports it; nothing re-implements the slug
rule, the house-route list or the path classification.

- If a tenant's doc is **missing, unreadable or invalid** (schema error, bad slug,
  missing or unusable invite key material), a gated tenant (`gate.mode: invite`) is
  **denied**, not served ungated and not served with defaults.
- Gated paths come from an **R0-side claims list**, seeded from today's live value, with
  the last-known-good copy of the doc as backup (`gatedTenantClaims`, U5a #6680). A missing doc on a claimed path
  is denied.
- Ungated (house) defaults never apply to a host or path that a gated tenant claims.
- The deny is a plain 403/404 with no tenant detail in the body. The reason goes only to
  the server log.
