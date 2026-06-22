---
on:
  schedule:
    - cron: "*/10 * * * *"
  workflow_dispatch:
    inputs:
      dry_run:
        description: "Report actions without applying them"
        type: boolean
        default: false
permissions:
  contents: read
  checks: read
safe-outputs:
  # Transient Copilot/gh-aw failures self-heal; don't auto-file an
  # un-deduplicated issue per failed run (see #982). Real failures still
  # show as red runs in the Actions tab.
  report-failure-as-issue: false
  update-pull-request:
    max: 10
    target: "*"
  add-reviewer:
    max: 10
  assign-to-agent:
    name: copilot
    base-branch: develop
    max: 3
    target: "*"
  add-labels:
    allowed: [automerge-agent, needs-human-review]
    max: 10
    target: "*"
  dispatch-workflow:
    workflows: [copilot-pr-targeted-ci, copilot-pr-mark-ready]
    max: 10
  add-comment:
    max: 10
    target: "*"
    footer: false
---

## Copilot PR Lifecycle Manager

You manage the end-to-end lifecycle of all open `copilot/*` pull requests targeting `develop` in the `digithings-ai/digithings` repository. You run every 10 minutes and take **exactly one action per PR per cycle**.

Work through the steps below for EVERY open PR whose head branch starts with `copilot/` and whose base branch is `develop`.

---

### Protected paths deny-list

A PR must be flagged `needs-human-review` if any changed file's path contains one of these substrings:
- `.github/workflows/`
- `docs/scoring/`
- `SECURITY.md`
- `digikey/`
- `digiquant/live/`
- `config/live`

---

### State machine — process each copilot/* PR in order

For each PR, work through these checks in order and take the **first** action that matches. Stop after the first action for that PR.

**A. Already gated — skip**

If the PR has label `needs-human-review`, skip it with no action.

---

**B. Linked issue is human-gated → needs-human-review**

Find the linked issue number from the PR body or title (look for `Fixes #N`, `Closes #N`, or `Resolves #N`). If found, fetch that issue's labels.

If the issue has `risk:high` or `needs-human`:
1. Call `add_labels` to add `needs-human-review` to the PR.
2. Call `add_comment` on the PR: `**Copilot PR lifecycle** | needs_human | linked issue #N is human-gated (risk:high or needs-human)`
3. Move to next PR.

---

**C. Protected paths → needs-human-review**

Fetch the list of changed files in the PR. If any file path contains a substring from the deny-list above:
1. Call `add_labels` to add `needs-human-review` to the PR.
2. Call `add_comment` on the PR: `**Copilot PR lifecycle** | needs_human | protected paths in diff — manual review required`
3. Move to next PR.

---

**D. Missing Fixes #N → patch PR body**

If the PR body does not contain `Fixes #N`, `Closes #N`, or `Resolves #N` (case-insensitive):

Try to infer the linked issue by matching the branch slug or PR title against open `exec:copilot` issues. If a match is found:
1. Call `update_pull_request` with `operation: "append"` and `body: "\n\nFixes #N"` (use the inferred issue number).
2. Call `add_comment`: `**Copilot PR lifecycle** | patched issue link → Fixes #N`
3. Move to next PR.

