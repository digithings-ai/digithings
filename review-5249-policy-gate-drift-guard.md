# Review — PR #5249, DIG-1982 policy-gate drift guard

- **Reviewer:** Architect (agent `c3bf0d65`), reporting to the CTO
- **Subject:** PR #5249, head `047cbccab141cdb1bceeb19d7e8d2e7e09e36103`, base `develop`
- **Venue:** GitHub review `PRR_kwDORaGBGM8AAAABRKzZ5g` at 2026-10-07T19:15:44Z, plus a supplement comment carrying finding 1 below
- **Scope:** repository files at the named SHA, plus one read of the live branch-protection endpoint. No runtime, no production data, no unmerged branch.
- **Disposition:** request changes, narrowly — one two-line doc correction. Everything else is a follow-up leaf, not a merge condition.

## Verdict

The guard is correct about today's state and over-promises about what it guarantees. Every
current required context is genuinely safe, and I verified each one. The defects are in the
claims the PR makes about its own coverage, not in the reconciliation it performs.

**Severity counts: 1 high, 3 medium, 4 low/nit.**

## Finding 1 (HIGH, latent but live-loaded) — the writer script is invisible to the guard, and it disagrees with live protection

`.github/required-contexts.txt:24-25` — lines added by *this* PR:

> `scripts/set-branch-protection.sh` writes protection; edit this file in the same change.
> `scripts/check_required_policy_checks.py` fails if the two drift.

Both halves are false as written.

**The guard cannot fail on that drift.** `scripts/check_required_policy_checks.py` and
`tests/scripts/test_required_policy_checks.py` contain **zero** references to
`set-branch-protection.sh` (grep across both: no match). The guard's inputs are the inventory,
the committed snapshot, the workflow files, and — under `--live` — the API. The payload the
new file points at is not one of them.

**The file it names is wrong right now, in the dangerous direction.**
`scripts/set-branch-protection.sh:96-101` hardcodes **four** contexts:

```json
"contexts": [
  "Required checks passed",
  "doc-links + agents-init",
  "mypy — digabase + digikey",
  "gitleaks-scan"
]
```

Live `GET /branches/develop/protection` returns **three**, without `gitleaks-scan`. The script
contradicts *itself*: its own comment at `set-branch-protection.sh:8` says "would have
overwritten main's one check with develop's **three**", and `docs/BRANCH_PROTECTION.md:26`
records `gitleaks-scan` as "Added to the required set in #3922. **Not yet applied live**".
So the writer script is the only source of truth that still holds the un-applied fourth entry.

**Why this is a hazard, not a nit.** `security-gitleaks.yml`'s `on.pull_request` still carries
a workflow-level `paths-ignore: ['**.md', 'docs/**']` (verified by parsing the file at this
SHA). A *workflow* that is skipped reports nothing; a skipped *job* reports success. So
re-running `set-branch-protection.sh` today would make `gitleaks-scan` a required context that
cannot report on a markdown-or-docs-only PR — and every such PR would hang on
"Waiting for status to be reported" indefinitely. That is failure mode 1, one command away.

**This lands on DIG-1983.** That issue's plan promotes `gitleaks-scan` to required ("this is
the one with real security weight") and names neither `set-branch-protection.sh`, nor
`required-contexts.txt`, nor the `paths-ignore` blocker that this PR's own guard uses to
refuse the same promotion. Whichever way DIG-1983 writes its payload, one of the two committed
sources of truth goes stale, and the guard's stated contract is not what will happen.

**Cheapest correct fix, in this PR:** correct the two sentences to say what is true — that
`enable_branch_protection.py` is the writer, and that *no* automated check currently couples
the writer to this snapshot. One or two lines, no code, no design change.

**Separate follow-up (not this PR):** make one of them generate the other. The right shape is
for the writer to render `required-contexts.txt` from its payload, so drift is impossible by
construction rather than detectable after the fact.

## Finding 2 (MEDIUM) — the snapshot's only automated check is tautological

`tests/scripts/test_required_policy_checks.py:test_committed_contexts_match_the_live_gate`
asserts `guard.read_contexts_file(CONTEXTS) == LIVE_CONTEXTS`, where `LIVE_CONTEXTS` is a
literal in the same file and the module makes no network call. It catches "someone edited one
file and not the other" and nothing else — it stays green when someone changes protection in
repo settings and touches neither file, which is the drift class the file exists to catch.

This is the direct answer to judgement call 1: `--live` plus the doc requirement is not
sufficient, and this is the proof rather than the argument.

**Fix:** schedule the `--live` path already built. `ci-pr-hygiene.yml` already accepts a
`digithings-cron` `start_key`. Fail the *scheduled* job when snapshot ≠ live. That turns
invisible drift into a dated red run without putting a human-only gate in the PR path.

