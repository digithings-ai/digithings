# Rails robustness (Plan 7: bounded-trend fits + fold-1/gate evaluation) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add trend-bounding options to the generic valuation rails (trailing lookback, eval-slope cap; linear form already exists) and prove which variant unpins fold-1 without breaking the other folds — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Two new fitter params on `fit_generic_valuation` (`fit_lookback_days`, `max_annual_trend`), implemented in the shared engine with unit tests (reusable for BTC's 2021-top folds — the generalized thesis), consumed by gold rails-fitter variants in the gate script. #3173 compliance is structural: the fitter only ever sees the passed IS series; lookback slices WITHIN it; caps rescale fitted coefficients; nothing touches OOS (the IS-only enforcement test stays green and unmodified). Evaluation is fold-1 replay first (cheap), full gate second (top-2 only).

**Tech Stack:** Python, NumPy (already used by the fitter), Polars, pytest (`-m unit`), ruff (line length 100). Simulator-only compute.

**Spec:** Recon 2026-09-30 (same session, recorded as completed Task 0): `fit_generic_valuation(dates, price, *, form="log_quadratic", notes="", max_fit_rows=None)` (`generic_valuation.py:69-76`); trend terms `t=(d-origin).days`, `x=t-mu`, design `[1,x]`/`[1,x,x²]` (`:100-110`); eval reuses IS origin/mu/coeffs for ANY date (`_evaluate_rails`, `:159-174`); saturation `below=(3.0*(log_median-log_price)/(log_median-log_low)).clip(0,3)` (`valuation.py:50-51`, price≤low rail → +3.0 max-buy); `GenericValuationRiskModel` low=q10/med=q50/high=q95 (`:199-206`); `gold_generic_rails_fitter` fits whole IS, default form (`run_gold_curve_search.py:107-114`); #3173 quotes (`walk_forward.py:11-14,226-231`, `optimize.py:52-55`, test `:115-162` — all UNTOUCHED by this plan); existing knobs table (form, max_fit_rows, notes, low/high quantiles, coefficients_path, rolling_window — NO lookback/cap/robust); `widen_factor=1.0` on fold-1 IS (span 3192d > 2922); `MIN_FIT_HISTORY_DAYS=730` floor (`quantile_rails.py:30`).

## Global Constraints

- #3173 inviolate: no fitter input outside the passed IS series; the IS-only enforcement test is never modified, never weakened (it must pass unmodified — explicit gate in Task 1).
- Pydantic/naming conventions of the engine files touched; ruff line length 100 on touched files only.
- Research-only: no `settings.json`, no `presets.json`, no `--push-supabase`, no workflow/manifest edits. Gold gate runs use existing `--seed-path` (v1 seed — vote UNCHANGED in this plan; rails-only delta).
- Cap/lookback values are experiment parameters, not production defaults: nothing changes engine defaults (`form`, `max_fit_rows=None`, no cap, no lookback remain the defaults).
- Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks. Never force-push.

---

### Task 1: Fitter params (lookback + slope cap) + unit tests

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/generic_valuation.py` (`fit_generic_valuation` signature + slicing + rescaling + docstrings)
- Modify: `tests/dq/strategies/sdca/test_generic_valuation.py` (append behavior tests; existing tests untouched)
- Possibly: `digiquant/src/digiquant/strategies/sdca/quantile_rails.py` — ONLY if the rescaling helper fits its layer better (read it first; default to keeping all new code in `generic_valuation.py`).

**Interfaces:**
- Consumes: existing `fit_generic_valuation` + `fit_quantile_regression` + coefficient types.
- Produces: `fit_lookback_days: int | None = None`, `max_annual_trend: float | None = None` with the exact semantics below. Task 2 consumes both.

- [ ] **Step 1: Write the failing tests (append to test_generic_valuation.py, header imports only)**

```python
def _bull_then_flat(n_bull: int = 2000, n_flat: int = 1100) -> tuple[pl.Series, pl.Series]:
    """Synthetic bull (20%/yr) then flat regime — the fold-1 shape in miniature."""
    import datetime as _dt
    import math as _m

    start = _dt.date(2004, 1, 1)
    growth = 1.20 ** (1.0 / 365.25)
    prices: list[float] = []
    p = 100.0
    for _ in range(n_bull):
        prices.append(p)
        p *= growth
    for _ in range(n_flat):
        prices.append(p)
    dates = pl.Series("date", [start + _dt.timedelta(days=i) for i in range(n_bull + n_flat)])
    return dates, pl.Series("price", prices, dtype=pl.Float64)


