# The PUBLISHED gold Stage A keep/drop — in-sample vs-flat-DCA (#4804)

Worktree: `.worktrees/4804-gold-pin-sets`, branch `chore/4804-gold-pin-sets`.
Research-only. Stage A only. **No performance claim beyond what the returned metrics
literally say.** Two of the findings below are defects in the *shipped* path, reported and
not worked around.

---

## 1. Read first — and the two answers that shaped everything

| Record | What it settled |
|---|---|
| `weight_search.py` (218 lines, read whole) | `optimize_stage_a_by_backtest` at line 137 takes `dates, prices, extra_z, rails_fitter, evaluator, shape, search_names, grid, valuation_grid, objective, n_folds, holdout_frac, oos_frac`. **No cycle windows.** Its grids are the defaults `(0.0, 0.5, 1.0)` × `(0.0, 0.5, 1.0)`. `_is_rank_score` (line 91) is the plain mean in-sample `vs_flat_dca_pct` — **it does not read `feasible`, and does not apply the cap.** `feasible` is recorded on line 131 as `in_sample.capital_deployed_pct >= floor` — **NET**, while `walk_forward.is_feasible` uses **PEAK**. Rails are fit once per fold on the IS window (line 168). Returns `StageABacktestResult` with `num_evaluations`, `search_names`, per-fold `FoldScore`. |
| `asset_profile.py` (169 lines, read whole) | `SdcaAssetProfile` is a frozen strict Pydantic model; the validator `_known_extras` accepts `GENERIC_TECHNICAL_NAMES | BTC_PLUGIN_INDICATOR_NAMES`. Classmethods: **`btc_v1()` and `eth_research_v1()` only — there is NO gold profile.** `stage_a_search_names(profile)` (line 154) returns `profile.extra_indicators`, falling back to `GENERIC_TECHNICAL_NAMES` when empty. |
| `walk_forward.py` (333 lines) | `SdcaOptimizeObjective` defaults 10.0 / 50.0. `score_trial_on_folds` refits rails per fold on the IS window, then evaluates OOS **on those same rails**. `is_feasible` uses `capital_deployed_peak_pct`. |
| `curve_sim.py` | `evaluate_sdca_trial_curve_sim` is the injected CI evaluator (no fills engine import). |
| `rolling_z.py` | `RollingZRiskModel.rails()` **left-joins** a stored `(date, mu, sigma)` table — it does **not** extrapolate. Confirmed by direct probe, §6. |
| `generic_valuation.py` | `GenericValuationRiskModel.rails()` **does** extrapolate — confirmed by probe. The difference is the whole story in §6. |
| `presets.py` / `presets.json` | `gold_reselect` shape = 35/60/65/30, curvature 1.0/1.0, mids null. `gold_optimized` = 35/45/50/30, c1.0/c2.0. Resolved by name, never restated. |
| `run_gold_stage_a_weights.py` (654 lines) + its test (633 lines, 20 pins) | The pattern to mirror: by-path harness load, the disclosure labels, the explicit feasibility-call discipline, and the test conventions (local script import, independent re-sweep, byte-identical determinism, no bare asserts). |
| `stage-a-weights-report.md` (precedent) | The RED→GREEN format, the "what I verified myself / where I made a judgement / concerns" self-review shape. |
| `indicator_catalog.py` | `GOLD_MACRO_NAMES` (10 gold macro legs) and `GENERIC_TECHNICAL_NAMES` (3 price oscillators) are both exported — so the gold allowlist is 13 names the module already publishes. |
| `fit_gold_indicators.py` | `ANCHOR_FORM = "rolling_z"`, `ANCHOR_ROLLING_WINDOW = 90`, `ANCHOR_ROLLING_Z = 1.0` — the no-trend anchor, re-derived independently and confirmed identical. |

### The two questions I was asked to answer up front

- **Does a gold profile exist?** **No.** Only `btc_v1()` and `eth_research_v1()`. Per the
  brief I did **not** edit `asset_profile.py`. The profile is built from the module's own
  public constructor `SdcaAssetProfile(...)` using the allowlist the module already
  publishes (`GOLD_MACRO_NAMES + GENERIC_TECHNICAL_NAMES`) and the pin set it already ships
  (`SdcaCycleWindows.gold_v1()`). A test asserts no gold factory exists, so if one ever
  ships the test fails and the runner stops building its own.
