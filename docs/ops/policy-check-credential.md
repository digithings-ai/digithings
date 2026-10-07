# `policy-check-reader` — the branch-protection read credential

> **Rule** (from [`credential-ownership.md`](credential-ownership.md)): *Any credential we hold by hand needs one owner, one refresh path, and a check that fails loudly when it is stale.*

This document registers the one credential that can read `develop`'s branch
protection. It exists for a single call: `scripts/check_required_policy_checks.py
--live`, which compares the committed inventory against the **real** required-set.
It is not a general CI token and must never become one.

---

## What it is

| Field | Value |
|---|---|
| **Owner** | **Security** (KeyMaster). One human backstop: Chris Stefan — creating the App is an owner action (see [Why I did not create it](#why-i-did-not-create-it)). |
| **Identity** | GitHub App **`policy-check-reader`**, repository-scoped, `public: false` |
| **Installation** | `digithings-ai/digithings` only |
| **Grants** | **`Administration: read`** — one permission, the minimum the branch-protection endpoint accepts |
| **Canonical store** | The App's **private key**, as GitHub Actions repo secret `POLICY_CHECK_APP_PRIVATE_KEY`, `cron` environment scope |
| **Identifiers** | `POLICY_CHECK_APP_ID` and `POLICY_CHECK_INSTALLATION_ID` as repo **variables** — identifiers, not secrets, so they travel in `vars.` and never touch `secrets.` |
| **Manifest** | [`.github/policy-check-reader-app.json`](../../.github/policy-check-reader-app.json) — the exact `default_permissions` to register |
| **Smoke call** | `python3 scripts/mint_policy_check_token.py --verify` — mints and performs the one read the guard needs ([`mint_policy_check_token.py`](../../scripts/mint_policy_check_token.py)) |
| **Staleness detector** | The drift guard's own `--live` run, which exits non-zero when the snapshot and the live set disagree; plus the daily `token-canary` dispatch — see [Staleness detector](#staleness-detector) |
| **Refresh path** | [Rotation](#rotation-90-days-and-immediately-after-a-suspected-leak) below |
| **Rotation owner** | Security (KeyMaster). Rotate without asking, per the standing mandate. |
| **Review horizon** | 90 days — re-verify the grant set and re-issue the key. **There is no automatic expiry; see the caveat.** |

**Manifest at a URL.** The repo is **public** (`repos/digithings-ai/digithings`
`.private == false`), so the manifest route works: raw URL is
`https://raw.githubusercontent.com/digithings-ai/digithings/develop/.github/policy-check-reader-app.json`.
`hook_attributes.url` and `redirect_url` are **required by GitHub's manifest
schema and are not used** by this credential — `default_events` is empty and no
OAuth flow exists. They point at the repo's issue URL rather than being invented
as live endpoints.

---

## Why a GitHub App, and not a fine-grained PAT

The house precedent is fine-grained PATs — `GH_DISPATCH_TOKEN` is
`digithings-cron-dispatch`, recorded in
[`SECRETS_INVENTORY.md`](SECRETS_INVENTORY.md) §(a). This credential is the one
place I would not follow it, and the reason is the org's shape:

> `GET /orgs/digithings-ai/members` returns **one** member: `chrizefan`, who is the
> org **owner** (`memberships/chrizefan` → `role: admin`). A fine-grained PAT is
> issued by and bound to a *user account*. Putting one in a scheduled job means
> every run authenticates **as the sole org owner**. Handing a person's account
> token to automation is exactly what my red lines put with Chris, so I am not
> doing it for a *read-only* convenience.

An App installation token is a separate, non-human identity, and it is short-lived:

| | Fine-grained PAT | App installation token |
|---|---|---|
| Identity | `chrizefan` — the org owner | `policy-check-reader` — an App |
| Lifetime | Until expiry or manual revoke (the house record shows 12-month PATs) | **≤ 1 hour**, minted per run |
| Leak from a runner | Live until someone notices and revokes it | Dead within the hour, on its own |
| Revocation | Revoke a token attached to a **person's** account | Uninstall the App — kills every token, touches no human account |
| Audit attribution | Reads as the owner | Reads as `policy-check-reader` |

The grant itself is **demonstrably available**: two installations on this org
already hold `administration: read` — `cursor` (id `108847534`) and
`graphite-app` (id `143386878`). Both are vendor apps whose private keys are
theirs, so neither is reusable; the point is that the permission is grantable to
an App at all, which no PAT claim can prove.

**Cost, stated honestly:** an App needs its private key as a second secret and a
minting step. That is ~150 lines of script that [`mint_policy_check_token.py`](../../scripts/mint_policy_check_token.py)
already covers and that `actions/create-github-app-token` covers in CI.

**The fallback, if the CTO prefers house precedent over a non-human identity:** a
fine-grained PAT named `digithings-policy-check-reader` with
`Administration: read` on `digithings-ai/digithings` satisfies the permission
identically and needs no minting — `gh` consumes it directly. Then the App
manifest is not used, the script is not used, and the manifest path in the table
above is struck. I recommend the App, but this is a defensible preference
difference, not a correctness one, and I would rather it be a decision than a
silent default.

---

## The three constraints, written into the design

### 1. It must never gate a merge

The guard's failure mode is *"the snapshot is stale"*, not *"someone broke
something"*. Wired as a required context, a credential outage becomes an outage
of **every merge in the repo** — an availability incident manufactured by a
safety check.

This is the same trade the repo already declined twice, and both precedents are
on the record:

- [`CODE_REVIEW_POLICY.md`](../agents/CODE_REVIEW_POLICY.md): *"Never let a
  metered third-party service hold a veto over deploys."*
- Cursor Bugbot was **not** made a required check on `main`, because it reports
  `neutral` on a usage-limit skip and a required check must report `success` —
  on 2026-08-05 that would have made all ten promotions unmergeable.

So: the job's name is not in
`GET /repos/digithings-ai/digithings/branches/develop/protection/required_status_checks`,
which today returns exactly three contexts — `Required checks passed`,
`doc-links + agents-init`, `mypy — digibase + digikey` — **and adding it there is
the specific change that would break this rule.** It reports by filing a tracker
issue on failure, the shape `token-canary.yml` already uses.

### 2. It must never sit on a deploy path

No deploy workflow reads this credential. The secret is `cron`-environment
scoped — DIG-248 (2026-10-04) put every job that reads a non-automatic
`secrets.*` behind an environment — and only the hygiene job declares
`environment: cron`. The `deploy-*-cloudflare.yml` pair is untouched: they are
`pull_request` build checks with `paths:` filters, not deploys on the PR path,
and they gain nothing here.

### 3. One repo, one permission

Installation on `digithings-ai/digithings` only. If the credential ever needs a
write, that is a new issue and a new decision — not a permission edit.

---

## Placement — and the correction to the premise

**The job block belongs inside
[`.github/workflows/ci-pr-hygiene.yml`](../../.github/workflows/ci-pr-hygiene.yml),
and the reason is stronger than the one given on the issue.**

The issue states that file "already has `schedule`". It does not. On `develop`
its only triggers are `pull_request` and `workflow_dispatch`, and the header says
so: *"Production clock: Cloudflare Worker digithings-cron. Schedule removed
#3579."* Re-adding one is not available:

- [`tests/scripts/test_no_gha_schedules.py`](../../tests/scripts/test_no_gha_schedules.py)
  asserts **no** workflow under `.github/workflows/` carries `on.schedule`, so a
  new `schedule:` fails CI outright.
- A schedule on `develop` would **double-fire** with the Worker, whose default
  branch is also `develop`.

**The clock already exists.** [`apps/digithings-cron/src/jobs.ts`](../../apps/digithings-cron/src/jobs.ts)
line 271 registers:

```
wd("ci-pr-hygiene", "21 6 * * *", DIGITHINGS, "ci-pr-hygiene.yml")
```

a daily 06:21 UTC `workflow_dispatch` against `develop`. So the new job block
**rides an existing dispatch: no new clock, no new `jobs.ts` row, no new
workflow file.** `workflow_dispatch`, `start_key` and `concurrency` are all
already in that file, which is what the issue noticed — it read the shape right
and the reason wrong.

Two wiring details that follow from the existing file, not from the issue:

- The new job must be **dispatch-only**. `path-filter` is guarded
  `if: github.event_name == 'pull_request'`, so it skips on a dispatch and the
  new job must not `needs: path-filter` or it will be skipped into a
  permanently-skipped state.
- It should dedupe on the existing `start_key` input, and the `concurrency` group
  already serialises the workflow.

---

## Rotation: 90 days, and immediately after a suspected leak

House cadence is 90 days ([`SECRETS_INVENTORY.md`](SECRETS_INVENTORY.md)), plus
immediately on a suspected leak.

**The caveat, because it is the whole point of choosing an App:** an App private
key has **no expiry**. A PAT's 90-day clock enforces itself; this one does not.
"Rotate every 90 days" therefore means *generate a new key on the App, publish it,
prove it, delete the old one* — a real rotation under a real discipline, but one
that depends on the owner doing it rather than on the credential expiring. What
compensates is that the credential is scoped to one repo with one read-only
permission and is revocable in one action (below).

### Routine rotation

1. Generate a new private key on the App (`POST /app/{slug}/keys`).
2. Publish it:
   `gh secret set POLICY_CHECK_APP_PRIVATE_KEY --env cron --repo digithings-ai/digithings --body-file <pem>`
3. **Smoke call** — prove the new key before the old one dies:
   `POLICY_CHECK_APP_ID=… POLICY_CHECK_INSTALLATION_ID=… POLICY_CHECK_APP_PRIVATE_KEY=… python3 scripts/mint_policy_check_token.py --verify`
   It prints the token's expiry and the required contexts it read. It never prints
   the token.
4. Delete the **old** key last (`DELETE /app/{slug}/keys/{key_id}`).

Old key last on purpose: if step 3 fails, the working credential is still in place
and nothing has stopped.

### Suspected leak — uninstall first

1. **Uninstall the App** (`DELETE /app/installations/{id}`). This revokes every
   installation token the App has minted.
2. Reinstall, mint a new key, publish, smoke-call per the routine above.

**Uninstall first, not a key delete.** A stolen PEM can mint a fresh token at any
time while the App is installed; deleting only the exposed key leaves the App able
to issue more. Uninstall is the action that actually stops the bleeding.

### If the App is ever deleted outright

Recreate from the manifest, reinstall on the one repo, re-grant
`Administration: read`, publish a fresh key, smoke-call. Nothing else in the repo
reads this credential (see [Blast radius](#blast-radius)).

---

## Staleness detector

`token-canary.yml` already probes the other scheduled credentials with
`scripts/check_workflow_tokens.py`, which validates a **static** secret — a PAT
via `GET /user` or an Actions-gated read. **This credential is not that shape, and
the canary must not be extended naively:**

- The liveness question is *"does the private key still mint, and does the minted
  token still carry `Administration: read`?"* — which is exactly
  `mint_policy_check_token.py --verify`.
- A canary that starts failing because **it** cannot read a secret is how #2541
  became a silent stop. If the canary job is given
  `secrets.POLICY_CHECK_APP_PRIVATE_KEY`, its absence must be reported as
  *unvalidated*, never as a credential failure — the shape
  `check_workflow_tokens.py` already uses for `CLAUDE_CODE_OAUTH_TOKEN` and
  `CURSOR_API_KEY`.
- Cheapest reliable signal is already free and separate: the drift guard's own
  `--live` run exits non-zero when the snapshot and the live set disagree, which
  is the condition this credential exists to detect.

**Recommended:** file a tracker issue on drift-guard failure only, reusing the
issue-filing step shape from [`token-canary.yml`](../../.github/workflows/token-canary.yml).
That keeps the canary out of the credential's blast radius entirely, which is
preferable to a second holder of a second secret.

---

## Storage

**One home: GitHub Actions.** Not Bitwarden (Secrets Manager is still empty under
DIG-95), not a Keychain copy, not a workflow `env:` literal, not the repo. The
GitHub Actions secret is **write-only**, which is a property here rather than a
limitation — it is not a backup path, and the inventory row must not imply one.

[`docs/adr/0029-secrets-management.md`](../adr/0029-secrets-management.md) proposes
one system of record synced outward; it is **Proposed**, not adopted, so it does
not bind this choice. Reading it does surface the Phase 0 item *"Add a
stale/unreferenced-secret check to CI"* — which is the same detector work as
[above](#staleness-detector), and the same answer.

---

## Blast radius

| Event | Effect | Not affected |
|---|---|---|
| App uninstalled, or key deleted | The drift guard stops running. | Every merge, every deploy, every other workflow. Nothing else reads this credential. |
| Key leaked | Attacker can mint tokens with `Administration: read` on one repo until the App is uninstalled. | Contents, secrets, other repos, and every human account. Read-only, one repo. |
| Secret missing from the environment | The guard's mint step fails; the job exits non-zero and files a tracker. | Merge — by design (constraint 1). |

The credential can **read** branch protection. It cannot write anything, cannot
read secrets, and cannot reach another repo.

---

## Why I did not create it

**Creating a GitHub App is an owner action and my red lines put it with Chris.**
`POST /orgs/digithings-ai/apps` needs `Administration: write` on the org, and on a
one-member org that is the owner account itself.

So this issue delivers the credential *defined* — type decided, manifest written,
scope fixed, rotation and detection specified, and the minting path implemented and
tested — and hands the one act of creation to Chris. Creating the App does **not**
raise any approval gate: it touches no auth or crypto code, no
`digikey/`, no broker path, and no deploy path. It is the 6th step of a
documented runbook.

**To provision, in order:**

1. Chris creates the App from the manifest URL (Install on `digithings-ai/digithings`
   only; permissions defaulted from the manifest).
2. Download the private key once. Never paste it into a comment, an issue, a chat,
   or a prompt — values never pass through a model.
3. Publish it and set the two identifiers:
   ```bash
   gh secret set POLICY_CHECK_APP_PRIVATE_KEY --env cron --repo digithings-ai/digithings --body-file <pem>
   gh variable set POLICY_CHECK_APP_ID           --repo digithings-ai/digithings --body <app id>
   gh variable set POLICY_CHECK_INSTALLATION_ID  --repo digithings-ai/digithings --body <installation id>
   ```
4. Smoke call, which proves the credential end to end:
   ```bash
   POLICY_CHECK_APP_ID=… POLICY_CHECK_INSTALLATION_ID=… \
     POLICY_CHECK_APP_PRIVATE_KEY="$(cat <pem>)" \
     python3 scripts/mint_policy_check_token.py --verify
   ```
   Expect the three contexts — `Required checks passed`, `doc-links + agents-init`,
   `mypy — digibase + digikey`. Anything else means the grant is wrong, and the
   failure is loud rather than a silent stale snapshot.
5. Add the inventory row in [`SECRETS_INVENTORY.md`](SECRETS_INVENTORY.md) §(a),
   and the rotation procedure in [`SECRETS_ROTATION.md`](SECRETS_ROTATION.md).

---

## Two things this issue is not

**Wiring the job is not in scope here.** The job block, the canary extension and
any `jobs.ts` change belong to **decision D of the DIG-2098 design note**, which
is not yet approved. This document fixes the credential those decisions consume.

**`security-scc.yml` does not exist.** The issue asks whether it and the two
`deploy-*-cloudflare.yml` workflows should be declared `advisory` or ignored.
`security-scc.yml` is **not in the tree** on `develop`, not in `git log --all`
for that path, and no workflow under `.github/workflows/` mentions it — so that
half of the question is moot. The two deploy workflows are
`pull_request`-triggered `paths:`-filtered **build checks**, not deploys, and
declaring them is a policy-surface decision inside DIG-2098 decision B, not a
credential question. Neither belongs here.

---

## Settled: the credential is necessary, and there is no anonymous way around it

The obvious objection to all of this is that `digithings-ai/digithings` is **public**,
so maybe the branch-protection gate is readable with no credential at all and the
whole App is unnecessary. That is worth settling rather than assuming, so it was
measured. First attempt failed to settle it: this machine's unauthenticated API quota
was exhausted (`GET /rate_limit` → `limit 60, remaining 0`) and the 403s came back
carrying `API rate limit exceeded` — a rate-limit answer, not a permission answer.
Reading those as a denial would have been the exact error this issue is about.

Re-measured on 2026-10-07 at 20:03 UTC with the quota freshly reset to 60/60, no
`Authorization` header at all:

| Request (anonymous) | Result |
|---|---|
| `GET /repos/digithings-ai/digithings/branches/develop/protection` | **401 Requires authentication** |
| `GET /repos/digithings-ai/digithings/branches/develop/protection/required_status_checks` | **401 Requires authentication** |
| `GET /repos/digithings-ai/digithings/rulesets` | 200 — one ruleset listed |
| `GET /repos/digithings-ai/digithings/rulesets/15270439` | 200 — but the wrong object, see below |

So the branch-protection read genuinely needs a credential. GitHub does publish
*some* protection state anonymously on a public repo, and that is the trap: the one
ruleset that is readable without authentication is `module-branch-protection`
(id 15270439), and it is **not develop's gate**. Its conditions are
`refs/heads/module/**` and its rules are `deletion`, `non_fast_forward` and
`pull_request` — there is no `required_status_checks` rule in it at all. develop's
three contexts live in classic branch protection, which is the 401.

So there is no anonymous substitute, and the guard would be reading a different
branch's ruleset if it settled for the one that is readable. **Provision the
credential.** If somebody later finds an unauthenticated route to develop's
protection state, the right follow-up is a note on DIG-2098, not an unwind of the App.