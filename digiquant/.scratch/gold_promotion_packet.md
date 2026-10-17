# Gold promotion packet — Plan 4 Task 5 (#4804)

Untracked decision packet. No settings write, no preset write, no sidecar/coefficients
check-in, no `--push-supabase`, no workflow edits. Every number in sections 2–4 carries
a source file + key citation; numbers without citations were removed per the brief.

## 1. Verdict

**NOT-YET** — no variant clears the gate as written, broadening hurt the mean, and two
structural failures (F1-negative, unstable sensitivity) persist across all three votes.

## 2. Gate table (v2 winner shapes + per-fold + sensitivity + mean, beside v1 for delta)

Candidate for promotion (if ever): **v2-deep** (primary, v1-comparable calendar).
Fear-gauge variant: **v2-full**. Baseline: **v1** (record from stdout log — on-disk
`gold_curve_search.json` was overwritten by the full run per Task 3).

### 2a. Search + winner shape

| field | v1 (baseline) | v2-deep (candidate) | v2-full (variant) |
|---|---|---|---|
| vote weights | valuation=1.0, m2=0.5, dxy=0.5 (`gold_curve_search.stdout.log`: `weights={...}`) | valuation=1.0, m2=0.5, dxy=0.5, walcl=0.5, breakeven_5y=0.25, nfci=0.25, gdx_gld=0.5, gld_slv=0.5; gvz=0.0, hy/ig=0.0 (`gold_curve_search_v2deep.json: weights`) | deep + gvz=0.5; hy/ig=0.0 (`gold_curve_search_v2.json: weights`) |
| shapes × evals | 1728 × 6912 (`gold_curve_search.stdout.log`: `grid: 1728 tiered shapes x 4 windows` / `search: 6912 evaluations`) | 1728 × 6912 (`gold_curve_search_v2deep.json: search.num_shapes` = 1728, `search.num_evaluations` = 6912) | 1728 × 6912 (`gold_curve_search_v2.json: search.num_shapes` = 1728, `search.num_evaluations` = 6912) |
| feasible | 1080 (`gold_curve_search.stdout.log`: `1080 feasible`) | 1080 (`gold_curve_search_v2deep.json: search.num_feasible` = 1080) | 216 (`gold_curve_search_v2.json: search.num_feasible` = 216) |
| winner worst_vs_flat | +9.00% (`gold_curve_search.stdout.log`: `winner worst_vs_flat=9.00%`) | +6.72% (`gold_curve_search_v2deep.json: search.worst_vs_flat_dca_pct` = 6.719458615029428) | −26.31% (`gold_curve_search_v2.json: search.worst_vs_flat_dca_pct` = −26.310781887747737) |
| winner shape (buy_max / buy_knee / sell_knee / sell_max) | 35 / 60 / 65 / 30, single-knee, no mids (`gold_curve_search.stdout.log`: `shape={'buy_max_rate': 35.0, 'buy_knee_risk': 60.0, 'sell_knee_risk': 65.0, 'sell_max_rate': 30.0, ... 'buy_mid_knee_risk': None, 'sell_mid_knee_risk': None}`) | 35 / 45 / 50 / 30 + sell-mid 85, curv 1.0/2.0 (`gold_curve_search_v2deep.json: search.shape` = {buy_max_rate 35.0, buy_knee_risk 45.0, sell_knee_risk 50.0, sell_max_rate 30.0, buy_curvature 1.0, sell_curvature 2.0, sell_mid_knee_risk 85.0}) | 35 / 45 / 50 / 10 + sell-mid 85, curv 1.0/2.0 (`gold_curve_search_v2.json: search.shape` = same with sell_max_rate 10.0, sell_mid_knee_risk 85.0) |
| gate projection drops mid-tier | false (`gold_curve_search.stdout.log`: `gate projection drops mid-tier keys: False`) | true (`gold_curve_search_v2deep.json: gate_projection_drops_mid_tier` = true) | true (`gold_curve_search_v2.json: gate_projection_drops_mid_tier` = true) |
| gated shape | = search shape (projection intact) | single-knee projection, sell_mid → null (`gold_curve_search_v2deep.json: gated_shape.sell_mid_knee_risk` = null) | single-knee projection, sell_mid → null (`gold_curve_search_v2.json: gated_shape.sell_mid_knee_risk` = null) |

### 2b. Gate: mean OOS + per-fold OOS/dd/feasibility + sensitivity