- **Does the objective consume cycle windows?** **No.** Verified three ways: the signature
  has no such parameter; `SdcaCycleWindows` does not appear in the function's source; and
  it builds its own folds via `make_walk_forward_folds`. **So ONE run is correct** — not two.
  The profile still carries `gold_v1()` because the model requires the field; it is inert,
  and `CYCLE_WINDOWS_INERT_LABEL` says so.

---

## 2. RED → GREEN

Fail-first was done by writing the spec against a runner that did not exist.

**RED** (no runner on disk, `pytest -q`):

```
collected 31 items
tests/dq/strategies/sdca/test_gold_published_stage_a.py ..........F...FF....F.............  [ 51%]
..
========================= 8 failed, 23 passed in 1.82s =========================
```

The 23 passing at RED were the pins about the *shipped module* rather than the runner
(the frozen grids, `_is_rank_score` not reading OOS, `extra_z` filtering) — correct
behaviour: those pins should be green before any of my code exists.

**Intermediate RED** after the first runner landed: 8 failures, all real. Two were my own
test bugs (an invalid `date(2020, 1, 40)` fixture date; a classmethod probe using
`getattr` on an already-bound method instead of `inspect.getattr_static`). Two exposed
**design findings in the runner**, not test bugs:

1. *A one-name sweep can never score below the baseline* — its grid contains the
   valuation-only row, so the best is `max(baseline, leg-on)`. The verdict vocabulary is
   therefore **keep / flat**, and `drop` is unreachable. Changed the runner, not the
   assertion.
2. *Wall time in the artifact broke byte-identical determinism* — and it should not be
   there at all. Wall time is a property of the machine, not a result; recording it would
   make every diff of the record against itself show a spurious change. Removed it from the
   payload with a `timing_note` explaining why.

**GREEN**:

```
collected 35 items
tests/dq/strategies/sdca/test_gold_published_stage_a.py ..................  [ 51%]
.................                                                        [100%]
============================== 35 passed in 1.65s ==============================
```

### The pins, and how each can fail

