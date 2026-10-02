# Gold combined-run note — Plan 8 Task 2 (#4804)

Untracked analysis. No code changed, nothing applied, no promotability verdict.
Rule: every number cites file+key; any number without a citation was removed
(not written). Values are full-precision from JSON; 2dp forms match the stdout
log lines cited alongside.

## 1. Comparison table (gate rows; bars as-run)

Combined seed = `gold_seed_v3.json` (valuation=1.0, m2=0.5, uup=0.5, rest 0.0;
`gold_curve_search_combined.stdout.log`: `weights={...uup...}`).
Search phase identical to v3 (same seed file, same grid): 1728 shapes ×
4 windows = 6912 evaluations, 1080 feasible, winner worst_vs_flat −4.53%,
same searched winner (buy_max 35 / buy_knee 45 / sell_knee 50 / sell_max 30 /
curv 1.0/2.0 / sell-mid 85), projection drops mid-tier keys True
(`gold_curve_search_combined.stdout.log`: `search:` / `gate projection` lines;
`gold_curve_search_v3.stdout.log`: identical `search:` / winner lines).
So combined-vs-v3 gate deltas are a rails+floor effect, not a new winner.

| variant (rails / floor) | mean OOS | beats_flat | F0 oos / dd / feas | F1 oos / dd / feas | F2 oos / dd / feas | sens stable / maxΔ / n |
|---|---|---|---|---|---|---|
| v1 (generic / 10) | +14.52% (`gold_curve_search.stdout.log` via `gold_promotion_packet.md` §2b: `gate: mean_oos_vs_flat=+14.52%`) | true (derived: mean>0; `optimize.py:390` defines beats as mean_oos>0) | +38.20 / 7.35 / False (packet §2b `fold 0` cell) | −11.19 / 26.05 / True (packet §2b `fold 1` cell) | +16.54 / 18.77 / True (packet §2b `fold 2` cell) | False / 3.86 / UNRECORDED (packet §2b sens cell carries no neighbor count; v1 log overwritten) |
| v3 = uup (UNRECORDED / 10) | 9.965535247091468 (`gold_curve_search_v3.json: gate.mean_oos_vs_flat_dca_pct`) | true (`gate.beats_flat_dca_oos`) | 23.30769238238368 / 7.097155792439212 / false (`gate.per_fold[0]`) | −11.160507911119943 / 26.05633623913365 / true (`gate.per_fold[1]`) | 17.749421270010668 / 18.773525870963113 / true (`gate.per_fold[2]`) | True / 0.44793236861546504 / 49 (`gate.sensitivity_stable`, `gate.sensitivity_max_abs_delta`, `gate.sensitivity_neighbor_count`) |
| B = railsB (quad_5y / 10) | 11.337767562314419 (`gold_curve_search_railsB.json: gate.mean_oos_vs_flat_dca_pct`) | true (`gate.beats_flat_dca_oos`) | 25.786466188299826 / 7.341069193761187 / false (`gate.per_fold[0]`) | −8.24530252237129 / 11.124051490494102 / false (`gate.per_fold[1]`) | 16.47213902101472 / 18.773492728315215 / true (`gate.per_fold[2]`) | False / 2.8342806254326103 / 46 (same three sens keys) |
| combined = uup×5y (quad_5y / 0) | 6.52686200889255 (`gold_curve_search_combined.json: gate.mean_oos_vs_flat_dca_pct`) | true (`gate.beats_flat_dca_oos`) | 11.396927426848858 / 6.605621748830448 / false (`gate.per_fold[0]`) | −5.08902284405528 / 6.01890813304925 / true (`gate.per_fold[1]`) | 13.272681443884071 / 18.483543352055246 / false (`gate.per_fold[2]`) | True / 0.7924224025636422 / 49 (same three sens keys) |

Mean cross-checks (derived, `_mean_oos` averages all folds regardless of
flags, `optimize.py`): combined (11.396927426848858 − 5.08902284405528 +
13.272681443884071)/3 = 6.52686200889255 ✓; B cells → 11.337767562314419 ✓;
v3 cells → 9.965535247091468 ✓; v1 (38.20 − 11.19 + 16.54)/3 = 14.5167 ≈ 14.52 ✓.
v3 rails variant UNRECORDED: `gold_curve_search_v3.stdout.log` has no
`rails-variant:` line (9-line log; flag defaults to `default` per
`run_gold_curve_search.py:169-172`, but the run may predate the flag — not
asserted). B rails = quad_5y (`gold_curve_search_railsB.stdout.log`:
`rails-variant: quad_5y`); combined rails = quad_5y
(`gold_curve_search_combined.stdout.log`: `rails-variant: quad_5y`,
`exit=0 wall=34s`).

## 2. As-written fold readings (combined; mechanical, not judgment)

- F0: infeasible, positive (+11.40), dd 6.61.
- F1: feasible, negative (−5.09), dd 6.02. No bar touches a fold's sign.
- F2: infeasible, positive (+13.27), dd 18.48.
- beats_flat_dca_oos True (mean +6.53 > 0).
- sensitivity stable True (maxΔ 0.79 ≤ bar 2.0, `SENSITIVITY_SPIKE_PCT`,
  `walk_forward.py:37`; stable rule `optimize.py` sensitivity section).

## 3. As-proposed reading (floor 0 already applied — what REMAINS failing)

