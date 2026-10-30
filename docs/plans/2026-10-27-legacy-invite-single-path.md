# OCC on the single chat path

**Status:** proposed, 2026-10-27. Restores OCC and removes the second shell in one change.
**Tickets:** filed from this plan; linked in the PR.

## The problem

There is one chat application and one chat container, but two front doors:

| Path | Today |
|---|---|
| `/chat` | Worker → Container (the app, `basePath: /chat`) |
| `/chat/occ` | Worker `legacyInviteGate` → `fetch(request)` → **Pages shell** → iframe `/embed?host=occ.digithings.ai` → Container |

That split has cost us three things:

1. **Two copies of the gate** — `apps/digichat-cloudflare/src/legacy-invite-gate.ts` in the Worker and `apps/digithings-web/functions/chat/occ/[[path]].ts` in Pages.
2. **Two copies of the same secret** — `OCC_INVITE_KEY` exists on both the Worker and the Pages project, with no check that the values match. The Worker gate runs first, so a link generated from the Pages copy 404s at the Worker and looks exactly like a bad token.
3. **Two deploy surfaces that drift** — the Pages project builds on push; the container deploys by manual dispatch. On 2026-10-27 the promotion merged but did not deploy, and OCC was reported broken while the Pages twin was healthy.

There is also a wiring defect behind the second door: `legacyInviteGate(request, key)` is called with no upstream, so the valid-invite branch falls back to `fetch(request)` — a fetch of the same URL the Worker is already serving. The unit tests inject a stub upstream (`vi.fn`), so they pass while the production path has never been exercised. `scripts/smoke_occ_invite_gate.sh` tests only the **uninvited** 404.

## The design

**One path, one gate, one secret, one deploy.**

`/chat/occ` becomes a path served by the chat app itself. The Worker keeps the invite check and proxies to the container it already knows how to reach. No iframe, no Pages shell, no second gate.

```
valid token or cookie
  └─ Worker legacyInviteGate
       ├─ validates against OCC_INVITE_KEY (edge only)
       ├─ answers 302 to the tokenless URL, with occ_invite cookie
       │    (HttpOnly, Secure, SameSite=Strict, Path=/chat) — the key never
       │    stays in the address bar or in history
       ├─ on the cookie request: rewrites /chat/occ → /chat/embed?host=occ.digithings.ai
       ├─ moves the invite to `x-embed-token` (the app's existing transport)
       ├─ drops `?token=` from the container request
       └─ container.fetch(...)  ← same proxy `/chat` uses

missing or invalid invite
  └─ the site's byte-for-byte 404 (status, body, headers), before the container is asked
```

### Why the container needs no change

The app already has the exact seam this needs:

- `apps/digichat/src/lib/embed-token-transport.ts` — `x-embed-token` is the canonical transport; `?token=` is only a fallback. `src/proxy.ts` already strips `token` from the URL and forwards it as that header.
- `apps/digichat/src/lib/embed-invite-only.ts` — `inviteRequiredButMissing(host, resolvedSlug)` decides access by whether the token resolves to the invite-only tenant. A valid token resolves `occ`; the gate passes. No new header, no new trust, no container code.
- `/chat/embed` is already a route (the same `embed-route-shell.tsx` that serves `/embed`).

### Invariants this must preserve

1. `GET /chat/occ` with no token and no cookie → **404**, byte-for-byte the site 404. No title, branding or loader.
2. `GET /chat/occ?token=<valid>` → **302** to the tokenless URL (the key leaves the address bar)
   → **200** chat shell, **no iframe**, OCC tenant.
3. The redirect sets `occ_invite` (HttpOnly, Secure, SameSite=Strict, **Path=/chat**, no Max-Age).
   It was `Path=/chat/occ` at first; that cookie never reached `/chat/api/*`, so after the 302 the
   page painted and every chat turn and tenant-config read was unbound (gap G1). The redirect also
   expires any leftover `Path=/chat/occ` cookie.
