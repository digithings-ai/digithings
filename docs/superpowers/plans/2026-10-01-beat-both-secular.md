# Beat both: secular-anchor vote vs lump + flat (Plan 13) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test whether a secular-scale no-trend gold vote can beat lump (buy-and-hold) AND flat DCA on walk-forward OOS — on branch `task/4804-sdca-strategy-for-gold--gld`. User bar (2026-10-01): "we need to beat both." Standing facts: 2010–2026 full-history ($1,000 start) lump +248.7% ($3,487) / flat +155.3% ($2,553) / v4 +123.5% ($2,235); v4 gate mean OOS +10.99% vs flat (UNSTABLE 2.61).

**Why v4 can't do it:** 90d anchor sells every grinding rally of a secular bull; every sell + unspent dollar is drag vs lump. The only lump-beating trade available is the secular round-trip (2011–12 top → 2015–16 bottom). That needs an anchor that stays neutral through grinds and fires only at multi-year extremes.

**Architecture:** v5 seed = `RollingZRiskModel` window **1260d** (~5yr, half of gold's ~decadal secular swing: 2001–11 bull / 2011–15 bear / 2015–26 bull — pre-registered here, BEFORE any run, no tuning) + z 1.0 (untouched default) + m2/uup 0.5 (slow macro only) + oscillators **0.0** (short-horizon votes sell the grind; that is the documented reason, not an oversight). Same gate machinery (space/bars/geometry/causal loop/objective untouched) + vs_lump recording + frontier analysis (how many feasible shapes beat BOTH — separates vote failure from winner-selection failure). Complies with the no-trend steer: trailing mean only, no time regressor (Mayer-style technical; catalog lists Mayer/200w as omitted — this does not add a Mayer function, it reuses RollingZRiskModel at long window).

**Tech Stack:** Python, Polars, Pydantic v2, pytest (`-m unit`), ruff (line length 100). Simulator-only compute.

**Promotion bar (all must hold or the plan reports NEGATIVE and stops):** mean OOS beats flat AND lump; all folds feasible; sens maxΔ ≤ 2.0; holdout stays spent (never re-scored — v5 ships with holdout ABSENT like v4, stated not hidden).

## Global Constraints

- Research-only. No live-trading paths, no Supabase push, no merge (owner-side). No pandas, pydantic v2, ruff 100 on touched files. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.
- Window 1260 / z 1.0 / oscillator-zero are FROZEN by this plan (pre-registered above). Any run-then-tweak of these = plan violation, enforced by review. A follow-up plan may tune only on an honest negative + new reasoning.
- No generic_valuation/log_linear/log_quadratic anywhere (grep-gated like v4).

---

### Task 1: v5 secular seed (frozen vote, tripwires)

**Files:**
- Create: `digiquant/scripts/run_gold_secular_index_v5.py` (standalone — mirror `run_gold_technical_index_v4.py` structure, NOT an edit of it)
- Create (untracked): `digiquant/.scratch/gold_seed_v5.json`
- Modify: NONE

**Interfaces:**
- Consumes: `resolve_sdca_risk_model("rolling_z", ...)` with window 1260 / z 1.0 literals + rationale comment citing this plan; `SdcaCompositeWeights(valuation=1.0, m2=0.5, uup=0.5, everything else 0.0)` with oscillator-zero rationale in docstring.
- Produces: v5 seed + coverage/null-footprint report. Task 2 gates it.

- [ ] **Step 1: Write the script (mirror v4 seed, new vote)**

Read `run_gold_technical_index_v4.py` fully first; mirror imports/flow/output shape with deltas: rails via `resolve_sdca_risk_model("rolling_z", dates=date_s, price=price_s, rolling_window=1260, rolling_z=1.0)` (literals + comment: 1260d ≈ 5yr ≈ half secular swing per Plan 13 header; frozen, not tuned); weights valuation 1.0 / m2 0.5 / uup 0.5 / ALL others 0.0 (docstring: oscillators zeroed because short-horizon votes sell the grind — the lump-beating requirement; sma_band overlap question is MOOT here since sma_band=0); NO generic_valuation import/fit (grep-verify); OUT `gold_seed_v5.json` with same keys as v4 seeds plus `"rails": "rolling_z/1260d/z1.0 secular trailing mean (no time trend)"` and `"trend_valuation": false`.

- [ ] **Step 2: Run + tripwires (no gate yet)**

Run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_secular_index_v5.py`
Expected: exit 0; coverage ≥ 80% of v1 bars (1260d warmup ≈ 5yr on a 2004-start calendar — assert explicitly, STOP if violated: the seed would start ~2009-2010 and fold geometry may starve; that STOP is a finding, not a failure to work around); buy-zone share + mean risk printed for the record (EXPECT rich-skewed: secular bull — state it, don't adjust); null footprint ZERO attributable to valuation (same one-liner check as v4; STOP if nonzero).

- [ ] **Step 3: Lint + commit the script (output untracked)**

Ruff clean, then:
```bash
git add digiquant/scripts/run_gold_secular_index_v5.py
git commit -m "Add gold secular (no-trend, lump-chasing) seed v5 (#4804)"
```

---

### Task 2: v5 gate run + vs_lump + frontier analysis

**Files:**
- Modify: `digiquant/scripts/run_gold_curve_search.py` — ONLY (a) a `rolling1260` rails-variant choice (same pattern as `rolling90`: shared literals so seed/gate cannot diverge) IF the factory needs it, and (b) vs_lump recording per fold + frontier count (feasible shapes beating BOTH flat and lump on mean OOS) — read the gate-record assembly first; minimal diff, grid/gates/folds/objective/weights UNTOUCHED.
- Create (untracked): `digiquant/.scratch/gold_curve_search_v5.json` (+ stdout log)
- Modify: NONE else (engine untouched; `--out`/`--causal-rolling` seam reused).

**Interfaces:**
- Consumes: v5 seed; causal rolling loop (window 1260 through the concatenated-history path — verify the helper generalizes to any window rather than assuming; if it hardcodes 90 anywhere, that literal becomes the shared constant, not a second one).
- Produces: v5 gate record with per-fold vs_flat AND vs_lump + frontier count. Task 3 judges it.

- [ ] **Step 1: Read-first (factory + record assembly + window plumbing)**

Read the `rolling90`/causal wiring added in commits `6731efece`/`0c6003854`: where window/z live (shared literals?), how the causal loop builds the model per fold, and where the gate record's per-fold dicts are assembled (to add vs_lump). Choices, recorded with line evidence: (i) generalize the existing seam to take window/z from the variant (preferred — one path, no fork); (ii) add a parallel `rolling1260` branch ONLY if (i) requires engine-protocol changes (then STOP with NEEDS_CONTEXT — same rule as Plan 12). vs_lump source: check what the trial evaluator returns — `SdcaBacktestReport` carries `vs_lump_pct` (same ×100 convention as vs_flat); if the per-fold path exposes it, record it; if not, STOP with NEEDS_CONTEXT (exact gap) rather than hand-rolling returns.

- [ ] **Step 2: Run the v5 gate (background, ~40s class)**

```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_curve_search.py --seed-path digiquant/.scratch/gold_seed_v5.json --rails-variant rolling1260 --out digiquant/.scratch/gold_curve_search_v5.json > digiquant/.scratch/gold_curve_search_v5.stdout.log 2>&1
```

(Backup+sha256 discipline per Plan 12 Ruling 3: every scratch file the run touches, hashes before/after in the report.) Expected: exit 0. Record wall + FULL table (winner shape; per-fold OOS-vs-flat / OOS-vs-lump / deployed-net/peak / dd / feasible; sens maxΔ + neighbor key; mean + beats_flat + beats_lump) + frontier count (feasible shapes beating both, of N feasible) + holdout-absence.

- [ ] **Step 3: Lint + commit (arg/record edit if any; outputs untracked)**

Ruff clean, then commit the script edit only (message per brief pattern). Report carries the table + the vote-vs-selection read (winner beats both? frontier nonzero but winner misses? frontier zero?).

---

### Task 3: Verdict + tearsheet-if-won + docs

**Files:**
- Create (untracked): v5 diagnostic tearsheet JSON via a `build_gold_v5_diagnostic_tearsheet.py` (mirror the v4 builder) — ONLY if the bar clears.
- Modify: `digiquant/ARCHITECTURE.md` (append-only paragraph: v5 outcome either way — one paragraph, win or honest negative).
- Verify: relevant suite + ruff + status.

**Interfaces:**
- Consumes: Task 2 record.
- Produces: verdict (BEATS-BOTH / NEGATIVE + which half failed + frontier read), optional tearsheet, docs line.

- [ ] **Step 1: Judge against the bar (no new runs)**

BEATS-BOTH requires: mean OOS vs flat > 0 AND mean OOS vs lump > 0, all folds feasible, sens maxΔ ≤ 2.0. Anything less = NEGATIVE: name exactly which condition failed (lump half? sens? feasibility?) + frontier read (zero → vote can't do it, shelve; nonzero-but-winner-misses → winner-selection follow-up, still NEGATIVE for v5-as-shipped). No re-runs, no tweaks, no second variant — the frozen vote stands judged.

- [ ] **Step 2: Tearsheet ONLY on BEATS-BOTH + preview entry**

Mirror `build_gold_v4_diagnostic_tearsheet.py` (rolling1260 literals, v5 weights/shape/notes with both benchmarks). Temp `page.tsx` entry (same REVERT-BEFORE-MERGE pattern). Serve check: page + JSON 200. On NEGATIVE: no tearsheet, no preview entry — write that down instead.

- [ ] **Step 3: Docs + verify + commit(s)**

ARCH append (v5 paragraph: vote, outcome, frontier, verdict — win or negative, same honesty either way). Suite green + ruff clean. Commit script(s) + ARCH (outputs untracked, preview edits uncommitted like v4).

---

## Out of scope (not this plan — enforced by review)

- Window/z/weight tuning after seeing results (frozen-vote rule).
- Objective-function changes (selection stays vs_flat-based; vs_lump is recorded + judged, not selected on — the frontier analysis is the selection critique, honestly separated).
- New indicators, TLT/TIP/CPER legs, holdout re-scoring (spent), promotion packet edits, nightly, credentials, merge.
- Nautilus v5 tearsheet (diagnostic curve-sim only, same as v1/v4 candidates).

## Self-review

1. Spec coverage: frozen vote + tripwires → Task 1 (mirror-v4 structure, grep gate, coverage assert adjusted for 1260d warmup with STOP-as-finding, null-footprint STOP); gate + vs_lump + frontier → Task 2 (read-first wiring choice with STOP branches, backup discipline, full table with both benchmarks); verdict + conditional tearsheet + docs → Task 3 (BEATS-BOTH bar with NEGATIVE paths specified, no re-runs).
2. Placeholder scan: window 1260, z 1.0, weights, file paths, JSON names, commands are literal. STOPs (coverage violation, null footprint, engine-protocol need, vs_lump gap, any bar miss) name trigger + action. `--rails-variant rolling1260` + `--out` + `--seed-path` reuse the landed seam.
3. Type consistency: `rolling1260` variant name vs `rolling_window=1260` literal vs `gold_seed_v5.json` / `gold_curve_search_v5.json` / `run_gold_secular_index_v5.py` / `build_gold_v5_diagnostic_tearsheet.py` identical everywhere; single-knee assert pattern reused; `mean reversion` label family unchanged.
