# digifetch scoping close-out — Design Spec

> **For agentic workers:** this is a verification/close-out spec, not an
> implementation plan. It ships no feature code; the only code-tree change it
> authorizes is the stale-pointer fix in `digiquant/ARCHITECTURE.md` §11. The
> executable steps live in
> `docs/superpowers/plans/2026-09-16-digifetch-scoping-closeout.md`.

- **Date:** 2026-09-16
- **Status:** draft — verification complete in the worktree; ready to close
  #3927 once the pointer fix lands.
- **Issue:** [#3927](https://github.com/digithings-ai/digithings/issues/3927)
  (`agent-task`, `component:digiquant`, priority:low) — still `OPEN`, no
  close-out comment on record.
- **Primary deliverable:** [2026-09-12-digifetch-scoping-design.md](2026-09-12-digifetch-scoping-design.md)
  (merged via #4070, revised via #4074).
- **Verified against:** worktree checkout of `origin/develop` at `118966117`
  (2026-09-16). Every file:line below was read in that tree.

---

## 1. Goal and scope

**Goal.** Walk #3927's seven acceptance criteria against the current tree,
record per-criterion evidence, identify genuinely residual scope, and close the
issue with a findings comment that links the evidence and routes what is left.

**In scope**

- Per-criterion verdicts with exact file:line evidence (§6).
- The one stale pointer the close-out fixes (§6 AC7 → plan Task 2).
- Disposition of the issue's "dashboard-page evaluation" half (satisfied by the
  spec §8; the *build* it evaluates was never in this issue's scope).
- The close-out comment content and the close action (plan Task 3).

**Out of scope**

- Implementing anything: all seven criteria are documentation or already-shipped
  work.
- Re-validating the upstream API with new live probes (the 2026-09-15 probes
  recorded in the spec remain the evidence; #4101 owns post-deploy drift).
- The `bunx gloomberb api list --json` CLI diff: it needs a Bun machine and was
  deliberately deferred in the spec; it is recorded as a carried spike item, not
  silently dropped (§2.3).

---

## 2. Background (verified 2026-09-16)

#3927 asked for a scoping/design spec plus a README-level dashboard-page
evaluation. The spec shipped, and the follow-up implementation (#4069 → PR
#4085) plus the #4110 coverage expansion (PRs #4112/#4119/#4126/#4135) already
landed. The issue is the last open artifact of that chain.

### 2.1 Deliverables and follow-ups, as they actually stand

| Artifact | State | Evidence |
|---|---|---|
| Scoping spec (primary deliverable) | merged | `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md`; PRs #4070, #4074 |
| Follow-up implementation #4069 | shipped, issue closed COMPLETED | PR #4085 merged 2026-09-15 by `chrizefan` (human — the gate was honored) |
| Entitlement layer (#4110 phase 5) | shipped | PR #4135, `5d8bb6dbc` |
| Coverage expansion (#4110 phases 1-3) | shipped | #4112 `6e5459aaa`, #4119 `a15eb1f0a`, #4126 `e109891a4` |
| Post-deploy verification | open | [#4101](https://github.com/digithings-ai/digithings/issues/4101) |
| Cookie runbook | open | [#4099](https://github.com/digithings-ai/digithings/issues/4099) |
| Surface integration (deep links / attribution UI) | open | [#4098](https://github.com/digithings-ai/digithings/issues/4098) |

### 2.2 Criterion-by-criterion verdict (summary)

| AC | Verdict | Note |
|---|---|---|
| 1 — capability table vs real source/CLI | **Satisfied with a recorded deviation** | Source read + 8 live probes done; `bunx … api list --json` diff explicitly not run and recorded (§2.3) |
| 2 — Decision section with recommendation + trade-offs | **Satisfied** | `## Decision` recommends approach (c), rejects (a)/(b), documents (d) as fallback |
| 3 — `digifetch_*` surface with Pydantic v2 schemas + range caps | **Satisfied with a recorded deviation** | 13 tools (news added), superseding the 12-row grep; caps pinned by tests |
| 4 — iframe ruled out | **Satisfied** | Spec §8 rules it out for three named reasons |
| 5 — human gate stated for the follow-up | **Satisfied with a correction** | Actual new dep shipped as `api.gloom.sh` (not direct Yahoo/SEC); human merge on #4085 |
| 6 — MIT notice retention | **Satisfied; retention clause not triggered** | No vendored code (approach (c)); copyright recorded in spec §10 |
| 7 — ARCHITECTURE §11 pointer | **Satisfied, pointer stale in one phrase** | Bullet exists at `digiquant/ARCHITECTURE.md:1693`; `:1697` still says "on their task branches" |

### 2.3 The one carried item (AC1's CLI half)

`bunx gloomberb api list --json` was never run — Bun is absent from the
authoring/review and CI environments. The spec records this in three places:
Validation item 5 (`:91-93`), Risks (`:379`), Follow-up outline item 5
(`:395-398`); `digiquant/ARCHITECTURE.md:1697` repeats it in the #4069 open
items. The **substantive** AC1 requirement — read the real source directly and
call out discrepancies vs the issue's paraphrased summary — was done: source at
`gloomberb 0.13.3` plus 8 anonymous live probes, with seven recorded deltas
(spec `:71-102`). The CLI diff is a redundant cross-check, not the evidence of
record. **Disposition:** carried as an open spike item in-tree (already
documented); also reachable via #4101 if it ever becomes load-bearing. Not a
close-out blocker.

### 2.4 Dashboard-page evaluation (issue title's second half)

The issue's goal was to "separately evaluate (but not build) a same-origin
digiquant dashboard market-data page instead of iframing term.gloom.sh." The
spec did exactly that: §8 (`:323-341`) rules iframing out and evaluates the
same-origin page as the alternative, explicitly "not committed, not built here"
(`:337-341`). The *build* was never in #3927's scope; the product surface is
owned by #4098 and #4110's phase 4c. **Disposition: satisfied; no residual
under #3927.**

---

## 3. Approved architecture

Verification-only; there is no build architecture to approve. The close-out
protocol is:

1. **Verify** each AC with a command whose output is quoted in the close-out
   comment (plan Task 1).
2. **Fix the stale pointer** in `digiquant/ARCHITECTURE.md` §11 — the one
   defect the verification found (plan Task 2).
3. **Close** #3927 with a findings comment carrying the per-AC evidence table
   and the residual routing (plan Task 3).

No new code, no new dependency, no interface change — consistent with the
issue's own risk assessment ("low — this issue produces a design document
only").

---

## 4. Contracts (evidence contract)

Every verdict in §6 is backed by a **reproducible command** and a **file:line**
in the current tree. The close-out comment must not assert anything that is not
in the table below, and must state the two deviations (AC1 CLI half, AC3 tool
count) plus the AC5 correction explicitly rather than claiming a clean sweep.

Comment format (normative for the plan):

```text
<!-- in-session-review --> is NOT used here (that marker is for code review);
this is an issue close-out comment.

## Close-out — #3927 acceptance criteria, verified 2026-09-16 @ 118966117

| AC | Verdict | Evidence |
...one row per AC with file:line and the command run...

**Carried item:** bunx gloomberb api list --json diff — not run (no Bun);
recorded in spec §3 Validation item 5 / §12 item 5 and ARCHITECTURE §11.
**Residual scope:** dashboard-page build → #4098 (surface integration) /
#4110 phase 4c; iframe ruled out by spec §8; no action in #3927.
**Superseded details:** the issue predicted direct Yahoo/SEC calls; the
shipped dependency is api.gloom.sh (approach (c)), so the human gate applied
to #4085 (merged by a human, 2026-09-15).
```

---

## 5. Normative values (evidence thresholds)

| Check | Exact expectation | Source |
|---|---|---|
| Tool rows in the scoping spec | ≥13 (`grep -c "^\| \`digifetch_"`) | spec `:147-161`; the 12-row AC test is superseded by Validation item 3 (`:83-87`) |
| Decision recommendation | `grep -A 20 "^## Decision"` contains "recommended" and "chosen approach" | spec `:117-120` |
| iframe ruling | `grep -i "iframe"` contains "ruled out" + "not viable and not recommended" | spec `:323-325` |
| Human gate | `grep -i "human_gates\|human sign-off"` non-empty | spec `:343-355` |
| MIT / notice | `grep -i "MIT\|copyright notice\|attribution"` non-empty | spec `:357-367` |
| ARCH §11 pointer | `grep -A3 "digifetch" digiquant/ARCHITECTURE.md` shows the bullet | `:1693-1697` |
| Family tests | `pytest tests/dq/test_mcp_gloomberb_tools.py tests/dq/data/test_gloomberb_*.py -m unit -q` green | 5 test modules |

---

## 6. Coverage matrix (AC → evidence → disposition)

| AC | Evidence (current tree) | Disposition |
|---|---|---|
| **1** capability validation | Spec §3 `:47-67` (14-method table), §3.2 `:104-115` (8 live probes), Validation `:71-102` (7 deltas vs the issue's summary); validated against `gloom-sh/gloomberb 0.13.3` (`:11-12`). CLI diff absent (`:91-93`, `:395-398`; `ARCHITECTURE.md:1697`) | **Satisfied with recorded deviation**; CLI diff carried (not a blocker) |
| **2** Decision section | Spec `## Decision` `:117`; recommendation `:119-120`; trade-offs `:123-128` (a/b rejected, c chosen, d fallback); placement `:130-138` | **Satisfied** |
| **3** MCP surface + Pydantic v2 + caps | Spec §5.1 `:140-178` (13 tools, input/output models), §5.2 `:180-213` (caps + #4100 escape hatch), §5.3 `:215-267`; shipped implementation `models.py:244-265` (`RESOLUTION_MAX_RANGE`), tests `tests/dq/data/test_gloomberb_models.py` | **Satisfied with recorded deviation** (13 rows; news added per author decision `:14-19`) |
| **4** iframe ruled out | Spec §8 `:323-341`; three reasons at `:328-336`; alternative evaluated `:337-341` | **Satisfied**; no residual (build → #4098) |
| **5** human gate | Spec §9 `:343-355`; actual dependency `api.gloom.sh` shipped via PR #4085 (merged 2026-09-15 by `chrizefan`); Yahoo pre-existing via `yfinance` (`spec §6 :300`); SEC via `/cloud/sec/*` | **Satisfied with correction** (issue's Yahoo/SEC-direct prediction superseded by approach (c)) |
| **6** MIT / notice retention | Spec §10 `:357-367`; copyright `:39`, `:359`; no vendored gloomberb code in the tree (`grep -rn "Gloomberb Contributors"` matches only the spec); `docs/LICENSING.md` has no gloomberb row | **Satisfied**; retention clause not triggered (no vendoring) |
| **7** ARCH §11 pointer | `digiquant/ARCHITECTURE.md:1693` (heading), `:1695` (spec link), `:1697` (family/phase summary + open items) | **Satisfied; one stale phrase** — `:1697` says phases 1–3 "are on their task branches" though they merged (#4112/#4119/#4126). Fix in plan Task 2 |

---

## 7. Sequencing and phases

| Step | Deliverable | Plan task |
|---|---|---|
| 1 | Verification pass with recorded command outputs | Task 1 |
| 2 | `ARCHITECTURE.md:1697` stale-phrase fix (one line) + docs PR | Task 2 |
| 3 | Close #3927 with the findings comment (links the merged fix + evidence) | Task 3 |

No phases beyond this: the close-out is three steps. The full #4110 coverage
program continues separately (its own spec/plan pair, same date).

---

## 8. Verification (measurable)

```bash
# The seven AC checks, exact commands (all offline)
grep -c "^\| \`digifetch_" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md
grep -A 20 "^## Decision" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md \
  | grep -Ei "recommend|chosen approach"
grep -i "iframe" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md \
  | grep -Ei "rule.*out|not (viable|recommended)"
grep -i "human_gates\|human sign-off" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md
grep -i "MIT\|copyright notice\|attribution" docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md
grep -A3 "digifetch" digiquant/ARCHITECTURE.md | head -20
pytest tests/dq/test_mcp_gloomberb_tools.py tests/dq/data/test_gloomberb_client.py \
       tests/dq/data/test_gloomberb_models.py tests/dq/data/test_gloomberb_normalizers.py \
       tests/dq/data/test_gloomberb_agent_tools.py -m unit -q

# The stale-pointer fix
grep -n "are on their task branches" digiquant/ARCHITECTURE.md   # before: 1 match at :1697
grep -n "are on their task branches" digiquant/ARCHITECTURE.md   # after: no match

# The close itself
gh issue view 3927 -R digithings-ai/digithings --json state      # before: OPEN; after: CLOSED
gh issue view 3927 -R digithings-ai/digithings --json comments --jq '.comments[-1].body' | head -20
```

Expected: every grep matches; the pytest run is green; the phrase grep is empty
after Task 2; the issue state flips to `CLOSED` with the findings comment as the
latest comment.

---

## 9. Risks and fallbacks

| Risk | Mitigation |
|---|---|
| Closing #3927 is read as "the CLI diff was done" | The close-out comment states the carried item explicitly; the in-tree records (spec §12 item 5, `ARCHITECTURE.md:1697`) remain the tracker |
| The docs fix conflicts with the other #4110 spec/plan PR from the same day | Both touch different files; the pointer fix is a one-line edit to an isolated phrase — rebase if the §11 bullet moves |
| A reviewer argues AC3's 12-row grep is the literal test | Pre-empt in the comment: Validation item 3 records the 13-tool supersession (author decision, news as the 13th tool); the issue's own text allows recording deviations |
| The `dashboard-page evaluation` is argued to require a built page | Quote §8 `:337-341` ("not committed, not built here") and route the build to #4098 |
| Someone wants `docs/LICENSING.md` to list gloomberb | Not required (no vendored code, attribution is appreciated, not required); recorded as open question Q3, not a task |

---

## 10. Out of scope

- Any implementation change beyond the one-line `ARCHITECTURE.md` pointer fix.
- Post-deploy verification (#4101), the cookie runbook (#4099), and surface
  integration (#4098) — they have owners.
- Re-running the 2026-09-15 probes or the Bun CLI diff.
- Adding a licensing row for gloomberb (optional courtesy; see Q3).

---

## 11. Open questions

1. **Should the carried CLI-diff spike item be closed as "won't do"?** It has
   been unreachable since 2026-09-12 (no Bun in any environment) and the
   evidence of record does not depend on it. Recommendation: leave the in-tree
   notes, close #3927 as completed, and let #4101 decide if the diff ever
   becomes load-bearing.
2. **Is the ARCH §11 stale phrase the only pointer drift?** The verification
   found no other stale references (`grep -rn "3927"` shows the spec and
   `ARCHITECTURE.md` only).
3. **Add gloomberb to `docs/LICENSING.md`?** Not required — approach (c) ports
   no code; the spec §10 carries the MIT copyright. Default: no, unless the
   owner wants the data-source attribution recorded there too.
