# `POLICY_CHECK_READER_TOKEN` — the branch-protection read credential

> **Rule** (from [`credential-ownership.md`](credential-ownership.md)): *Any credential we hold by hand needs one owner, one refresh path, and a check that fails loudly when it is stale.*

This document registers the one credential that can read `develop`'s branch
protection. It exists for a single call: the planned drift guard
`scripts/check_required_policy_checks.py --live` (DIG-2098 decision D, not yet
written), which compares the committed inventory against the **real**
required-set. It is not a general CI token and must never become one.

The credential is a **fine-grained personal access token** with one repository
and one read-only permission. There is no App, no manifest and no minting
script: a PAT is already the thing it is, and the guard's whole need is one
`GET`. See [Decision record](#decision-record--a-github-app-was-recommended-and-was-not-chosen)
for why that is the choice rather than a fallback.

---

## What it is

| Field | Value |
|---|---|
| **Owner** | **Security** (KeyMaster). One human backstop: Chris Stefan — creating and revoking a token on his own account is his step, never an agent's (see [Why an agent does not create it](#why-an-agent-does-not-create-it)). |
| **Identity** | Fine-grained PAT named **`digithings-policy-check-reader`**, owned by the `chrizefan` account |
| **Repository** | `digithings-ai/digithings` only — selected one, not "all repositories" |
| **Permission** | **`Administration` → `Read-only`** — one permission, the minimum the branch-protection endpoint accepts |
| **Canonical store** | The token value, as GitHub Actions repo secret `POLICY_CHECK_READER_TOKEN`, `cron` environment scope |
| **Identifiers** | **None.** A PAT needs no app id and no installation id, so nothing travels in `vars.`. There is no separate identity to name. |
| **Lifetime** | **90 days, set on the token.** Fine-grained PATs expire on their own, so the house cadence is enforced by GitHub rather than by discipline |
| **Smoke call** | One authenticated `GET` on `branches/develop/protection/required_status_checks` — see [Provisioning](#provisioning-chris-five-steps) |
| **Staleness detector** | The drift guard's own `--live` run, which exits non-zero when the snapshot and the live set disagree; plus the daily `token-canary` dispatch — see [Staleness detector](#staleness-detector) |
| **Refresh path** | [Reissue](#reissue-every-90-days-and-immediately-after-a-suspected-leak) below |
| **Rotation owner** | Security (KeyMaster). Reissue without asking, per the standing mandate. |
| **Review horizon** | 90 days — the same date the token expires. There is no earlier expiry to miss, because expiry *is* the review. |

---

## Decision record: a GitHub App was recommended, and was not chosen

The original design for this credential was a **GitHub App** named
`policy-check-reader`, with a committed manifest and a minting script. I
recommended it and it was **rejected on 2026-10-07** on review: *"GitHub app is
to much, can we run the policy checks with GitHub Actions instead."* A PAT card
put the alternative in the same run and was **accepted**. The App manifest, the
minting script and its tests are deleted by the same change that rewrites this
document, so the repo carries exactly one design and this section is the record
of why.

**What the App would have bought, stated so the tradeoff is legible:**

| | Fine-grained PAT (**chosen**) | App installation token (**recommended, declined**) |
|---|---|---|
| Identity | `chrizefan` — a human account, and on this org the owner | `policy-check-reader` — an App |
| Lifetime | 90 days, **expires on its own** | ≤ 1 hour per run, but the **private key has no expiry at all** |
| Revocation | Revoke on a person's account — **a Chris-only step** | Uninstall the App — one call, touches no human account |
| Audit attribution | Reads as the org owner | Reads as `policy-check-reader` |
| Movable parts | **None.** One `GET` | Manifest, private key, two identifiers, a minting script, a verifier |
| Capability if leaked | `Administration: read` on one repo, until expiry (≤ 90 days) | Mint `Administration: read` tokens on one repo, **indefinitely**, until uninstall |

Neither row favours itself across the whole table. The App is better on
identity and on revocation. The PAT is better on the one axis that most often
gets skipped — **the expiry is real** — and it deletes three files instead of
maintaining them. Chris chose the PAT. That is a decision, it is recorded, and
this document describes the chosen design only.

**The overlap with R14, stated rather than hidden.**
[`SECRETS_INVENTORY.md`](SECRETS_INVENTORY.md) **R14** (DIG-363, accepted
2026-10-05) is the accepted risk that `digithings-cron`'s only GitHub credential
is a fine-grained PAT on a human account — and Chris declined a GitHub App there
too, precisely because it "would add a second long-lived secret with power to
mint dispatch and issue tokens." This credential is the **second** such PAT, so
the shape of the objection lands a second time. Two things are worth keeping
straight about that:

- The PAT has **strictly less power** than the App private key would have had:
  no minting, no events, no dispatch, no issue writes, one repository, one
  read-only permission, and a fixed expiry. R14's objection was to *power*, and
  this token has less of it than the alternative.
- **The boundary that holds the red line is the writer, not the reader.** An agent
  may publish a value Chris hands over and prove the grant with one `GET`. An
  agent may not create, mint, extend or revoke a credential on a personal
  account — that is Chris's step, every time, on a one-member org where the
  personal account *is* the org owner. Nothing below asks an agent to do it, and
  nothing below can be reordered to make it possible.

**A consequence to record with the choice:** revoking this token is a
personal-account action, so the leak response in
[Reissue](#reissue-every-90-days-and-immediately-after-a-suspected-leak) is
**not** self-service. Under the App design, uninstalling was one unauthenticated
-feeling `DELETE` against the org. Here it is Chris in his own settings. That is
a real reduction in response speed, and it is the price of the decision.

---

## The three constraints, written into the design

### 1. It must never gate a merge

The guard's failure mode is *"the snapshot is stale"*, not *"someone broke
something"*. Wired as a required context, a credential outage becomes an outage
of **every merge in the repo** — an availability incident manufactured by a
safety check. An **expired token** is the most likely way this happens: at day
91 the read returns 401 and the guard has nothing to say.

This is the same trade the repo already declined twice, and both precedents are
on the record:

- [`AGENTS.md`](../../AGENTS.md) (§ Review coverage): *"Never let a metered
  third-party service hold a veto over deploys."*
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

No deploy workflow reads this credential, and the secret is `cron`-environment
scoped. Two honest caveats about that scoping, because it is weaker than it looks:

- **`cron` is not a private environment.** `GET /repos/digithings-ai/digithings/environments/cron`
  returns `protection_rules: []`, and `grep -rln 'environment: cron'
  .github/workflows/` returns **19 files** — every cron pipeline, plus
  `agent-backlog-snapshot`, `agent-pr-finalizer`, `pipeline-*`,
  `secret-staleness-check`, `token-canary`, `sync-digiquant-runner-*`. A
  `cron`-scoped secret is therefore readable by all of them, not only by the
  guard job. That is acceptable here because the permission is
  `Administration: read` on one repo; it would not be for anything with write.
- **The gate is real but currently empty.** `SECRETS_INVENTORY.md` R13 §2 records
  that environment-scoped secrets stay invisible to jobs that do not declare that
  environment, and that the values are still at repo/org scope pending re-entry.
  `gh secret list --env cron` returns nothing today. So a `secrets.*` name added
  to a `cron` job resolves to empty exactly as it would with no environment at
  all. **Whoever wires the job must declare `environment: cron` on it**, or the
  read fails as "no key" and never as "permission denied" — and provisioning step
  3 below ends by proving the name actually landed at that scope.

The `deploy-*-cloudflare.yml` pair is untouched: they are `pull_request` build
checks with `paths:` filters, not deploys on the PR path, and they gain nothing
here.

### 3. One repo, one permission, one human account

`digithings-ai/digithings` only, `Administration: read` only, and the token is
pinned to a single named account rather than issued to whatever identity happens
to be configured. If the credential ever needs a write, that is a new issue and a
new decision — not a permission edit on the token.

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
wd("ci-pr-hygiene", "21 6 * * *", MONOREPO, "ci-pr-hygiene.yml")
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

## Provisioning (Chris, five steps)

**An agent does not create this token, and the reason is a red line rather than
a technical limit.** A fine-grained PAT is issued from a **personal account**,
and on this one-member org the personal account *is* the org owner
(`GET /orgs/digithings-ai/members` returns one member, `chrizefan`, `role:
admin`). Owner accounts and Chris's personal accounts are out of bounds for
agents, so creating, extending and revoking this token are all Chris's steps.
An agent's part is steps 3–5: publish a value Chris hands over, prove it, record
it. None of that needs the token to be created by anything but a browser.

**To provision, in order:**

1. **Create the token** at
   `https://github.com/settings/personal-access-tokens/new` —

   | Field | Value |
   |---|---|
   | Token name | `digithings-policy-check-reader` |
   | Expiration | **90 days** — the house cadence, and the reason the expiry is real |
   | Resource owner | `digithings-ai` (if the page offers only your own account, that is the same shape `GH_DISPATCH_TOKEN` has and is acceptable) |
   | Repository access | **Only select repositories** → `digithings` |
   | Repository permissions | `Administration` → **Read-only**. Nothing else. |

   **The value is shown exactly once.** Save it straight into the command in
   step 2. Never paste it into a comment, an issue, a chat, or a prompt — values
   never pass through a model.
2. Publish it as a secret. `gh secret set` reads the value from **stdin**; there
   is no `--body-file` flag (`gh` 2.102.0). Run it under `umask 077` so a staged
   copy lands `0600` rather than world-readable:
   ```bash
   umask 077
   gh secret set POLICY_CHECK_READER_TOKEN --env cron \
     --repo digithings-ai/digithings < <pat-file>
   ```
   If you would rather not stage it in a file at all, run the same command with
   no redirect and paste the value into it, then press Ctrl-D. Do **not** put the
   value in `GH_TOKEN` here — that variable is `gh`'s *own* login, and pointing
   it at the PAT would publish the secret while authenticating the write as the
   credential it is publishing.
3. **Prove the secret landed at the scope you think it did.** This is the step
   R13 §2 makes load-bearing, and `gh secret list --env cron` is empty today, so
   it proves nothing until you have set something:
   ```bash
   gh secret list --env cron --repo digithings-ai/digithings
   ```
   The name must appear. If it does not, the guard will read **empty** and fail
   as "no key" — not as "permission denied" — and that is indistinguishable
   from a mis-wired job.
4. **Smoke call**, which proves the grant and not just the plumbing. Setting
   `GH_TOKEN` makes `gh` authenticate **as the PAT**, so this call fails if the
   token does — which is the point. The value stays in the environment for the
   life of the command and is never an argv value:
   ```bash
   GH_TOKEN="$(cat <pat-file>)" gh api \
     repos/digithings-ai/digithings/branches/develop/protection/required_status_checks
   ```
   Expect a JSON body, and expect these three contexts in it — `Required checks
   passed`, `doc-links + agents-init`, `mypy — digibase + digikey`. **Then delete
   the staged file.**
5. **Only then** add the inventory row in
   [`SECRETS_INVENTORY.md`](SECRETS_INVENTORY.md) §(a), with the expiry date from
   step 1, and the reissue procedure in
   [`SECRETS_ROTATION.md`](SECRETS_ROTATION.md). This document deliberately
   carries **no** inventory row for a credential that does not exist yet: until
   step 3 prints the name, the row would be a claim rather than a record.

**Reading the smoke call's outcome.** `gh api` exits `0` on 200 and non-zero
otherwise, and the three failures mean different things:

| Outcome | Means | What it authorises |
|---|---|---|
| `200`, three contexts listed | **Proved.** The grant works. | Continue to step 5. |
| `401`, `403` or `404` on that path | **Proven wrong.** Token invalid or expired, or `Administration: read` was not actually granted. | Fix the token. Do **not** record it as live. |
| Transport error, DNS failure, `gh` could not reach the API | **Could not tell.** | Nothing. Re-run before changing anything. |

"Could not tell" is not a stale snapshot and must never be treated as one —
deleting a working credential on an unproven failure is how a good credential
gets destroyed.

---

## Reissue: every 90 days, and immediately after a suspected leak

Because the token carries its own expiry, the 90-day cadence is **not a
discipline, it is a date**. This is the one place the PAT is strictly better
than the App design it replaced: an App private key has no expiry at all, so its
90 days was a promise. Here GitHub enforces it, and the expiry **is** the
review date recorded in the inventory row.

### Routine reissue

1. Chris creates a new `digithings-policy-check-reader` token, 90-day expiry, the
   same single repository and the same single read-only permission.
2. Publish it — step 2 above, from **stdin**, then re-run step 3.
3. **Smoke call** — step 4 above. Prove the new token before the old one dies.
4. **Revoke the old token** — Settings → Developer settings → Fine-grained
   tokens → `digithings-policy-check-reader` → **Revoke**. Revoke is
   per-token, so `GH_DISPATCH_TOKEN` and this one are independent: revoking
   either does not touch the other.

Old token last on purpose: if step 3 fails, the working credential is still in
place and nothing has stopped.

### Suspected leak — revoke first, and it is not self-service

1. **Revoke the token** on the `chrizefan` account, in its settings page.
2. Create a new one, publish, prove, per the routine above.

**Revoke first, and expect to wait for Chris.** There is no "uninstall" one step
away here: the credential belongs to a human account, so an agent cannot revoke
it, and the *account* is the unit of risk. The compensating control is not
speed, it is the ceiling — a leaked token carries `Administration: read` on one
repository, expires on its own within 90 days, and is not the `GH_DISPATCH_TOKEN`
that can dispatch every cron run. So the honest statement is: **the blast radius
of a leak is small, but the time to stop it depends on a person.** That is the
residual this design accepts.

### If the token is deleted or expires outright

Create a new one with the same name, same repository and same single
read-only permission, publish, prove. Nothing else in the repo reads this
credential (see [Blast radius](#blast-radius)), so there is no second call site
to update.

---

## Staleness detector

`token-canary.yml` already probes the other scheduled credentials with
[`scripts/check_workflow_tokens.py`](../../scripts/check_workflow_tokens.py),
which validates a **static** secret — and a PAT is exactly that shape, which is
new for this credential and worth being careful with:

- A fine-grained PAT is probeable by an authenticated `GET /user`, and by the one
  endpoint this credential exists to read. The liveness question is *"does this
  token still carry `Administration: read` on `digithings-ai/digithings`?"* —
  which is the [smoke call](#provisioning-chris-five-steps) verbatim, not a
  generic probe.
- **A canary that starts failing because *it* cannot read a secret is how #2541
  became a silent stop.** If the canary job is given
  `secrets.POLICY_CHECK_READER_TOKEN`, its absence must be reported as
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
| Token revoked, deleted, or expired | The drift guard stops reading and fails loudly. Reissue to restore. | Every merge, every deploy, every other workflow. Nothing else reads this credential. |
| Token leaked | Attacker can read branch administration on **one** repo, with **no writes**, until the token expires (≤ 90 days) or is revoked. | Contents, secrets, other repos, the dispatch cron, and `GH_DISPATCH_TOKEN`. Stopping it needs Chris on his own account. |
| Secret missing from the environment | The guard's read fails; the job exits non-zero and files a tracker. | Merge — by design (constraint 1). |

The credential can **read** branch protection. It cannot write anything, cannot
read secrets, and cannot reach another repo. What it *is* — a token on the org
owner's personal account — is the real residual, and it is recorded rather than
argued away.

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
whole exercise is unnecessary. That is worth settling rather than assuming, so it
was measured. First attempt failed to settle it: this machine's unauthenticated API quota
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

So the branch-protection read genuinely needs a credential, and `GITHUB_TOKEN`
cannot be it: `administration` is **not** among the permission keys a workflow
token can be granted, so no amount of workflow permission configuration reaches
this endpoint. The check does already run in GitHub Actions
([`ci-pr-hygiene.yml`](../../.github/workflows/ci-pr-hygiene.yml)); it is the
*API read* inside it that needs a credential, and no anonymous substitute exists
for that.

GitHub does publish *some* protection state anonymously on a public repo, and
that is the trap: the one ruleset that is readable without authentication is
`module-branch-protection` (id 15270439), and it is **not develop's gate**. Its
conditions are `refs/heads/module/**` and its rules are `deletion`,
`non_fast_forward` and `pull_request` — there is no `required_status_checks`
rule in it at all. develop's three contexts live in classic branch protection,
which is the 401.

So **provision the credential.** If somebody later finds an unauthenticated
route to develop's protection state, the right follow-up is a note on DIG-2098,
not an unwind of this credential.