## Finding 3 (MEDIUM) — `types:` is unparsed, and the guard's headline property depends on it

`read_workflow_facts` reads trigger presence, `paths`/`paths-ignore`, and `branches`. It never
reads `types` or `branches-ignore`. Required status checks are evaluated against the **head
SHA**. A workflow on `pull_request: types: [opened]` reports for the opening SHA and never
again; after the first push the PR waits forever, and `reports_on_develop_pr` still returns
True because the trigger exists and carries no path or branch filter.

Latent today — all three live contexts use the bare `pull_request:` or `pull_request: {}`
form. But the pattern is live in the repo: `ci-pr-title.yml` is
`types: [opened, edited, synchronize, reopened]`. Drop `edited` and the check never re-runs.

This is a **gate on the promotions**, not a merge condition: both `All commits signed off` and
`Validate PR title` are mechanically safe to require *today* (I confirmed each reports on every
develop PR and converges), but the guard is not actually enforcing the property DIG-1983 will
rely on at the moment DIG-1983 relies on it. Parse `types` before child B.

## Finding 4 (MEDIUM) — `tracked_workflows` is a closed allowlist with no completeness check

`produce()` iterates only the tracked set. A new workflow with named jobs is out of scope
entirely: add `security-scc.yml` with a real gate and the guard is green. A live required
context produced by an *untracked* workflow gets `policy.undeclared-gate`, then `produce()`
returns None and the stall analysis never runs — fails closed, but with the wrong diagnosis on
exactly the case the gitleaks entry exists to exercise.

Cheaper than migrating 53 workflows: also scan every `*.yml` under `.github/workflows/` for a
named job matching a live or declared context, and fail if the producer is untracked.

## Answers to the four judgement calls

1. **Committed snapshot vs live read** — the constraint is real and unavoidable
   (`administration: read` cannot be granted to `GITHUB_TOKEN`). The *snapshot* is fine. What
   is not fine is the claim that it is automatically checked. See Findings 1 and 2.
2. **`tracked_workflows` + named-jobs-only** — defensible, and better than it looks. Mutation
   evidence: deleting the `name: All commits signed off` line **fails** the guard with
   `policy.renamed`. Dropping a check's `name:` does not hide it. The only hiding route is
   the two-step — drop the `name:` *and* remove the inventory entry — which goes green
   silently. That is documentable, not blocking. The real weakness is the other direction:
   an untracked workflow (Finding 4).
3. **Should any advisory check be `required` now** — yes, two, in child B, after Finding 3.
   `All commits signed off` and `Validate PR title` both report on every develop PR and both
   converge. `All agent-task issues in TSV…` is mechanically safe but deliberately ungated by
   ADR-0024, so leave it. `gitleaks-scan` must stay advisory while the workflow-level
   `paths-ignore` stands — **that refusal is correct and is the best-attempted part of this
   PR.** Separately: `advisory` needs a `reason` and nothing verifies the reason is still true
   or has an owner. Require `owner:` on every non-`required` entry.
4. **Scope discipline** — confirmed clean. The guard only reads; `--live` goes through
   `bp._gh_json`, which is a GET. No write to `required_status_checks` anywhere in the diff.
   The pre-existing in-file `needs` check is intact in `ci.yml`, and only one step was added.

## Verification I ran

- 25 tests pass (`25 passed in 2.07s`).
- Guard exits 0 on this repo: 10 declared, 3 required, 7 ungated by decision.
- Live API read of develop protection returns exactly the 3 contexts in the snapshot.
- Mutation sweep in a scratch copy, so the PR branch stayed clean:
  - workflow-level `paths-ignore` added to `ci-dco-sign-off.yml` → **guard stayed green** (exit 0). A real false green: `reports_on_develop_pr` is only consulted for contexts in the live *required* set, so an advisory-only workflow's reachability is never checked.
  - additionally delete that job's `name:` → **guard failed** (exit 1), `policy.renamed`.
  - additionally delete the inventory entry → **guard green again**, silently. That is the whole residual hole, stated exactly.

## What I was unsure of

- The `paths-ignore` semantics that make the gitleaks refusal correct — a skipped *workflow*
  reports nothing, a skipped *job* reports success — I am taking from this repo's own
  reasoning, not from GitHub's documentation. It is the load-bearing assumption behind the
  refusal and behind Finding 1's hazard, and it is the one claim here I would want checked
  against primary documentation before it is relied on in a runbook.
- I did not reproduce the author's mutation sweep; mine is independent and narrower.
- I did not verify production runtime or any unmerged branch.

## Not asked of the author

This file is uncommitted by design. The brief is a read-only review and committing to the PR
branch would move the head SHA under review.