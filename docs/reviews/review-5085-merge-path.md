# Review — PR #5085, the DIG-506 merge path

| | |
|---|---|
| Reviewer | fresh-context subagent reviewer (`space-bunny-free`), in-session, per `docs/agents/CODE_REVIEW_POLICY.md` |
| Subject | PR #5085, `task/506-twelve-x-merge-queue` |
| Commit range | `faa339419dffc010e102f82a6bc22cafd3f608c6` (github/develop) .. `5365920d6` |
| Verdict | **Request changes** — the merge queue can land a PR whose checks were never re-run against the new base, and the branch-protection apply path targets an endpoint that does not exist |
| Severity counts | blocker 0 · major 5 · minor 8 · nit 2 |

Scope reviewed: `scripts/merge_queue.py`, `scripts/enable_branch_protection.py`,
`scripts/merge_queue_policy.json`, `docs/MERGE_QUEUE.md`, the new
`docs/BRANCH_PROTECTION.md` section, `tests/scripts/conftest.py`, and both new test
files. Every finding below was reproduced with a command; the command is named.

**The honest-blocker framing is honest.** The central claim — `digithings-ai` is Free,
`twelve-x` is private, protection/rulesets/merge-queue are refused with HTTP 403 — is
verified, not assumed. Reproduced live against the real repo:

```
$ python3 scripts/enable_branch_protection.py status --repo digithings-ai/twelve-x --branch develop
repo:        digithings-ai/twelve-x
visibility:  private
org plan:    free
admin:       yes
BLOCKED: … requires GitHub Pro for private repositories
protection on develop: NOT READABLE — gh: Upgrade to GitHub Pro or make this repository public… (HTTP 403)
rulesets: NOT READABLE — gh: Upgrade to GitHub Pro or make this repository public… (HTTP 403)
```

The repo survey table also verifies row-for-row (visibility, default branch, protection,
ruleset count, and `required_pull_request_reviews: null` on `digithings` all match the
API). `~$4/month for one seat` for Pro matches GitHub's published pricing. Done-test items
1 (branch protection) and 2 (native merge queue) are **not** met, and the PR does not claim
they are — that part of the framing is accurate. Findings F4, F9 and F10 are accuracy
defects *inside* that otherwise-honest frame, not overclaims of the blocker itself.

---

## Findings

### 1. major — `scripts/merge_queue.py:269` — the queue merges a `BEHIND` PR on its pre-merge green check, which is the exact outcome a merge queue exists to prevent

`evaluate()` gates `mergeStateStatus` only on the literal `BLOCKED`:

```python
if str(pr.get("mergeStateStatus") or "") == "BLOCKED":
    reasons.append("mergeStateStatus=BLOCKED")
```

After the queue merges PR #1, PR #2 is `MERGEABLE` + `BEHIND`, and its `test` check is
still the run computed against the *previous* `develop` tip. Nothing waits for a re-run,
so #2 lands with the same green evidence as #1 — the "landed untested combination" failure
the change is written to stop. The ruleset path sets `strict: true` for exactly this; the
local queue, which is the path actually in use today, has no equivalent.

Reproduced:

```
$ python3 -c '… mq.evaluate(pr(mergeStateStatus="BEHIND"), pol, acting_role="cto", attest_role="qa")'
BEHIND -> True ()
DIRTY  -> True ()
```

`DIRTY`/`HAS_HOOKS` are covered in practice by the `mergeable == MERGEABLE` check;
`BEHIND` is not. It matters because it defeats the re-read-after-every-merge design that
F1's sibling comment in `main()` advertises: `docs/MERGE_QUEUE.md:93-95` says re-reading
"is what makes that visible instead of sending a stale-base merge", but the re-read only
surfaces *conflicts*, never a stale verdict. Fix direction: gate on any `mergeStateStatus`
outside `{CLEAN, UNSTABLE}`, or require the base SHA to have moved through CI.

### 2. major — `scripts/enable_branch_protection.py:368` (+ `:391`) — the ruleset apply targets `PUT /repos/{owner}/{repo}/rulesets`, which does not exist

