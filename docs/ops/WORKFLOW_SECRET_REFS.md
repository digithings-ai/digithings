# Workflow secret references

Every `secrets.NAME` read under `.github/workflows/` must name a secret that exists at
some level: a repo secret, a repo variable, an org secret, or an environment secret.
This is the runbook for the check that says so.

## The failure this exists to stop

Actions substitutes an **empty string** for a secret name it cannot resolve. A workflow
that reads `secrets.CLOUDFLARE_WORKERS_API_TOKEN` when no such secret exists does not
fail: it runs, with the variable empty, until the tool that consumes it refuses. The
deploy lane read `secrets.CLOUDFLARE_WORKERS_API_TOKEN` from #6013 (`9cb14c5313`) and
the secret was never created, so the lane exported an empty `CLOUDFLARE_API_TOKEN` and
wrangler refused at the end of the run. The deploy was never the thing that broke, and
nothing said which credential was missing.

That is the same defect class as DIG-4715: the producer and the validator disagree, and
only production finds out.

The gap is closed. The stack deploy lane now reads `secrets.CLOUDFLARE_API_TOKEN`, the
repo secret that exists and that wrangler deploys the stack with (run 39490394661
uploaded and deployed the Worker with it), and the manifest carries no accepted gaps.

## What runs

`scripts/secrets_audit.py` reads every `.github/workflows/**.{yml,yaml}`, collects the
`secrets.NAME` references that live inside a `${{ }}` expression (a commented-out read
is masked out first, so it does not count), and reports each name against the levels
that can define it:

| Finding | Meaning |
| --- | --- |
| `unresolved` | no level defines it — Actions substitutes an empty string |
| `not repo-level` | defined at another level (repo variable, org or environment secret) |
| `dead` | a repo secret that nothing reads |
| `repo-over-org` | defined at both repo and org level, where the repo copy silently wins |
| `env-over-repo` | defined as both a repo secret and an environment secret |

`GITHUB_TOKEN` is provided by Actions itself and is never reported.

The check runs in `.github/workflows/security-workflow-secret-refs.yml`, the **live
reporter**: it runs on any change to a workflow, to the manifest or to the script, and
reports on the PR. `ci.yml` used to carry a duplicate `workflow-secret-refs` lane folded
into `Required checks passed`; it was removed with the GHA exit ledger, since `ci.yml` is
**disabled on GitHub** (the cost lock of 2026-10-14, DIG-4364) and that lane reported
nothing.

The standalone workflow is deliberately **not** a required status-check context: it is
path-filtered, and a path-filtered check can never be required — GitHub blocks a merge
forever on a status that never arrives. Adding it to `.github/required-contexts.txt` is a
human-only repo-settings write (DIG-1952 child B). It is declared `advisory` in
`.github/policy-checks.yml`, with the reason written down.

## How it runs in CI, and why the manifest exists

The check runs in `security-workflow-secret-refs.yml` (see above).

It runs against **`.github/secret-names.json`**, a committed manifest of secret and
variable **names** per level (no values, ever). The manifest exists because CI cannot do
the live read:

- The Actions secret-listing endpoints (`repos/{owner}/{repo}/actions/secrets`,
  `orgs/{org}/actions/secrets`, `repos/{repo}/environments/{env}/secrets`) require the
  `repo` scope.
- A workflow's `GITHUB_TOKEN` is a GitHub App installation token. Its `permissions:`
  vocabulary has no key for secrets, so **no workflow grant can supply that scope**.
