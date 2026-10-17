# Honest re-measure (Plan 9: peak-floor predicate + neighbor key + three re-runs + decision) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the feasibility predicate to veto on peak-deployed (capital once at risk) instead of net-deployed (penalizes profit-taking), thread per-fold deployed figures + the worst sensitivity neighbor into the gate record, re-run the three best configurations through honest accounting, and render the binding ship-or-shelf decision — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Minimal thread-through across the existing layers. `SdcaTrialMetrics` gains REQUIRED `capital_deployed_peak_pct` (fail-closed: every hand-built constructor must state peak deliberately); both evaluators populate it from already-available report fields; `is_feasible` compares peak vs the unchanged floor value; `_sensitivity_of` tracks the argmax neighbor into a new defaulted `worst_neighbor_key`; the gold writer emits per-fold net/peak + gate-level neighbor key. Deliberately OUT (different predicates by design): `weight_search.py:131` inline IS floor, `CurveOptimizeGates`/`CurveTrialScore`, dd-cap value, sensitivity threshold/bump, test_walk_forward enforcement test (still passes — refit discipline untouched).

**Tech Stack:** Python, Pydantic v2, pytest (`-m unit`), ruff (line length 100). Three simulator gate re-runs (~40s class each).

**Spec:** Recon 2026-09-30 (same session, recorded as completed Task 0): `is_feasible` exact text (`walk_forward.py:287-293`, OOS-only, sole call sites `:263` + `:298` via `objective_score`); type fields (`SdcaOptimizeObjective:40-51`, `SdcaTrialMetrics:66-77` no peak, `FoldScore:94-102` nests metrics); report types carry both net+peak (`backtest.py:65-68,234-235`, `tearsheet_data.py:222-231`, `dca_metrics.py:151-152`) but `curve_sim.py:57-62` and `nautilus_evaluator.py:80-85` drop peak; `SensitivityReport` magnitude-only (`optimize.py:80-89`), argmax discarded at `:422` with key recoverable by one-key diff; sensitivity is winner-level mean-OOS (NO per-fold neighbor exists — gate-level key only, per-fold keys need a redesign, explicitly out); test pins list (`test_walk_forward.py:58-67,69-77,79-87,127-143`, `test_optimize.py:92-112,173`, `test_weight_search.py:89-94,133-138,154-199,179-184,214-219`, `test_two_stage.py:66-71,146-147`; `test_curve_optimize` separate system, untouched); gold writer (`run_gold_curve_search.py:263-271` per-fold, `:297-306` gate block, `:303-304` comment to UPDATE); production callers in radius (`optimize.py:373` BTC path via HTTP/MCP/CLI/LangGraph, `two_stage.py:88`, gold scripts) with the re-ranking consequence stated (infeasible excluded from the mean; all-infeasible → `-inf`).

## Global Constraints

- This plan CHANGES shared-engine behavior deliberately (the falsifiable bet). Blast radius is bounded by the recon list: predicate + peak field + neighbor key + writer keys + pin updates. Nothing else in the engine moves (no rails/fitter/shape/vote/threshold/cap changes).
- Pydantic strictness preserved: new metric field REQUIRED (stale constructors break loudly and get fixed deliberately — that is the mechanism, not collateral); new report field defaulted `None` (additive, back-compat).
- The binding stop rule (owner-agreed): after the three re-runs, apply the gate as-written. If none clears → gold goes diagnostic-only (tooling merges standalone, packet finalized NOT-YET). Task 4 computes this mechanically — no judgment, no new experiments, no fourth re-run.
- Research-only for gold artifacts: no `settings.json`, no `presets.json`, no `--push-supabase`, no workflow/manifest edits. The ENGINE changes (predicate/fields) are the deliberate exception — they ship as normal code with tests, reviewable for BTC independently.
- ruff line length 100 on touched files only. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.

---

