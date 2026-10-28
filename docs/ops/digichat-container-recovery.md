# Recovering a wedged digichat container

How to recover `digithings-digichat` when a Container instance stops
serving and will not be reclaimed. Written 2026-10-19 after the fourth
occurrence, with the reset lever added the same day.

## When this applies

- Chat fails repeatedly with `503 container_booting`, or with
  `Maximum number of running container instances exceeded`, and it does **not**
  clear within about five minutes.
- `wrangler containers instances <app-id>` shows an instance stuck in `running`
  while real requests fail, and it is still there long after idling past
  `sleepAfter` (one minute).

Two things that are **not** signals, measured on 2026-10-19:

- **The `health` counters.** digichat reports `active: 1, healthy: 0` as its
  normal steady state while running — it reported exactly that after a
  perfectly successful cold start. It reports `healthy: 1` only while
  stopped/inactive. Do not page on this field.
- **A 5xx within ~90 seconds of a deploy.** That is a rollout artefact. The
  deploy resets the Durable Object and signals the instance to exit, so the
  request in flight fails. The Worker now answers that with a retryable 503
  and a `Retry-After` header, and retries a request without a body once
  itself. Back off and repeat the request; do not reset a container that is
  still starting.

## Application ids

| App | Application id |
|---|---|
| digichat | `a034d556-d4a1-405e-8ed5-a74d7a1a1c47` (`digithings-digichat-digichatcontainer`) |
| stack (digistack) | `a03202c3-9e75-414b-acd4-34addec6460d` |
| stack (digiquant mcp) | `a032ed8e-723d-4800-bf65-315c5f0d4454` |
| runner | `a037b73d-b719-4435-aa91-d3e56795b24f` |

These change if an application is ever deleted and recreated — which is exactly
what step 5 does, so update this table if you use it.

## Step 1 — confirm, do not guess

```bash
npx wrangler@4.133.0 containers instances a034d556-d4a1-405e-8ed5-a74d7a1a1c47 --json
curl -s -o /dev/null -w '%{http_code}\n' 'https://digithings.ai/embed?host=occ.digithings.ai'
```

## Step 2 — reset the instance (preferred)

```bash
curl -s -X POST https://digithings.ai/_digichat-admin/container/reset \
  -H "x-digi-admin-key: $(security find-generic-password -s digithings-local/DIGICHAT_ADMIN_KEY -w)"
```

Expect `200 {"ok":true,"action":"container_destroyed","instance":"shared-<deploying sha12>"}`.
The `instance` is the id this deploy derived from `DIGICHAT_CONTAINER_REV` (see
`apps/digichat-cloudflare/src/paths.ts`), which is also what the Worker proxies
to and what `GET /_digichat/meta` reports.
The instance moves to `stopped` within about ten seconds and the next real
request cold-starts a fresh one (20–60 s). Verified 2026-10-19: destroyed a live
instance and the following OCC chat came back and executed a live ticket lookup.

Status codes are deliberate:

- `404` — the lever is unset, or the key is missing or wrong. All three are
  identical, so the response never says whether a key was valid.
- `405` with `Allow: POST` — wrong method.

The key is Worker-only (`DIGICHAT_ADMIN_KEY`); it is never forwarded into the
container. Rotation: [SECRETS_ROTATION.md](SECRETS_ROTATION.md) §15.

## Step 3 — retry the user path, expecting one possible 503

The first request after a restart can answer:

```json
{"error":"upstream_unavailable","message":"digikey did not answer the bff_session exchange — it is cold or unreachable (last answer: 503). This is not a DIGIKEY_BFF_TOKEN problem; retry in a few seconds."}
```

That is the cold-dependency case, and it is retryable: the response is `503`
with a `Retry-After: 5` header. digikey runs **inside the stack container**,
which sleeps, so a cold digikey fails the exchange until the container is
awake. Retry after the `Retry-After` window.

A **rejected token** answers differently — `502` with
`{"error":"upstream_auth","message":"digikey rejected the bff_session exchange (answered 401). Check DIGIKEY_BFF_TOKEN and digikey configuration."}`.
That one is a real credential problem and a retry does not clear it: compare
the digichat and stack copies per [SECRETS_ROTATION.md](SECRETS_ROTATION.md) §2.

A **digikey with no grant** answers `502 upstream_auth` as well, with
`"digikey has no DIGIKEY_BFF_TOKEN configured (the bff_session grant is not set on the digikey side). Check the digikey side, not only the digichat copy."`.
digikey answers this with `503 {"detail":"bff_session grant not configured (DIGIKEY_BFF_TOKEN)"}`
when it has no `DIGIKEY_BFF_TOKEN` in its own env; the copy on the digichat
side is then irrelevant. This one is permanent: a retry does not clear it.

The three are distinct on purpose (DIG-4424): before, a cold digikey, a
digikey with no grant and a refused token all answered `502 upstream_auth` and
all pointed at `DIGIKEY_BFF_TOKEN`, which sent the diagnosis at the wrong
subsystem.

## Step 4 — fallback: move the instance id by redeploying

If the lever is unavailable (key lost, route removed), deploy the digichat
Worker from a commit whose rev differs. The Container id is *derived* from the
deploying commit — `shared-<sha12>` via `DIGICHAT_CONTAINER_REV`, injected by
`apps/digichat-cloudflare/scripts/deploy.mjs` — so a new rev mints a **new**
instance and abandons the old one (it does not stop it). There is no literal to
bump and no test pin to update.

Beware the reverse: re-deploying the **identical** commit derives the same id and
reuses the warm instance, so a same-rev redeploy is not a recycle. If nothing has
changed to commit and the lever is gone, step 5 is the remaining option.

## Step 5 — last resort: delete and recreate

`npx wrangler containers delete <app-id>`, then redeploy the Worker. The
application id **changes**, so update the table above. This is the only step
that loses the instance outright, and the only one Cloudflare currently
supports from outside the Worker for a single instance — the CLI can list
instances but not stop one, and the REST API exposes only listing and SSH.

## Why it happens

`max_instances = 10` (`apps/digichat-cloudflare/wrangler.toml`, DIG-4487; was 2
until t1702u), so bad instances still leave slots for a cold start; only ten
bad instances exhaust the pool. The only reaper is
`sleepAfter = "5m"` via the base `onActivityExpired()`, which calls `stop()` —
and `stop()` is a no-op unless the container is `running`.

**Hypothesis, not yet proven:** `isActivityExpired()` returns false while
`inflightRequests > 0`, and that counter is incremented in `containerFetch` but
decremented only when the stream closes. A hung stream could therefore pin the
slot indefinitely. Until this is proven, no self-healing `destroy()` trigger is
wired — a wrong predicate would kill healthy requests, which is worse than a
wedge.
