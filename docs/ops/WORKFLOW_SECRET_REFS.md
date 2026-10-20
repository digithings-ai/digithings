# Workflow secret references

Every `secrets.NAME` read under `.github/workflows/` must name a secret that exists at
some level: a repo secret, a repo variable, an org secret, or an environment secret.
This is the runbook for the check that says so, and for the one gap it currently knows
about.

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

The check runs in two places, on the same one-line command against the same manifest:

| Where | What it is |
| --- | --- |
| `ci.yml`, job `workflow-secret-refs` | folded into the `Required checks passed` aggregator, so a failure **blocks a merge to `develop`** |
| `.github/workflows/security-workflow-secret-refs.yml` | the **live reporter**: it runs on any change to a workflow, to the manifest or to the script, and reports on the PR |

Both exist because `ci.yml` is **disabled on GitHub** — the cost lock of 2026-10-14
(DIG-4364) turned the whole CI suite off, and it has not been turned back on. A lane
inside a disabled workflow reports nothing at all, so the standalone workflow is what
makes the check run today. When CI comes back, the ci.yml copy is the one that gates,
and the standalone copy is the reporter.

The standalone workflow is deliberately **not** a required status-check context: it is
path-filtered, and a path-filtered check can never be required — GitHub blocks a merge
forever on a status that never arrives. Adding it to `.github/required-contexts.txt` is a
human-only repo-settings write (DIG-1952 child B). It is declared `advisory` in
`.github/policy-checks.yml`, with the reason written down.

## How it runs in CI, and why the manifest exists

The check runs in `ci.yml` as the `workflow-secret-refs` lane, folded into the
`Required checks passed` aggregator, so a failure blocks a merge to `develop`.

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

**The manifest is names only.** `docs/ops/SECRETS_INVENTORY.md` already publishes every
name in it, so committing it adds no new exposure. The check refuses to run when a level
in the manifest could not be listed: a level the writer could not read is recorded as
`"read": false`, and the audit then reports "levels: not checked" instead of pretending
it looked at everything.

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
"CLOUDFLARE_WORKERS_API_TOKEN": {
  "workflows": [".github/workflows/deploy-digithings-stack-cloudflare.yml"],
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

### The one open entry

`CLOUDFLARE_WORKERS_API_TOKEN` exists at no level. The lane needs a Cloudflare API token
with the **Workers Scripts:Edit** permission, under that name and not another: the repo's
`CLOUDFLARE_API_TOKEN` is the Vectorize/D1 token, and exporting it makes wrangler fail
with error 10000. The lane's own preflight refuses to deploy without it and says which
credential is missing, so the gap is loud where it is used.

Minting the token is a human action. Until it exists, this entry is the record.

## What this check does not do

- It does not check that a credential is **valid**, only that a name is **defined**.
  `scripts/check_workflow_tokens.py` is the separate liveness probe.
- It does not check secret **age**. That is `scripts/secret_staleness_check.py`, which is
  deliberately not automated (DIG-477 option D); rotation is recorded by hand in
  `docs/ops/SECRETS_INVENTORY.md`.
- It does not read values. Nothing in this path reads a secret value, and the manifest
  holds names only.
