# Decoupled sell gate + v6 long-biased gate (Plan 15, phase b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the owner's long-biased decoupled design (buys on the medium-term vote, sells only at secular extremes) as a MINIMAL generic engine mechanism + gold mask content, and gate the resulting v6 vote against beating BOTH lump and flat — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Standing facts:** v5 NEGATIVE (lump −12.45, frontier 0/432); Plan-14a NO-GO for blind extension (real-rate 2015 miss; 200w whipsaw 349d); conjunction exploratory finding (strict box z≤−2 & m≥1.5: 74 joint days, 13 outside 2011 window = 0.3%, fires 2011-09-06, silent 2020-08-07 + now; joint-cheap readout ZERO days in history — buys stay medium-term). Engine confirmed single-blend/single-curve.

**Architecture (minimal generic mechanism, NOT a gold special-case):**
- Engine gains an optional sell-allow mask: `run_backtest(..., sell_dates: set[date] | None = None)` — when the curve rate is negative (sell) and `sell_dates` is not None and `dates[i]` is not in it, the day becomes hold (state carries, MTM continues — same treatment as null-risk days). `None` (default) = today's behavior, BTC-identical by construction.
- `SdcaStrategyConfig.sell_dates: frozenset[date] | None = None`; `on_bar` mirrors the backtest rule exactly (same date-membership check before sizing sells; long-only clamp untouched, ordering preserved).
- Gold provides mask CONTENT (strict-box booleans per GLD date, causal — both inputs causal at t, no future info) via a gold-side builder; the engine never knows what a conjunction is.
- v6 buy vote = v4 vote unchanged (rolling90 anchor 1.0 + m2/uup 0.5 + osc 0.25 — the measured +10.99-OOS vote); the mask only vetoes its sells outside secular extremes. Long-bias emerges: sells are rare because the mask is rare.
- Selection UNCHANGED (vs_flat + floor/cap, Plan-13 precedent); winner judged on both benchmarks + frontier-on-both recorded. Robustness: mask-box variants reported, never selected on.

**Pre-registered frozen box (disclosed exploratory origin):** z≤−2.0 & m≥1.5 was found exploratory (4 pairs tried — stated, not hidden). Frozen here as the candidate; the OOS gate + mask-robustness check (report-only) is the honesty mechanism. Any re-freezing after results = plan violation.

**Promotion bar (all must hold or NEGATIVE + shelve):** mean OOS beats flat AND lump; all folds feasible; sens maxΔ ≤ 2.0. Holdout stays spent (ABSENT, stated).

## Global Constraints

- Research-only. No live-trading paths, no Supabase push, no merge/push (owner-side). No pandas, pydantic v2, ruff 100 on touched files. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.
- BTC parity is the hard gate: every pre-existing BTC/engine/Nautilus test passes UNMODIFIED (None-mask identical behavior). Any red = STOP, not fix-forward.
- Frozen: strict-box levels, v4 buy vote/weights, gate space/bars/geometry/objective. No generic_valuation/log fits anywhere new (grep-gated).
- Standing owner rule: every iteration ships visuals (tearsheet + charts) — Task 4 regardless of outcome.

---

