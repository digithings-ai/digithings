# v3 promotion evidence + artifacts (Plan 10) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score the v3 winner on the pristine holdout, prepare the promotion artifacts (settings entry, preset, provenance sidecar, test pins) on the branch, and write the live-path work order for the BTC-hardcoded nightly path — stopping before push, merge, or nightly edits — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Holdout via the existing compliant path (`_holdout_metrics` semantics: rails fit on the pre-holdout 4400-bar span, score the 2022-05-12..2026-09-29 tail; or a `run_sdca_walk_forward` call whose `holdout_metrics` comes back populated — read both call sites first, use whichever is cleaner, record the choice). Artifacts mirror the btc_optimized precedent exactly (settings shape, preset entry with override-record description, `SdcaOptimizeProvenance` sidecar). The live path (`generate_tearsheets.py` SDCA branch) is NOT touched in this plan — its generalization is a written work order, because it changes BTC live behavior and needs owner scoping.

**Tech Stack:** Python, pytest (`-m unit`), ruff (line length 100). One simulator holdout run.

**Spec:** Recon 2026-10-01 (same session, recorded as completed Task 0): fold geometry recomputed (holdout idx 4400..5498 = 2022-05-12..2026-09-29); `_holdout_metrics` (`optimize.py:467-485`) + `run_sdca_walk_forward` (`:328-399`, `holdout_metrics` → `persist_btc_optimized` `:488-533` serializes `holdout_vs_flat_dca_pct`); v3 winner (shape 35/45/50/30/1.0/2.0, mids null after projection; weights valuation 1.0/m2 0.5/uup 0.5; evaluator `evaluate_sdca_trial_curve_sim` — same evaluator or incomparable); settings entry schema (`settings.json:34-55`); preset schema (`presets.py:54-62`, hand-promoted entries carry mid keys + override descriptions); provenance schema (`optimize.py:121-140`, keys incl. `holdout_vs_flat_dca_pct|null`, `beats_flat_dca_oos`, `rails_protocol`, `notes` with SUPERSEDED pattern); NO gold coefficients file needed (runtime fit; live branch hardcodes BTC rails — part of the work order); test pins (`test_presets.py:9-15,231-270`, `test_optimize.py:196-232`, `test_asset_profile.py:110-113`, `test_tearsheet_charts.py:114-355`, `test_export_sdca_macro.py:103-119`); nightly gap (no GLD fetcher — `fetch_coinbase.py:28-30` BTC/ETH/SOL only; UUP not in SERIES_FILES and sourceless; SDCA branch hardcodes BTC weights `:793-801`, drop-guard `:814-818`, `BtcPowerLawRiskModel` `:161-168,834`, provenance `:855-859`); hy/ig residual: v3 votes neither — BAML depth does NOT gate v3.

## Global Constraints