| variant | mean OOS | F0 OOS / dd / feas | F1 OOS / dd / feas | F2 OOS / dd / feas | sens |
|---|---|---|---|---|---|
| v1 | +14.52% (`gold_curve_search.stdout.log`: `gate: mean_oos_vs_flat=+14.52%`) | +38.20% / 7.35% / false (`gold_curve_search.stdout.log`: `fold 0: oos_vs_flat=+38.20% max_dd=7.35% feasible=False`) | −11.19% / 26.05% / true (`gold_curve_search.stdout.log`: `fold 1: oos_vs_flat=-11.19% max_dd=26.05% feasible=True`) | +16.54% / 18.77% / true (`gold_curve_search.stdout.log`: `fold 2: oos_vs_flat=+16.54% max_dd=18.77% feasible=True`) | unstable, maxΔ 3.86 (`gold_curve_search.stdout.log`: `sensitivity_stable=False (max_abs_delta=3.86)`) |
| v2-deep | +5.67% (`gold_curve_search_v2deep.json: gate.mean_oos_vs_flat_dca_pct` = 5.667001624715854), beats_flat true (`gate.beats_flat_dca_oos`) | +10.85% / 5.47% / false (`gate.per_fold[0]`: oos 10.851864378460307, dd 5.473593738863906, feasible false) | −9.14% / 24.49% / true (`gate.per_fold[1]`: oos −9.13870465625709, dd 24.494610094745443, feasible true) | +15.29% / 18.76% / true (`gate.per_fold[2]`: oos 15.287845151944346, dd 18.76410093403125, feasible true) | unstable, maxΔ 2.40, neighbors 47 (`gate.sensitivity_stable` = false, `gate.sensitivity_max_abs_delta` = 2.3979045677131543, `gate.sensitivity_neighbor_count` = 47) |
| v2-full | +3.04% (`gold_curve_search_v2.json: gate.mean_oos_vs_flat_dca_pct` = 3.043631068418936), beats_flat true (`gate.beats_flat_dca_oos`) | +2.37% / 1.49% / false (`gate.per_fold[0]`: oos 2.3701814557279155, dd 1.4915224077174467, feasible false) | −8.43% / 24.45% / true (`gate.per_fold[1]`: oos −8.430071334200761, dd 24.447740317320328, feasible true) | +15.19% / 18.75% / true (`gate.per_fold[2]`: oos 15.190783083729652, dd 18.75447264299652, feasible true) | unstable, maxΔ 3.87, neighbors 47 (`gate.sensitivity_stable` = false, `gate.sensitivity_max_abs_delta` = 3.8740175212303365, `gate.sensitivity_neighbor_count` = 47) |

### 2c. Deltas (derived: cited cells above differenced; no new measurement)

- v1 → deep: feasible 1080 → 1080 (derived: `gold_curve_search.stdout.log` 1080 feasible vs `gold_curve_search_v2deep.json: search.num_feasible` 1080); winner-worst +9.00 → +6.72 (derived: log `9.00%` vs v2deep `search.worst_vs_flat_dca_pct` 6.719458615029428); mean +14.52 → +5.67, Δ −8.85 (derived: log `+14.52%` vs v2deep `gate.mean_oos_vs_flat_dca_pct` 5.667001624715854); F0 +38.20 → +10.85 both infeasible (derived cells above); F1 −11.19 → −9.14, Δ +2.05 (derived cells above); F2 +16.54 → +15.29, Δ −1.25 (derived cells above); sens 3.86 → 2.40, both unstable (derived: log `max_abs_delta=3.86` vs v2deep `gate.sensitivity_max_abs_delta` 2.3979045677131543).
- deep → full: winner sell_max 30 → 10 (derived: v2deep `search.shape.sell_max_rate` 30.0 vs v2full `search.shape.sell_max_rate` 10.0); feasible 1080 → 216 (derived: v2deep `search.num_feasible` 1080 vs v2full `search.num_feasible` 216); winner-worst +6.72 → −26.31 (derived keys above); mean +5.67 → +3.04, Δ −2.63 (derived: `gate.mean_oos_vs_flat_dca_pct` 5.667001624715854 vs 3.043631068418936); F0 +10.85 → +2.37 (derived per_fold[0] cells); F1 −9.14 → −8.43, Δ +0.71 (derived per_fold[1] cells); F2 +15.29 → +15.19, Δ −0.10 (derived per_fold[2] cells); sens 2.40 → 3.87, both unstable (derived max_abs_delta keys above).

