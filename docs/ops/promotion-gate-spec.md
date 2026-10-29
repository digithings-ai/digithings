# Promotion gate: spec

Status: draft for review by One · Owner: QA (W3/W5) · 29 Oct 2026
Applies to: digithings promotion PRs from the local Forgejo (digiforge) into GitHub `develop`
Related: dev-flow upgrade plan (W1, W3, W4, W5, W7), [MERGE_QUEUE.md](../MERGE_QUEUE.md), [BRANCH_PROTECTION.md](../BRANCH_PROTECTION.md), [`scripts/local-ci/README.md`](../../scripts/local-ci/README.md)

## 1. Scope and model

Work is committed and reviewed on the local Forgejo. Each change gets local-ci and a Docker full-stack smoke on the Mac. Changes reach GitHub only as part of a **batch**, through one **promotion PR** into `develop`. The promotion PR is opened by `sctl promote`, which the Coder lane is building in digiforge.

This spec defines the **promotion gate**: the check that decides whether a promotion PR may merge. It covers the gate's rules, how verdicts are stored, the promotion PR body, the Human Gate, and how the gate itself is tested. It does not change branch protection. Making `promotion-gate` a required context is Chris's call (plan decision A, "develop protection").

Definitions:

| term | meaning |
|---|---|
| change | One Forgejo PR (one work item iteration) with its own commits. |
| batch | The ordered set of changes that one promotion PR carries. |
| commit in the batch | Every non-merge commit in `origin/develop..<promotion head>` on GitHub. |
| head | The commit SHA a verdict, a CI run or a smoke run was made against. |
| platform | One of `claude`, `cursor`, `grokbot` or `paperclip`. Attribution is by platform only (Chris, 29 Oct 2026). |
| session | One run of an agent on a platform: a chat, a cloud-agent run or a Paperclip run. Each session has a stable id. |
| verdict | `approve` or `changes-requested`, recorded against exactly one commit SHA, by one reviewer session. |

Ownership: each change is owned by its author's platform, taken from the `Source-Platform:` trailer (W7). On GitHub, the promotion PR is owned by the platform whose agent pushes it. The PR carries that platform's `src:<platform>` label and lists every platform in the batch. **The `reviewed:*` labels (`reviewed:owner`, `reviewed:agent` and the rest) are retired.** The gate never reads them, and adding one changes nothing.

## 2. The gate passes only when all of these hold

The gate evaluates the promotion PR's current head. If any rule fails, the gate fails and names the rule and the commit.

### G1. One independent verdict for every commit, on that commit's SHA

For every commit `C` in the batch:

1. At least one verdict exists whose `head` equals `C`'s SHA, either the full 40 hex characters or a unique prefix of 12 or more. A verdict on any other SHA does not count for `C`, including `C`'s parent or an earlier head of the same change.
   - Shortcut: a change with several commits may be reviewed once, at its last commit `T`. That verdict covers every commit of that change up to and including `T`, as long as the verdict's `range` field lists them (see §3). One verdict per change is the normal case. One verdict per commit is not required.
2. The latest verdict for `C` from each reviewer session is `approve`. If any reviewer session's latest verdict for `C` is `changes-requested`, that is a standing change request (see G3).
3. The verdict is **independent**. A verdict is independent when:
   - its reviewer session differs from the session that authored `C`; **a fresh session on the same platform qualifies**; and
   - it is never from the session that wrote the code. A verdict from the same session as the commit's `Source-Session` fails G1 even when it says approve.
   - If the commit carries no session id, the gate cannot prove independence on the same platform. In that case only a verdict from a **different platform** counts. Fail closed: no session id and same platform means not independent.
4. A verdict posted inside the push window of its head is not a verdict. The 60 s rule in `review_pass_filter.review_too_close_to_push` already covers this, and the gate reuses it.

### G2. Green local-ci and a passing Docker full-stack smoke for every change

For every change in the batch:

