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
| Base branch | `develop` only. `main`, `master` and `release/*` are refused (exit 3), and a PR whose `baseRefName` is anything else is refused too. |
| Required check | The names in `required_checks_by_repo` for this repo must each have **reported** from a workflow run, and concluded `SUCCESS`. For `twelve-x` that is `test`. For `digithings` it is `Required checks passed`, `doc-links + agents-init` and `mypy — digibase + digikey`. |
| Other checks | Any other check in a failing conclusion blocks the merge. |
| Mergeable | `mergeable == MERGEABLE`. Drafts and `CONFLICTING` do not queue. |
| Up to date | `mergeStateStatus` must be `CLEAN`. `BEHIND`, `DIRTY`, `UNKNOWN` and `BLOCKED` do not queue. |
| Review | An `APPROVED` review from a person who is neither the author nor a bot, or `--attest-review` from a role on the review path that is not the merging role. |
| Change requests | Any `CHANGES_REQUESTED` review blocks. |

Two of these are deliberate choices worth stating plainly.

**`NEUTRAL` and `SKIPPED` fail a required check.** A required check that reports nothing
is indistinguishable from a check that was never asked to run — which is exactly the hole
being closed. This has a real cost: Bugbot reports `neutral` when it is out of quota, so a
required Bugbot check would block merges indefinitely. Do not put a metered third-party
service on the required list. See `CODE_REVIEW_BASELINE.md`.

**A green commit status is not a passing build.** GitHub's commit status docs are explicit
that "any person or integration with write permissions can set the state of any status
check". So a required check only satisfies the gate if it arrived as a *check run* — one
bound to an Actions workflow — not as a bare status anyone with write access can type. Every
required check on both repos is a check run, so this costs nothing; it is here because the
alternative is a queue that any agent holding a token could green-light its own PR.

**Required check names are per repo, and a name that matches nothing is called out
separately.** The two repos in this org report different names for the same idea:
`twelve-x` runs one job called `test`, while `digithings` drives every suite through
reusable workflows, so GitHub reports `digibase / test`, `digiclaw / test` and ten
more, and names nothing `test` at all. A single global list can therefore only be
right for one of them — and when it is wrong it is *silently* wrong, because an
unmatched required name produces `required check 'test' has not reported`, which is
byte-identical to the message for an untested PR. That is exactly how DIG-690 blocked
all 28 open `digithings` PRs with a gate that could never pass and no way to tell it
apart from CI being broken.

So `required_checks_by_repo` carries the real names, an unlisted repo falls back to
`defaults.required_checks` (never to nothing — a queue that stops checking is worse
than one that refuses), and `list`/`run` additionally compare the required names
against everything the queue *did* report. A name absent from **every** open PR while
other checks did report is announced on stderr as a misconfiguration, naming the gate
that cannot match, what CI is really reporting, and the file to edit. It is compared
against the union rather than per PR, so the legitimate path-filtered case — one
Python-only PR with no `digichat / test` — stays quiet. **It only ever warns; it never
unblocks.** A gate that cannot match must still block.

**A bot's approval is not a review.** `coderabbitai[bot]` approving a PR means a linter
found nothing to complain about, not that a person owns the change. GitHub's own review
summary ignores bot reviews for the same reason, so the queue does too.

**A PR behind its base does not queue.** After PR #1 lands, PR #2's checks have not
re-run — its green `test` is from the run against the *previous* base, and GitHub reports
it `MERGEABLE + BEHIND`. Merging on that evidence is precisely what a merge queue exists to
prevent, and nothing in the check rollup reveals it. This is what the ruleset path calls
`strict_required_status_checks_policy`; a local queue has to enforce it itself. It also
means each merge in a batch has to wait for the next PR's CI, which is the cost of doing
it correctly. `run` re-reads the queue after every merge for the same reason: a verdict
computed before a merge is stale the moment that merge lands.

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

