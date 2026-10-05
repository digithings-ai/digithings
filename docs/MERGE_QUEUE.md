# The develop merge queue

This document is the merge path for `develop`. It answers three questions:

1. **Who merges.** The CTO and the Engineering Manager. Nobody else.
2. **What may be merged.** A PR that has passed the required checks and carries a
   review from the review path.
3. **Where the queue lives.** In `scripts/merge_queue.py`, in this order, oldest
   first.

If you are here because you need a merge and you do not want to open a card asking for
permission: you do not need one. Run the queue.

---

## The problem this solves

Every merge into a protected branch was becoming a decision. Someone opened a card, a
human decided, the decision got written down, and the branch sat still until then. That
put a person in the path of routine work for no reason other than the absence of a
defined path.

A merge queue turns "should this land?" into "is this landable?". The second question has
an answer that can be computed, so it does not need a human.

---

## Who merges

| Role | Key | In `digithings-ai` |
|---|---|---|
| CTO | `cto` | `chrizefan` |
| Engineering Manager | `em` | `chrizefan` |
| QA | — | **reviews, does not merge** |

`scripts/merge_queue_policy.json` is the machine-readable roster. QA reviews. QA does not
merge — a reviewer cannot be the one who signs off on their own pass, and the CEO's
instruction was that the EM and the CTO are the merge path.

**One GitHub login, two roles.** Both authorities merge with the same org credential, so
GitHub records the same committer for either. The role is an *assertion*, not something
GitHub can verify: pass it with `--acting-role`, and the queue writes it into the audit
comment on the PR so the record names who acted. Adding a role to the roster is a policy
change and needs the CEO — it is not something an agent does on its own initiative.

An approval is likewise asserted when the reviewer is not a distinct GitHub account:
`--attest-review <role>` records which role reviewed. The merging role may **not** attest
its own review, which is what stops a single-credential setup from silently collapsing
into "I reviewed it and merged it".

## What may be merged

`scripts/merge_queue.py` refuses a PR unless all of the following hold.

| Gate | Rule |
|---|---|
| Base branch | `develop` only. `main`, `master` and `release/*` are refused (exit 3). |
| Required check | `test` must have **reported** and concluded `SUCCESS`. |
| Other checks | Any other check in a failing conclusion blocks the merge. |
| Mergeable | `mergeable == CLEAN`. Drafts and `CONFLICTING` do not queue. |
| Review | An `APPROVED` review from someone other than the author, or `--attest-review` from a role on the review path that is not the merging role. |
| Change requests | Any `CHANGES_REQUESTED` review blocks. |

Two of these are deliberate choices worth stating plainly.

**`NEUTRAL` and `SKIPPED` fail a required check.** A required check that reports nothing
is indistinguishable from a check that was never asked to run — which is exactly the hole
being closed. This has a real cost: Bugbot reports `neutral` when it is out of quota, so a
required Bugbot check would block merges indefinitely. Do not put a metered third-party
service on the required list. See `CODE_REVIEW_BASELINE.md`.

**Order is FIFO, not greenest-first.** Sorting by check status turns a queue into a race
that the loudest PR wins. Oldest-eligible-first is the only ordering that is fair and only
one that is easy to explain to whoever has been waiting.

## Running it

```bash
# What is waiting, and why anything is not.
python3 scripts/merge_queue.py list --repo digithings-ai/twelve-x --acting-role cto

# Merging a review that happened in-session rather than on GitHub.
python3 scripts/merge_queue.py list --repo digithings-ai/twelve-x \
  --acting-role cto --attest-review qa

# Merge the oldest eligible PR. Default is one merge per run.
python3 scripts/merge_queue.py run --repo digithings-ai/twelve-x --acting-role em

# See the plan without touching anything.
python3 scripts/merge_queue.py run --repo digithings-ai/twelve-x --acting-role cto --dry-run
```

`run` re-reads the queue **after every merge**. Merging a PR moves the base, which can
turn the next PR into `CONFLICTING`; re-reading is what makes that visible instead of
sending a stale-base merge. The queue stops and reports when it happens.

Each merge passes `--match-head-commit`, so a push landing between evaluation and merge
aborts the merge rather than landing a commit that was never gated. The queue never passes
`--admin`.

Every merge leaves an audit comment on the PR naming the role, the head SHA, the merge
method, the review basis and the checks that were green. That comment is the answer to
"who merged this and on what authority".

### Exit codes

| Code | Meaning |
|---|---|
| 0 | Merged, or nothing was eligible. |
| 1 | Operational failure — `gh` could not read the queue. |
| 2 | The role you claimed is not on the merge-authority roster. |
| 3 | The base branch is one that needs a human. |

Exit 2 and 3 are refusals with a reason. They are not failures to retry.

## What this does not do

**It cannot stop a direct push to `develop`.** The queue governs the merge path; it does
not gate the branch. Only [branch protection](BRANCH_PROTECTION.md) does that, and see the
next section for why that is currently not available on `twelve-x`.

