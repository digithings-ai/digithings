# digifetch scoping close-out Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify #3927's seven acceptance criteria against the current tree, fix the one stale pointer the verification finds, and close the issue with a findings comment that links the evidence and routes residual scope.

**Architecture:** Verification-only: three steps — record per-AC evidence with reproducible commands, land a one-line `digiquant/ARCHITECTURE.md` §11 pointer fix, then close #3927 with the evidence table. No feature code, no new dependency, no interface change.

**Tech Stack:** `grep`/`gh`/`pytest` on the existing tree; markdown-only diff; no build or runtime change.

**Spec:** `docs/superpowers/specs/2026-09-16-digifetch-scoping-closeout-design.md` — the plan argues from the spec; executors read both.

## Global Constraints

- **Issue / branch discipline:** work on `task/3927-*`, cut with `make task ISSUE=3927` from a fresh `module/digiquant` (the script fetches `origin` and refuses a stale module base); PR base `module/digiquant`. The PR body carries `Closes #3927`. Docs-only diff — no human gate applies.
- **Evidence only:** every claim in the close-out comment must be a command output from Task 1 or a file:line in the spec's §6 table. Do not assert a clean sweep: the AC1 CLI-diff deviation and the AC3 13-vs-12 tool-count deviation must be stated.
- **The primary deliverable already shipped** (`docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`, PRs #4070/#4074); the follow-up shipped as #4069 → PR #4085 (merged by a human, 2026-09-15). Do not re-litigate the design.
- **Residual routing (fixed):** the dashboard-page *build* → #4098 / #4110 phase 4c (the iframe *evaluation* is satisfied by spec §8); post-deploy verification → #4101; cookie runbook → #4099; the `bunx gloomberb api list --json` diff stays a documented carried item (no Bun in any environment).
- **No new external dependency, no code change beyond the one-line docs fix.** If verification surfaces something bigger, stop and report to #4110 rather than expanding this plan.
- **Cross-references:** #4069/#4085 (implementation origin), #4110 (coverage expansion; its spec/plan pair is `docs/superpowers/{specs,plans}/2026-09-16-digifetch-coverage-expansion*`), #4098, #4099, #4101.
- **Naming:** lowercase `digi*` in prose, commits, and PR text; the upstream project is `gloomberb` (lowercase in this repo's prose).
- **Review + merge:** a docs-only one-liner still needs the repo's merge hygiene — CI green, review coverage on the record per `docs/agents/CODE_REVIEW_POLICY.md` (a trivial docs diff clears via `/review` or `reviewed:owner`), then merge into `module/digiquant`.

---

### Task 1: Verification pass (no tree changes)

**Files:**
- Create: none (evidence is captured in the terminal / the PR body)
- Test: the shipped Gloomberb test modules (read-only run)

**Interfaces:**
- Consumes: `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`, `digiquant/ARCHITECTURE.md`, the shipped `digiquant/src/digiquant/data/gloomberb/` modules and their tests.
- Produces: the quoted outputs Task 3's close-out comment needs, including the expected single hit for the stale phrase.

- [ ] **Step 1: Cut the branch**

Run:
```bash
make task ISSUE=3927
```
Expected: a worktree on `task/3927-<slug>` from `refs/remotes/origin/module/digiquant`; the script prints the base and refuses if the module branch is behind `origin/develop`.

- [ ] **Step 2: Run the seven AC commands and capture the outputs**

Run (each line prints the evidence the comment quotes):
```bash
grep -c "^\| \`digifetch_" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md
grep -A 20 "^## Decision" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md \
  | grep -Ei "recommend|chosen approach"
grep -i "iframe" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md \
  | grep -Ei "rule.*out|not (viable|recommended)"
grep -i "human_gates\|human sign-off" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md
grep -i "MIT\|copyright notice\|attribution" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md
grep -A3 "digifetch" digiquant/ARCHITECTURE.md | head -20
grep -n "are on their task branches" digiquant/ARCHITECTURE.md
```
Expected:
- tool rows: a number ≥ 13;
- Decision: `**Recommended approach: (c)**` and `"Chosen approach" is (c)`;
- iframe: the line containing `It is not viable and not recommended` (spec §8 first line);
- human gate: `human_gates` line(s) from spec §9;
- MIT: the copyright/`MIT` lines from spec §10;
- ARCH pointer: `### Gloomberb Market-Data Integration (#3927, implemented in #4069; coverage expanded in #4110)` and the spec link;
- stale phrase: exactly one hit, `digiquant/ARCHITECTURE.md:1697` — `are on their task branches`. Record the line number.

- [ ] **Step 3: Run the shipped family tests**

Run:
```bash
pytest tests/dq/test_mcp_gloomberb_tools.py tests/dq/data/test_gloomberb_client.py \
       tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py \
       tests/dq/data/test_gloomberb_agent_tools.py -m unit -q
```
Expected: PASS (offline; no stack, no live API).

- [ ] **Step 4: Capture the issue state and the human-merge evidence**

Run:
```bash
gh issue view 3927 -R digithings-ai/digithings --json state,title
gh pr view 4085 -R digithings-ai/digithings --json state,mergedBy,mergedAt
```
Expected: issue `OPEN`; PR #4085 `MERGED`, `mergedBy` a human account (evidence the §9 human gate was honored).

- [ ] **Step 5: Record the verdicts**

Write the outputs into the Task 3 comment body template (below); no commit in this task — the verification is a prerequisite, not a deliverable.

---

### Task 2: Fix the stale ARCHITECTURE §11 pointer

**Files:**
- Modify: `digiquant/ARCHITECTURE.md:1697` (one sentence)

**Interfaces:**
- Consumes: the Task 1 Step 2 stale-phrase hit.
- Produces: a tree where `grep -n "are on their task branches" digiquant/ARCHITECTURE.md` returns nothing; the PR that Task 3's comment links.

- [ ] **Step 1: Confirm the exact stale sentence**

Run: `sed -n '1697p' digiquant/ARCHITECTURE.md`
Expected (current text, wrapped in the real file): `… #4110 phases 1–3 (macro/credit/search/transcript; statements/tweets/venues/screener/13F; valuation/executives/risk/filing-events/short-interest/equity-diagnostic) are on their task branches, and the remaining surface (plugin-only panes, digiquant surface integration) stays open in that issue. …`

- [ ] **Step 2: Apply the one-line edit**

In `digiquant/ARCHITECTURE.md:1697`, replace:

```text
#4110 phases 1–3 (macro/credit/search/transcript; statements/tweets/venues/screener/13F; valuation/executives/risk/filing-events/short-interest/equity-diagnostic) are on their task branches, and the remaining surface (plugin-only panes, digiquant surface integration) stays open in that issue.
```

with:

```text
#4110 phases 1–3 (macro/credit/search/transcript; statements/tweets/venues/screener/13F; valuation/executives/risk/filing-events/short-interest/equity-diagnostic) merged via #4112/#4119/#4126 (entitlement layer #4135), and the remaining surface (plugin-only panes, digiquant surface integration) stays open in that issue.
```

- [ ] **Step 3: Verify the fix and the docs gate**

Run:
```bash
grep -n "are on their task branches" digiquant/ARCHITECTURE.md   # expect: no output
grep -n "merged via #4112/#4119/#4126" digiquant/ARCHITECTURE.md  # expect: one hit at :1697
make doc-check
```
Expected: the stale phrase is gone; the new phrase is present; `make doc-check` passes.

- [ ] **Step 4: Commit, push, open the PR**

```bash
git add digiquant/ARCHITECTURE.md
git commit -m "docs(digiquant): correct gloomberb phase status in ARCHITECTURE §11 (#3927)"
git push -u origin "$(git branch --show-current)"
gh pr create --base module/digiquant \
  --title "docs(digiquant): correct gloomberb phase status in ARCHITECTURE §11 (#3927)" \
  --body "$(cat <<'EOF'
Closes #3927.

Close-out of the digifetch scoping issue: the scoping spec
(docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md) and the
follow-up implementation (#4069 → #4085) shipped; verification of the seven
acceptance criteria is recorded in
docs/superpowers/specs/2026-09-16-digifetch-scoping-closeout-design.md.

This PR carries the only defect the verification found: ARCHITECTURE §11 still
described the #4110 phases as "on their task branches" after they merged.

Advances #4110 (phase 4a spec/plan pair landed separately); the issue itself
stays open for phases 4b/4c.
EOF
)"
```

- [ ] **Step 5: Merge when ready**

Wait for required CI; review coverage for a docs-only one-liner clears via `/review` or `reviewed:owner` per `docs/agents/CODE_REVIEW_POLICY.md`; then `gh pr merge <PR>` into `module/digiquant`.

---

### Task 3: Close #3927 with the findings comment

**Files:**
- None (GitHub only)

**Interfaces:**
- Consumes: Task 1 outputs; the merged Task 2 PR number.
- Produces: #3927 `CLOSED` with the evidence comment as its last comment.

- [ ] **Step 1: Confirm the docs fix merged**

Run:
```bash
gh pr view <PR> -R digithings-ai/digithings --json state,mergedAt
git fetch origin && git show origin/module/digiquant:digiquant/ARCHITECTURE.md | grep -c "are on their task branches"
```
Expected: PR `MERGED`; the grep count is `0` on the updated module branch.

- [ ] **Step 2: Close with the findings comment**

Run (replace `<PR>` with the merged PR number; the comment body is normative):

```bash
gh issue close 3927 -R digithings-ai/digithings --reason completed --comment "$(cat <<'EOF'
## Close-out — #3927 acceptance criteria, verified 2026-09-16 @ `118966117`

All seven criteria verified against the current tree; two carry recorded
deviations, none blocks the close. Verification spec:
`docs/superpowers/specs/2026-09-16-digifetch-scoping-closeout-design.md`.

| AC | Verdict | Evidence |
|---|---|---|
| 1 — capability table vs real source/CLI | Satisfied with a recorded deviation | Spec §3 (14-method table) + §3.2 (8 live probes, 2026-09-15) + Validation items 1-7; validated against `gloom-sh/gloomberb 0.13.3`. `bunx gloomberb api list --json` was **not run** — recorded in spec §3 Validation item 5, §11, §12 item 5 and `ARCHITECTURE.md` §11 open items (no Bun in any environment) |
| 2 — Decision with recommendation and trade-offs | Satisfied | Spec `## Decision`: recommends approach (c) (Python HTTP client over `api.gloom.sh` + digifetch), rejects (a) CLI shell-out and (b) vendoring with explicit trade-offs, documents (d) as fallback |
| 3 — `digifetch_*` surface + Pydantic v2 + caps | Satisfied with a recorded deviation | Spec §5.1/§5.2/§5.3: **13** tools (news added by author decision 2026-09-15), superseding the issue's 12-row grep (Validation item 3). Shipped and pinned by `tests/dq/data/test_gloomberb_models.py` (`RESOLUTION_MAX_RANGE` caps, reject-never-clamp) |
| 4 — iframe ruled out | Satisfied | Spec §8: iframe is "not viable and not recommended" for three named reasons (egress proxy at investigation time, human gate, cross-origin DOM blindness); same-origin page evaluated but not committed |
| 5 — human gate stated | Satisfied with a correction | Spec §9 states the new-dependency gate. The shipped dependency is `api.gloom.sh` (approach (c)) — not direct Yahoo/SEC as the issue predicted (Yahoo was pre-existing via `yfinance`; SEC goes through `/cloud/sec/*`). The gate was honored: PR #4085 merged by a human on 2026-09-15 |
| 6 — MIT notice retention | Satisfied; retention clause not triggered | Spec §10 records MIT / `Copyright (c) 2026 Gloomberb Contributors`; approach (c) vendors no code, so no file notice is required (`grep -rn "Gloomberb Contributors"` matches the spec only) |
| 7 — ARCHITECTURE §11 pointer | Satisfied; stale phrase fixed | Bullet at `digiquant/ARCHITECTURE.md:1693` with the spec link; the "on their task branches" phrase was corrected to "merged via #4112/#4119/#4126 (entitlement layer #4135)" in #<PR> |

**Residual scope routing**

- Dashboard-page evaluation: satisfied by spec §8 (evaluation only — the page was explicitly not built). The build belongs to #4098 (surface integration) / #4110 phase 4c.
- Post-deploy verification of the family: #4101. Cookie runbook: #4099. Coverage expansion phases 4b/4c: #4110.
- Carried item: the Bun CLI diff stays documented in-tree (spec §12 item 5, `ARCHITECTURE.md` §11) and is reachable via #4101 if it ever becomes load-bearing.
EOF
)"
```

Expected: issue closed as completed; the comment appears as the latest comment.

- [ ] **Step 3: Verify the close**

Run:
```bash
gh issue view 3927 -R digithings-ai/digithings --json state,stateReason
gh issue view 3927 -R digithings-ai/digithings --json comments --jq '.comments[-1].body' | head -5
```
Expected: `{"state":"CLOSED","stateReason":"COMPLETED"}`; the last comment begins `## Close-out — #3927 acceptance criteria`.

- [ ] **Step 4: Report**

Post a one-line back-reference on #4110 (optional but useful for the chain):
```bash
gh issue comment 4110 -R digithings-ai/digithings \
  --body "Scoping close-out (#3927) complete: verification of the seven acceptance criteria and the residual routing are recorded there; the phase 4a spec/plan pair for this issue is \`docs/superpowers/{specs,plans}/2026-09-16-digifetch-coverage-expansion*\`."
```

---

## Self-Review

**1. Spec coverage.** Spec §6's AC→evidence→disposition table → Task 1 Steps 2-4 (commands) and Task 3 (comment). Spec §6 AC7 "stale phrase" → Task 2. Spec §7 sequence (verify → fix → close) → the three tasks in order. Spec §8 verification → Task 2 Step 3 and Task 3 Steps 1/3. Spec §9 risks (carried item stated, dashboard routing, licensing) → the Global Constraints and the comment's "Residual scope routing" + AC1/AC6 rows. Spec §10 out-of-scope → no task re-runs probes or adds a licensing row.

**2. Placeholder scan.** `<PR>` is the only bracketed token and is explicitly defined as "the merged PR number" in both places it appears; every command has an expected output; the comment body is complete prose.

**3. Type consistency.** The comment's AC numbering, verdicts, and file:line references match the spec §6 table exactly (AC1 deviation, AC3 13-tool deviation, AC5 correction, AC6 not-triggered, AC7 fix). The Task 2 edit's old/new strings are the same sentence; the grep checks in Task 2 Step 3 and Task 3 Step 1 assert the same replacement. The PR body's `Closes #3927` matches Task 3's close action.