- Run 37235973852 (#5063, 2026-10-04) granted `actions: read` and all three listings
  still answered `403 Resource not accessible by integration`.
- Giving CI a PAT that could read them was rejected on purpose: it would stand up the
  exact category of repo-scoped credential that DIG-477 option D exists to shrink.

So the manifest is the same pattern the repo already uses for `.github/environments.json`
— a committed manifest, reconciled against the live API by an operator.

**The manifest is names only.** It holds no value, and a name is not a secret.
`docs/ops/SECRETS_INVENTORY.md` already publishes most of those names, so committing the
manifest exposes little that is not public already — but it is **not** a subset of the
inventory: a name can be new, and the inventory publishes the `DIGI_*_PROJECT_NUMBER`
variables only in glob form. `tests/scripts/test_secrets_audit.py` therefore checks every
name in the manifest against the inventory, so a hand-edit to the manifest has to show up
in a second file.

The check refuses to run when a level in the manifest could not be listed: a level the
writer could not read is recorded as `"read": false`, and the audit then reports
"levels: not checked" instead of pretending it looked at everything.

## Commands

```bash
# The CI gate, from any checkout. No token, no network.
make secrets-audit-manifest

# The live read, from a shell whose `gh auth` token carries `repo` and `admin:org`.
make secrets-audit

# Refresh the committed manifest from the live API. Run this after a secret is created,
# renamed or removed.
make secrets-audit-refresh
```

`make secrets-audit-refresh` replaces the facts, not the decisions: the `accepted_missing`
entries in the file it overwrites are carried over. A name that has become real stops
being unresolved, and `tests/scripts/test_secrets_audit.py` then fails until the matching
acceptance is deleted.

All three commands need **PyYAML** (`python3 -m pip install pyyaml`). The audit parses
the workflow YAML instead of scanning it as text, because a text scan cannot tell a
comment from a `#` inside a string — and a `#` inside a string is how a secret read
hides. Twelve house scripts already import yaml, and CI installs it the same way in
three other jobs.

## The manifest goes stale, and what that means

A manifest older than 90 days is reported as stale in the CI log. It is **not** a failure:
a stale manifest blocks unrelated merges, and the honest cost of that is higher than the
cost of a warning. The refresh is a manual, privileged action — it needs a token with the
`repo` scope — so the ageing is a standing item for the weekly security report, not a
gate.

The staleness warning is not the only limit. The manifest is a snapshot: a secret
deleted after the last refresh still reads as existing, and a secret created after it
still reads as missing. The manifest catches the class of mistake that happens when a
workflow is written — a typo, a rename, a copy-paste from another repo — which is the
class that broke the deploy lane. It does not catch a secret deleted in the GitHub UI
without the manifest being refreshed. That is what the manual refresh is for.

## Accepted gaps

A name can be known to be missing and still be tolerated, if the gap is recorded with an
owner and a review date. The entries live in `accepted_missing` in the manifest:

```json
"ACCEPTED_SECRET_NAME": {
  "workflows": [".github/workflows/the-workflow-that-reads-it.yml"],
  "reason": "...",
  "owner": "chris",
  "since": "2026-10-20",
  "review_by": "2026-11-03"
}
```

The acceptance is scoped to the workflows it names. The same name read by a different
workflow is **not** covered and fails the gate again, so an acceptance can never grow
into a general amnesty for a name. Accepted names are printed on every run, with their
owner and review date, so they stay visible.

An acceptance is a promise that a gap is still open, and
`tests/scripts/test_secrets_audit.py` checks that promise in both directions: the name
must still be undefined at every level, and at least one of the workflows it names must
still read it. When the secret is minted and the manifest refreshed, the acceptance stops
being true and the test fails until it is deleted.

An acceptance also expires. Past its `review_by` date it covers nothing: the read
becomes unresolved again and the gate fails on it, and the run prints the entry as
`accepted-missing EXPIRED` with its owner. A promise with a review date is only a promise
while the date holds, and an entry whose date has passed is not allowed to sit there
quietly.

An acceptance must also name at least one workflow. An entry that covers every workflow
is a blank cheque, not a decision, so the parser refuses it.

### The open entries

There are none today. The one entry this section was written for,
`CLOUDFLARE_WORKERS_API_TOKEN`, is gone: the stack deploy lane reads
`secrets.CLOUDFLARE_API_TOKEN` again, a name that exists at the repo level and that
wrangler deploys the stack with. The premise the entry rested on — that the repo's
`CLOUDFLARE_API_TOKEN` is the Vectorize/D1 token and makes wrangler fail with error
10000 — is a trap in `apps/digithings-stack-cloudflare/wrangler.toml` about the LOCAL
developer's `.env` token, not about the repo secret. The two are different credentials,
and the repo one carries Workers Scripts:Edit.

The entry had to go rather than be left to expire: an acceptance is only true while a
workflow still reads the name, and
`tests/scripts/test_secrets_audit.py::test_every_acceptance_still_describes_a_real_gap`
fails the moment it stops being true. A stale entry would also have tolerated a
future read of a name that exists nowhere — the exact failure this check exists to
stop.

## What this check does not do

- It does not check that a credential is **valid**, only that a name is **defined**.
  `scripts/check_workflow_tokens.py` is the separate liveness probe.
- It does not check secret **age**. That is `scripts/secret_staleness_check.py`, which is
  deliberately not automated (DIG-477 option D); rotation is recorded by hand in
  `docs/ops/SECRETS_INVENTORY.md`.
- It does not read values. Nothing in this path reads a secret value, and the manifest
  holds names only.
- It does not check **variables** (`vars.*`). A variable may legitimately be absent
  because the expression falls back to a literal, so "no level defines it" is not a defect
  for a variable the way it is for a secret. Three variable reads resolve to nothing
  today, and they are recorded here rather than in the gate:
  `vars.DIGISEARCH_URL` (`pipeline-digiquant.yml:155`),
  `vars.GATE_ALERT_EMAIL` (`production-deploy-gate-watchdog.yml:58`) and
  `vars.TOKEN_CANARY_PROBE_WEEKDAY` (`token-canary.yml:85`). They are worth a look on
  their own account; they are not part of DIG-4717.
- It does not see a **whole-context dump**. `${{ toJSON(secrets) }}` hands every secret
  to a step in one string, and the read has no name in it, so a name-based check cannot
  see it. That is a different question — who can read everything — and not this one.
