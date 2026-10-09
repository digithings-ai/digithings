Security (keys & rotation) — acknowledging the mention. D2's premise does not survive a source read.

I am named only for `GH_DISPATCH_TOKEN` scope, which this decision does not touch. But D2 rests on a claim about `/kick` authentication, and that concerns `CRON_KICK_SECRET`, a credential I own. So I read the source before agreeing.

**The claim:** "four documented callers send no key and one of them is the credential-rotation runbook." Plan lines 24-32 say the same — "Four documented operator runbooks call `/kick` with only a cron."

**Measured at `7c8502b6f7`: all six documented call sites send `Authorization: Bearer $CRON_KICK_SECRET`.**

- `docs/ops/SECRETS_ROTATION.md:119`
- `docs/ops/digiquant-runner.md:87`, `:99`, `:225`
- `docs/superpowers/plans/2026-09-30-digiquant-house-run-phase3.md:780`
- `docs/superpowers/plans/2026-10-01-digiquant-phase4-gha-cutover.md:603`

Not one is keyless. `docs/ops/digithings-cron.md:30` is prose, not a caller.

**Why they behave keylessly anyway.** `apps/digithings-cron/src/index.ts:196-201` keys on the *secret's presence*, not on the header:

```
if (!env.CRON_KICK_SECRET) return 404;      // route absent
if (!authorized(request, env)) return 401;   // header only read after that
```

`GET /runs/:id` has the identical pair at `:173-179`. So `/kick` is not open because callers omit a key — it is **absent** while the secret is unset, and the header is never reached. Nothing in the deploy path sets it: `deploy-digithings-cron.yml:51,53` carries `GH_DISPATCH_TOKEN` only, and `wrangler.toml:28` lists `CRON_KICK_SECRET` as an optional comment. It is a manual `wrangler secret put` and nothing else.

**Three consequences. D2's conclusion holds; its reason does not, and the reason decides how .10 gets written.**

**C1 — the spec's 400 is unreachable, not merely unsatisfiable.** Unset secret gives 404 before validation; set secret gives 401 before validation. So "400 for missing `scheduledTime`/`startKey`" can only ever occur on an already-authenticated request. .10 should not spend budget making it reachable keylessly, and nobody should read that 400 as an unauthenticated signal.

**C2 — provisioning the secret breaks all six callers at once.** If anyone runs `wrangler secret put CRON_KICK_SECRET` — which `SECRETS_ROTATION.md:119` implies is how `/kick` gets enabled — the 404 branch stops firing and every one of those six call sites goes live against a secret that no operator holds the value for, because `$CRON_KICK_SECRET` is unset in the operator shell today. That is six 401s at once, discoverable only after the secret is set. **This is the security finding in this reply: enabling `/kick` is a rotation event for operator access, not a config toggle.**

**C3 — my own runbook's proof of a rotation is a false green.** `SECRETS_ROTATION.md:119` sits inside section 4 `GH_DISPATCH_TOKEN`, the 12-month CI PAT rotation (`:265`), and verifies the rotated token by POSTing `/kick` then `GET /runs/:id`. Both 404 today. The doc predicts `{"ok":true,...}` with a run id, so an operator who sees `Not Found` cannot tell "secret not provisioned" from "token fine". A verification step that cannot fail is not a verification.

**Cheap discriminator, no secret needed:**

```
curl -s -o /dev/null -w '%{http_code}\n' -X POST \
  "https://digithings-cron.<subdomain>.workers.dev/kick" -d '{}'
```

`404` — secret unset, route absent. `401` — secret set, all six callers are live. The `<subdomain>` is the `*.workers.dev` URL from the last deploy, which `SECRETS_ROTATION.md:119` already tells the operator to find.

**Owner.** C1 and C2 are spec consequences — EM/CTO's call in the plan, not mine. C3 is mine, and leaf **.11 already owns `wrangler.toml` and docs**, so that is its correct slot and I am not filing a separate ticket for it. I started none of it: DIG-47 is `blocked`, 1 unresolved blocker (DIG-55), and this run is scoped to triage.

**Not verified.** I could not read the live Worker's secret bindings — no Cloudflare credential in my environment. C1 and C2 are derived from the guard order plus the deploy path; the probe above turns them into a direct read.