### Task 1: Peak thread-through + predicate fix + pin updates

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/walk_forward.py` (metric field, `is_feasible`, docstrings)
- Modify: `digiquant/src/digiquant/strategies/sdca/curve_sim.py` (populate peak)
- Modify: `digiquant/src/digiquant/strategies/sdca/nautilus_evaluator.py` (populate peak — one mapping line)
- Modify: `tests/dq/strategies/sdca/test_walk_forward.py`, `test_optimize.py`, `test_weight_search.py`, `test_two_stage.py` (constructor + semantic updates per the pin list)
- Modify: NONE of `weight_search.py`, `curve_optimize.py`, `test_curve_optimize.py`, `test_backtest.py`, `test_dca_metrics.py`, enforcement test.

**Interfaces:**
- Consumes: recon field map.
- Produces: peak-based feasibility with updated pins. Tasks 3–4 consume the new semantics.

- [ ] **Step 1: Write the failing pin updates FIRST (TDD on the contract)**

In `test_walk_forward.py`: update the three pin tests to construct `SdcaTrialMetrics` WITH `capital_deployed_peak_pct` and assert the NEW semantics — floor test: net 5% + peak 40% → FEASIBLE now (the take-profit case; this is the behavior flip, assert it deliberately); add a new test `test_infeasible_when_peak_below_floor` (net 5%, peak 5% → infeasible); cap test: add peak 50% (unchanged verdict). Update the `:127-143` scaffold + every stub evaluator in `test_optimize.py:92-112`, `test_weight_search.py` stubs, `test_two_stage.py:66-71` to include peak values matching their intended feasibility (feasibility-true scaffolds get peak ≥ floor; the `:154-199` all-cash case gets peak 0.0 → still infeasible, meaning preserved — assert that explicitly). Do NOT touch `test_curve_optimize.py`, `test_backtest.py`, `test_dca_metrics.py`, or the enforcement test.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_walk_forward.py tests/dq/strategies/sdca/test_optimize.py tests/dq/strategies/sdca/test_weight_search.py tests/dq/strategies/sdca/test_two_stage.py -m unit -q`
Expected: FAIL — `TypeError` on missing required `capital_deployed_peak_pct` (proves fail-closed) plus the flipped floor assertion.

- [ ] **Step 3: Implement (three production edits, nothing else)**

1. `walk_forward.py:66-77`: add `capital_deployed_peak_pct: float` (REQUIRED, no default) with docstring "Peak net deployed over the window — the floor measures capital once at risk; net can go negative after take-profit sells."
2. `curve_sim.py:57-62`: add the peak mapping from `report.capital_deployed_peak_pct` (field verified present by recon — re-verify by reading before editing; STOP with NEEDS_CONTEXT if absent).
3. `nautilus_evaluator.py:80-85`: add the peak mapping from `dca.capital_deployed_peak_pct` (same re-verify rule).
4. `is_feasible` (`walk_forward.py:287-293`): compare `metrics.capital_deployed_peak_pct < objective.capital_deployed_floor_pct`; keep the dd clause byte-identical; update the docstring to state peak semantics + the take-profit rationale. Objective field names UNCHANGED (smallest diff).
5. Explicitly NOT touched (verify each with `git diff --stat` at the end): `weight_search.py:131`, `curve_optimize.py`, dd-cap, sensitivity, enforcement test, `test_curve_optimize.py`.

- [ ] **Step 4: Run to verify it passes**

Run: the Step-2 selection + `tests/dq/strategies/sdca/test_curve_optimize.py -m unit -q` (must pass UNMODIFIED — separate system).
Expected: all green.

- [ ] **Step 5: Lint + commit**

Ruff check + format-check all touched files.
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/walk_forward.py digiquant/src/digiquant/strategies/sdca/curve_sim.py digiquant/src/digiquant/strategies/sdca/nautilus_evaluator.py tests/dq/strategies/sdca/test_walk_forward.py tests/dq/strategies/sdca/test_optimize.py tests/dq/strategies/sdca/test_weight_search.py tests/dq/strategies/sdca/test_two_stage.py
git commit -m "Feasibility floor measures peak-deployed capital (#4804)"
```

(Commit body: one paragraph — net goes negative after take-profit sells so the floor vetoed profitable folds; peak records capital once at risk; BTC production path (`_run_sdca_optimize`) re-ranks accordingly by design.)

---

### Task 2: Worst-neighbor key + writer keys

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/optimize.py` (`_sensitivity_of` argmax tracking + `SensitivityReport.worst_neighbor_key`)
- Modify: `digiquant/scripts/run_gold_curve_search.py` (per-fold net/peak deployed + gate-level neighbor key; UPDATE the `:303-304` comment)
- Modify: `tests/dq/strategies/sdca/test_optimize.py` (neighbor-key assertion on the existing sensitivity test path — read it first; no new test file)

