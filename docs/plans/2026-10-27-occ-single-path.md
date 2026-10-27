# OCC on the single chat path

**Status:** proposed, 2026-10-27. Restores OCC and removes the second shell in one change.
**Tickets:** filed from this plan; linked in the PR.

## The problem

There is one chat application and one chat container, but two front doors:

| Path | Today |
|---|---|
| `/chat` | Worker → Container (the app, `basePath: /chat`) |
| `/chat/occ` | Worker `occGate` → `fetch(request)` → **Pages shell** → iframe `/embed?host=occ.digithings.ai` → Container |

That split has cost us three things:

1. **Two copies of the gate** — `apps/digichat-cloudflare/src/occ-gate.ts` in the Worker and `apps/digithings-web/functions/chat/occ/[[path]].ts` in Pages.
2. **Two copies of the same secret** — `OCC_INVITE_KEY` exists on both the Worker and the Pages project, with no check that the values match. The Worker gate runs first, so a link generated from the Pages copy 404s at the Worker and looks exactly like a bad token.
3. **Two deploy surfaces that drift** — the Pages project builds on push; the container deploys by manual dispatch. On 2026-10-27 the promotion merged but did not deploy, and OCC was reported broken while the Pages twin was healthy.

There is also a wiring defect behind the second door: `occGate(request, key)` is called with no upstream, so the valid-invite branch falls back to `fetch(request)` — a fetch of the same URL the Worker is already serving. The unit tests inject a stub upstream (`vi.fn`), so they pass while the production path has never been exercised. `scripts/smoke_occ_invite_gate.sh` tests only the **uninvited** 404.

## The design

**One path, one gate, one secret, one deploy.**

`/chat/occ` becomes a path served by the chat app itself. The Worker keeps the invite check and proxies to the container it already knows how to reach. No iframe, no Pages shell, no second gate.

```
valid token or cookie
  └─ Worker occGate
       ├─ validates against OCC_INVITE_KEY (edge only)
       ├─ sets occ_invite cookie (HttpOnly, SameSite=Strict, Path=/chat/occ)
       ├─ rewrites /chat/occ → /chat/embed?host=occ.digithings.ai
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
2. `GET /chat/occ?token=<valid>` → **200** chat shell, **no iframe**, OCC tenant.
3. The same request sets `occ_invite` (HttpOnly, SameSite=Strict, Path=/chat/occ, no Max-Age).
4. A reload with the cookie and no query token → **200**, no `Set-Cookie` re-issue.
5. The invite key **never** appears in the container request URL, the HTML, or the flight payload.
6. The key exists in **one** place: the Worker secret.
7. An invalid invite never wakes the container.

## The change (one PR)

**Worker**
- `src/occ-gate.ts`: `occGate(request, key, containerUpstream, siteUpstream = fetch)`.
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
1. Unit (`occ-gate.test.ts`): the container request path is `/chat/embed`, `host` is set, `token` is absent, `x-embed-token` is the key, the cookie is set only for the token arm, and the 404 uses the site upstream (not the container).
2. Source contract (Python, with the other `tests/scripts` checks): `index.ts` passes a container upstream to `occGate`; the Pages shell and Pages function do not exist. That is the test that would have caught today's wiring bug.
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