### 2d. Fold geometry (shared calendar; risk availability differs for full)

- F0 IS 2004-11-18..2009-04-02, OOS 2009-04-03..2013-08-15; F1 IS ..2013-08-15, OOS 2013-08-16..2017-12-27; F2 IS ..2017-12-27, OOS 2017-12-28..2022-05-11; holdout 2022-05-12..2026-09-29 never scored (`task-3-report.md`: Fold dates — recomputed via `make_walk_forward_folds` same call+args as script).
- Deep folds exactly match v1 folds; full differs only in risk availability (GVZ null until 2008-06-30), not geometry (`task-3-report.md`: Fold dates).
- Coverage: v1 seed 5107 bars (`gold_macro_expansion.json: candidates.seed.coverage` = 5107); v2-deep 5102 bars = 99.9% of v1 (`gold_price_family_expansion.json: candidates.ratio_pair.coverage` = 5102; `task-3-report.md`: New P3); v2-full 4591 bars = 89.9% of v1, GVZ-inception-bound (`gold_macro_expansion.json: candidates.vol_and_liquidity.coverage` = 4591; `task-3-report.md`: P3 diagnosis — GVZ first bar 2008-06-03, v2 first valid risk bar 2008-06-30).
- Holdout absence: `"holdout" in json` false for deep and full; writer never serializes `_holdout_metrics` — gate keys are beats/mean/per_fold/sens only (`task-3-report.md`: Holdout-absence confirmations).

## 3. Vote: final weight vector (v2) + hy/ig status + collinearity flags

### 3a. Final weight vectors (v2)

- v2-deep (`gold_curve_search_v2deep.json: weights`): valuation 1.0, m2 0.5, dxy 0.5, walcl 0.5, breakeven_5y 0.25, nfci 0.25, gdx_gld 0.5, gld_slv 0.5; gvz 0.0, hy_oas 0.0, ig_oas 0.0, rs_eth 0.0, weekly_rsi 0.0, weekly_macd 0.0, sma_band 0.0.
- v2-full (`gold_curve_search_v2.json: weights`): identical with gvz 0.5; hy_oas 0.0, ig_oas 0.0.
- hy_oas/ig_oas are 0.0 in every v2 weight vector by construction (Task-2 red — `task-2-report.md`: Task 3 entry ticket granted: gate runs hy/ig at 0.0 citing the gap JSON).

### 3b. hy/ig status: Task-1 decision + Task-2 depth block

- Task-1 duel (offline, truncated window): hy_only and ig_only both coverage 732 (`gold_hy_ig_duel.json: candidates.hy_only.coverage` = 732, `candidates.ig_only.coverage` = 732) with buy-zone share 0.0 both (`gold_hy_ig_duel.json: decision.hy_buy_zone_share` = 0.0, `decision.ig_buy_zone_share` = 0.0) → tie on primary criterion; tie-break keeps **ig_oas** on lower max|r| 0.635 < 0.674 (`gold_hy_ig_duel.json: decision` = {keep ig_oas, ig_max_abs_r 0.635, hy_max_abs_r 0.674}); seed repro diff 0.0 (`gold_hy_ig_duel.json: seed_repro_max_abs_diff` = 0.0).
- Thin-basis warning: decision rests entirely on the tie-break (margin 0.039, derived: `gold_hy_ig_duel.json: decision.hy_max_abs_r` 0.674 − `decision.ig_max_abs_r` 0.635), both legs rich over a 2023-09-30+ bull window (`task-1-report.md`: Concerns) — re-confirmation at full depth required before any gate weight.
- Task-2 depth block: verifier exit 1 with exactly the two BAML gaps (`gold_depth_handoff.md`: gap JSON — BAMLH0A0HYM2 have_first 2023-09-30 / have_rows 785, BAMLC0A0CM have_first 2023-09-30 / have_rows 784; need_first 1996-12-31, need_rows 7000). Follow-up trigger: re-run duel + gate only after verifier exits 0 (`gold_depth_handoff.md`: Follow-up trigger). Until then hy/ig stay at weight 0.

### 3c. Collinearity flags (standing, cited)

