# Frontier re-selection on a lump-aware criterion (Plan 16) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-select the v6 winner among the 144 frontier shapes (feasible + beating BOTH benchmarks) on a pre-registered lump-aware criterion, sens-check the selection, and judge it against the beat-both bar — on branch `task/4804-sdca-strategy-for-gold--gld`. No new search, no new votes, no threshold/mask/space changes.

**Standing facts:** v6-as-shipped NEGATIVE (mean flat +15.38 beats / lump −1.72 miss; sens UNSTABLE 2.75; mask-days 73/0/1, f1 zero-mask). Frontier-both 144/1080 in `gold_curve_search_v6.json`. Robustness tight (8 variants, none beats lump) — the winner's miss is systematic, but 144 shapes clear both, so selection (not the vote) is the suspect.

**Pre-registered selection (frozen here, BEFORE any per-shape read):**
- Eligible = feasible AND mean_flat > 0 AND mean_lump > 0 (the frontier as recorded — recompute, don't trust the count blindly).
- Select = argmax of min(mean_flat, mean_lump); tie-break 1: higher mean_lump; tie-break 2: lower mean abs drawdown (state if used).
- Bounded descent: sens-check #1; if sens fails (> 2.0), try #2, then #3; beyond #3 → NEGATIVE, stop (no endless walk down the ranking).
- Selection-bias disclosure (mandatory in every artifact): the selected shape is chosen ON the reported OOS metric — expect optimism. Independent checks are sens (fresh neighbors, not used in selection) + the pre-registered robustness neighborhood. f2-split consistency reported (f2 has 1 mask day — weak confirm, stated not hidden).

**Promotion bar (all must hold or NEGATIVE + shelve):** selected shape mean OOS beats flat AND lump; all folds feasible (inherited from frontier); sens maxΔ ≤ 2.0 on FRESH neighbors for the selected shape; holdout stays spent (ABSENT, stated).

## Global Constraints

- Research-only. No live-trading paths, no Supabase push, no merge/push (owner-side). No pandas, pydantic v2, ruff 100 on touched files. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.
- No new gate search, no vote/mask/space/objective/geometry changes, no re-freezing. The ONLY new compute allowed: sensitivity neighbors for the selected shape(s) (≤ 3 shapes) via the landed machinery, plus read-only selection over the recorded frontier.
- Frozen: criterion above (incl. tie-breaks and 3-attempt bound). Reading per-shape numbers then changing the criterion = plan violation, enforced by review.
- Standing owner rule: every iteration ships visuals — Task 3 regardless of outcome (page entry ONLY on BEATS-BOTH).

---

## Ruling 1 (Plan 16): persist-and-reselect re-run (issued after Task-1 STOP)

Task 1's STOP fired correctly: per-shape OOS was never persisted — the v6 record holds counts + winner-only means (`feasible_params` lived in-memory only, script:468/487/532), so the 144/1080 frontier is unrecountable and unselectable-from. No values invented.
Pivot (authorized here, same frozen everything): ONE re-run of the identical v6 gate with per-shape OOS persistence added to the record (gold-side record-keeping ONLY — vote, GRID space, bars, geometry, objective, mask, seed file all untouched). Reproduction is guaranteed by construction: the search enumerates `itertools.product` over GRID (script:373) — fully deterministic, no RNG. Precondition (binding): the re-run MUST reproduce the recorded v6 winner exactly (means +15.38/−1.72, same gated shape, same sens 2.75) — verified before any selection. Non-reproduction → STOP (nondeterminism found, no selection, report it). The re-run writes a NEW file (`gold_curve_search_v6b.json`); the original v6 record is read-only input (hash-unchanged proof required). Selection then proceeds per the frozen criterion on the v6b per-shape table; sens-check bound (≤3) unchanged.

### Task 1: Re-select + sens-check (bounded)

**Files:**
- Modify: gate script ONLY IF the sensitivity machinery cannot rescore an arbitrary recorded shape (read-first: how sens neighbors are built for the winner — reuse the seam with a shape override; minimal diff; if the seam needs engine changes → STOP with NEEDS_CONTEXT)
- Create (untracked): `digiquant/.scratch/gold_reselect_v6.json` (selected shape(s), criterion values, per-fold table, fresh sens, attempt log)
- Modify: NONE else (no seed/mask/builder/test changes unless the sens seam forces a test-only addition — then extend, don't create)

**Interfaces:**
- Consumes: `gold_curve_search_v6.json` frontier as recorded.
- Produces: selection + fresh sens (≤ 3 attempts). Task 2 judges.

- [ ] **Step 1: Read-first (frontier record layout + sens seam)**

Record with line evidence: (a) where per-shape OOS lives in the v6 record (recompute the 144 count independently — trust-nothing: quote the recomputation); (b) the sens-neighbor seam (can it score a non-winner shape? exact call + what it writes); (c) whether mask threading covers a rescored shape automatically (cite Task-2's choke-point site — if yes, no wiring work). STOP: per-shape OOS not recorded (NEEDS_CONTEXT with what's actually in the file — the plan then pivots, no invention); sens seam needs engine changes (NEEDS_CONTEXT).

- [ ] **Step 1b (per Ruling 1): persist-edit + identical re-run + reproduction check**

Add per-shape OOS persistence (params + mean_flat + mean_lump + feasible per shape for ALL evaluated shapes, or feasible ones at minimum — state which) to the gate record assembly ONLY (no scoring-path hunks; prove with `git diff` that evaluation code is untouched). Re-run the v6 gate byte-identical invocation + `--out gold_curve_search_v6b.json` (background, ~40s class; backup+sha256 discipline incl. v6-input-unchanged proof). Reproduction check FIRST: winner means/shape/sens equal the recorded v6 values (quote both sides) — mismatch → STOP, no selection. Then recount the frontier from the v6b table (trust-nothing; report both the old 144 claim and the recount).

- [ ] **Step 2: Select (read-only over v6b) + sens-check (≤ 3 attempts, background runs)**

Apply the frozen criterion verbatim, log the top-5 with criterion values (transparency: show what was NOT picked). Sens-check #1 via the seam (background); pass (≤ 2.0) → done; fail → #2, then #3; three fails → NEGATIVE, stop. Backup+sha256 discipline on every scratch file read or written (the v6 record is read-only input — verify its hash unchanged after, quote it). Record wall + exit per run.

- [ ] **Step 3: Lint + tests + commit (seam edit if any; outputs untracked)**

Relevant suites green + ruff clean, then commit the seam edit only (message per brief pattern). If no edit was needed, no commit — record that.

---

### Task 2: Verdict (no new runs)

**Files:** NONE (judgment only).

- [ ] **Step 1: Judge against the bar**

BEATS-BOTH requires: selected shape mean OOS vs flat > 0 AND vs lump > 0, feasible everywhere (inherited — verify, don't assume), fresh sens ≤ 2.0. Plus mandatory disclosures: selection-on-reported-metric optimism (one sentence, every artifact); f2-split consistency (report f2 flat/lump for the selection with the 1-mask-day weakness stated); f1 zero-mask caveat (selection barely sees the mask on f1 — the 73-day f0 + robustness carry the mask evidence, state that). Anything less = NEGATIVE naming the failed condition (sens failure after 3 attempts = NEGATIVE with the attempt log; frontier-exhaustion logic already ran).

---

### Task 3: Visuals + docs (every iteration ships visuals)

**Files:**
- Create (untracked): reselected-shape diagnostic tearsheet JSON (mirror v4/v5/v6 builders: buy vote + mask + frozen box + BOTH benchmarks + selection-criterion + optimism disclosure in notes) + public/ copy
- Modify: plot script (selected-shape overlay: equity vs lump + flat with the selection marked? stdlib SVG same pattern — read-first what exists, minimal addition) + public/ copy
- Modify: `page.tsx` TEMP entry (REVERT-BEFORE-MERGE pattern, uncommitted) ONLY on BEATS-BOTH; on NEGATIVE serve JSON + chart only (established rule)
- Modify: `digiquant/ARCHITECTURE.md` (append-only paragraph in SDCA section: criterion, selection, sens, verdict, disclosures)

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: served visuals + docs. Verify: JSON/chart (+page iff BEATS-BOTH) 200s, suite + ruff, status.

- [ ] **Step 1: Build + serve visuals**
- [ ] **Step 2: Docs + verify + commits (scripts + ARCH; outputs/preview state untracked-or-dirty)**

---

## Out of scope (not this plan — enforced by review)

- New searches, votes, masks, boxes, thresholds, spaces, objectives, geometries.
- Criterion changes after reading per-shape numbers (the core violation this plan guards).
- Attempts beyond #3; sens-neighborhood tuning to pass a failing shape.
- Nautilus enablement, broker paths, Supabase, nightly, credentials, merge, holdout.

## Self-review

1. Spec coverage: read-first + frozen-criterion selection + bounded sens (≤3) → Task 1 (STOPs for missing per-shape data / engine-needing seam; trust-nothing recount; backup discipline incl. input-hash-unchanged proof); verdict-only judging with mandatory disclosures → Task 2 (bar with NEGATIVE paths, optimism + f2 + f1 caveats all required sentences); visuals-every-iteration + docs → Task 3 (conditional page entry rule restated, serve proofs).
2. Placeholder scan: criterion formula, tie-breaks, 3-attempt bound, file paths, JSON names, sens 2.0 bar are literal. STOPs name trigger + action.
3. Type consistency: `gold_reselect_v6.json` naming distinct from `gold_curve_search_v6.json` everywhere; min(mean_flat, mean_lump) identical in plan header, implementation, notes, and ARCH.