**Interfaces:**
- Consumes: Task-1 peak field (writer reads `fs.out_of_sample.capital_deployed_peak_pct`).
- Produces: gate records carrying deployed figures + neighbor attribution. Task 3 reads them.

- [ ] **Step 1: Implement the neighbor key (read `_sensitivity_of:394-429` first)**

Track the argmax over `deltas` inside the existing loop; derive the key by diffing `neighbors[i]` vs `best_params` (exactly one numeric key differs — assert that invariant in code with a clear error, do not silently pick first on multi-diff); format `"${key}:${sign}${frac_pct}"` (e.g. `buy_max_rate:+5%`, sign from neighbor-vs-best comparison). Add `worst_neighbor_key: str | None = None` to `SensitivityReport` (defaulted — back-compat for existing constructors; `None` when no neighbors evaluated). Do NOT restructure the loop, the skip logic, or the threshold math. Per-fold neighbor keys are explicitly OUT (mean-OOS design — record that boundary in the field docstring).

- [ ] **Step 2: Writer keys (gold script `:263-271` + `:297-306`)**

Per-fold dicts gain `oos_capital_deployed_pct` (net — available today) + `oos_capital_deployed_peak_pct` (Task-1 field); gate block gains `sensitivity_worst_neighbor_key` from `result.sensitivity.worst_neighbor_key`; UPDATE the `:303-304` comment (it now describes the landed attribution). Downstream safety: `build_gold_diagnostic_tearsheet.py:89-90,206` reads `gate[...]` keys — additive only, verify by reading those lines (no change expected; if the reader does strict key validation, STOP with NEEDS_CONTEXT).

- [ ] **Step 3: Test + lint + commit (two commits)**

