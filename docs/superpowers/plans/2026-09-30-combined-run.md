# Combined run (Plan 8: 5y rails × uup vote × floor-0) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the first gate combining all three evidence-led changes — 5y trailing rails, uup-for-dxy vote, floor-0 objective — and record whether anything clears the gate as-written vs as-proposed, on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Call-site overrides only. `--deployed-floor` / `--dd-cap` CLI args plumb into `SdcaOptimizeObjective(...)` at the gold gate's `run_sdca_walk_forward` call (defaults reproduce library behavior exactly). Library constants, test pins, and the sensitivity threshold are untouched — sensitivity stays analytical (recorded maxΔ judged post-hoc against 2.0 and 4.0, Plan-4 counterfactual style). Seed is the uupswap v3 file; rails variant is the landed `quad_5y` path (no new fitter code).

**Tech Stack:** Python, pytest (`-m unit`), ruff (line length 100). One simulator gate run (~40s class).

**Spec:** Standing evidence (all file-recorded): v3 gate (uup vote, full rails): mean +9.97%, F0 +23.31/F (floor veto, dd 7.10) / F1 −11.16/T / F2 +17.75/T, sens stable 0.45; quad_5y gate (v1 vote, 5y rails): mean +11.34%, F0 +25.79/F / F1 −8.25/F (floor veto — bounded rails read the decline as rich) / F2 +16.47/T, sens 2.83 unstable; Plan-4 calibration (floor 10→0 recommended, cap 50 hold, sens→4.0 weak); `run_sdca_walk_forward(..., objective: SdcaOptimizeObjective | None = None)` accepts the override (`optimize.py:313`); objective fields `capital_deployed_floor_pct=10.0, max_drawdown_cap_pct=50.0` (`walk_forward.py:50-51`).

## Global Constraints

- Research-only: no `settings.json`, no `presets.json`, no `--push-supabase`, no workflow/manifest edits, no library-default changes, no test-pin changes.
- The ONLY behavioral delta vs prior runs is (rails=quad_5y, vote=uupswap-v3, floor=0). Shape space, gates, folds, dd-cap (50), sensitivity computation, seed file, holdout discipline all identical. Any other diff in the gate invocation fails review.
- Sensitivity is NOT re-tuned: whatever maxΔ the run records is judged against both bars analytically. Touching the threshold or the bump size fails review.
- Predictions are banned: the implementer records the table, not a verdict on promotability (that belongs to a packet update, out of this plan — Task 2 states the numbers + what would still need overriding, nothing more).
- ruff line length 100 on touched files only. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.

---

### Task 1: Objective-override args + combined gate run

**Files:**
- Modify: `digiquant/scripts/run_gold_curve_search.py` (`--deployed-floor` / `--dd-cap` args → `SdcaOptimizeObjective` at the existing call site; defaults = current library behavior)
- Create (untracked): `digiquant/.scratch/gold_curve_search_combined.json` (+ stdout log)

**Interfaces:**
- Consumes: `--seed-path gold_seed_v3.json` (landed), `--rails-variant quad_5y` (landed).
- Produces: combined gate record. No new modules, no helper functions (inline construction at the call site, 3 lines).

- [ ] **Step 1: Add the args (only change)**

In `run_gold_curve_search.py` (read the `run_sdca_walk_forward` call site + existing argparse block first): add `--deployed-floor (type=float, default=None)` and `--dd-cap (type=float, default=None)`; at the call site, `objective = None` when both are None (today's behavior, byte-identical path), else `SdcaOptimizeObjective(capital_deployed_floor_pct=args.deployed_floor if args.deployed_floor is not None else 10.0, max_drawdown_cap_pct=args.dd_cap if args.dd_cap is not None else 50.0)` (field names verified against `walk_forward.py:50-51` — read them, don't trust memory; STOP with NEEDS_CONTEXT if the constructor differs). Prove with `git diff` that ONLY arg-parse + objective-construction hunks changed.

- [ ] **Step 2: Sanity-proof the default path (no new tests — behavioral proof instead)**

Run the parser default path and assert construction returns None: `.venv/bin/python -c "import argparse; ..."` — NO, do not simulate. Instead: run the FULL suite gate with NO new args after the edit? That costs a gate run to prove identity. Cheaper sufficient proof: `git diff` shows the objective variable is `None` under defaults by reading the hunk (reviewer verifies), plus the existing engine suite passes (Step 4 covers). Record that reasoning explicitly. If the hunk cannot preserve the None path exactly, STOP.

- [ ] **Step 3: Run the combined gate (background, ~40s class)**

```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_curve_search.py --seed-path digiquant/.scratch/gold_seed_v3.json --rails-variant quad_5y --deployed-floor 0 > digiquant/.scratch/gold_curve_search_combined.stdout.log 2>&1
```