- hy–ig pair 0.86 — keep-one premise confirmed (`gold_hy_ig_duel.json: correlations.hy_oas.ig_oas` = 0.86; also `gold_macro_expansion.json: correlations.hy_oas.ig_oas` = 0.86).
- dxy–gdx_gld ratio max 0.514 (`gold_price_family_expansion.json: correlations.dxy.gdx_gld` = 0.514) — flagged for the ratio-leg read.
- nfci–hy 0.674 / nfci–ig 0.635 (`gold_hy_ig_duel.json: correlations.hy_oas.nfci` = 0.674, `correlations.ig_oas.nfci` = 0.635) — what drove the thin tie-break.
- Standing attribution context (IS, not gate): seed vs-flat +117.09 (`gold_attribution.json: seed.vs_flat_dca_pct` = 117.09435050807886), challenger log-linear identical (`gold_attribution.json: challenger_log_linear.vs_flat_dca_pct` = 117.09435050807886), macro load-bearing on drop_m2/drop_dxy deltas −66.97/−69.30 (`gold_attribution.json: drop_m2.delta_vs_seed_pp` = −66.97105069663033, `drop_dxy.delta_vs_seed_pp` = −69.3001937185751).

## 4. Bars: current vs recommended (Task-4 block) + what each change would require

Current bars (library defaults; gate script passes no objective so defaults hold — `task-4-report.md`: Sources):

- deployed floor 10% (`digiquant/src/digiquant/strategies/sdca/walk_forward.py:50` — `capital_deployed_floor_pct` default 10.0; pinned `tests/dq/strategies/sdca/test_walk_forward.py:59`).
- dd cap 50% (`walk_forward.py:51` — `max_drawdown_cap_pct` default 50.0; pinned `test_walk_forward.py:59,80`).
- sensitivity bar 2.0 (`walk_forward.py:37` — `SENSITIVITY_SPIKE_PCT = 2.0`, stable iff maxΔ ≤ bar per `optimize.py:420`; NO test pin).
- Feasibility = deployed ≥ floor AND dd ≤ cap (`walk_forward.py:287-293` — `is_feasible`).

Recommended (Task-4 RECOMMENDATION, `gold_calibration_note.md`: RECOMMENDATION — owner-accept required, nothing applied):

1. **floor 10 → 0, gold scope.** Cells: deep F0 (+10.85, dd 5.47), full F0 (+2.37, dd 1.49), v1 F0 (+38.20, dd 7.35) — all floor-vetoed by elimination with dd far under the cap, so each veto is sizing, not risk (`gold_calibration_note.md`: Counterfactual table 1). Floor 5 NOT recommended: F0 at floor 5 INDETERMINATE (deployed unmeasured), so 5 buys no provable fix (`gold_calibration_note.md`: Counterfactual table 2). **Requires:** library edit (gold-scope objective defaults) or preset-bars equivalent; alternatively carried as an override-on-record promotion without moving library bars — BTC precedent: `btc_optimized` promoted 2026-09-29 with fold-1 dd veto (max_dd 51.84 vs cap 50) + unstable sensitivity 5.62 overridden on record (`digiquant/src/digiquant/strategies/sdca/presets.json`: `btc_optimized.description`).
2. **cap 50 HOLD.** All 9 fold-cells NO CHANGE at 55/60; max recorded dd 26.05 leaves 23.95pp margin (`gold_calibration_note.md`: Counterfactual table 3). **Requires:** nothing — no change, no vehicle.
3. **sens 2.0 → 4.0, gold scope, WEAK (bar-fitting risk flagged).** Deep 2.40 clears by 1.60; full 3.87 and v1 3.86 clear by 0.13/0.14 — thin enough that 4.0 looks fitted, and the knee-cliff rationale is UNMEASURED (no worst-neighbor key in either v2 JSON or the v1 log) (`gold_calibration_note.md`: Counterfactual table 4 + Sensitivity attribution). **Requires:** library edit (`SENSITIVITY_SPIKE_PCT`, gold scope) or override-on-record with the unstable label carried — BTC precedent as above. Owner picks, on the record.
4. **NO bar change fixes F1-negative** (deep −9.14, full −8.43, v1 −11.19, all feasible — `gold_calibration_note.md`: Headline) **or the broadening-hurt ranking** (+14.52 → +3.04 means invariant to bars — means average all folds regardless of flags, `gold_calibration_note.md`: Counterfactual table 2). Any promotion despite those is an override-on-record decision per the BTC precedent, not a calibration outcome.

Measurability limits standing behind every bar call: vetoing BAR derivable by elimination (all three infeasible folds have dd ≤ 50, excluding the cap); deployed magnitudes + worst-neighbor key unmeasurable from record — writer emits no deployed value and no veto field (`gold_calibration_note.md`: Derivation rule).