- Research-only except the artifact files (settings/presets/sidecar/tests), which are prepared ON THE BRANCH and never pushed, merged, or `--push-supabase`d in this plan. Promotion takes effect only via a later owner-merged PR + operator push.
- Holdout scored EXACTLY once in this plan (the reserve is then spent — state that in the output; no second holdout run for any reason within this plan).
- No live-path edits (`generate_tearsheets.py`, workflows, fetchers, export SERIES_FILES for UUP, manifest). The work order is a document, not code.
- Rails fit for holdout uses the pre-holdout span ONLY (2004-11-18..2022-05-11); holdout dates never enter the fitter (#3173 extends naturally — the enforcement test's spirit; state compliance explicitly).
- ruff line length 100 on touched files only. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push. Never open a PR (owner decides timing with the merge strategy).

---

### Task 1: Holdout validation run (v3 winner, scored once)

**Files:**
- Create: `digiquant/scripts/run_gold_holdout_validation.py`
- Create (untracked): `digiquant/.scratch/gold_holdout_v3.json` (+ stdout log)

**Interfaces:**
- Consumes: v3 winner shape + weights (read from `gold_curve_search_honest_v3.json` — never re-derive); seed calendar (v3 seed file); `_holdout_metrics` or `run_sdca_walk_forward` (read both call sites first, use the cleaner vehicle, record the choice); `gold_generic_rails_fitter` (import from the gate script iff side-effect-free, else define locally with identical body + record).
- Produces: one holdout record. No gate rerun, no shape/weight changes.

- [ ] **Step 1: Write the script**

Create `digiquant/scripts/run_gold_holdout_validation.py`: load v3 seed dates/prices + winner shape/weights from the honest-v3 JSON; recompute folds via `make_walk_forward_folds` (same args as the gate) and ASSERT holdout == (2022-05-12, 2026-09-29) (mismatch → SystemExit with both geometries, do not proceed); fit rails on the pre-holdout span (dates[0]..folds[-1].oos_end — assert equals 2004-11-18..2022-05-11); build full-calendar causal extra_z for the v3 weights via the established pattern; evaluate `evaluate_sdca_trial_curve_sim` on the holdout slice; assess feasibility with default `SdcaOptimizeObjective()` (floor 10 peak-based — state which predicate version applies); write `.scratch/gold_holdout_v3.json` with `{weights, shape, rails_fit_window, holdout_window, metrics{vs_flat_dca_pct, vs_lump_pct, capital_deployed_pct, capital_deployed_peak_pct, max_drawdown_pct}, feasible, holdout_scored_once: true}`. Docstring: this spends the reserve — no second holdout run in this plan for any reason.

- [ ] **Step 2: Run it (once)**

Run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_holdout_validation.py`
Expected: exit 0; JSON with the holdout metrics; stdout echoed. Record wall time. Any SystemExit stops the plan — investigate, do not adjust windows.

- [ ] **Step 3: Lint + commit the script (output untracked)**

Ruff check + format-check.
Expected: clean.

```bash
git add digiquant/scripts/run_gold_holdout_validation.py
git commit -m "Add gold v3 holdout validation script (#4804)"
```

---

### Task 2: Promotion artifacts (branch-only, no push/merge)

**Files:**
- Modify: `digiquant/src/digiquant/strategies/settings.json` (new `gold_sdca` entry)
- Modify: `digiquant/src/digiquant/strategies/sdca/presets.json` (new `gold_optimized` entry)
- Create: `digiquant/src/digiquant/strategies/sdca/gold_optimized_provenance.json` (per `SdcaOptimizeProvenance`)
- Modify: `tests/dq/strategies/sdca/test_presets.py` (EXPECTED set + gold shape/description/provenance pins mirroring the btc_optimized tests)
- Modify: `tests/dq/strategies/sdca/test_asset_profile.py` (gold settings-shape pin ONLY if the file's pattern extends cleanly — read first; else skip with a note)

**Interfaces:**
- Consumes: v3 winner record + Task-1 holdout number + packet override record.
- Produces: merge-ready artifacts. Nothing takes effect without a later merge + push (state that in each commit body).

- [ ] **Step 1: Write the failing pin updates FIRST**

In `test_presets.py`: extend `EXPECTED_PRESET_NAMES` with `gold_optimized`; add `test_gold_optimized_shape_is_v3_candidate` (shape == the gated v3 shape incl. null mids), `test_gold_optimized_description_records_gate_outcome` (description contains the v3 numbers + sensitivity-stable + the honest re-measure pointer), `test_gold_optimized_provenance_*` (notes contain the override/floor-peak record + holdout number). Mirror the btc_optimized tests' structure (read `:231-270` first).

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_presets.py -m unit -q`
Expected: FAIL (missing preset/provenance keys).

- [ ] **Step 3: Implement the three artifacts**

1. `presets.json`: `gold_optimized` with `description` (v3 gate numbers + sensitivity-stable-0.45 + peak-floor re-measure pointer + "Promoted to candidate on owner accept <date TBD — DO NOT PUSH from agent env>" style per BTC precedent + holdout number), `long_only: false` (match v3 long/short behavior — verify from the gate evaluator path, don't assume; if v3 ran long-only, match that instead and say so), `shape` = the gated v3 shape EXACTLY (mids null).
2. `gold_optimized_provenance.json` per `SdcaOptimizeProvenance`: preset `gold_optimized`, evaluator `curve_simulator`, objective floor 10/cap 50, fit_window folds[0].is_start..folds[-1].oos_end, folds list, holdout dates, best_params (shape keys + weight keys), means, `holdout_vs_flat_dca_pct` = Task-1 number, beats_flat true, sensitivity_stable true + neighbor key, `rails_protocol` = the `RAILS_PROTOCOL` text (import the constant — don't retype), notes (override record: floor now peak-based per Plan 9 + holdout pointer + hy/ig-at-zero + BAML depth outstanding).
3. `settings.json`: `gold_sdca` entry mirroring `btc_sdca` shape — symbol `GLD-USD`, ccxt_symbol `"GLD/USD"` (verify this is the CCXT form the codebase would expect — grep ccxt_symbol usage; if uncertain, STOP with NEEDS_CONTEXT rather than inventing), label, kind `dca`, `strategy_type: sdca`, `sdca: {preset: gold_optimized, risk_model: generic_valuation, long_only: <as verified>, initial_cash: 1000.0, indicator_weights: {full 16-key vector from the v3 JSON weights}}`.

- [ ] **Step 4: Run to verify it passes + check nothing else reads settings unexpectedly**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_presets.py tests/dq/strategies/sdca/test_asset_profile.py tests/dq/test_export_sdca_macro.py -m unit -q`
Expected: PASS. Plus: grep for settings["strategies"] iteration sites that might break on a new entry (generate_tearsheets SDCA branch handles unknown sdca entries how? — read the branch dispatch: if it KeyErrors on unknown risk_model/weights, record it as a known merge-time behavior, do NOT fix the live path here).

- [ ] **Step 5: Lint + commit (artifacts + tests)**

Ruff check + format-check touched files (JSON validated by the test suite itself).
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/settings.json digiquant/src/digiquant/strategies/sdca/presets.json digiquant/src/digiquant/strategies/sdca/gold_optimized_provenance.json tests/dq/strategies/sdca/test_presets.py tests/dq/strategies/sdca/test_asset_profile.py
git commit -m "Add gold v3 promotion artifacts, unmerged (#4804)"
```

(Commit body: takes effect only via owner-merged PR + operator push; nightly/live path NOT yet generalized — see the Plan 10 work order.)

---

### Task 3: Live-path work order + verify + evidence log

**Files:**
- Create: `docs/superpowers/plans/2026-10-0X-gold-live-path.md` — NO. Work orders live with the evidence: create (untracked) `digiquant/.scratch/gold_live_path_workorder.md` (the follow-up plan gets written when it's scheduled, not now).
- Modify: `digiquant/ARCHITECTURE.md` — NO (promotion unmerged; docs change at merge time. Skip entirely.)
- Verify: suite + ruff + status.

**Interfaces:**
- Consumes: recon §4 gap + Tasks 1–2.
- Produces: work order + evidence log.

- [ ] **Step 1: Write the live-path work order (untracked note, decisions flagged not made)**

`gold_live_path_workorder.md` sections: (1) problem (SDCA branch BTC-hardcoded — the 4 sites with file:line from recon); (2) decisions NEEDED (GLD price source for nightly: R2 sealed `market-data/price/GLD` generations vs extending `fetch_coinbase` vs Yahoo — options with trade-offs, NO recommendation beyond stating them; UUP staging source: manifest can't carry price files — where do price CSVs come from at nightly runtime today? name the gap; weights passthrough design: iterate entry's `indicator_weights` vs hardcoded list; `risk_model` dispatch via `resolve_sdca_risk_model` vs hardcoded `BtcPowerLawRiskModel`); (3) acceptance (gold tearsheet generates from nightly-staged files with uup leg live + drop-guard over all nonzero weights + provenance naming the preset); (4) explicit non-goals (no backfill redesign, no new indicators, no bar changes). Each decision section ends with an open question, not an answer).

- [ ] **Step 2: Full verification**

```bash
.venv/bin/python -m pytest tests/dq/strategies/sdca/test_presets.py tests/dq/strategies/sdca/test_asset_profile.py tests/dq/strategies/sdca/test_walk_forward.py tests/dq/strategies/sdca/test_optimize.py -m unit -q
ruff check digiquant/scripts/run_gold_holdout_validation.py
ruff format --check digiquant/scripts/run_gold_holdout_validation.py
git status --short
```

Expected: green (stash-prove any failure); status shows plan commits + `??` staging/outputs only; settings/presets/provenance modifications are TRACKED commits (intended — branch-only), no push.

- [ ] **Step 3: Report with evidence log (no commit — Task-2 commit was the last)**

Final section: plan commits, holdout number + feasibility, artifact inventory, work-order path, residual owner items (hy/ig depth, live staging + push, merge strategy, BTC return), the stop-rule lineage (Plan 9 verdict → this plan's evidence).

---

## Out of scope (not this plan — enforced by review)

- `--push-supabase`, PR opening, merge, nightly/workflow/fetcher/export/manifest edits, live-path code changes.
- Second holdout run for any reason (reserve spent in Task 1 — a rerun fails review).
- Coefficients file (not needed — runtime fit per recon).
- New votes/rails/shapes/bars/indicators; credentialed runs.

## Self-review

1. Spec coverage: holdout scored once compliantly → Task 1 (asserted windows, pre-holdout fit, same evaluator, feasibility with current predicate); artifacts + pins → Task 2 (failing pins first, BTC-precedent shapes, ccxt/STOP branch, live-branch read check); work order + verify → Task 3 (decisions flagged, not made; no ARCH churn pre-merge).
2. Placeholder scan: function/file/field names, window dates, command strings, JSON names are literal. STOPs (window mismatch, ccxt uncertainty, strict reader) name trigger + action. "No second holdout run" is a stated invariant with review enforcement.
3. Type consistency: `gold_holdout_v3.json` / `gold_optimized` / `gold_sdca` / `gold_optimized_provenance.json` / `gold_live_path_workorder.md` identical in tasks and triggers; v3 shape/weights referenced (never re-typed where avoidable — read from JSON); provenance keys match the recon-held `SdcaOptimizeProvenance` list.
