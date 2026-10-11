# Review — PR #5059 (DCO 1.1 sign-off + TRADEMARKS.md)

- **Subject:** `a0ee3d688` feat(root): land DCO 1.1 sign-off and TRADEMARKS.md → branch `task/393-dco-sign-off-and-trademarks`, PR #5059
- **Reviewer:** Director OSS (`f22eb6f2-67b8-4117-b224-fba3c0ad7568`)
- **Date:** 2026-10-04
- **Verdict:** land after the two fixes in this file; not fresh-context review coverage (see § Reviewer independence)
- **Scope:** `CONTRIBUTING.md`, `TRADEMARKS.md`, `.github/workflows/ci-dco-sign-off.yml` (+ one row in `docs/agents/CI_CONVENTIONS.md`)
- **Severity counts:** 1 blocker (fixed here), 1 major (deferred, needs repo admin), 2 minor (one fixed, one noted)

## Verification run

| Check | Command | Result |
|---|---|---|
| Workflow parses as YAML, expected triggers/jobs | `python3 -c "yaml.safe_load(...)"` | OK — `on: pull_request(opened, synchronize, reopened), workflow_dispatch`; job `dco-sign-off` |
| Repo-wide workflow invariants | `pytest tests/scripts/test_workflow_environment_concurrency.py tests/scripts/test_secrets_audit.py -q` | 36 passed, 32 skipped (skips are the `environment:`-gated sweep; this workflow declares no environment, so `cancel-in-progress: true` cannot queue-starve) |
| Internal markdown links | `make doc-check` | OK (559 files scanned) |
| PR #5059 CI state | — | **not verified.** No `gh` binary and no GitHub token in this run's secrets (`GET /api/agents/me/secrets` → `{"secrets":[]}`), so "CI green" is unconfirmed from here. |

## Findings

### 1. BLOCKER — `TRADEMARKS.md` claimed a pending registration that does not exist

`TRADEMARKS.md` shipped: *"Registration is pending at EUIPO and USPTO."*

Nothing has been filed. Counsel's own policy file contradicts the draft it
contained:

- `knowledge/oss-policy.md:153` — "**Filing is Chris's action** … Counsel does not file."
- `knowledge/oss-policy.md:224` — action 4 (EUIPO + USPTO register search) is still open and "must be run manually before any filing fee is paid".
- `knowledge/oss-policy.md:225` — action 5 (file the word mark + logo) is assigned to **Chris**, not done.

So the public legal file asserted a registry state we cannot evidence. This is
the exact failure the repo warns about (AGENTS.md, review-coverage section:
PR #1891 rated Low shipped two false public claims). A trademark file that
overstates your own rights is the worst place for it — it is the document a
counterparty reads first.

**Fixed in this branch.** Replaced with the true state:

> We use them as trademarks; no registration application has been filed yet.

The substantive restriction (no implied endorsement / affiliation) is unchanged.
This is a factual correction, not a change of legal position: it removes a claim
we cannot support. Counsel or Chris can revert the sentence if a filing lands
before merge — in which case it becomes true as written.

Confidence: **CONFIRMED** (the counter-evidence is in the policy file that
carries the approved drafts).

### 2. MAJOR — the gate is advisory, and squash-merge drops the trailer (deferred: needs repo admin)

Two things weaken the mechanism this PR adds:

- **Not a required check.** A workflow that is not in the branch-protection
  ruleset cannot block a merge; it only tells you afterwards. The issue scope
  said "do not claim a gate that does not exist" — correct, and the gate does not
  *enforce* yet either. Registering it needs repo admin settings, which no agent
  on this issue holds. Deferred to IT support.
- **Squash-merge drops the trailer.** `.github/workflows/agent-pr-finalizer.yml:174`
  runs `gh pr merge --auto --squash`, and `agent-pr-automerge.yml` enables squash
  auto-merge. GitHub's default squash message keeps the commit *subjects*, not the
  bodies where `Signed-off-by` lives, so the trailer does not reach `develop`'s
  history. Confidence: **LIKELY** — GitHub's documented squash behaviour; the
  repo's current "include commit messages in the merge commit" setting could not
  be read without admin API access.

The evidence is not lost: GitHub keeps a PR's commits (and their full messages)
after the branch is deleted, so a chain-of-title audit can cite PR + sha. What
was missing was telling anyone that. **Fixed in this branch** — `CONTRIBUTING.md`
now says so, which is also the honest version for an outside contributor reading
the file for the first time.

Not fixed here, and should not be, without the ruleset change first: adding a
`push`-triggered sign-off check on `develop`. Every squash-merged commit from
the moment this lands would fail it, so it would turn the next merge into a red
`develop`.

### 3. MINOR — unused `GH_TOKEN` in the DCO job

`ci-dco-sign-off.yml:30-31` exports `GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}` but
no step calls the API. Harmless, but it reads as a claim that the check verifies
something on GitHub's side. Left in place — deleting it is cosmetic and the PR
should not grow another commit for it.

### 4. MINOR — the two new root files were invisible from the workflow inventory

`docs/agents/CI_CONVENTIONS.md` states every workflow file has a row in its
inventory. `ci-dco-sign-off.yml` had none, and the row that now exists records
honestly that the check is not yet required.

### First-hour experience (my lane, not a defect)

`CONTRIBUTING.md` now tells a first outside contributor: what the DCO is for
(MIT collects nothing from you), how to sign (`-s` or `format.signoff`), that the
CI check rejects unsigned PRs, that it is forward-only, where the record lives
after squash-merge, and that MIT does not carry the name (`TRADEMARKS.md` link).
That is the whole path with no dead ends. I would not change it further.

## Reviewer independence — read this before treating this as coverage

This issue's earlier run authored `a0ee3d688` under this same agent identity. Per
`AGENTS.md` ("Author session must not review its own work") **this is a
verification pass, not review coverage.** It does not satisfy `reviewed:agent` and
must not be used to justify the merge. The merge still needs a real hatch:
Cursor Bugbot, an approved review, or `reviewed:owner` from Chris. Filed as a
follow-up for IT support.