## 5. Overrides required (to promote the v2-deep candidate despite the gate as written)

Each item names the bar, the fold, and the numbers. Eight items: three deep-gate, three full-variant (if the full variant were promoted instead), two cross-cutting.

1. **Floor bar, deep F0:** floor 10 vetoes F0 at OOS +10.85% with dd 5.47% (`gold_curve_search_v2deep.json: gate.per_fold[0]` — oos 10.851864378460307, dd 5.473593738863906, feasible false). Veto is sizing, not risk (dd far under cap 50). Requires floor → 0 (gold scope) or override-on-record.
2. **F1-negative, deep F1 (NO bar covers this):** F1 is feasible and OOS −9.14% with dd 24.49% (`gold_curve_search_v2deep.json: gate.per_fold[1]` — oos −9.13870465625709, dd 24.494610094745443, feasible true). No bar change moves any OOS number or flips any F1 sign. Promotion despite this is a pure override-on-record judgment call.
3. **Sensitivity bar, deep gate:** unstable at maxΔ 2.40 vs bar 2.0, 47 neighbors (`gold_curve_search_v2deep.json: gate.sensitivity_stable` false, `gate.sensitivity_max_abs_delta` 2.3979045677131543, `gate.sensitivity_neighbor_count` 47). Requires sens → 4.0 (gold scope, WEAK) or override-on-record carrying the unstable label.
4. **Floor bar, full F0 (variant):** floor 10 vetoes F0 at OOS +2.37% with dd 1.49% (`gold_curve_search_v2.json: gate.per_fold[0]` — oos 2.3701814557279155, dd 1.4915224077174467, feasible false). Same sizing-not-risk read.
5. **F1-negative, full F1 (variant, NO bar covers this):** feasible and OOS −8.43% with dd 24.45% (`gold_curve_search_v2.json: gate.per_fold[1]` — oos −8.430071334200761, dd 24.447740317320328, feasible true). Pure override-on-record.
6. **Sensitivity bar, full gate (variant):** unstable at maxΔ 3.87 vs bar 2.0, 47 neighbors (`gold_curve_search_v2.json: gate.sensitivity_stable` false, `gate.sensitivity_max_abs_delta` 3.8740175212303365, `gate.sensitivity_neighbor_count` 47). Requires sens → 4.0 (thin margin +0.13 — bar-fitting risk) or override-on-record.
7. **hy/ig weight pending full-depth re-run (cross-cutting):** v2 vectors run hy_oas = ig_oas = 0.0 by construction under the Task-2 red (`gold_curve_search_v2deep.json: weights.hy_oas` 0.0, `weights.ig_oas` 0.0). Promoting the vote as final before the credentialed BAML re-stage (verifier exit 0) + duel re-confirmation + gate re-run means overriding the Task-2 follow-up trigger (`gold_depth_handoff.md`: Follow-up trigger).
8. **Holdout unscored (cross-cutting):** holdout 2022-05-12..2026-09-29 never scored in any variant (`task-3-report.md`: Holdout-absence confirmations). Promoting before the holdout validation run means accepting OOS-only evidence with the final reserve unspent.

## 6. Promotion touch-list (the six files/steps; gold values where known, TBD where unknown)

From recon (plan §5/§11: settings entry, preset, provenance sidecar, coefficients file, test pins, operator push; nightly needs no change; SERIES_FILES already covers BAML).