That is the real limitation, and it is worth being blunt about it: an agent with push
access can still push to `develop` directly, and this queue will not notice.

## Branch protection and the native merge queue: blocked by plan

DIG-506 asked for two things: native branch protection on `develop` with a required `test`
check, and GitHub's own merge queue. Neither is available on `digithings-ai` today.

`digithings-ai` is on the GitHub Free plan with one seat. GitHub's own documentation:

> Protected branches are available in public repositories with GitHub Free and GitHub Free
> for organizations, and in public and private repositories with GitHub Pro, GitHub Team,
> GitHub Enterprise Cloud, and GitHub Enterprise Server.

`twelve-x` is private, so both are Pro-only. The merge queue is configured *through*
branch protection, so it is gated the same way.

The refusal is reproduced by the tooling, not asserted:

```console
$ python3 scripts/enable_branch_protection.py status --repo digithings-ai/twelve-x --branch develop
visibility: private
org plan: free
admin: yes
BLOCKED: digithings-ai/twelve-x is private and the digithings-ai plan is 'free'.
        Protected branches require GitHub Pro for private repositories.
...
Upgrade to GitHub Pro or make this repository public to enable this feature.
```

This is a plan limit, not a misconfiguration. The decisive test: the identical API call
succeeds on the **public** `digithings-ai/digithings` and is refused on the private
`digithings-ai/twelve-x`, same org, same token, same admin permission. Visibility and plan
are the only variables. There is no permission, token, or org-setting fix.

### The two real options

1. **Upgrade `digithings-ai` to Pro.** About $4/month for one seat. This unblocks branch
   protection, the native merge queue, and rulesets across all three org repos at once.
   This is a billing decision.
2. **Make the repo public.** Not an agent's call, and never a client repo's call. The
   CEO's own boundary for DIG-506 was to come back rather than touch client repo settings.

Until one of those happens, `scripts/merge_queue.py` is the merge path and
`scripts/enable_branch_protection.py` is the unblock script, ready to apply the moment the
plan allows it.

## Apply protection when the plan allows it

```bash
# What is there now, and whether it can be changed.
python3 scripts/enable_branch_protection.py status \
  --repo digithings-ai/twelve-x --branch develop

# Rehearse the exact payloads. Writes nothing.
python3 scripts/enable_branch_protection.py apply \
  --repo digithings-ai/twelve-x --branch develop \
  --check test --mode ruleset --merge-queue --dry-run

# Apply.
python3 scripts/enable_branch_protection.py apply \
  --repo digithings-ai/twelve-x --branch develop \
  --check test --require-approvals 1 --mode ruleset --merge-queue
```

`--mode ruleset` is required for `--merge-queue`: classic branch protection has no
merge-queue field, so the ask would be silently dropped rather than refused. The script
refuses that combination instead.

`--check` is mandatory. A branch with no required check looks protected and enforces
nothing, which is worse than an unprotected branch because it is believed.

## Repo survey

The CEO asked whether the same gap exists elsewhere. It does — on every private repo in
both orgs. Only the public `digithings-ai/digithings` has protection, and it has it
precisely because public repos are not Pro-gated.

| Repo | Visibility | Default branch | Protection | Rulesets |
|---|---|---|---|---|
| `digithings-ai/digithings` | public | `develop` | **yes** — 3 required checks, `strict` | 1 |
| `digithings-ai/twelve-x` | private | `develop` | Pro-gated (403) | Pro-gated (403) |
| `digithings-ai/digithings-ops` | private | `main` | Pro-gated (403) | Pro-gated (403) |
| `DataTapStream/datatap-web` | private | `main` | Pro-gated | Pro-gated (403) |
| `DataTapStream/datatap-mcp` | private | `master` | Pro-gated | Pro-gated (403) |
| `DataTapStream/apollo` | private | `master` | Pro-gated | Pro-gated (403) |
| `DataTapStream/gaia` | private | `master` | Pro-gated | Pro-gated (403) |
| `DataTapStream/zeus` | private | `master` | Pro-gated | Pro-gated (403) |

Both orgs are on the Free plan, so a Pro upgrade in one does not cover the other. The
`DataTapStream` repos are client repos: changing their visibility or their billing is a
client conversation, routed through the CSM.

`digithings-ai/digithings` currently has `required_pull_request_reviews: null` — no review
is required on `develop`, only checks. That is a separate gap from the plan limit and can
be closed with `--require-approvals 1` today, since the repo is public.

Regenerate this table with one command per repo:

```bash
python3 scripts/enable_branch_protection.py status --repo OWNER/NAME --branch BRANCH
```

## See also

- [BRANCH_PROTECTION.md](BRANCH_PROTECTION.md) — required checks per branch, why a
  path-filtered required check is a trap, the emergency bypass.
- `scripts/merge_queue_policy.json` — the roster.
- `scripts/merge_queue.py` — the queue.
- `scripts/enable_branch_protection.py` — status and apply.
- `BRANCHING.md` — the branch taxonomy this queue sits on top of.