1. The change's head has a `local-ci` success. With the W3 branches merged, that run also includes the scoped pytest suites for every module the change touches.
2. The change's head has a passing **Docker full-stack smoke**: the W4 `stack-verify` target brings the whole stack up in Docker on the Mac, runs the smoke tests and tears the stack down. The run is recorded with its run id, its head SHA and its result.

The batch as a whole must also pass. The promotion head has never been tested as a combination, so it needs its own `local-ci` success **and** its own Docker smoke on exactly the promotion head SHA. Green changes do not make a green batch.

### G3. No open change requests and no unresolved review threads

1. No change in the batch, and not the promotion PR itself, has a standing change request. A change request stands until one of these happens: the same reviewer session (or the same seat or session identity, under `review_pass_filter.outstanding_change_requests`) posts `approve` on a later head; the review is dismissed; or, for a request that names no session, a later verdict that names one clears it. The merge queue already uses these rules.
2. Every review thread on every change and on the promotion PR is resolved, or answered by the author after the thread's last reviewer comment. These are the rules `review_applied.evaluate` uses today.
3. On GitHub, the promotion head has a **completed automated reviewer run** (Bugbot, while it is configured on the repository) whose head is the promotion head, with no unresolved findings. This rule exists because of #6616 (§5.2).

### G4. The promotion PR body is complete and matches the branch

The body follows §4, and the gate parses it.

- The manifest lists **exactly** the commits in `origin/develop..<head>`: none missing, none extra, in order.
- Every verdict link in the manifest resolves, and the verdict it points at matches the manifest's `head` and digest.
- A body that is missing a section, or whose manifest does not match the branch, fails the gate. Unlike `pr-template` on task PRs, this is not a warning: the body is the gate's input, and #6627 and #6642 were cut-down templates (§5.3).

### G5. Human Gate

If any change in the batch has a ticked Human Gate box, the promotion needs **Chris's recorded approval on the promotion PR, at its current head**. Human Gate areas: auth or crypto, live trading, new JWT scopes, the code-exec gate, new network exposure, a new external service, `SECURITY.md`, or a novel architecture pattern. The gate also infers a Human Gate from the paths the change touches (§6.2), because a box nobody ticked is exactly the #6603 and #6601 failure.

> **OPEN QUESTION for One:** the exact mechanism for "Chris's recorded approval". `reviewed:owner` is retired and must not be used. Three options, none decided:
> 1. A GitHub `APPROVED` review on the promotion PR whose `commit_id` is the head. The problem: Chris and the queue share the `chrizefan` identity today (plan P0-2), so this does not prove that a human approved.
> 2. A signed approval: a Forgejo approval by Chris's own account, or an SSH-signed `Human-Gate-Approved: <head>` statement checked against a key only Chris holds.
> 3. A decision card in the Grok Bot or Paperclip flow that writes the approval with Chris's identity and the head SHA.
>
> Until this is decided, the gate treats **any** Human Gate batch as failing with "Human Gate: awaiting Chris's recorded approval (mechanism TBD)". Such a batch cannot be promoted through the gate.

## 3. Verdict storage that survives the Forgejo-to-GitHub hop

### 3.1 Requirements

- A verdict is bound to a commit SHA, so the hop must preserve SHAs. `sctl promote` builds the promotion branch by **fast-forwarding or merging** the reviewed Forgejo commits. It never squashes, rebases or cherry-picks them. The promotion PR merges into GitHub `develop` with a **merge commit**, not squash or rebase, so every reviewed SHA exists on `develop` afterwards.
- Verdicts must remain readable when the Forgejo instance is unavailable, and after the Forgejo PR is closed.
- A verdict must be hard to forge or edit after the fact, and an edit must be detectable.

### 3.2 Format: one verdict format

The format is one canonical JSON record per verdict, as plan P1-7 asks. The legacy formats are the `Review verdict:` line, the in-session marker and seat markers. They are read for history only and not accepted for new verdicts.