4. A reload with the cookie and no query token → **200**. It re-affirms the same session cookie on
   `Path=/chat` (and expires the `Path=/chat/occ` one) so a browser holding the earlier cookie
   migrates without a new invite link.
8. The page's `/chat/api/*` calls are OCC **only** when the `/chat` cookie is valid **and** the
   Referer is `/chat/occ` (`bindLegacyInviteApiCall`; the gate serves the page with
   `Referrer-Policy: same-origin`). From that page the client's own tenant headers are dropped; a
   client `X-Digi-Tenant` is dropped on every `/chat/api/*` call; a house page with the cookie stays
   the house. The cookie never reaches the container.
9. The client renders at a bare `/chat/occ`: the server hands the rendered `host` to `EmbedClient`
   (`initialHost`), since Next keeps `window.location` as the client URL.
5. The invite key **never** appears in the container request URL, the HTML, or the flight payload.
6. The key exists in **one** place: the Worker secret.
7. An invalid invite never wakes the container.

## The change (one PR)

**Worker**
- `src/legacy-invite-gate.ts`: `legacyInviteGate(request, key, containerUpstream, siteUpstream = fetch)`.
  - valid: build `/chat/embed?host=occ.digithings.ai`, set `x-embed-token`, delete `token`, call `containerUpstream`.
  - invalid: `siteNotFound(origin, siteUpstream)` — the 404 still comes from Pages, never the container.
- `src/index.ts`: compute the container before the OCC branch and pass `(req) => container.fetch(req)`.
- `wrangler.toml`: keep `/chat/occ*` explicit above `/chat*` (longest-prefix is enough, but explicit is readable).

**Delete**
- `apps/digithings-web/app/chat/occ/page.tsx`
- `apps/digithings-web/functions/chat/occ/[[path]].ts`
- `ChatPageShell`'s `acceptsInviteToken` path if nothing else uses it.

**Ops (after the deploy is verified)**
- Remove `OCC_INVITE_KEY` from the Pages project `digithings-ai`. The Worker secret stays.
- Keep the Pages project: it still serves the marketing site.

**Tests**
1. Unit (`legacy-invite-gate.test.ts`): the container request path is `/chat/embed`, `host` is set, `token` is absent, `x-embed-token` is the key, the cookie is set only for the token arm, and the 404 uses the site upstream (not the container).
2. Source contract (Python, with the other `tests/scripts` checks): `index.ts` passes a container upstream to `legacyInviteGate`; the Pages shell and Pages function do not exist. That is the test that would have caught today's wiring bug.
3. Smoke (`scripts/smoke_occ_invite_gate.sh`): keep the uninvited 404 check, add an invited check that runs only when `OCC_INVITE_KEY` is set, asserting 200 and shell markup, and that the response is not an iframe.

**Docs**
- `apps/digichat-cloudflare/README.md` path map: `/chat/occ` becomes "Worker → Container (invite-gated at the edge)", not "Pages shell".
- This plan.

## Rollout and rollback

- One Worker dispatch from `main`, behind the `production` approval.
- Verify in order: invalid token 404 (unchanged), valid token 200 and **no iframe**, cookie reload 200, container rev is the deployed commit.
- Rollback: Cloudflare keeps Worker versions — redeploy the previous version. The Pages shell is deleted in the same PR, so rollback also means reverting that commit; note this in the PR.

## What this does not do

- It does not change the tenant model: OCC stays a tenant of the same container.
- It does not remove the `/embed` compatibility route — other tenants and existing integrations still use it.
- It does not touch the invite key's value or rotation.

## Definition of done

- `/chat/occ?token=<valid>` serves the chat with no iframe, under the OCC tenant.
- `/chat/occ` without an invite is the site's 404, unchanged.
- The cookie reload works.
- `OCC_INVITE_KEY` exists only as a Worker secret.
- The valid path is covered by a test that runs against the real wiring, and by a smoke test.