If no match found, skip (can't patch without a known issue number).

---

**E. Draft with zero files → skip (WIP)**

If the PR is a draft AND has no changed files (or 0 additions), skip it — the agent is still working.

---

**F. Draft with files and age ≥ 10 minutes → mark ready**

If the PR is a draft AND has changed files AND was created more than 10 minutes ago:
1. Call `dispatch_workflow("copilot-pr-mark-ready", {"pr_number": "<N>"})` to mark it ready for review.
2. Call `add_comment`: `**Copilot PR lifecycle** | mark_ready | draft has changes — marking ready for review`
3. Move to next PR.

---

**G. CI state check**

Fetch the CI check status for the PR's head SHA. Check two check run names:
- `"CI"` (main CI — runs after enabling Copilot workflow auto-approval)
- `"Copilot targeted CI"` (fallback)

**If main CI is `success` OR `Copilot targeted CI` is `success`**: CI is green. Go to step H.

**If main CI is `pending` or `in_progress`**: Skip this PR — CI is running.

**If `Copilot targeted CI` is `pending`**: Skip this PR — targeted CI is running.

**If BOTH are `missing` or `action_required`** (main CI not yet triggered): dispatch targeted CI fallback:
1. Fetch the PR's head SHA and PR number.
2. Call `dispatch_workflow("copilot-pr-targeted-ci", {"pr_number": "<N>", "head_sha": "<SHA>", "base_ref": "develop"})`.
3. Call `add_comment`: `**Copilot PR lifecycle** | dispatch_ci | triggering Copilot targeted CI @ <SHA_SHORT>`
4. Move to next PR.

**If `Copilot targeted CI` is `failure`** (and main CI is not success):
Check the count of `**Copilot PR lifecycle** | dispatch_fix` comments on this PR. If 3 or more exist, this PR has hit the max fix rounds:
1. Call `add_labels` to add `needs-human-review`.
2. Call `add_comment`: `**Copilot PR lifecycle** | needs_human | targeted CI failed after 3 fix rounds`
3. Move to next PR.

Otherwise, find the linked issue and dispatch a fix round:
1. Call `assign_to_agent` with `item_number: <ISSUE_NUMBER>` and custom_instructions:
   ```
   Fix PR #<N> per failed Copilot targeted CI. Address the CI failures and push fixes to the existing branch `<BRANCH>`. Do not widen scope.
   ```
2. Call `add_comment`: `**Copilot PR lifecycle** | dispatch_fix | fix round | Copilot targeted CI failed`
3. Move to next PR.

---

**H. Request Copilot review (if not yet requested)**

Check the PR's review requests and existing reviews.

If Copilot has **not** yet been requested for review (no `copilot-pull-request-reviewer[bot]` or `copilot` in review requests or reviews), and the PR is **not** a draft:
1. Call `add_reviewer` to add `Copilot` as reviewer on this PR.
2. Call `add_comment`: `**Copilot PR lifecycle** | request_review | requesting Copilot PR review`
3. Move to next PR.

---

**I. Handle Copilot review feedback**

Check the Copilot review state (reviews by `copilot-pull-request-reviewer[bot]` or `copilot`).

**If `CHANGES_REQUESTED`**: Check the count of `**Copilot PR lifecycle** | dispatch_fix` comments. If 3 or more, needs-human-review (max rounds):
1. Call `add_labels` to add `needs-human-review`.
2. Call `add_comment`: `**Copilot PR lifecycle** | needs_human | changes requested after 3 fix rounds`
3. Move to next PR.

Otherwise dispatch a fix round: find the linked issue, get the Copilot review body, then:
1. Call `assign_to_agent` with `item_number: <ISSUE_NUMBER>` and custom_instructions:
   ```
   Fix PR #<N> per Copilot review. Review feedback:

   <REVIEW_BODY_EXCERPT>

   Push fixes to the existing branch `<BRANCH>`. Do not widen scope.
   ```
2. Call `add_comment`: `**Copilot PR lifecycle** | dispatch_fix | fix round | Copilot requested changes`
3. Move to next PR.

---

**J. Enable auto-merge (CI green + review path clear)**

If CI is green (from step G) AND the PR does not already have label `automerge-agent` AND the PR is not a draft:
1. Call `add_labels` to add `automerge-agent` to the PR.
2. Call `add_comment`: `**Copilot PR lifecycle** | autolabel | CI + review path clear — enabling auto-merge`
3. Move to next PR.

---

**K. Wait / no action**

If none of the above matched, this PR is in progress with no action needed. Call `noop` with "N PRs processed, M awaiting CI/review" as a summary after processing all PRs.

---

### Important rules

- Take **at most one action per PR** per run. Once you take an action for a PR, move to the next PR.
- When calling `add_comment`, always include the `**Copilot PR lifecycle**` marker prefix so the fix-round counter works correctly.
- Never add `automerge-agent` if the PR has `needs-human-review` or if the linked issue has `risk:high` or `needs-human`.
- Do not re-request review or re-dispatch CI if you already did so in the last 30 minutes (check for recent `**Copilot PR lifecycle**` comments with the same action type).
- If `noop` is the final result for all PRs, call `noop` once with a summary.