- Floor clause is vacuous at 0 for any deployed ≥ 0, yet F0/F2 stay
  infeasible → by elimination deployed < 0 on both (derivation in §6; the
  Plan-4 Table-2 `feas*` prediction carried an explicit "provided deployed ≥ 0"
  proviso, and the record shows the proviso fails on F0/F2). The floor-0
  proposal therefore does NOT admit F0/F2 — the veto moved from
  "deployed < 10" to "deployed < 0", magnitude unmeasured in both cases.
- Cap: no veto anywhere (max dd 18.48 ≤ 50 on combined; all-variant max 26.05).
- Sensitivity: no bar failing (0.79 ≤ 2.0, stable).
- What remains failing: F1 negative while feasible (−5.09 — sign, not a bar
  matter) and F0/F2 infeasible via the negative-deployed clause.

## 4. uup×5y interaction arithmetic (derived differences of cited cells)

- Δv3 = 9.965535247091468 − 14.52 = −4.554464752908532 (≈ −4.55)
- ΔB = 11.337767562314419 − 14.52 = −3.182232437685581 (≈ −3.18)
- Sum of single deltas = −7.736697190594113 (≈ −7.74)
- Δcombined = 6.52686200889255 − 14.52 = −7.99313799110745 (≈ −7.99)
- Additive prediction = 14.52 − 7.736697190594113 = 6.783302809405887 (≈ 6.78);
  actual 6.52686200889255 (≈ 6.53).
- Interaction = −7.99313799110745 − (−7.736697190594113) = −0.256440800513337
  (≈ −0.26pp): the combination underperforms the additive prediction by
  0.26pp — mildly SUB-ADDITIVE (the joint loss exceeds the sum of the
  single losses by 0.26pp).
- Rails-only decomposition (same searched winner, v3 → combined; derived):
  Δmean −3.4387 = F0 −11.9108 (11.396927426848858 − 23.30769238238368) /
  F1 +6.0715 (−5.08902284405528 − −11.160507911119943) /
  F2 −4.4767 (13.272681443884071 − 17.749421270010668). Quad_5y rails cost
  F0/F2 and halve the F1 loss, net −3.44.

## 5. Explicit non-claims

- No promotion verdict; no bar change (floor, cap, sens) decided or applied.
- No holdout decision: `grep -ci holdout` = 0 over combined JSON and stdout
  log (Task 1 report §3); `_holdout_metrics` never serialized.
- No hy/ig decision; no coverage claim beyond the 5499-bar seed line.
- No worst-neighbor attribution: develop `SensitivityReport` carries none
  (script says so; Task 1 report §3). Knee-cliff status unchanged: UNMEASURED.
- Unrecorded, not guessed: per-fold capital_deployed_pct (all runs; writer
  emits oos/dd/feasible only, `run_gold_curve_search.py:266-268`); v1
  sensitivity neighbor count; v3 rails variant.
- Sensitivity–uup pattern is an observed correlation with n=5 (see report),
  not a proven cause. Confounds on the record: rails variant (v3 unrecorded
  vs quad_5y on B/combined), winner shape (v1 35/60/65/30 vs 35/45/50/30
  elsewhere), neighbor counts (46/47/49).

## 6. Puzzle 1 derivation (code path traced, not memory)

Gate call (`run_gold_curve_search.py:245-261`): `--deployed-floor 0` builds
`SdcaOptimizeObjective(capital_deployed_floor_pct=0.0, max_drawdown_cap_pct=50.0)`
and passes it as `objective=` to `run_sdca_walk_forward`. That function's
signature (`optimize.py:320`) has NO gates parameter. It calls
`score_trial_on_folds` (`optimize.py` gate section), which sets
`feasible=is_feasible(out_of_sample, objective)` (`walk_forward.py:263`).
`is_feasible` (`walk_forward.py:287-293`) has exactly two clauses:
deployed < floor → False; dd > cap → False; else True.
`CurveOptimizeGates` (require_2025_sells=False, concentration bars 0.0/off;
`run_gold_curve_search.py:96-...`) enters ONLY the search phase via
`score_shape_on_index(..., gates=GATES)` (`run_gold_curve_search.py:214-215`).
Exclude-by-path: require_sells / concentration gates CANNOT veto gate folds —
they are not in the gate call chain, and concentration bars are 0.0 (off)
even where they do apply.
With floor=0: F0/F2 feasible=False requires deployed < 0 or dd > 50.
Recorded dd (F0 6.605621748830448, F2 18.483543352055246,
`gold_curve_search_combined.json: gate.per_fold`) are ≤ 50 → the cap clause
passes → by elimination the floor clause fires: capital_deployed_pct < 0.
Mechanism (code-derived): `backtest.py:183` net_deployed = initial_cash − cash;
`backtest.py:234` deployed_pct = final net / initial × 100. Negative ⟺ final
cash > initial ⟺ sell proceeds exceeded gross spend on that OOS window. The
gated shape sells (sell_max_rate 30.0), so a sell-into-strength OOS window
(F0 OOS 2009-2013 and F2 OOS 2017-2022 are both strong positives, +11.40 /
+13.27) reaching cash > initial is structurally unsurprising — but the exact
deployed values are UNMEASURED from the record (missing field:
per-fold `capital_deployed_pct`; writer limitation, not an oversight to fill).
Answer: veto = floor clause on negative deployed (proceeds > spend); magnitude
unattributed; no third gate exists in this path.