1. **Settings entry** — `digiquant/src/digiquant/strategies/settings.json`, `strategies` map (cf. existing `btc_sdca` block with `strategy_type sdca`, `preset`, `risk_model`, `indicator_weights`): new `gold_sdca` entry — symbol GLD-USD (TBD exact `symbol`/`ccxt_symbol` strings), `risk_model: generic_valuation` (gold has no power-law fit — TBD confirmed), `indicator_weights` = v2-deep vector (§3a) or v2-full vector (TBD which variant), `preset` = new gold preset name (TBD, e.g. `gold_optimized`). All values TBD until owner picks variant + bars.
2. **Preset** — `digiquant/src/digiquant/strategies/sdca/presets.json` (cf. `btc_optimized` shape block): new gold preset with shape = v2-deep gated winner — buy_max_rate 35.0, buy_knee_risk 45.0, sell_knee_risk 50.0, sell_max_rate 30.0, buy_curvature 1.0, sell_curvature 2.0, no mid-tiers (`gold_curve_search_v2deep.json: gated_shape`); `long_only` TBD (gate ran long/short-capable shapes — TBD owner call); `description` must carry the override record (BTC precedent: `presets.json: btc_optimized.description` carries vetoes + owner-accept date).
3. **Provenance sidecar** — new file beside the BTC sidecars (`digiquant/src/digiquant/strategies/sdca/btc_optimized_provenance.json` pattern), e.g. `gold_optimized_provenance.json` (TBD exact name): must record seed path (`gold_seed_v2deep.json`), gate output (`gold_curve_search_v2deep.json`), evaluator, bars-in-force at promotion, and the §5 override list verbatim. TBD content until promotion accepted.
4. **Coefficients file** — gold uses `generic_valuation` (no fitted power-law coefficients like `btc_power_law_coefficients.json`): no coefficients file expected (TBD confirmed — if a fitted gold valuation rail is ever introduced, its fit procedure + file are a separate task).
5. **Test pins** — `tests/dq/strategies/sdca/test_walk_forward.py:59,80` pin floor 10 / cap 50; sens 2.0 unpinned. If gold-scope bar changes are applied as library edits, pins need gold-scope coverage (TBD exact test edits); if carried as overrides-on-record (BTC precedent — library bars unmoved), no pin change (TBD owner call).
6. **Operator push** — `generate_tearsheets.py --strategy gold_sdca --signal-delay-days 3` after a real Nautilus run, then `--push-supabase` (operator-only; never from an agent env). Exact command + venue/cash TBD. Nightly workflow needs no change. `SERIES_FILES` in `digiquant/scripts/export_sdca_macro.py:43` already covers BAMLH0A0HYM2/BAMLC0A0CM — no staging-code change needed for the re-stage.

## 7. Reserves + enrichment context

- **Holdout reserve:** 2022-05-12..2026-09-29 (~4.4y) never scored in any variant (`task-3-report.md`: Holdout-absence confirmations; `task-3-report.md`: Fold dates). Final validation reserve — run only after promotion acceptance, never before (brief Out of scope).
- **Enrichment snapshots as labeling context:** `digiquant/data/enrichment/` staging (gitignored snapshots; committed README) holds per-tool dated pages with provenance headers for GLD options-skew, 13f-gld, econ-calendar, gold-news, and the LBMA probe (`digiquant/data/enrichment/README.md`: Pull inventory + Provenance header). Nobody consumes snapshots yet — labeling context for analysis only (`digiquant/data/enrichment/README.md`: Consumers). First live run is a post-merge operator action via the weekly `enrich-gold-refresh` workflow `workflow_dispatch` (`digiquant/data/enrichment/README.md`: Cadence). LBMA probe verdict still open pending the live catalog (`digiquant/data/enrichment/README.md`: LBMA probe verdict).

## 8. Owner-accept checklist (ALL UNCHECKED — the owner checks them)

- [ ] (a) Bar values: floor 10 → 0 (gold scope), cap 50 HOLD, sens 2.0 → 4.0 WEAK-or-hold — accepted as stated in §4, or amended on the record.
- [ ] (b) Override acceptance per item: each of the §5 items 1–8 accepted or rejected individually, on the record (rejection of any of items 1–3 blocks deep-candidate promotion; 4–6 block the full variant; 7–8 block any promotion-before-evidence).
- [ ] (c) hy/ig full-depth re-run trigger: credentialed BAML re-stage run per `gold_depth_handoff.md` re-stage commands, verifier exit 0 confirmed, Task-1 duel re-run, gate re-run — or explicitly waived on the record (covers §5 item 7).
- [ ] (d) Live-data staging owner: named owner who runs the credentialed re-stage + operator push (§6 item 6); agent envs never run `--push-supabase`.
- [ ] (e) Merge + nightly pickup confirmation: branch merged into its base, nightly tearsheet workflow verified picking up the gold entry (or confirmed no-change), first live enrichment run dispatched.

---

## 9. Plan 9 honest re-measure — binding decision (Task 4, 2026-10-01)

Prior sections (§1–§8) preserved as-written; this section appends the stop-rule verdict. No bar was moved, no setting/preset/push was applied — promotion action belongs to a follow-up owner PR, not this plan.