Test: extend the existing sensitivity test in `test_optimize.py` (the `:173` neighbor_count one — read its fixture first) to assert `worst_neighbor_key` names the bumped param on a canned winner (if the fixture makes the key unpredictable, construct a minimal direct `_sensitivity_of` call with a 2-trial stub instead — concrete, offline). Run: the test + full `test_optimize.py` + `test_weight_search.py`.
Expected: green. Ruff on touched files.
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/optimize.py tests/dq/strategies/sdca/test_optimize.py
git commit -m "Attribute worst sensitivity neighbor (#4804)"
git add digiquant/scripts/run_gold_curve_search.py
git commit -m "Emit deployed figures + neighbor key in gold gate record (#4804)"
```

---

### Task 3: Three re-runs through honest accounting (no other deltas)

**Files:**
- Create (untracked): `digiquant/.scratch/gold_curve_search_honest_{v1,v3,B}.json` (+ stdout logs)

**Interfaces:**
- Consumes: Tasks 1–2 (new predicate + writer keys land before any run).
- Produces: three gate records, each comparable to its pre-fix namesake except feasibility/means/keys. NOTHING else differs per run.

- [ ] **Step 1: Re-run the exact three configurations (background, ~40s class each, sequential)**

Identical invocations to the original runs (same seeds, same rails args/defaults, same default objective — the PREDICATE changed underneath, that is the experiment):
- v1: `--seed-path gold_seed.json` (no rails flag, no objective flags) → `gold_curve_search_honest_v1.json`
- v3: `--seed-path gold_seed_v3.json` (no rails flag) → `gold_curve_search_honest_v3.json`
- B: `--seed-path gold_seed.json --rails-variant quad_5y` → `gold_curve_search_honest_B.json`

(copy-before-overwrite discipline per run; wall times + exit codes recorded; holdout-absence confirmed per file.) If any run's winner SHAPE differs from its pre-fix namesake, STOP with NEEDS_CONTEXT (shape comes from the untouched search phase — a difference means the predicate leaked into search, invalidating comparability).

- [ ] **Step 2: Record the three tables (no analysis beyond transcription)**

Report: per run, winner shape (must match namesake — assert it), per-fold OOS/net-deployed/peak-deployed/dd/feasible (NEW keys present), sensitivity (stable/maxΔ/neighbor key — FIRST EVER recorded neighbor identities), mean OOS + beats_flat. Transcription only; Task 4 decides.

- [ ] **Step 3: Report (no commit — outputs untracked)**

Report carries the three tables in full + the shape-identity assertions + wall times. Self-review + concerns.

---

### Task 4: Binding decision (mechanical, then done)

**Files:**
- Modify: `digiquant/.scratch/gold_promotion_packet.md` (untracked — append a "Plan 9 re-measure" section; do not rewrite history)
- Modify: NOTHING committed (if the packet appendix is the only output, no commit; ARCH gets no row — the predicate change is documented in code docstrings + commit bodies, and a follow-up may document it properly at merge time)

**Interfaces:**
- Consumes: Task-3 tables + the gate as-written (floor 10 peak-based / cap 50 / sens 2.0 / beats_flat / all folds feasible).
- Produces: the verdict. No judgment calls, no new runs, no fourth configuration.

- [ ] **Step 1: Apply the gate as-written to each re-run (mechanical checklist per run)**

For v1/v3/B: all folds feasible? mean OOS > 0? sensitivity stable (maxΔ ≤ 2.0)? List the exact failing clause per run (or "CLEARS" if none fails). This is arithmetic on the Task-3 tables, not analysis.

- [ ] **Step 2: Render the stop-rule verdict + packet appendix**

If ≥1 run CLEARS as-written → verdict PROMOTE-CANDIDATE (that run): packet appendix names it, lists remaining owner items (hy/ig depth, holdout validation, live staging, merge), and explicitly does NOT promote (no settings/push — owner PR follows). If NONE clears → verdict DIAGNOSTIC-ONLY: packet appendix records the final numbers, the tooling-merge list (snapshot store, depth verifier, rails params, UUP leg, honesty patterns — each independently shippable), and the BTC-loop return note (predicate + neighbor fixes port directly). Quote the verdict block VERBATIM in the report. Either way the plan ends here — a fifth re-run or a new variant inside this task fails review.

- [ ] **Step 3: Report (no commit)**

Report quotes the verdict block + the per-run checklists in full. The SDD ledger records plan completion with the verdict.

---

## Out of scope (not this plan — enforced by review, not goodwill)

- A fourth re-run or any new variant (weights/rails/shapes/bars/indicators) inside Task 4. The stop rule binds or it means nothing.
- `weight_search.py:131`, `CurveOptimizeGates`, dd-cap value, sensitivity threshold/bump, enforcement test, BTC-specific runs.
- Promotion action, nightly jobs, credentialed runs, live snapshots, per-fold neighbor redesign.

## Self-review

1. Spec coverage: predicate+peak+pins → Task 1 (fail-closed field, both evaluators, flipped-floor test deliberate, blast-radius exclusions enumerated); neighbor key + writer keys → Task 2 (argmax at the live site, one-key-diff invariant asserted, gate-level only with the per-fold boundary recorded, tearsheet-reader check); three identical re-runs → Task 3 (shape-identity tripwire, transcription-only); mechanical verdict → Task 4 (checklist arithmetic, quoted verdict, no fourth run). The stop rule has exactly one owner: Task 4's checklist.
2. Placeholder scan: signatures, formulas (`peak < floor`, key format), file paths, JSON names, invocation strings, pin line-refs are literal. STOPs (constructor mismatch, shape drift, strict-reader) name trigger + action. "Same invocations as original runs" is anchored to the three named seed/rails combos, not memory.
3. Type consistency: `capital_deployed_peak_pct` identical in type, both evaluators, pins, writer keys, JSON names; `worst_neighbor_key` identical in report type, writer, JSON; `gold_curve_search_honest_{v1,v3,B}.json` identical in tasks and triggers; `oos_capital_deployed_pct` (net) vs `oos_capital_deployed_peak_pct` (peak) never interchanged.