`cmd_apply` registers the ruleset step as endpoint `repos/{repo}/rulesets` and
`_gh_api_status(..., method="PUT", ...)` issues it as `gh api PUT repos/O/R/rulesets --input -`.
GitHub's REST API has no `PUT` on that collection: **Create a repository ruleset** is
`POST /repos/{owner}/{repo}/rulesets`, and **Update** is `PUT /repos/{owner}/{repo}/rulesets/{ruleset_id}`
(verified against <https://docs.github.com/en/rest/repos/rules>). So the documented apply
command — `apply --check test --require-approvals 1 --mode ruleset --merge-queue`
(`docs/MERGE_QUEUE.md:182-184`) — returns 404 and exits 1. `--mode ruleset` is the default
mode, and it is the *only* mode that can carry a merge queue, so there is no working path to
the feature this script exists to install. It fails loudly (no silent under-enforcement),
and there is no create-or-update-by-name logic, so even fixing the verb to `POST` would
duplicate the ruleset on every re-run. Related: F13, the test that reaches this write path
cannot catch the wrong verb.

### 3. major — `scripts/enable_branch_protection.py:178` — `apply` can silently *reduce* protection on an already-protected branch

`classic_payload` sends `"contexts": checks` from `--check`, and `PUT
/repos/{owner}/{repo}/branches/{branch}/protection` is a **full replace** of the protection
object (the repo's own `docs/BRANCH_PROTECTION.md:151-153` says so). The script never reads
the branch's current contexts and never warns. `docs/MERGE_QUEUE.md:215-217` points an
operator straight at the one repo that is protected: *"That is a separate gap from the plan
limit and can be closed with `--require-approvals 1` today, since the repo is public."*

Verified live state of that repo:

```
$ gh api repos/digithings-ai/digithings/branches/develop/protection \
    --jq '{contexts: .required_status_checks.contexts, strict: .required_status_checks.strict}'
{"contexts":["Required checks passed","doc-links + agents-init","mypy — digibase + digikey"],"strict":true}
```

So `apply --repo digithings-ai/digithings --branch develop --check test --require-approvals 1`
replaces three live required checks with one, exits 0, and prints "applied". This is the one
place `apply` really can enforce less than the operator believes they are getting. Fix
direction: read current state, and refuse (or require an explicit `--replace`) when the
payload drops a check that is live today.

### 4. major — `docs/MERGE_QUEUE.md:141-150` — the `$` console block is a rewording of the script's output, not its output

The section's claim is *"The refusal is reproduced by the tooling, not asserted."* The
transcript is hand-edited: it drops the `repo:` line the script prints, collapses the
column alignment (`visibility: private` vs the real `visibility:  private`), and rewrites
the BLOCKED sentence (`"is private and the digithings-ai plan is 'free'. Protected branches
require GitHub Pro"` vs the real `"is private and org 'digithings-ai' is on the 'free'
plan; branch protection, rulesets and the server-side merge queue all require GitHub Pro for
private repositories"`). The trailing `Upgrade to GitHub Pro…` line paraphrases the real
`protection on develop: NOT READABLE — gh: Upgrade to GitHub Pro … (HTTP 403)` line rather
than being it. The `...` signals elision, but a `$` block is read as captured output. The
facts are correct; the artifact is not, and this is the one place the PR asserts its own
evidence. Paste the real output, or label the block as a paraphrase.

### 5. major — `scripts/merge_queue.py:173` — `--limit` (default 50) truncates the *newest* PRs, so above 50 open PRs the oldest are never fetched, reported, or merged

`fetch_queue` passes `--limit str(limit)` and `gh pr list` returns **newest-first**; the
script then sorts ascending. Verified live against `twelve-x`:

```
$ gh pr list --repo digithings-ai/twelve-x --base develop --state open --limit 5 \
    --json number,createdAt
[{"createdAt":"2026-10-05T00:23:30Z","number":258}, … {"createdAt":"2026-10-04T21:27:18Z","number":251}]
```

(`cli/cli#10244` confirms `createdAt` desc is the fixed default; there is no `--sort`.)
So the window is the 50 newest, sorted ascending: the head of the queue is dropped before
the FIFO sort ever sees it. `list` then reports a shorter queue and an operator concludes
nothing older is waiting — the failure is silent and points the wrong way. Latent today
(`gh pr list --base develop --state open --limit 200 --json number --jq length` → 12), but
the doc stakes an explicit fairness claim on this ordering.

### 6. minor — `scripts/merge_queue.py:189` — the required-check gate accepts any entry named `test`, including a commit status posted by any integration

`_check_name` falls back to `context`, so a `StatusContext` satisfies the gate as readily as
a check run, and nothing pins the source. GitHub's own docs: *"Any person or integration
with write permissions to a repository can set the state of any status check in the
repository."* Reproduced: a rollup of `[{"__typename":"StatusContext","context":"test","state":"SUCCESS"}]`
with no CI run evaluates as eligible. Every agent in this org holds write access, and the
org already has a "same job name in multiple workflows" hazard documented in
`docs/BRANCH_PROTECTION.md`. Fix direction: require `__typename == "CheckRun"` (or pin
`workflowName`), matching the `integration_id` the ruleset payload already omits.

### 7. minor — `scripts/merge_queue.py:232` — any non-author `APPROVED` review satisfies the review gate, including a bot

`approved_by_other` matches on login only. Reproduced: `reviews=[{"author":{"login":"coderabbitai[bot]"},"state":"APPROVED"}]`
with no `--attest-review` → eligible. Combined with F6, both halves of the gate can be
satisfied by an automation identity and no role ever appears in the audit comment. Worth an
explicit policy decision rather than an accident: either exclude App/bot logins or require
the attested role regardless.

### 8. minor — `scripts/enable_branch_protection.py:340` — `status` exits 0 when both protection and rulesets reads 403'd

Reproduced live: the `twelve-x` `status` run above prints two `NOT READABLE … (HTTP 403)`
lines and exits 0. Any wrapper or CI step that reads exit 0 as "state known" gets a false
pass on exactly the repo the script exists to diagnose. Add a distinct exit code (or a
non-zero return) for "unreadable".

### 9. minor — `docs/MERGE_QUEUE.md:176-179` — the documented "Rehearse the exact payloads. Writes nothing." command prints no payload on `twelve-x`

`cmd_apply` returns at `:351-352` on the plan gate, which is *before* the `--dry-run` block
at `:381-386`. Verified live: that exact command prints the BLOCKED block, prints no JSON,
and exits 3. The doc's own §Merge-when-ready workflow depends on being able to see the
payload before a plan upgrade. Either print the payload before refusing, or say so in the
doc.

### 10. minor — `docs/MERGE_QUEUE.md:130-137` and `scripts/merge_queue.py:4-6` — the merge queue is a *ruleset* rule, not branch protection, and the quoted paragraph is no longer at its cited source

"The merge queue is configured *through* branch protection" contradicts the sibling
script's own correct statement at `enable_branch_protection.py:209` ("A ruleset is the only
way to get a server-side merge queue") — merge queue is the `merge_queue` rule type inside a
ruleset, which is why `--mode classic` has to be refused. Separately, the block quote
attributed to "GitHub's own documentation" is not on the current
<https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches>
page (fetched today); plan availability now lives on the plans pages, where Free's feature
list omits protected branches for private repos. The conclusion is unchanged — re-cite and
date it.

### 11. minor — `scripts/merge_queue_policy.json:26` — the roster overstates what the code refuses

"It refuses a self-attestation when that role authored the PR" is not implemented.
`_gate_review` refuses only `attest_role == acting_role`; the script has no per-role
authorship signal at all, because every role shares one login. `docs/MERGE_QUEUE.md:46-49`
states the same gap more honestly ("the role is an assertion, not something GitHub can
verify") — but then leans on the refusal as "what stops a single-credential setup from
silently collapsing into 'I reviewed it and merged it'", when `--acting-role cto
--attest-review qa` is a single self-asserted command line. Both flags need the same
disclaimer.

### 12. minor — `tests/scripts/conftest.py:124` — the previously-live `gh` calls are fixed, but nothing structurally prevents a regression

`gh_stub` is deliberately not autouse (`:136-139` says so). I verified the *current* suite
cannot reach the network two ways: every test that shells out takes the fixture (checked
by scanning for `_run(` without `gh_stub` on the signature — one hit,
`test_merge_queue_with_classic_mode_is_refused`, which is safe only because the validation
precedes the preflight), and re-running the suite with `/opt/homebrew/bin` removed from
`PATH` still passes 59/59, so no test falls through to a real `gh`. So the two live-call
tests are genuinely closed. What is missing is the guard that would keep them closed: an
autouse fixture that points `gh` at a loud stub (or fails the test) by default, with
`gh_stub` opting *in* to real behaviour. Today the safety property is per-test discipline,
which is exactly how the two live calls got in.

### 13. minor — `tests/scripts/` — the dangerous directions are the untested ones

Gaps, in rough priority order:

- **No assertion that `gh pr list` is called with `--base`.** `blocked_bases` only guards
  the `--base` *argument*; if that filter were dropped from the fetch, the queue would pull
  PRs targeting any branch and merge them. Nothing pins the argv.
- **No test of the ruleset write method/endpoint** — F2's root cause. The only test that
  reaches the write path (`test_enable_branch_protection.py:216`) matches
  `^api (PUT )?.*/rulesets`, which accepts either verb by design, so it is tautological on
  exactly the field that is wrong.
- **No test for `--limit` truncation** (F5), a `BEHIND` PR (F1), a duplicate-name required
  check, a `StatusContext`-only rollup (F6), or a bot approval (F7).
- `test_run_never_escalates_with_admin` asserts `stub.matching("pr merge")` is truthy and
  that no call contains `--admin` — fine, but it would also pass if the merge used some
  other escalation flag; pinning the full argv would be stronger.

The tests that *do* exist pin real behaviour: the NEUTRAL/SKIPPED/absent cases, the
duplicate green+red case (verified failing correctly), author-self-approval, self-attestation
refusal, prefix-matched blocked bases, re-read-after-merge ordering, and the `--match-head-commit`
pin are all genuine regression pins, not assertions on the stub's own bookkeeping.

### 14. nit — `docs/MERGE_QUEUE.md:60` — the gate table says `mergeable == CLEAN`

`CLEAN` is a `mergeStateStatus` value, not a `mergeable` one (`MERGEABLE` /
`CONFLICTING` / `UNKNOWN`). The code requires `mergeable == "MERGEABLE"` and separately
rejects only `mergeStateStatus == "BLOCKED"` — which is also the gap in F1.

### 15. nit — `docs/MERGE_QUEUE.md:232` — `[BRANCHING.md](BRANCHING.md)` is broken as rendered

From `docs/`, it resolves to `docs/BRANCHING.md`, which does not exist; the file is at the
repo root. `scripts/check_doc_links.py:165-167` accepts it because it also tries a
repo-root candidate, so `make doc-check` passes (verified: `check_doc_links: OK (463
markdown files scanned)`) while the GitHub link 404s. `../BRANCHING.md` is the fix.

---

## What passed

- The plan-gate reasoning in `enable_branch_protection.py` is right in direction and
  honest about its own uncertainty: an unreadable plan proceeds rather than guessing Free,
  which is the correct way round (`test_an_unreadable_plan_does_not_block`). The
  `{"enabled": bool}` unwrapping is correctly handled and tested in both shapes, and it
  really is the difference between "force-pushes blocked" and "force-pushes allowed".
- The ruleset payload is field-accurate against the current REST schema (`non_fast_forward`,
  `deletion`, `required_status_checks` with `do_not_enforce_on_create`, `pull_request`
  with `require_last_push_approval`, `merge_queue` with `ALLGREEN` + `max_entries_to_merge: 1`).
- `_gate_checks` handles the genuinely dangerous cases correctly: absent, `NEUTRAL`,
  `SKIPPED`, empty conclusion, and in-progress all fail; a duplicate `test` with one red
  entry fails; a non-required red check fails; `--admin` is never passed; `--match-head-commit`
  is always passed and pinned to the evaluated SHA.
- FIFO ordering and tie-breaking are correct given the window that reaches them (F5 is
  about the window, not the sort).