def test_lookback_bounds_extrapolation_on_synthetic() -> None:
    from digiquant.strategies.sdca.generic_valuation import fit_generic_valuation

    dates, price = _bull_then_flat()
    is_dates, is_price = dates[:2000], price[:2000]
    oos_dates = dates[2000:]
    full = fit_generic_valuation(is_dates, is_price)
    bounded = fit_generic_valuation(is_dates, is_price, fit_lookback_days=756)
    from digiquant.strategies.sdca.generic_valuation import GenericValuationRiskModel

    full_med = GenericValuationRiskModel(full).rails(oos_dates)["median"]
    bounded_med = GenericValuationRiskModel(bounded).rails(oos_dates)["median"]
    assert full_med[-1] > bounded_med[-1] * 1.5


def test_slope_cap_bounds_rails_growth() -> None:
    from digiquant.strategies.sdca.generic_valuation import fit_generic_valuation

    dates, price = _bull_then_flat()
    is_dates, is_price = dates[:2000], price[:2000]
    oos_dates = dates[2000:]
    capped = fit_generic_valuation(is_dates, is_price, max_annual_trend=0.10)
    from digiquant.strategies.sdca.generic_valuation import GenericValuationRiskModel

    med = GenericValuationRiskModel(capped).rails(oos_dates)["median"].to_list()
    years = (oos_dates[-1] - oos_dates[0]).days / 365.25
    implied = (med[-1] / med[0]) ** (1.0 / years) - 1.0
    assert implied <= 0.10 * 1.05


def test_lookback_below_min_history_raises() -> None:
    from digiquant.strategies.sdca.generic_valuation import fit_generic_valuation

    dates, price = _bull_then_flat(n_bull=800, n_flat=100)
    with pytest.raises(ValueError, match="[Ll]ookback"):
        fit_generic_valuation(dates[:800], price[:800], fit_lookback_days=500)


def test_defaults_unchanged_without_params() -> None:
    from digiquant.strategies.sdca.generic_valuation import fit_generic_valuation

    dates, price = _bull_then_flat()
    a = fit_generic_valuation(dates[:2000], price[:2000])
    b = fit_generic_valuation(dates[:2000], price[:2000], fit_lookback_days=None, max_annual_trend=None)
    assert a.model_dump() == b.model_dump()
```

(`pl`/`pytest` already imported in that file — verify with grep; if not, extend the header block. `model_dump` shape: confirm the coefficients model supports it — if not, compare selected fields (`origin`, `mu`, `form`, per-rail `(c,a,b)`) instead; do not guess, read the type first.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_generic_valuation.py -m unit -v -k "lookback or slope_cap or defaults_unchanged"`
Expected: FAIL (unexpected keyword arguments — `TypeError`).

- [ ] **Step 3: Implement**

In `fit_generic_valuation` (after reading `:69-143` in full — anchors below are content-based):