### Task 1: Engine sell_dates (backtest + Nautilus + tests, TDD)

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/backtest.py` (`run_backtest` gains keyword-only `sell_dates: set[date] | None = None`; veto rule on the sell branch ONLY — buy branch, sizing, MTM, report math byte-untouched; docstring documents hold-treatment parity with null-risk days)
- Modify: `digiquant/src/digiquant/strategies/sdca/nautilus_strategy.py` (config field + `on_bar` mirror — read the rate/sign/sizing block first; same membership check, same ordering around the long-only clamp)
- Modify: nearest backtest + Nautilus-parity test files (grep `run_backtest` / `TestSdcaStrategyNautilusParity` homes first — extend, don't create)
- Modify: NONE else (composite/curve/shapes/providers/settings/workflows read-only)

**Interfaces:**
- Consumes: nothing new (date sets from caller).
- Produces: generic veto mechanism with None-default. Tasks 2–3 consume it.

- [ ] **Step 1: Failing tests first**

Backtest tests: empty-set mask → zero sells, buys proceed, state/MTM consistent (construct a downhill window where unmasked sells fire — assert masked run holds cash/units flat ex-MTM); None ≡ legacy (same inputs → identical frame + report, assert equality not just shape); mask-as-superset-of-sell-days ≡ None (boundary). Nautilus test: extend the parity home with a sell_dates case (masked Nautilus run == masked backtest run). Expect FAIL (no kwarg).

- [ ] **Step 2: RED, then minimal implementation (veto on sell branch only)**

Implement both mirrors. STOP branches: on_bar block shape differs from recon (NEEDS_CONTEXT with quotes); config construction path can't carry an optional field cleanly (NEEDS_CONTEXT, don't restructure).

- [ ] **Step 3: GREEN + BTC-parity suites + lint + two commits**

Run: touched test files FULL + engine subset + Nautilus parity file + presets/asset-profile (per Plan-11 suite list habits) `-m unit -q` — all UNMODIFIED-green except new tests. Ruff clean. Then:
```bash
git add <backtest.py> <backtest tests>
git commit -m "Add optional sell-dates veto to SDCA backtest (#4804)"
git add <nautilus_strategy.py> <parity tests>
git commit -m "Mirror sell-dates veto in SDCA Nautilus strategy (#4804)"
```

---

### Task 2: Strict-box mask builder + v6 gate run

**Files:**
- Create: `digiquant/scripts/build_gold_sell_mask.py` (reads staged DFII10.csv + mayer JSON (or recomputes both via SHIPPED functions only — read-first choice, no duplicated math if a shipped path exists); emits per-GLD-date booleans for the FROZEN strict box; causal by construction — assert in-code that mask[t] uses inputs ≤ t with a comment citing why (forward-filled macro + completed-week SMA))
- Create (untracked): `digiquant/.scratch/gold_sell_mask.json` (date list + box levels + builder provenance)
- Modify: gate path for v6 (read-first: how run_gold_curve_search consumes seed/rails/variant + where the trial evaluator is invoked — add a v6 mode reusing the causal loop with buy vote = v4 seed (rolling90 + weights) and sell mask passed through to `evaluate_sdca_trial_curve_sim`/`run_backtest`; minimal diff, engine protocol untouched)
- Create (untracked): `digiquant/.scratch/gold_curve_search_v6.json` (+ stdout log)
- Modify: new unit test for the builder (causality test: mask[t] == recompute on calendar-truncated-at-t for several t — mirrors the Plan-12 causal-test pattern; colocate sensibly)

**Interfaces:**
- Consumes: Task-1 veto; v4 seed vote; frozen box.
- Produces: v6 gate record (vs_flat + vs_lump per fold + frontier-both + mask-robustness table). Task 3 judges, Task 4 renders.

- [ ] **Step 1: Read-first (gate consumption sites + shipped-function reuse)**

Record with line evidence: (a) where the v4/v5 gate builds the buy index + invokes the evaluator per fold (exact seam for mask pass-through); (b) whether shipped `real_rate_z` + mayer-series read can serve the builder with zero math duplication (preferred) vs documented plain-Python mirror (only if the shipped path forces engine imports — the plot script precedent); (c) test home for the builder. STOP: evaluator seam can't take a mask without engine-signature changes (NEEDS_CONTEXT — the Task-1 kwarg should have covered it; if not, say so exactly).

- [ ] **Step 2: Builder + causality test FIRST (fail-first), then gate wiring**

Builder test must be REAL (truncation-equality across a regime break; a vacuous pass fails review). Gate wiring: buy index identical construction to v4 seed (same literals/weights — diff-prove no vote drift), mask threaded to every trial evaluation (IS + OOS + sensitivity neighbors — verify neighbors re-score through the mask, cite the site).

- [ ] **Step 3: Run v6 gate (background, ~40s class) + mask-robustness (report-only, 8 extra runs)**

Main run: v6 buy vote + frozen mask, same space/bars/geometry. Backup+sha256 discipline (all touched scratch files, before/after). Record wall + FULL table (winner shape; per-fold OOS-vs-flat / OOS-vs-lump / deployed-net/peak / dd / feasible; sens maxΔ + neighbor key; mean + beats flags) + frontier-both (feasible shapes beating both, of N) + holdout-absence + mask descriptive stats (mask-day count, which folds contain mask days — a fold with zero mask days is pure buy-and-hold-plus-oscillator-noise: state it).
Robustness (SAME binary, 8 box variants: z ∈ {−1.5,−2.5} × m ∈ {1.4,1.6} × both-axes-loose/tight — 8 runs, background, outputs to `gold_curve_search_v6_robust_*.json` untracked): record mean-flat/lump + feas count per variant ONLY. Selection NEVER touches these (state that twice: in code comment + report).

- [ ] **Step 4: Lint + tests + commit (builder + gate-script edit + builder test; outputs untracked)**

Suites green + ruff clean, then commit (message per brief pattern). Report carries table + frontier + robustness + the vote-vs-selection read.

---

### Task 3: Verdict (no new runs)

**Files:** NONE (judgment only).

- [ ] **Step 1: Judge against the bar**

BEATS-BOTH requires: mean OOS vs flat > 0 AND vs lump > 0, all folds feasible, sens ≤ 2.0. Else NEGATIVE naming the failed condition + frontier read (zero → mask+vote can't do it; nonzero-but-winner-misses → selection follow-up proposal, still NEGATIVE for v6-as-shipped) + robustness read (does the result survive the box neighborhood, or is it a knife-edge? — reported, never re-selected). No re-runs, no re-freezing.

---

### Task 4: Visuals + docs (every iteration ships visuals)

**Files:**
- Create (untracked): v6 diagnostic tearsheet JSON (mirror v4/v5 builder: buy vote + mask described in notes with mask-day count + gate table with BOTH benchmarks + robustness one-liner) + public/ copy for preview
- Modify: plot script (add mask-rug chart: full-history risk or price with mask days marked + event labels — stdlib SVG, same pattern) + public/ copy
- Modify: `page.tsx` TEMP entry (REVERT-BEFORE-MERGE pattern, uncommitted) IF verdict is BEATS-BOTH; on NEGATIVE serve the JSON + chart only (no page entry — keeps the preview index honest: pages are candidates, charts are evidence)
- Modify: `digiquant/ARCHITECTURE.md` (append-only paragraph in SDCA section: mechanism, mask, outcome, verdict)

**Interfaces:**
- Consumes: Tasks 2–3.
- Produces: served visuals + docs. Verify: page/JSON/chart 200s (dev server; relaunch if down with the exact background command), suite + ruff, status.

- [ ] **Step 1: Build + serve visuals**
- [ ] **Step 2: Docs + verify + commits (scripts + ARCH; outputs/preview-edits untracked-or-dirty)**

---

## Out of scope (not this plan — enforced by review)

- Re-freezing the box on results; objective/selection changes; new indicators/legs; weight/window/curve-space tuning; threshold optimization of any kind.
- Nautilus live-trading enablement; broker paths; Supabase push; nightly; credentials; merge.
- Holdout re-scoring (spent). COT/Dow-gold/CPI-oil legs (recon-listed only).
- v4/v5 seed/gate/output alterations (frozen lineage stays comparable).

## Self-review

1. Spec coverage: generic veto + mirrors + parity gate → Task 1 (fail-first with None-identity + empty-mask + Nautilus parity, BTC-hard-gate STOPs, two commits); mask builder (causality-tested) + v6 gate + vs_lump + frontier + report-only robustness → Task 2 (read-first seams with STOPs, buy-vote drift-proof, neighbor re-scoring verified, backup discipline); verdict-only judging → Task 3 (bar with NEGATIVE paths, robustness-read-not-selected); visuals-every-iteration + docs → Task 4 (conditional page entry keeps index honest, serve-200 proofs).
2. Placeholder scan: box levels, file paths, JSON names, commands, 8-variant grid, metric names are literal. STOPs (parity red, seam mismatch, config-shape drift, backup gaps, any bar miss) name trigger + action. `--rails-variant`/`--out`/`--causal-rolling`/`--seed-path` reuse landed seams (verify names read-first; brief guesses are VERIFY-FIRST).
3. Type consistency: `sell_dates: set[date] | None` vs config `frozenset[date] | None` distinguished everywhere (mutable-in/backtest, immutable-in/config); `gold_sell_mask.json` / `gold_curve_search_v6.json` / `build_gold_sell_mask.py` identical in tasks; strict-box levels identical in plan header, builder, mask JSON, notes, and ARCH.