```json
{
  "schema": "digithings.verdict/v1",
  "repo": "digithings-ai/digithings",
  "change": "forgejo:digithings#123",
  "work_item": "DIG-1234",
  "head": "<40-hex sha>",
  "range": ["<sha>", "<sha>"],
  "verdict": "approve",
  "reviewer": {"platform": "cursor", "session": "<session id>"},
  "author": {"platform": "claude", "session": "<session id from Source-Session>"},
  "human_gate": false,
  "findings": [{"id": "F1", "severity": "P1", "status": "resolved", "thread": "<url>"}],
  "at": "2026-10-29T13:40:00Z"
}
```

`range` lists the commits this verdict covers, oldest first. Its last element must equal `head`. `digest` is computed as `sha256` over the canonical JSON (sorted keys, no whitespace) and is not stored inside the record.

### 3.3 Where it lives

| copy | role | survives Forgejo down? |
|---|---|---|
| sctl's verdict store on Forgejo, as a review comment on the change carrying the JSON record in a fenced `verdict` block | source of truth, written at review time | no |
| The promotion manifest (§4), which carries each record's `digest`, its Forgejo URL and the full record in a collapsed block | transport across the hop, readable on GitHub | **yes** |
| `refs/notes/verdicts` on the promotion branch's commits, pushed with the promotion | durable copy keyed by SHA, readable with `git notes --ref=verdicts show <sha>` | **yes** |

The gate reads the manifest copy and checks each record's digest. When Forgejo is reachable, which is the normal case since the gate runs on the Mac, it also re-fetches the source record and fails if the two differ. When Forgejo is not reachable, it accepts the notes copy only if that copy matches the manifest digest, and it logs that the source was not re-checked.

> Judgement call: git notes are pushed explicitly (`git push origin refs/notes/verdicts`). GitHub stores them but does not show them. If One prefers not to push notes, the manifest copy alone still meets the "survives the hop" requirement. The notes add a SHA-keyed copy that does not depend on the PR body staying unedited.

### 3.4 Stale verdicts: a commit after the verdict

A verdict covers its `range` and nothing else. When any commit lands on a change after its verdict, whether a fix, a merge of `develop` or a rebase:

1. The new head has **no verdict** and fails G1 until it is reviewed again. sctl marks the old verdict `stale` in its store, keeping it as history, so tooling does not show it as current.
2. The new review covers the whole change, not just the new commit. Its `range` lists every commit of the change up to the new head.
3. **No carry-forward on merges of the base.** A merge of `develop` into a change produces a new head that nobody has reviewed. #6616 merged at exactly such a head. The gate treats it like any other new commit. To keep this cheap, sctl promote merges `develop` into the *promotion* branch once per batch, and that batch head is covered by G2's batch-level `local-ci` and Docker smoke plus G3.3's automated reviewer run. It does not merge into every change.
4. **Promotion-branch merge commits** (`sctl promote`'s own merges of reviewed changes) are the only commits exempt from G1. They are exempt only if `git diff <merge>^1..<merge>` equals the union of the reviewed changes' diffs, that is, the merge resolved no conflicts. A merge that resolved a conflict is a new commit and needs a verdict.
5. **Promotion PR updates.** If the promotion branch moves after the gate passed, the gate result is void and the gate re-runs on the new head. The gate's status is posted against the head SHA, so a new head starts with no status.

## 4. The promotion PR body

`sctl promote` generates the body. Humans and agents do not hand-edit it. The template lives at `.github/PULL_REQUEST_TEMPLATE/promotion.md` (to be added with sctl promote), and the gate checks it under G4. Required sections, in order:

~~~~markdown
## Promotion

Batch: <batch id>  ·  Base: develop@<sha>  ·  Head: <sha>
Pushed by: src:<platform>  ·  Platforms in batch: claude, cursor
Docker smoke (batch head): <run id> at <head sha>: pass
local-ci (batch head): <status url>

## Changes

| # | work item | change | commits (oldest → newest) | author platform | verdict | reviewer platform/session | local-ci | Docker smoke | Human Gate |
|---|---|---|---|---|---|---|---|---|---|
| 1 | DIG-1234 | forgejo:digithings#123 | `abc123…` `def456…` | claude | approve @def456… <forgejo verdict url> `sha256:…` | cursor / s-9f2… | ✅ <url> | ✅ <run id> | no |

## Manifest

<details><summary>machine-readable manifest (do not edit)</summary>

```json
{"schema": "digithings.promotion/v1", "batch": "...", "base": "...", "head": "...",
 "changes": [{"change": "...", "commits": ["..."], "verdicts": [{"url": "...", "digest": "sha256:...", "record": {...}}],
              "local_ci": {"head": "...", "state": "success"}, "docker": {"run": "...", "head": "...", "state": "pass"}}],
 "batch_checks": {"local_ci": {...}, "docker": {...}}}
```

</details>

## Human Gate

Batch needs Chris: yes | no
Changes with a Human Gate: <list, or "none">
Chris's approval: <link, or "pending">   <!-- mechanism: open question, §2 G5 -->

## Open threads and change requests

none   <!-- or a list; any entry fails G3 -->
~~~~

The PR title is `promote(develop): <batch id> (<n> changes)`.

## 5. Known failure modes and how the gate fixes them

### 5.1 review-applied goes stale when the queue merges right after an approve (#6543, #6567, #6635)

In each of these the queue merged right after an approve, and the `review-applied` result it relied on had been computed before the last change to the PR. Nothing tied the verdict to the head that actually merged. Fixes:

- G1 binds every verdict to a SHA, and §3.4 voids it on any later commit.
- The gate status is posted per head (§3.4.5), so there is no stale green row to read.
- On task PRs, branch `qa/review-applied-skip-until-review` no longer counts an approve of an earlier head as a review pass, and posts nothing until the head has been reviewed.

### 5.2 Merges at a develop merge commit with no fresh Bugbot run (#6616)

#6616 merged at a head created by merging `develop` into the branch, and no automated reviewer had run on that head. Fixes:

- §3.4.3: no carry-forward over base merges.
- G3.3: the promotion head needs a completed automated reviewer run on itself.
- G2: the batch head needs its own `local-ci` and Docker run.

### 5.3 Cut-down promotion templates (#6627, #6642)

These promotions shipped bodies with the batch list and the evidence trimmed away, so nobody could check what was in them. Fixes:

- The body is generated (§4), and G4 fails on a missing section or on a manifest that does not equal `origin/develop..head`.
- This is the one template check that stays blocking. On task PRs, `pr-template` becomes a warning (branch `qa/pr-template-warn`).

### 5.4 Human Gate boxes ignored (#6603, #6601)

Both PRs had a Human Gate box ticked, and nothing enforced it. The template check only asks whether the question is answered. The other human signal, `reviewed:owner`, is a label any agent can add, and 20 of 38 develop merges since 27 Oct carry it, some added after the merge. Fixes:

- G5 requires Chris's recorded approval at the promotion head. Labels never satisfy it, and the mechanism is an open question.
- §6.2 infers the Human Gate from paths, so an unticked box does not escape.
- On task PRs, `pr-template` keeps the Human Gate blocking and now also fails a ticked box answered "No" (branch `qa/pr-template-warn`).

## 6. Implementation notes

### 6.1 Where the gate runs

The gate is a new lane, `scripts/local-ci/promotion_gate.py`, run by the local-ci tick on the Mac for PRs into `develop` that carry the `promotion` label and come from the promotion identity. It posts the `promotion-gate` context with the existing local-ci app identity, which the gate needs in order to reach Forgejo. The existing static gates and scoped pytest still run on the promotion head as normal `local-ci`. QA writes the checker and its tests, and Platform wires the launcher. Making the context required is Chris's branch-protection decision. **Until then, the gate reports but does not block.**

### 6.2 Human Gate path inference

A change touching any of these paths sets `human_gate: true` regardless of its boxes. The list is a starting set for One to confirm:
- `digikey/**` (signing, JWT, scopes)
- `**/auth/**`, `**/*jwt*`, `**/*crypto*`
- `digiquant/**/broker*/**`, `digiquant/**/execution/**`
- any file that defines or reads `DIGI_ALLOW_CODE_EXEC`
- any compose or Docker file that adds a `0.0.0.0` bind or a published port
- `SECURITY.md`

### 6.3 Reused code

- `review_pass_filter.outstanding_change_requests`: standing change requests (G3.1).
- `review_pass_filter.review_too_close_to_push`: the push window (G1.4).
- `review_applied.evaluate`'s thread rules (G3.2).
- `pr_template`'s Human Gate parser (G5 box detection).

## 7. Test plan for the gate itself

### 7.1 Unit tests (`tests/scripts/test_promotion_gate.py`, stdlib plus fixtures, no network)

Every external read (GitHub REST, Forgejo, git) is injected, the same way `review_applied` takes `run_rest`. No test calls a live service or any paid inference API.

| # | case | expected |
|---|---|---|
| U1 | every commit has an approve on its SHA from another platform; local-ci and Docker green; no threads | pass |
| U2 | approve from a fresh session on the same platform | pass |
| U3 | approve from the authoring session (`Source-Session` equals the reviewer session) | fail G1 "not independent" |
| U4 | same platform and no `Source-Session` on the commit | fail G1 "cannot prove independence" |
| U5 | approve on commit N-1; commit N lands after it | fail G1 for N; the old verdict is reported as stale |
| U6 | a change merges `develop` after its approve (the #6616 shape) | fail G1 for the merge commit |
| U7 | clean promotion merge commit, no conflicts | exempt; pass |
| U8 | promotion merge that resolved a conflict | fail G1 for that merge |
| U9 | verdict range covers commits 1..3 with head = 3 | pass for all three |
| U10 | standing `changes-requested` from one session, `approve` from another | fail G3.1 |
| U11 | change request cleared by the same session's later approve on the current head | pass |
| U12 | an unresolved thread with no author reply | fail G3.2 |
| U13 | no automated reviewer run on the promotion head (the #6616 shape) | fail G3.3 |
| U14 | change head has local-ci green but no Docker run | fail G2.2 |
| U15 | batch head has no own local-ci or Docker run (only the changes do) | fail G2 batch |
| U16 | manifest missing a commit in `develop..head` | fail G4 |
| U17 | manifest with an extra commit not on the branch | fail G4 |
| U18 | body with the Manifest or Changes section removed (the #6627 and #6642 shape) | fail G4 |
| U19 | the manifest digest does not match the Forgejo record (edited verdict) | fail G4 |
| U20 | Forgejo unreachable; the notes copy matches the digest | pass with a "source not re-checked" log line |
| U21 | Forgejo unreachable and no notes | fail closed |
| U22 | Human Gate box ticked (the #6603 and #6601 shape) | fail G5 "awaiting Chris's recorded approval" |
| U23 | a `digikey/` path touched with no box ticked | fail G5 (path inference) |
| U24 | a `reviewed:owner` label is present and nothing else | the label is ignored; the result is the same as without it |
| U25 | the promotion head moves after a pass | the old status is not read for the new head; the gate re-runs |
| U26 | a verdict posted within 60 s of the push | fail G1.4 |
| U27 | an unreadable GitHub or Forgejo response | fail closed, with the reason in the description (max 139 chars) |

### 7.2 Replay tests on real history (read-only)

Build fixtures from the recorded GitHub data for #6543, #6567, #6635, #6616, #6627, #6642, #6603 and #6601, and assert that the gate **fails** each one for the expected rule (§5). Build fixtures from two clean recent promotions and assert that the gate passes them, or that it fails only on G5 or G2's Docker evidence, which did not exist at the time. Fixtures are frozen JSON in `tests/scripts/fixtures/promotion_gate/`. The tests never fetch live data.

### 7.3 Dry run before it can block

1. Run `promotion_gate.py --dry-run --pr N` against the first three `sctl promote` drafts. It posts nothing and prints the per-rule result.
2. Compare the results with QA's manual check of the same PRs. Any disagreement is a bug in the gate or in the spec. Fix it before step 3.
3. Post `promotion-gate` as a non-required context for one week. Track the rate of false reds. A false red on a batch that QA judged good must be zero before Chris is asked to make it required.

### 7.4 Regression guard

- The gate's own code (`scripts/local-ci/promotion_gate.py`, its tests and its fixtures) needs an independent verdict like any change. Plan P0-5 asks for this: gate code must not merge without an independent approve.
- `make test-unit` includes `tests/scripts/`, so local-ci's `scripts` pytest suite (branch `qa/local-ci-scoped-pytest`) runs the gate's tests on any change to the gate.

## 8. Open questions and dependencies

1. **The Human Gate approval mechanism** (G5). **This is for One. It blocks enabling G5 for real.**
2. `Source-Session` trailer: G1's same-platform independence needs a session id on every commit. W7 (Docs) owns the trailer spec, and this spec asks W7 to add `Source-Session:` alongside `Source-Platform:`.
3. Whether to push `refs/notes/verdicts` (§3.3).
4. The promotion identity (plan P0-2 and decision A): a GitHub App or bot account. Until it exists, "pushed by the promotion identity" in §6.1 cannot be checked.
5. W4 `stack-verify` must emit a run id, a head SHA and a result in a machine-readable form, so G2 can read them.
6. `sctl promote` must not squash or rebase (§3.1), and the promotion PR must merge with a merge commit.

## 9. Proposed defaults for the open questions

These are defaults so the gate and `sctl promote` can be built now. Each one stands until One or Chris overrides it.

1. **Human Gate approval (G5): pending Chris via One.** Proposed: Chris approves the batch head with his own Forgejo account, and `sctl promote` copies that approval into the manifest as an SSH-signed `Human-Gate-Approved: <head>` line checked against a key only Chris holds. Until Chris picks a mechanism, G5 keeps failing closed as §2 G5 says.
2. **`Source-Session` trailer.** Every commit carries `Source-Session: <platform>:<session id>` next to `Source-Platform:`, added by the harness, not typed by the agent. For G1, a same-platform verdict counts only when its reviewer session differs from every `Source-Session` in its `range`. A commit with no `Source-Session` can only be cleared by a reviewer on a different platform.
3. **git notes.** Push `refs/notes/verdicts` with every promotion, written only by the promotion identity. The manifest stays the primary copy. The gate reads the notes only when Forgejo is unreachable, and a notes copy whose digest differs from the manifest fails G1.
4. **Promotion identity.** A GitHub App (or bot account) that Chris creates himself; agents never create it or hold its credentials outside the promote job. Until it exists, the gate logs `promotion identity: unchecked` and stays report-only, and the push restriction on `develop` waits for it.
5. **Smoke result format.** W4 `stack-verify` writes a `stack-verify.json` artifact (`schema: digithings.stack-verify/v1`, `run_id`, `head`, `result: pass|fail`, per-suite pass/fail counts, image digests) and posts a `stack-verify` commit status on the head, with the run id in its description. G2 passes only when the JSON's `head` equals the commit and `result` is `pass`.
6. **Merge-commit-only promotions.** A promotion PR merges into `develop` with a merge commit only. The gate fails a promotion PR whose recorded merge method is squash or rebase, and `sctl promote` never squashes, rebases or cherry-picks (§3.1). Changing the repository's allowed merge methods stays Chris's call.