`digithings-ai` is on the GitHub Free plan with one seat. GitHub's plans page lists
**Protected branches** under the paid org plan's "Advanced tools and insights in private
repositories", not under Free, and the pricing comparison marks *Repository rules*
"Public repositories" on Free and "Public repositories / Private repositories" on Team.

`twelve-x` is private, so both are paid-plan features. The merge queue is a branch
protection setting ("Require merge queue" on the About-protected-branches page), so it is
gated the same way.

Note the naming: GitHub's per-seat paid plan is **GitHub Team**, at **$4/user/month for the
first 12 months**. Older docs and blog posts call it "GitHub Pro" for organizations. The
API's error message says "Upgrade to GitHub Pro", and this doc uses "Pro" when quoting that
message; the plan to actually buy is Team.

The refusal is reproduced by the tooling, not asserted:

Verbatim output, trimmed only where marked:

```console
$ python3 scripts/enable_branch_protection.py status --repo digithings-ai/twelve-x --branch develop
repo:        digithings-ai/twelve-x
visibility:  private
org plan:    free
admin:       yes

BLOCKED: digithings-ai/twelve-x is private and org 'digithings-ai' is on the 'free' plan; branch protection, rulesets and the server-side merge queue all require GitHub Pro for private repositories

Unblocking this is a billing decision, not a config change:
  1. Upgrade the owning org to GitHub Pro. This is the supported route and it
     also unblocks the server-side merge queue for every private repo in the org.
     (The plan GitHub actually sells per seat is 'Team', $4/user/month for the
     first 12 months; 'Pro' is the name in the API's own error message.)
  2. Making the repository public unblocks protection on the Free plan, but it
     publishes the code and the history — never a client repo's decision to take
     here, and never an agent's.
Until one of those happens, use scripts/merge_queue.py: it applies the same gates
on the merge path, under a named merge-authority role, but it cannot stop a
direct push to the branch.

protection on develop: NOT READABLE — gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)
rulesets: NOT READABLE — gh: Upgrade to GitHub Pro or make this repository public to enable this feature. (HTTP 403)
```

`status` exits 0 here: it succeeded in reporting the gate. Callers that branch on the
exit code must read the `BLOCKED:` line, or use `apply`, which exits 3.

This is a plan limit, not a misconfiguration. The decisive test: the identical API call
succeeds on the **public** `digithings-ai/digithings` and is refused on the private
`digithings-ai/twelve-x`, same org, same token, same admin permission. Visibility and plan
are the only variables. There is no permission, token, or org-setting fix.

### The two real options

1. **Upgrade `digithings-ai` to the paid org plan.** GitHub's per-seat plan is **Team**,
   $4/user/month for the first 12 months — about $4/month at one seat. (The API's 403
   names it "Pro", which is the wording it has always used; `github.com/pricing` no longer
   lists a per-seat Pro tier. Either way the gate is the same: Free orgs get repository
   rules and protected branches on **public repositories only**.) This unblocks branch
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
# This is also what it does today: on a plan-blocked repo it refuses with exit 3
# before printing anything, because there is no payload that would be accepted.
# Run it once the plan allows it to see the payload.
python3 scripts/enable_branch_protection.py apply \
  --repo digithings-ai/twelve-x --branch develop \
  --check test --mode ruleset --merge-queue --dry-run

# Apply.
python3 scripts/enable_branch_protection.py apply \
  --repo digithings-ai/twelve-x --branch develop \
  --check test --require-approvals 1 --mode ruleset --merge-queue
```

Rulesets are created with `POST` and updated with `PUT` to the ruleset's own id, looked up
by name — GitHub has no upsert, and a `POST` per run would stack up same-named rulesets
whose combined effect nobody could reason about.

Applying never *reduces* protection. The check list is a union of `--check` and whatever
the branch already requires, so naming one check on a branch that requires three keeps all
three. `--replace-checks` opts out and is the only way to drop one.

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
- [`BRANCHING.md`](../BRANCHING.md) — the branch taxonomy this queue sits on top of.