| Pin | Test |
|---|---|
| Shipped grids un-widened / un-narrowed | `test_the_shipped_function_still_declares_the_frozen_grids`, `test_the_runner_never_overrides_a_grid_or_the_fold_geometry` (scans the runner source for `grid=` / `valuation_grid=` / `n_folds=` / `holdout_frac=` / `oos_frac=`) |
| Independent re-sweep agrees on winner **and** count | `test_the_winner_is_the_argmax_of_an_independently_swept_full_grid` — re-implements the full loop from the spec, includes an **inverted** leg so a skipped name changes the argmax |
| OOS reported, never selected | `test_oos_is_reported_but_never_selects_the_winner` (behavioural: the fixture's OOS is the negative of its IS, so a peek at OOS picks differently) + `test_the_shipped_rank_function_cannot_read_the_oos_field` (source-level) |
| The rank does not gate, and that is disclosed | `test_the_rank_does_not_gate_on_the_floor_or_the_cap_and_that_is_disclosed` — a 0%-deployed, 95%-drawdown row still wins on IS; the flag is recorded |
| The floor basis differs between stages | `test_the_floor_basis_difference_between_the_two_stages_is_stated` |
| An all-cash OOS is **detected**, not narrated | `test_an_all_cash_oos_is_detected_and_never_presented_as_evidence` |
| Feasibility narrowing recorded, never silent | `test_a_name_over_the_coverage_limit_is_excluded_and_recorded`, `test_a_name_exactly_at_the_coverage_limit_is_kept`, `test_the_gate_is_the_worst_scored_window_not_the_span_average`, `test_a_leg_missing_only_at_the_very_end_of_the_span_is_still_searched` |
| One probe row per allowlist name | `test_every_allowlist_name_gets_exactly_one_per_extra_probe_row` — the fixture carries z for **all 13** names, so a name cannot go unreported |
| Determinism | `test_two_identical_runs_serialize_byte_identically` |
| No gold profile / no cycle windows / rails / curve | `test_the_profile_is_built_from_the_module_surface_and_says_so`, `test_the_objective_does_not_consume_cycle_windows_and_that_is_stated`, `test_the_rails_are_the_shipped_rolling_z_anchor_no_time_trend`, `test_the_curve_is_the_shipped_no_trend_gold_curve_not_a_power_law` |
| Nothing live touched | `test_the_runner_writes_only_to_scratch_and_never_touches_settings_or_supabase` |
| Clean `ValueError`s, no bare asserts | `test_the_runner_has_no_bare_assert_statements`, `test_an_unknown_allowlist_name_is_a_clean_refusal`, `test_every_searched_name_has_a_built_z_series` |
| Labels | `test_in_sample_and_oos_are_labelled_separately_everywhere`, `test_the_diagnostic_and_the_published_objective_are_never_blended`, `test_no_performance_claim_beyond_the_returned_metrics` |

---

## 3. The result

```
run                          evals   IN-SAMPLE  feasible   wall_s  weights
--------------------------------------------------------------------------
baseline_valuation_only          2      16.713         2      0.1  val=1 (valuation-only)
joint_sweep                   2186     119.964         3     59.6  val=0.5 weekly_rsi=1 weekly_macd=1
```

**Evaluation count: 2,186 joint + 2 baseline + 130 across the 13 probes.**
**Wall time: 59.6 s** for the joint sweep, 68.2 s for the whole run.

### Per-extra keep/drop — IN-SAMPLE vs-flat-DCA vs the valuation-only baseline

Each row is a single-leg call to the **shipped** search, so the table and the joint sweep
cannot drift apart.

| extra | decision | best weight | **IN-SAMPLE** vs-flat-DCA | Δ vs baseline | in joint | worst scored window |
|---|---|---|---|---|---|---|
| `weekly_rsi` | **keep** | 0.5 | **+104.499** | +87.786 | yes | 5.7% (`fold0_is`) |
| `weekly_macd` | **keep** | 0.5 | **+87.639** | +70.926 | yes | 11.0% (`fold0_is`) |
| `uup` | keep | 1.0 | +34.887 | +18.175 | no (coverage) | 53.7% (`fold0_is`) |
| `walcl` | keep | 1.0 | +31.561 | +14.848 | no (coverage) | 35.3% (`fold0_is`) |
| `real_rate` | keep | 1.0 | +29.549 | +12.836 | yes | 1.7% (`fold0_is`) |
| `gdx_gld` | keep | 1.0 | +28.004 | +11.291 | no (coverage) | 36.1% (`fold0_is`) |
| `gld_slv` | keep | 1.0 | +23.047 | +6.334 | no (coverage) | 34.6% (`fold0_is`) |
| `nfci` | keep | 0.5 | +20.990 | +4.277 | yes | 1.8% (`fold0_is`) |
| `breakeven_5y` | keep | 1.0 | +19.352 | +2.639 | yes | 1.7% (`fold0_is`) |
| `sma_band` | keep | 0.5 | +17.003 | +0.290 | yes | 2.6% (`fold0_is`) |
| `gvz` | flat | 0.0 | +16.713 | +0.000 | no (coverage) | 82.5% (`fold0_is`) |
| `hy_oas` | flat | 0.0 | +16.713 | +0.000 | no (coverage) | 100.0% (`fold2_oos`) |
| `ig_oas` | flat | 0.0 | +16.713 | +0.000 | no (coverage) | 100.0% (`fold2_oos`) |

**"flat" means no keep earned, not "drop".** A one-name sweep shares its grid with the
valuation-only row, so its best is `max(baseline, leg-on)` and a negative delta is
structurally unreachable. Whether a flat leg actively *hurts* is not observable from this
sweep — read the joint winner's weight vector for that.

### Fold detail (winner vs baseline)

| fold | window | baseline IS | winner IS | winner deployed (peak) | winner dd | feasible |
|---|---|---|---|---|---|---|
| 0 | 2004-11-18..2009-04-02 | +2.062 | **+69.052** | 100.00% | 27.19% | True |
| 1 | 2004-11-18..2013-08-15 | +4.453 | **+132.888** | 100.00% | 36.43% | True |
| 2 | 2004-11-18..2017-12-27 | +43.623 | **+157.951** | 100.00% | 44.89% | True |

Deployed capital is 100.00% peak in every winner fold, against the 10% floor. Drawdown
peaks at 44.89% in fold 2, inside the 50% cap. The baseline's fold 0 is flagged
**infeasible** on NET deployed (−47.33%) while peak-deployed is 100.00% — the floor-basis
difference in §5.

---

## 4. Shape vs the published `btc_sdca` reference

Reference: `valuation=1.0, m2=0.5, dxy=0.5, weekly_macd=0.5, weekly_rsi=0.25`
(SMA band and BTC/ETH RS at 0) — five legs, four partial-weight. **Shape comparison only:
not a tuning target, not a benchmark, nothing copied or steered toward.**

| | legs | partial-weight legs |
|---|---|---|
| published `btc_sdca` | 5 | 4 (0.5 / 0.5 / 0.5 / 0.25) |
| **gold, published objective (this run)** | **3** | **2** (`weekly_rsi=1.0`, `weekly_macd=1.0`) |
| gold, cycle-overlap diagnostic (preceding run) | 2 | 1 (one 0.5 leg) |
| gold, cycle-overlap, `require_extras=False` | 1 | 0 (valuation-only) |

**The published objective agrees with — and goes beyond — the diagnostic rather than
agreeing with its collapse.** The diagnostic's `require_extras=False` rows returned
valuation-only on both pin sets; the published objective returns `valuation=0.5` plus
**two full-weight oscillator legs**. The shape is no longer "valuation plus one 0.5 leg":
the winner carries two legs at full weight, which is closer to the `btc_sdca` precedent
than the diagnostic ever got, though still narrower (3 legs vs 5, and both gold legs sit on
the price oscillators rather than on macro).

Stated plainly: **the published objective overturns the valuation-only collapse.** That is a
headline finding. It is also a finding about **two different objectives answering two
different questions**, so it is not a licence to merge them — `NOT_THE_DIAGNOSTIC_LABEL`
carries that instruction into the artifact, the console and the chart.

---

## 5. Two defects found in the shipped path

### 5a. The rank does not gate on the floor or the cap

`_is_rank_score` is the plain mean in-sample `vs_flat_dca_pct`. It does not read `feasible`
and does not apply the cap — its own docstring says Stage B's gates are not applied here.
The artifact therefore reports the flag **as recorded fact**, and `RANK_NOT_GATED_LABEL`
says in substance that nothing was vetoed. Pinned behaviourally: a row with 0% deployed and
95% drawdown still wins on IS.

Related, and worth the owner's attention: the floor is measured on **NET**
`capital_deployed_pct` in Stage A but on **PEAK** `capital_deployed_peak_pct` in Stage B
(`FLOOR_BASIS_LABEL`). The baseline's fold 0 reads infeasible here despite peak-deployed
100.00%, because net went to −47.33% after selling into strength.

### 5b. OOS is structurally VOID with the owner-ruled no-trend rails

Every OOS window deployed **zero** capital: peak 0.00%, drawdown 0.00%, and
`vs_flat_dca_pct` identical to the valuation-only baseline to the digit (−6.491) for
*every* weight vector. That identity is the tell — it is one all-cash book repeated.

Direct probe, not inference:

```
RollingZRiskModel, dates AFTER the fit window:      low/median/high = null, null, null
GenericValuationRiskModel, dates AFTER the fit window: 750.97 / 1018.68 / 1254.37   (extrapolates)
```

`optimize_stage_a_by_backtest` refits rails on each fold's IS window and evaluates OOS on
those rails. That is correct per the #3173 no-leak rule **and fine for a model that
extrapolates** — the trend rails do. But `RollingZRiskModel` is a *trailing* model: its
`rails()` left-joins a stored `(date, mu, sigma)` table, so every later date is null → null
rails → null risk → no trades → all cash.

**Consequence: the no-trend rolling-z anchor and the engine's per-fold walk-forward are not
compatible as written.** In-sample numbers are unaffected (in-sample dates are inside the fit
window). Stage B must score folds through the concatenated-history rolling loop that
`run_gold_curve_search.py` already carries on this branch (and which already calls the
engine walk-forward void for these rails), or use rails that extrapolate.

**Not fixed here.** A fix belongs in `walk_forward.py` or `rolling_z.py`, both owner
territory and both on my STOP list. The runner *computes* `oos_is_degenerate` from the fold
metrics rather than asserting it in prose, so the disclosure cannot be wrong about its own
subject, and the chart marks the OOS panel VOID at the point of use.

---

## 6. Feasibility call

| | |
|---|---|
| Allowlist (published name set) | **13** — `stage_a_search_names(gold_profile())` |
| Un-narrowed projection | `3**13 × 3 = 4,782,969` evals × **measured 33.0 ms** ≈ **43.9 h** |
| Joint sweep actually run | **6 names, 2,186 evals, 59.6 s** |
| Rule | z present on ≥75% of the leg's **worst scored window** |

**The rule was wrong once and I fixed it after measuring.** My first version gated on the
aggregate **searchable-span** share of missing z, which admitted 11 names (531,441 evals
≈ 4.9 h) and re-created the infeasibility. Re-measuring showed why: the macro legs' missing
history is concentrated in the **earliest in-sample fold** — `uup` averages 13.4% missing
across the whole span while missing **53.7% of `fold0_is`**. The span average is exactly the
statistic that hides the folds which decide the winner. The rule now gates on the worst
scored window, which is also the granularity at which the null does damage (the composite
blend nulls any day one enabled leg is missing). Both numbers are reported per name.

Held out: `uup` (53.7%), `gvz` (82.5%), `walcl` (35.3%), `gdx_gld` (36.1%), `gld_slv`
(34.6%) — all on `fold0_is`; `hy_oas` and `ig_oas` at 100% on `fold2_oos` (the BAML spread
pair has no data before 2020, so it is simply absent from this search span).

**No name goes unreported.** Each of the 13 gets a single-leg probe row regardless, so the
per-extra table covers the whole allowlist. Recorded in four places: `FEASIBILITY_NOTE` in
the script, the JSON, the console, and `digiquant/ARCHITECTURE.md`.

---

## 7. Chart

`digiquant/scripts/plot_gold_published_stage_a.py` — hand-rolled stdlib SVG only (no
matplotlib / numpy / pandas), mirroring `plot_gold_pin_set_fits.py`'s `_text` / `_wrap` /
`_block` / hatch-pattern pattern. Five panels:

1. **Keep / no-keep per extra**, signed around the baseline; kept legs solid green to the
   right, no-keep hatched red (texture **and** hue, so it survives greyscale and
   colour-vision deficiency).
2. **Deployed capital** against the 10% floor, drawn as a labelled rail.
3. **Drawdown** against the 50% cap, drawn as a labelled rail.
4. **The shape comparison** — gold's legs and partial-weight count against `btc_sdca`.
5. **OOS below a heavy rule, headed VOID**, with the mechanism stated where it is read.

The rails are labelled as rails, not filters, because the rank did not gate on them. Valid
XML (checked with `xml.dom.minidom`). Written to
`apps/digiquant-web/public/gold_charts/gold_published_stage_a.svg` and copied to
`digiquant/.scratch/gold_pngs/` (both UNTRACKED). 32,079 bytes.

**HTTP code: `200`** — `curl -s -o /dev/null -w '%{http_code}'`
`http://127.0.0.1:4011/gold_charts/gold_published_stage_a.svg`. The 4011 server is served
from the **rescue** worktree (which has `node_modules`; this clean one does not), so the SVG
was copied to
`.worktrees/task/4804-sdca-strategy-for-gold--gld/apps/digiquant-web/public/gold_charts/`
for the check.

---

## 8. Verification

| Gate | Result |
|---|---|
| New spec file | **35 passed** |
| Full `tests/dq/strategies/sdca/` | **688 passed, 1 skipped, 1 failed** |
| The 1 failure | `test_gold_sell_mask.py::test_frozen_box_grounds_on_real_inputs` — `FileNotFoundError: digiquant/.scratch/gold_mayer_multiple.json`. **PRE-EXISTING** (the artifact is in no commit at base). Not fixed, not worked around. |
| The 1 skip | `test_gold_pin_set_fits.py` side-effect probe, "no fits artifact present" — pre-existing behaviour. |
| `ruff check` (3 new files) | All checks passed |
| `ruff format --check` (3 new files) | 3 files already formatted |
| `make doc-check` | `check_doc_links: OK (448 markdown files scanned)` |

Untracked and deliberately **not** committed: `.scratch/gold_published_stage_a.json`,
`.scratch/gold_pngs/`, `apps/digiquant-web/public/gold_charts/`, and
`digiquant/data/price-history` (the **symlinked** CSVs — never commit that symlink).

---

## 9. SHAs

| SHA | Commit |
|---|---|
| `5448f26fa` | research(digiquant): run the published gold Stage A keep/drop (#4804) — runner + tests |
| `0d3ff552e` | research(digiquant): chart the published gold Stage A (#4804) — chart script |
| `2967fe3fb` | docs(digiquant): document the published gold Stage A (#4804) — ARCHITECTURE.md |
| `4a8607700` | branch tip before this work (the cycle-overlap diagnostic run) |

---

## 10. Self-review

**What I verified myself rather than taking on trust:**

- The 33.0 ms/eval rate is **measured on this machine against this calendar** (a timed
  k=8 sweep: 19,682 evals in 650.4 s), not estimated. It is the entire basis of the
  feasibility arithmetic.
- The "objective does not consume cycle windows" claim is checked three ways — signature,
  source text, and the fold construction — not inferred from the absence of a keyword.
- The OOS void is a **direct probe** of both rail models on dates after their fit window,
  not a deduction from the identical numbers. Both probes are in §5b.
- The coverage numbers are recomputed from the artifact rather than trusted from the first
  run's console — which is how I caught that my first rule was the wrong statistic.
- The loader path is `load_sdca_ohlcv(symbols=["GLD-USD"], data_path=...)`, which reads the
  `close` **column by name**; column index 1 is `open`, a trap that already caused one
  wrong-date incident in this repo.
- The feasibility rule is pinned to **inclusivity at the boundary** and to the *worst
  window*, with a test that a leg averaging well but missing half of fold 0 is still held
  out, and a test that a merely-late leg is **not** held out. Both directions, so the rule
  cannot be quietly tuned either way.

**Where I made a judgement the owner may want to revisit:**

1. **The coverage rule and its 25% budget.** It follows from data coverage, not from any
   score, and it is recorded everywhere — but 25% is my number, and it is the one thing
   that could bias §4's shape finding (four macro legs are held out, and `uup` alone would
   add +18.2). The full 13-name sweep is ~43.9 h; that is a compute decision worth making
   deliberately.
2. **Per-extra verdicts as keep/flat rather than keep/drop.** Forced by the shipped grid,
   not chosen — but it means the table cannot distinguish "harmless" from "harmful". If the
   owner wants that distinction it needs a leave-one-out sweep on the joint subset, which is
   a different (and larger) experiment.
3. **Building the gold profile in the script instead of in `asset_profile.py`.** Followed
   the brief. The alternative — a first-class `gold_research_v1()` factory — is cleaner and
   is what the module's own pattern implies, but it is a source change.

**Concerns:**

1. **The OOS void (§5b) is the most important thing here.** It is not a gold problem: any
   asset whose rails do not extrapolate gets a silently all-cash OOS under
   `optimize_stage_a_by_backtest`. Nothing flags it today — the numbers look like a real,
   mildly negative result. Worth a guard in `walk_forward.py` that refuses (or loudly warns)
   when a fold's OOS deploys zero capital.
2. **The in-sample number is a selected upper bound, twice over.** The winner is a maximum
   over the frozen weight grid, scored against the same in-sample folds it was fitted on,
   over 2004–2017 GLD — a strong secular bull market. +119.964% vs flat DCA is what the
   metrics say and nothing more. It is **not** evidence of edge, and the OOS panel that
   would normally temper it is void (§5b), so there is currently **no** out-of-sample read
   on these weights at all.
3. **The rank does not gate (§5a)**, so the deployed floor and the drawdown cap were
   reported but never binding. Stage A's job here is ordering candidates; feasibility is
   Stage B's. But it means "subject to a 10% floor and a 50% cap" is true of the objective's
   *definition* and not of its *enforcement* at this stage.
4. **`weekly_rsi` and `weekly_macd` are both price oscillators on the same close series**,
   and `sma_band` too. The winner uses the two weekly ones at full weight with valuation at
   0.5, so the composite leans hard on one family. The known overlap between `sma_band` and
   the rolling-z anchor is disclosed in the gold seed scripts; the RSI/MACD pair adds a
   further collinearity the same scripts do **not** quantify. That is a next question, not
   a defect in this run.
5. **`hy_oas` / `ig_oas` are absent from the search span entirely** (100% null). They are
   reported as flat with that coverage quoted, not as tested-and-rejected. They have never
   been evaluated on this calendar.