1. Signature += `fit_lookback_days: int | None = None, max_annual_trend: float | None = None`.
2. Lookback: after the series are materialized and BEFORE `origin`/`mu`/design construction, if `fit_lookback_days is not None`: keep rows with `(last_date - d).days < fit_lookback_days`. If the sliced window spans fewer than `MIN_FIT_HISTORY_DAYS` (import it from `quantile_rails` — verify the import path, don't guess), raise `ValueError(f"fit_lookback_days={...} leaves ... days, below MIN_FIT_HISTORY_DAYS=...")`. `origin`, `mu`, `fit_start`/`fit_end`, and `notes` (append `f"lookback={fit_lookback_days}d"`) all derive from the SLICED window. Rationale in docstring: lookback slices within the caller-passed IS series — #3173-compliant by construction (the fitter never sees OOS regardless of caller).
3. Slope cap: after the QuantReg fit (all 7 rails, post linear-fallback), compute the median rail's slope at the LAST fit bar: `slope_per_day = a + 2*b*x_last` (median rail `(c,a,b)`; linear form → `b=0`, same formula). Implied annual growth `g = 10**(slope_per_day*365.25) - 1`. If `max_annual_trend is not None and g > max_annual_trend`: scale `s = log10(1+max_annual_trend)/log10(1+g)`; multiply `(a,b)` of EVERY rail by `s` (keep `c` — level preserved, growth bounded; shape preserved, still exact for linear). Append `f"trend_cap={max_annual_trend} (scaled {s:.3f})"` to `notes`. Docstring states the guarantee precisely: post-scale median-rail annualized growth at fit-end ≤ cap (the test asserts it on EVAL rails, which reuse the same coefficients — consistent).
4. Docstrings on both params (semantics + #3173 note + defaults-unchanged note). No other behavior change: `form`, `max_fit_rows`, fallback, widen, return type all untouched.

- [ ] **Step 4: Run to verify it passes + #3173 test unmodified-green**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_generic_valuation.py tests/dq/strategies/sdca/test_walk_forward.py -m unit -q`
Expected: PASS — including `TestRailsRefitPerFold` UNMODIFIED (if it fails, the implementation leaked across the IS boundary — STOP, do not weaken the test).

- [ ] **Step 5: Lint + commit**

Ruff check + format-check both files.
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/generic_valuation.py tests/dq/strategies/sdca/test_generic_valuation.py
git commit -m "Add lookback + trend-cap options to generic valuation fit (#4804)"
```

---

### Task 2: Rails-variant matrix on fold-1 (v1 vote, v1 shape)

**Files:**
- Create: `digiquant/scripts/run_gold_rails_variants.py`
- Create (untracked): `digiquant/.scratch/gold_rails_variants.json`

**Interfaces:**
- Consumes: Task-1 params; v1 seed weights + v1 winner shape/params (read from `gold_seed.json` / `gold_curve_search.json` — never re-derive); `score_trial_on_folds` on the single fold-1 object (pattern from the attribution script — read it first); `gold_generic_rails_fitter` source as the template (import nothing from the gate script except the fitter if importable without side effects — else define variant fitters locally with the same body + params; record which).
- Produces: per-config OOS + pinned-fraction + the top-2 configs for Task 3. No gate runs, no weight/shape changes.

- [ ] **Step 1: Write the script**

Create `digiquant/scripts/run_gold_rails_variants.py` with configs (fitter closures over `fit_generic_valuation` + `GenericValuationRiskModel`):
- `quad_full` (control: today's behavior — default form, no lookback, no cap)
- `linear_full` (form="log_linear")
- `quad_3y` (fit_lookback_days=756), `quad_5y` (fit_lookback_days=1260)
- `quad_cap10` / `quad_cap15` / `quad_cap25` (max_annual_trend=0.10/0.15/0.25)
- `quad_5y_cap15` (both)

For each config: build the rails fitter, run `score_trial_on_folds` on `[fold1]` with the v1 winner params + v1 seed weights (fold dates recomputed via `make_walk_forward_folds` on the v1 seed calendar with the Plan-6 assert), record OOS vs-flat + feasibility + dd. Additionally compute the PINNED FRACTION directly from rails: fit the config's rails on fold-1 IS, evaluate median/low over fold-1 OOS dates, report fraction of OOS bars with `price <= low` (the saturation condition from `valuation.py:50`) + fraction with valuation-z at exactly ±3.0 (via `valuation_z_score` — import it; read its signature first). Sanity gates (SystemExit, do not proceed on violation): `quad_full` OOS must equal the v1 gate fold-1 (−11.19%) to 2dp (replay control — same bar as Plan 6); pinned fraction for `quad_full` must be ≈0.99 (the 1094/1100 finding — methodology control). Write `.scratch/gold_rails_variants.json` with `{configs: {name: {oos, feasible, dd, pinned_frac, saturated_frac}}, top2: [...]}` where top2 = the two configs with highest OOS (ties → lower pinned fraction). Docstring: vote and shape fixed (v1) — rails-only delta; full-gate confirmation is Task 3.

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_rails_variants.py`
Expected: 8 config lines + both sanity gates passing + top2 line + wrote-line. Either SystemExit stops the plan — investigate, do not adjust thresholds.

- [ ] **Step 3: Lint + commit the script (output untracked)**

Ruff check + format-check.
Expected: clean.

```bash
git add digiquant/scripts/run_gold_rails_variants.py
git commit -m "Add gold rails-variant matrix script (#4804)"
```

---

### Task 3: Full gate on top-2 rails variants (v1 vote, v1 shape space)

**Files:**
- Modify: `digiquant/scripts/run_gold_curve_search.py` (`--rails-variant` arg only; grid/gates/folds/objective/weights untouched)
- Create (untracked): `digiquant/.scratch/gold_curve_search_rails{A,B}.json` (+ stdout logs)

**Interfaces:**
- Consumes: Task-2 top2 (names + exact params); v1 seed via existing `--seed-path`.
- Produces: two full gate records. Vote, shape space, bars, geometry all identical to v1 — rails-fitter ONLY delta.

- [ ] **Step 1: Add `--rails-variant` (only change)**

In `run_gold_curve_search.py`: add `argparse --rails-variant` with choices `default` (today's `gold_generic_rails_fitter`, byte-identical behavior) + the Task-2 top2 names mapped to their exact fitter closures (import the closures from `run_gold_rails_variants.py` if importable without side effects — else define them inline with the same params and record which; params must match Task-2 JSON exactly). Default stays `default`. Prove with `git diff` that ONLY the arg + fitter-selection hunks changed (grid/gates/folds/objective/weights lines context-only).

- [ ] **Step 2: Run both gates (background, ~40s class each)**

```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_curve_search.py --seed-path digiquant/.scratch/gold_seed.json --rails-variant <top1> > digiquant/.scratch/gold_curve_search_railsA.stdout.log 2>&1
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_curve_search.py --seed-path digiquant/.scratch/gold_seed.json --rails-variant <top2> > digiquant/.scratch/gold_curve_search_railsB.stdout.log 2>&1
```

(copy-before-overwrite discipline for the JSON outputs → `gold_curve_search_railsA.json` / `..._railsB.json`.) Expected: both exit 0. Record wall times + FULL tables (winner shape, per-fold OOS/dd/feasible, sensitivity, mean OOS) + v1-vs-each deltas. The comparison that matters: do the variants hold folds 0/2 while fixing fold-1 (no robbing Peter to pay Paul)?

- [ ] **Step 3: Lint + commit (arg edit only; outputs untracked)**

Ruff check + format-check the script.
Expected: clean.

```bash
git add digiquant/scripts/run_gold_curve_search.py
git commit -m "Add rails-variant selection to gold curve search (#4804)"
```

---

### Task 4: Docs + verify + evidence log

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (rails/fitter passages: document the two params + #3173-compliance note; touch nothing else; skip-with-note if the passage is absent)
- Verify: engine-heavy suite + ruff + status.

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: docs + evidence log (final report section: plan commits, variant matrix table + top2, both gate tables + deltas with the Peter/Paul verdict, open items).

- [ ] **Step 1: Fitter docstrings (Task-1) + ARCH row**

Confirm Task-1 docstrings landed (they're part of the Task-1 diff — verify by reading, don't assume). ARCH: grep the generic-valuation/rails passage; append the two params with one-line semantics + the sentence "lookback slices within the caller-passed IS window and caps rescale fitted coefficients, so neither sees OOS (#3173)". Nothing else.

- [ ] **Step 2: Full verification**

```bash
.venv/bin/python -m pytest tests/dq/strategies/sdca/test_generic_valuation.py tests/dq/strategies/sdca/test_walk_forward.py tests/dq/strategies/sdca/test_valuation.py tests/dq/strategies/sdca/test_risk_index.py tests/dq/strategies/sdca/test_providers.py tests/dq/strategies/sdca/test_sdca_gold_uup.py -m unit -q
ruff check digiquant/src/digiquant/strategies/sdca/generic_valuation.py tests/dq/strategies/sdca/test_generic_valuation.py digiquant/scripts/run_gold_rails_variants.py digiquant/scripts/run_gold_curve_search.py
ruff format --check <same file list>
git status --short
```

Expected: green (stash-prove any failure; the #3173 test must pass UNMODIFIED — confirm with `git diff --stat` showing no test_walk_forward.py modification); status shows plan commits + `??` staging only.

- [ ] **Step 3: Commit docs**

```bash
git add digiquant/ARCHITECTURE.md
git commit -m "Document rails lookback + trend-cap options (#4804)"
```

---

## Out of scope (not this plan)

- Winsorized/residual-robust fits (heavier quantile_rails surgery — follow-up if lookback+cap underperform).
- Changing engine defaults, the #3173 test, or any gate bar/threshold.
- BTC application of the new params (same code path benefits automatically; no BTC runs here).
- Weight/shape/vote changes of any kind (v1 throughout); promotion; nightly jobs; credentialed runs.

## Self-review

1. Spec coverage: params + tests + #3173-green → Task 1 (synthetic bull-then-flat fixture encodes the fold-1 shape; floor + defaults-unchanged guards included); 8-config matrix + sanity gates → Task 2 (replay control + methodology control, top2 rule coded); full gates on top2 → Task 3 (rails-only delta, Peter/Paul verdict required); docs + verify → Task 4. Winsorized fits explicitly deferred, not dropped.
2. Placeholder scan: signatures, formulas (`a+2*b*x_last`, `10**(slope*365.25)-1`, scale factor), config values, commands, file paths, JSON keys are literal. STOPs (leak, mismatch, top2-run failure) name trigger + action. The Task-2 fallback (import vs local fitters) is recorded either way.
3. Type consistency: `fit_lookback_days` / `max_annual_trend` spelled identically in signature, tests, variant closures, arg choices, ARCH row; `gold_rails_variants.json` / `gold_curve_search_rails{A,B}.json` identical in tasks and triggers; `quad_full` control ties Task 2 to the v1 record numerically (−11.19% to 2dp).