(copy-before-overwrite discipline → `gold_curve_search_combased.json`... no — `gold_curve_search_combined.json`; check the script's output handling first as before.) Expected: exit 0. Record wall time + FULL table (winner shape, per-fold OOS/dd/feasible, sensitivity maxΔ + worst neighbor, mean OOS + beats_flat) + holdout-absence confirmation. Do NOT interpret beyond recording (no verdict, no override list — Task 2).

- [ ] **Step 4: Lint + test + commit (arg edit only; output untracked)**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/ -m unit -q` (engine untouched — expect green, proves no collateral) + ruff check/format on the script.
Expected: clean.

```bash
git add digiquant/scripts/run_gold_curve_search.py
git commit -m "Add objective-override args to gold curve search (#4804)"
```

---

### Task 2: Combined-run analysis (record, don't verdict)

**Files:**
- Modify: NONE committed. Analysis lives in the report + appends to `digiquant/.scratch/gold_calibration_note.md` — NO (untracked notes stay appendable? The note is untracked evidence; appending is allowed but keep it clean: write a NEW untracked note `digiquant/.scratch/gold_combined_note.md` instead of editing the old one).

**Interfaces:**
- Consumes: `gold_curve_search_combined.json` + all standing records (v1/v3/railsA/railsB tables, Plan-4 counterfactuals).
- Produces: `gold_combined_note.md` (untracked) + report section. No code, no commit.

- [ ] **Step 1: Write the comparison (numbers only + two analytical judgments)**

`gold_combined_note.md` holds: (1) the combined table beside v1/v3/B rows (same columns); (2) as-written verdict per fold (feasible? beats_flat? sens stable?) — mechanical reading, not judgment; (3) as-proposed reading: which folds flip under floor-0 (already applied — state what REMAINS failing: sensitivity bar and/or negative folds, with numbers); (4) the uup×5y interaction read (does the combination behave additively vs the single deltas? state the arithmetic, e.g. combined−v1 vs (v3−v1)+(B−v1)); (5) explicit non-claims list (what this run does NOT decide: promotion, bar changes, hy/ig, holdout). Every number cites file+key. Any number without a citation is removed.

- [ ] **Step 2: Report (no commit)**

Report quotes the as-written fold table + the interaction arithmetic in full. No verdict on promotability (that belongs to a future packet refresh, explicitly out of scope).

---

### Task 3: Docs + verify + evidence log

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (gold gate-script row: document the three CLI overrides `--seed-path` / `--rails-variant` / `--deployed-floor`+`--dd-cap` with defaults-behavior note; touch nothing else; skip-with-note if the row is absent)
- Verify: suite + ruff + status.

**Interfaces:**
- Consumes: Tasks 1–2.
- Produces: docs + evidence log.

- [ ] **Step 1: ARCH row**

Grep the gold gate-script row (prior plans touched nearby rows); append the override documentation in matching style. Nothing else.

- [ ] **Step 2: Full verification**

```bash
.venv/bin/python -m pytest tests/dq/strategies/sdca/ tests/dq/test_export_sdca_macro.py tests/dq/test_verify_macro_depth.py -m unit -q
ruff check digiquant/scripts/run_gold_curve_search.py
ruff format --check digiquant/scripts/run_gold_curve_search.py
git status --short
```

Expected: green (stash-prove any failure); status shows plan commits + `??` staging only.

- [ ] **Step 3: Commit docs**

```bash
git add digiquant/ARCHITECTURE.md
git commit -m "Document gold gate overrides (#4804)"
```

---

## Out of scope (not this plan)

- Sensitivity threshold/bump changes of any kind (analytical judgment only).
- Packet refresh or promotion verdict (future decision point with the owner).
- hy/ig weights, new indicators, new rails variants, grid/shape changes.
- Credentialed runs, live snapshots, nightly jobs.

## Self-review

1. Spec coverage: override args + default-identity proof + combined run + table → Task 1 (vote/space/bars-except-floor/geometry identical; sens untouched); numbers + interaction + non-claims → Task 2 (citation-or-remove rule, no verdict); docs + verify → Task 3. Promotion verdict explicitly deferred, not dodged (it needs the owner + packet refresh, which this plan feeds but does not write).
2. Placeholder scan: field names (verified-by-reading with STOP branch), commands, file paths, JSON names are literal. The Step-2 default-identity proof is a read-hunk + suite argument, stated as such — not a test, not hand-waving.
3. Type consistency: `--deployed-floor`/`--dd-cap` identical in arg def, construction, Task-3 docs; `gold_curve_search_combined.json` / `gold_combined_note.md` identical in tasks and triggers; quad_5y + gold_seed_v3.json are landed names, not new ones.