Gate as-written (peak-based floor 10 / dd cap 50 / sens 2.0 / beats_flat / all folds feasible). Source JSONs: `digiquant/.scratch/gold_curve_search_honest_{v1,v3,B}.json`; transcription tables in Plan 9 `task-3-report.md` Step 2. Means recomputed from folds in-task: exact float match on all three runs. Precision note: honest-run gate numbers below are full precision from their own JSONs; v1 *namesake-delta* (pre-fix baseline) comparisons rest on 2dp log values — the pre-fix v1 JSON was clobbered before Plan 9 (`task-3-report.md`: Concern 1).

Checklists (each clause verified against the JSON, not the brief's summary):

- honest_v1: (a) feasible T/T/T PASS; (b) peak 99.99986724690903 / 100.0 / 100.0 ≥ 10 PASS; (c) dd 7.351331234809402 / 26.046717442936234 / 18.77352829494503 ≤ 50 PASS; (d) mean 14.518330428992982 > 0 PASS; (e) beats_flat true PASS; (f) sens maxΔ 3.855151400175803 ≤ 2.0 FAIL (46 neighbors, worst `buy_knee_risk:+5%`). FAILING CLAUSE: sensitivity stability.
- honest_v3: (a) feasible T/T/T PASS; (b) peak 98.70814285831842 / 100.0 / 100.0 ≥ 10 PASS; (c) dd 7.097155792439212 / 26.05633623913365 / 18.773525870963113 ≤ 50 PASS; (d) mean 9.965535247091468 > 0 PASS; (e) beats_flat true PASS; (f) sens maxΔ 0.44793236861546504 ≤ 2.0 PASS (49 neighbors, worst `buy_knee_risk:-5%`). CLEARS — no failing clause.
- honest_B: (a) feasible T/T/T PASS; (b) peak 99.99670332553873 / 93.85191004935702 / 100.0 ≥ 10 PASS; (c) dd 7.341069193761187 / 11.124051490494102 / 18.773492728315215 ≤ 50 PASS; (d) mean 11.337767562314419 > 0 PASS; (e) beats_flat true PASS; (f) sens maxΔ 2.8342806254326103 ≤ 2.0 FAIL (46 neighbors, worst `buy_knee_risk:+5%`). FAILING CLAUSE: sensitivity stability.

Verdict: PROMOTE-CANDIDATE — honest_v3 (`gold_curve_search_honest_v3.json`).

Clearing run identity: seed `gold_seed_v3.json` (valuation 1.0, m2 0.5, uup 0.5, all else 0.0 — hy_oas/ig_oas 0.0 by construction under the Task-2 red); gated shape buy_max 35.0 / buy_knee 45.0 / sell_knee 50.0 / sell_max 30.0 / buy_curv 1.0 / sell_curv 2.0, mid-tiers projected out (`gate_projection_drops_mid_tier` true); folds F0 +23.30769238238368 (peak 98.70814285831842, dd 7.097155792439212), F1 −11.160507911119943 (peak 100.0, dd 26.05633623913365), F2 +17.749421270010668 (peak 100.0, dd 18.773525870963113); mean +9.965535247091468; sens stable at 0.44793236861546504.

Remaining owner items (unchecked — the owner checks them; NO promotion action taken in this plan):

- [ ] (a) hy/ig full-depth re-run: credentialed BAML re-stage per `gold_depth_handoff.md`, verifier exit 0, Task-1 duel re-confirmation, gate re-run — or explicitly waived on the record. The v3 vector runs hy/ig at 0.0; promoting it as final before the re-stage overrides the Task-2 follow-up trigger.
- [ ] (b) Holdout validation: holdout 2022-05-12..2026-09-29 never scored in any Plan 9 run (`grep -ci holdout` = 0 in all six files) — run only after promotion acceptance, never before.
- [ ] (c) Live staging: named owner runs the credentialed re-stage + operator push (`generate_tearsheets.py --strategy gold_sdca` after a real Nautilus run, then `--push-supabase`); agent envs never run `--push-supabase`.
- [ ] (d) Merge via owner PR: settings entry, preset, provenance sidecar, test pins per §6 touch-list (values TBD until owner accepts); nightly pickup confirmation.

Explicitly: NOTHING IS PROMOTED by this verdict. No settings/preset/push change was made; the tree is untouched except untracked scratch files. Plan 9 ends here — a fifth re-run or new variant inside this plan fails review.

---

## 10. Plan 17 reselect promotion — branch-side record (Task 3, 2026-10-01)

Prior sections (§1–§9) preserved as-written, including the v3 PROMOTE-CANDIDATE verdict (§9) and its holdout trail. This section records the owner-picked promotion of the reselected shape (Plan 17, #4804): `gold_sdca` entry moves to the new `gold_reselect` preset; v3 settings values/preset/provenance REMAIN in the tree for history (nothing deleted).

### 10a. Reselected identity (every number keyed to its JSON)

- Selection: `gold_reselect_v6.json` attempt 1, chosen rank 1 of `eligible_count` = 144, frozen criterion `argmax min(mean_flat, mean_lump); tie-breaks higher-lump, lower-DD` (`frozen_criterion`).
- Shape (rank-1 `chosen_params`, single-knee projection — no mids): buy_max 35.0 / buy_knee 60.0 / sell_knee 65.0 / sell_max 30.0 / buy_curv 1.0 / sell_curv 1.0; `gate_projection_drops_mid_tier` = true (`gold_curve_search_v6b.json`).
- Weights (v4 vote): valuation 1.0, m2 0.5, uup 0.5, weekly_rsi/macd/sma_band 0.25 each, rest 0.0 (`gold_seed_v4.json: weights`; reselect `chosen_params` identical). Rails rolling_z 90d/z1.0 (`gold_seed_v4.json: rails`; `rolling_z.py: DEFAULT_ROLLING_WINDOW = 90`, `z = 1.0`).
- Means: flat +24.321143737074134 / lump +3.852892415834841 (`chosen_table_means`).
- Fresh sensitivity: STABLE, maxAbsDelta 1.6300156870418547, 48 neighbors, worst `sell_knee_risk:-5%` (`fresh_sens`).
- Per-fold (feasible all folds, Rule-B): f0 +63.52 flat / +9.09 lump, 73 mask days; f1 −7.88 flat / +3.28 lump, 0 mask days; f2 +17.32 flat / −0.81 lump, 1 mask day (`fresh_per_fold`).
- Frontier: 144 beats-both of 1080 feasible (`eligible_count` 144; `gold_curve_search_v6b.json: gate.frontier_beats_both` 144, `search.num_feasible` 1080).
- Mask: strict box z≤−2.0 & m≥1.5, z_window 1260, sma_window 1000 (entry `sell_mask`; `build_gold_sell_mask.py: FROZEN_Z_THRESH/M_THRESH`).

### 10b. Why it supersedes v3 (on-record, v3 kept)

- Beats-BOTH vs flat-only: reselect mean-OOS +24.32% flat / +3.85% lump vs v3 +9.97% flat-only (`gold_optimized_provenance.json: mean_oos_vs_flat_dca_pct` 9.965535247091468).
- Holdout trail: v3's honest holdout is −21.15507952929604% vs flat DCA (`gold_optimized_provenance.json: holdout_vs_flat_dca_pct`); the reselect carries no holdout score (holdout ABSENT — `grep -c holdout` = 0 in `gold_reselect_v6.json`), so the supersession rests on the OOS beats-both read, stated as a candidate judgment, not a proven beat.

### 10c. Caveats carried into every promotion artifact (entry note + preset description + provenance)

1. Thin lump margin: +3.85 mean with f2 at −0.81 on 1 mask day.
2. f1 ran with 0 mask days (its +3.28 vs lump is unmasked).
3. Ranks 1–4 projection tie (identical means, mid-tier keys only).
4. Selection-on-metric optimism (argmax-min over 144 eligible).
5. Holdout ABSENT for the reselect (spent on v3, never re-scored).

### 10d. Branch-side promotion state (Task 3 commit)

- `settings.json` `gold_sdca`: preset → `gold_reselect`, risk_model stays `generic_valuation`, explicit `rolling_window` 90 / `rolling_z` 1.0 (equal to shipped selector defaults — behavior-preserving), weights → v4 vector (osc 0.25), `sell_mask` strict box unchanged, `promotion_note` records the supersession + thin-margin caveat. No other entry touched.
- `presets.json`: NEW `gold_reselect` (v3 `gold_optimized` untouched); entry points at the new one.
- NEW `gold_reselect_provenance.json` beside v3's (gate numbers, mask, criterion, 4 disclosures + holdout-absent + optimism; v3 file untouched).
- Live-path premise (Tasks 1–2b): fail-closed mask (Ruling 1, e3a1d2887) + DFII10 staging with series-support guard (Ruling 2, 3a0dcf943). End-to-end proof is Task 4 (not this section).
