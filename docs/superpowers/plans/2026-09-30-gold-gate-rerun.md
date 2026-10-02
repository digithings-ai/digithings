# Gold gate re-run (Plan 4: broadened vote, calibration, promotion packet) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decide the hy/ig keep-one, re-run the gold walk-forward gate with the broadened deep-leg vote, calibrate (recommend, not change) the dd-cap/floor/sensitivity bars, and deliver an owner-accept promotion packet — with NO settings write and NO Supabase push — on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** Reuse, don't rebuild. The gate is `run_gold_curve_search.py` (257 lines): 3 folds + unscored holdout, tiered grid (~1728 shapes × 4 windows, worst-vs-flat ranking), per-fold OOS feasibility (10% deployed floor, 50% dd cap), 2.0 sensitivity bar, mean-OOS-vs-flat decision. This plan adds a `--seed-path` override + a v2 seed, runs it once with broadened weights, and analyzes. Library constants (`walk_forward.py:37,50-51`) and test pins stay untouched. Full-depth BAML cannot be staged in this environment (R2/Supabase/FRED creds all unset — verified) so hy/ig run at weight 0 pending a credentialed-env re-stage whose exact procedure + verification script ship in this plan.

**Tech Stack:** Python, Polars, Pydantic v2, pytest (`-m unit`), ruff (line length 100). No network calls in tests; the gate script itself is local-compute only (reads staged CSVs + seed JSON).

**Spec:** Recon 2026-09-30 (same session, worktree reads only) — recorded as completed Task 0 in the SDD ledger with the report as evidence. Key holdings: fold geometry (F0 IS ..2009-04-02 / OOS ..2013-08-15; F1 IS ..2013-08-15 / OOS ..2017-12-27; F2 IS ..2017-12-27 / OOS ..2022-05-11; holdout 2022-05-12..2026-09-29 NEVER scored); prior winner (single-knee 35/60/65/30, mean OOS +14.52%, F0 +38.20% vetoed by the 10% floor at dd 7.35%, F1 −11.19% feasible, F2 +16.54%, sensitivity 3.86 unstable); BTC precedent (`btc_optimized` promoted 2026-09-29 with fold-1 dd veto + unstable sensitivity overridden on record); sensitivity 2.0 has NO test pin (floor 10/cap 50 pinned at `test_walk_forward.py:59,80`); promotion touch-list (settings entry, preset, provenance sidecar, coefficients file, test pins, operator `--push-supabase`; nightly workflow needs no change; SERIES_FILES already covers BAML).

## Global Constraints

- Research-only to the finish: NO `settings.json` edit, NO `presets.json` edit, NO `--push-supabase`, NO nightly-workflow edits. The plan ends in a decision packet, not a promotion. Violating this fails the plan.
- Library gate constants untouched: `SENSITIVITY_SPIKE_PCT`, `SdcaOptimizeObjective` defaults, fold geometry, test pins. Calibration output is a RECOMMENDATION with counterfactual tables, applied nowhere.
- No credentials reachable here: R2_*, CORE_SUPABASE_*, FRED_API_KEY all unset. Any step needing them is a written procedure + verification script, executed where creds exist — never faked, never bypassed with truncated data presented as full.
- Truncated data never gates: hy/ig (785 rows from 2023-09-30) stay at weight 0 in every gate run until the depth verifier passes. Presenting a 732-bar gate as a full-history verdict fails the plan.
- The holdout (2022-05-12..) stays unscored through this plan — it is the final validation reserve for the promotion follow-up, not a debugging aid.
- ruff line length 100 on touched files only. Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`; `.venv/bin/python`, `PYTHONPATH=digiquant/src`. Sequential tasks.

---

### Task 1: hy/ig keep-one decision (offline)

**Files:**
- Create: `digiquant/scripts/run_gold_hy_ig_duel.py`
- Create (untracked): `digiquant/.scratch/gold_hy_ig_duel.json`

**Interfaces:**
- Consumes: staged (truncated) HY/IG CSVs + deep legs via `load_sdca_extra_sources`; `extra_z_vectors` / `extra_indicators_for_window` / `build_risk_index`; frozen rails (same resolver call as the seed script).
- Produces: single-leg index stats + decision record (keep HY xor IG xor neither, with criterion values).

- [ ] **Step 1: Write the script**

Create `digiquant/scripts/run_gold_hy_ig_duel.py` — mirror `run_gold_macro_expansion.py`'s structure (read it first: imports, `_stats`, rails, matrix, output handling) with candidates `seed` (valuation 1.0/m2 0.5/dxy 0.5 — repro gate vs `gold_seed.json`, diff must equal 0.0 or SystemExit), `hy_only` (seed + hy_oas 0.5), `ig_only` (seed + ig_oas 0.5). Report per candidate: coverage, buy-zone share, mean risk; plus pairwise |r| of each single leg vs dxy/nfci/valuation on the overlapping window. Decision criterion (in code, printed): keep the leg with the higher buy-zone share; tie-break: lower max |r| vs (dxy, nfci, valuation). Write `.scratch/gold_hy_ig_duel.json` with `{candidates, correlations, decision: {keep, reason}}`. Docstring states: relative comparison on truncated data only — the winner still waits on full-depth staging (Task 2) before any gate weight.

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_hy_ig_duel.py`
Expected: three candidate lines, repro 0.0, a `decision: {keep: <hy_oas|ig_oas>, reason: ...}` line, wrote-line. SystemExit (repro drift) stops the plan — investigate, do not adjust.

- [ ] **Step 3: Lint + commit the script (output stays untracked)**

Ruff check + format-check the script.
Expected: clean.

```bash
git add digiquant/scripts/run_gold_hy_ig_duel.py
git commit -m "Add gold HY/IG keep-one duel script (#4804)"
```

---

### Task 2: Full-depth re-stage procedure + depth verifier

**Files:**
- Create: `digiquant/scripts/verify_macro_depth.py`
- Create: `docs/superpowers/plans/2026-09-30-gold-macro-inputs.md` — NO (plan docs aren't edited post-hoc). Instead: procedure lives in the Task 2 report + `digiquant/.scratch/gold_depth_handoff.md` (untracked).

**Interfaces:**
- Consumes: `export_sdca_macro.export_series` cascade (supabase → FRED API full from 1959 → fredgraph); staged CSVs.
- Produces: a verifier with exit-code contract + a credentialed-env handoff note. No staging changes here (re-exporting over good files with fredgraph would be a no-op at best).

- [ ] **Step 1: Write the verifier**

Create `digiquant/scripts/verify_macro_depth.py`:

```python
#!/usr/bin/env python3
"""Assert staged macro CSVs meet full-depth floors (credentialed-env gate, #4804).

Exits 0 if every series passes; exits 1 listing gaps (series, have-first-date,
need-first-date, have-rows, need-rows). The gold gate (Plan 4 Task 3) consumes
this exit code: hy/ig stay at weight 0 until this passes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "price-history"

FLOORS: dict[str, dict] = {
    "M2SL": {"first": "1959-01-01", "rows": 700},
    "DTWEXBGS": {"first": "1990-01-01", "rows": 5000},
    "GVZCLS": {"first": "2008-06-01", "rows": 4000},
    "WALCL": {"first": "2002-12-01", "rows": 1000},
    "BAMLH0A0HYM2": {"first": "1997-01-01", "rows": 7000},
    "BAMLC0A0CM": {"first": "1997-01-01", "rows": 7000},
    "T5YIE": {"first": "2003-01-01", "rows": 5000},
    "NFCI": {"first": "1971-01-01", "rows": 2500},
}

FRED_STARTS: dict[str, str] = {  # full-history start per FRED (approx, for the handoff note)
    "BAMLH0A0HYM2": "1996-12-31",
    "BAMLC0A0CM": "1996-12-31",
}


def main() -> int:
    gaps = []
    for series, floor in FLOORS.items():
        path = STAGING / f"{series}.csv"
        if not path.is_file():
            gaps.append({"series": series, "missing": True})
            continue
        frame = pl.read_csv(path)
        first = str(frame["observation_date"].to_list()[0])[:10]
        rows = len(frame)
        if first > floor["first"] or rows < floor["rows"]:
            gaps.append(
                {
                    "series": series,
                    "have_first": first,
                    "need_first": floor["first"],
                    "have_rows": rows,
                    "need_rows": floor["rows"],
                }
            )
    if gaps:
        print(json.dumps({"depth_ok": False, "gaps": gaps}, indent=2))
        return 1
    print(json.dumps({"depth_ok": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write the verifier test (offline, tmp staging)**

Create `tests/dq/test_verify_macro_depth.py`: monkeypatch the script's `STAGING` to tmp_path (import via the `importlib` file-location seam from `test_export_sdca_macro.py:11-15`), write one passing CSV (BAMLH0A0HYM2, 1996-12-31 start, 7000+ rows — generate programmatically, small values) and one failing CSV (first 2023-09-30, 785 rows); assert exit 0 with all-pass staging, exit 1 with the gap listed for the truncated staging. `pytestmark = pytest.mark.unit`.

- [ ] **Step 3: Run tests + run the verifier here (expect the BAML gap)**

Run: `.venv/bin/python -m pytest tests/dq/test_verify_macro_depth.py -m unit -v`
Expected: PASS. Then run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/verify_macro_depth.py; echo "exit=$?"`
Expected: exit=1 with gaps listing exactly BAMLH0A0HYM2 + BAMLC0A0CM (all other series pass). That failure output is the handoff artifact — not a plan failure.

- [ ] **Step 4: Write the credentialed-env handoff note**

Create `digiquant/.scratch/gold_depth_handoff.md` (untracked) with: the exact re-stage commands
```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/export_sdca_macro.py --cache-dir digiquant/data/price-history --series BAMLH0A0HYM2,BAMLC0A0CM
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/verify_macro_depth.py; echo "exit=$?"
```
the env required (`FRED_API_KEY`, or Supabase creds for the first-hit tier), expected post-fix bounds (BAML from ~1996-12-31, ~7500 rows; verifier exit 0), and the paste of this run's gap JSON. Then re-run the Task-1 duel + Task-3 gate only after exit 0 (stated as the follow-up trigger).

- [ ] **Step 5: Lint + commit (script + test only; handoff note stays untracked)**

Ruff check + format-check both files.
Expected: clean.

```bash
git add digiquant/scripts/verify_macro_depth.py tests/dq/test_verify_macro_depth.py
git commit -m "Add macro depth verifier + credentialed re-stage handoff (#4804)"
```

---

### Task 3: Broadened-vote gate re-run (deep legs only)

**Files:**
- Create: `digiquant/scripts/run_gold_frozen_index_v2.py`
- Modify: `digiquant/scripts/run_gold_curve_search.py` (`--seed-path` arg only; default unchanged)
- Create (untracked): `digiquant/.scratch/gold_seed_v2.json`, `digiquant/.scratch/gold_curve_search_v2.json` (+ stdout log)

**Interfaces:**
- Consumes: deep-leg CSVs (all except HY/IG); `gold_seed.json` (repro tripwire source only).
- Produces: v2 seed + v2 gate record. hy_oas/ig_oas weights are 0.0 in v2 (depth verifier red — cite the Task-2 gap JSON in the commit body).

- [ ] **Step 1: Write the v2 seed script**

Create `digiquant/scripts/run_gold_frozen_index_v2.py` — byte-mirror of `run_gold_frozen_index.py` (read it first) with exactly two deltas: `SEED_WEIGHTS = SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, gvz=0.5, walcl=0.5, breakeven_5y=0.25, nfci=0.25, gdx_gld=0.5, gld_slv=0.5)` (hy_oas=0.0, ig_oas=0.0 — depth gate red) and `OUT_PATH = .../gold_seed_v2.json`. Docstring records the weight rationale pointer (expansion-script candidate stats) and the hy/ig exclusion. Weight choice justification (from evidence, not taste): gvz/walcl at seed-macro 0.5; breakeven/nfci at 0.25 (narrower history / survey overlap); ratios at 0.5 (max ratio-leg |r| 0.514 — independent votes).

- [ ] **Step 2: Self-check the v2 script against the v1 tripwire**

Before running v2 weights: temporarily run the v2 script with v1 weights? No — simpler enforced check: after writing v2 output, run a one-liner comparing `gold_seed_v2.json` risk against `gold_seed.json` risk ONLY to record how the broadened vote moves the index (no equality expected — different weights). The REAL tripwire is Step 4's gate sanity (fold shapes + prior winner comparability). Additionally assert v2 coverage ≥ v1 coverage − 5% (new legs must not collapse the calendar; BAML-bound collapse is excluded by construction since hy/ig are zero-weighted — if coverage drops >5%, STOP: a deep leg is unexpectedly short).
```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_frozen_index_v2.py
.venv/bin/python -c "
import json
v1 = json.load(open('digiquant/.scratch/gold_seed.json'))
v2 = json.load(open('digiquant/.scratch/gold_seed_v2.json'))
c1 = sum(1 for v in v1['risk'] if v is not None); c2 = sum(1 for v in v2['risk'] if v is not None)
print(f'v1 coverage {c1}, v2 coverage {c2}'); assert c2 >= 0.95 * c1, 'coverage collapse — investigate'
print('weights:', v2['weights'])"
```

- [ ] **Step 3: Add `--seed-path` to the curve-search script (only change)**

In `run_gold_curve_search.py`: add `argparse --seed-path (default: gold_seed.json path constant)` and use it at the seed-load site (line 136 area) AND for `SEED_WEIGHT_PARAMS` (lines 73–81 — replace the hardcoded dict with `SdcaCompositeWeights(**seed["weights"])` so file and params cannot diverge again). Grid (83–92), gates (94–104), folds (143), objective call (196–204) all UNCHANGED — same shape space, same bars, same geometry as the prior run; only the vote broadens. Commit this one-line-shape edit separately:
```bash
git add digiquant/scripts/run_gold_curve_search.py
git commit -m "Allow seed override in gold curve search (#4804)"
```

- [ ] **Step 4: Run the v2 gate (long compute — background, then verify)**

Run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_curve_search.py --seed-path digiquant/.scratch/gold_seed_v2.json > digiquant/.scratch/gold_curve_search_v2.stdout.log 2>&1` (plus `--out` if the script supports an output path; otherwise it writes the default JSON — check the script's output handling first and, if fixed-path, copy the default output to `gold_curve_search_v2.json` immediately after, BEFORE any other run can overwrite it).
Expected: exit 0; `gold_curve_search_v2.json` with winner shape, per-fold OOS/dd/feasibility, sensitivity maxΔ, mean OOS. Runtime is unknown (prior run: 6912 evals) — run in background and continue only on completion; do NOT tune the grid to make it faster (same space or the comparison is void).

- [ ] **Step 5: Record the v2 gate table (no analysis yet — Task 4 analyzes)**

Print + paste into the report: winner shape, per-fold (OOS vs-flat, dd, feasible + which bar vetoed), sensitivity (stable/unstable, maxΔ, worst neighbor), mean OOS + beats_flat, and the delta vs the v1 record (fold-by-fold). Then:
```bash
git add digiquant/scripts/run_gold_frozen_index_v2.py
git commit -m "Add gold v2 seed + broadened-vote gate run (#4804)"
```
(outputs stay untracked; cite the Task-2 gap JSON for hy/ig=0 in the commit body).

---

### Task 4: Calibration analysis (recommend, change nothing)

**Files:**
- Create (untracked): `digiquant/.scratch/gold_calibration_note.md`
- Modify: NOTHING committed (analysis only). If the analysis needs code (counterfactuals), it reads the v2 JSON with one-liners — no new files.

**Interfaces:**
- Consumes: `gold_curve_search_v2.json` (+ v1 record for delta).
- Produces: a calibration note + recommendation. No code, no commit (report carries it; the note stays untracked).

- [ ] **Step 1: Build the counterfactual table**

From the v2 JSON, tabulate per fold: OOS vs-flat, dd, deployed, feasibility at the CURRENT bars (floor 10 / cap 50 / sens 2.0) with the vetoing bar named; then recompute feasibility at counterfactual bars WITHOUT rerunning the gate (pure arithmetic on recorded fold metrics): floor ∈ {10, 5, 0}, cap ∈ {50, 55, 60}, sens ∈ {2.0, 4.0, 6.0} — for sensitivity, the recorded maxΔ either clears the bar or not (no re-bump needed). Present as three one-dimensional sweeps (vary one bar, hold the other two at current).

- [ ] **Step 2: Attribute the sensitivity result**

Record the worst-neighbor key from v2 (prior: `buy_knee_risk` knee cliff, all cycles). If v2's worst neighbor is again a knee parameter with maxΔ ≫ 2.0 while economics barely move, state the knee-cliff hypothesis explicitly: the 2.0 bar measures grid discreteness, not economic instability — with the supporting numbers (Δ metric vs Δ OOS for that neighbor if present in the JSON; else mark as unmeasured, do not invent).

- [ ] **Step 3: Write the recommendation (untracked note + report section)**

`gold_calibration_note.md` holds: the counterfactual tables, the sensitivity attribution, the BTC precedent (`btc_optimized` promoted with overrides on record), and a RECOMMENDATION block with exact values (e.g. "floor 10→5 for gold (fold-0 dd 7.35% shows the veto is sizing, not risk), cap 50 hold, sens 2.0→4.0 with knee-cliff rationale" — values illustrative; the implementer writes what the v2 numbers support, each value tied to a table cell). Every recommendation cites the owner-accept requirement: applying any of it (library edit, preset bars, or override-on-record promotion) is a follow-up decision, not this task. No commit for the note; the report quotes the recommendation block verbatim.

---

### Task 5: Promotion decision packet (no promotion)

**Files:**
- Create (untracked): `digiquant/.scratch/gold_promotion_packet.md`
- Modify: NOTHING. Explicitly: no `settings.json`, no `presets.json`, no sidecar/coefficients check-ins, no `--push-supabase`, no workflow edits. A diff touching any of those fails review.

**Interfaces:**
- Consumes: all Plan-4 outputs + standing evidence (attribution, expansions, duel, calibration note, enrichment README, depth handoff).
- Produces: the packet. Review gates its accuracy, not its verdict.

- [ ] **Step 1: Write the packet with these exact sections**

1. `Verdict`: PROMOTE / PROMOTE-WITH-OVERRIDES / NOT-YET (one, with one-line reason).
2. `Gate table`: v2 winner shape + per-fold OOS/dd/feasibility/veto + sensitivity + mean OOS, beside the v1 row for delta.
3. `Vote`: final weight vector (v2) + hy/ig status (Task-1 decision + Task-2 depth block) + collinearity flags (0.86 pair, ratio max 0.514).
4. `Bars`: current vs recommended (Task-4 block) + what each change would require (library edit / preset bars / override-on-record with the BTC precedent named).
5. `Overrides required`: enumerated list (empty if none) — each item names the bar, the fold, the numbers.
6. `Promotion touch-list`: the six files/steps from recon §5 (settings entry, preset, provenance sidecar, coefficients file, test pins, operator push) with gold-specific values filled in where known (preset shape = v2 winner; weights = v2 vector) and TBD where genuinely unknown.
7. `Reserves`: holdout 2022-05-12.. unscored (final validation reserve); enrichment snapshots available as labeling context (first live run post-merge).
8. `Owner-accept checklist`: checkboxes for (a) bar values, (b) override acceptance per item, (c) hy/ig full-depth re-run trigger (Task-2 handoff), (d) live-data staging owner (who runs the credentialed re-stage + push), (e) merge + nightly pickup confirmation. All unchecked — the owner checks them.

- [ ] **Step 2: Self-check the packet against the evidence (report section)**

For every number in sections 2–4, cite the source file + key (e.g. `gold_curve_search_v2.json: folds[1].oos_vs_flat_dca_pct`). Any number without a citation is removed before finishing. The reviewer re-verifies a sample.

- [ ] **Step 3: Report (no commit)**

No commit in this task (packet stays untracked). The report quotes sections 1 + 5 + 8 in full. The SDD ledger records plan completion with the packet path.

---

## Out of scope (follow-ups, not this plan)

- Applying calibration (library edits, preset bars, override-on-record promotion) — owner decision after the packet.
- Credentialed full-depth BAML re-stage + hy/ig-weighted gate re-run — triggered by Task-2 exit 0.
- Holdout validation run — after promotion acceptance, never before.
- Snapshot consumers / labeling analysis (Plan 3 deferred); TLT/TIP/UUP/CPER legs (Plan 2 declared scope); live snapshot backfill (Plan 3 operator action).

## Self-review

1. Spec coverage: recon held as Task 0 (fold map, constants, precedent, touch-list all cited above with file:line); keep-one → Task 1 (criterion in code); depth procedure+verifier → Task 2 (exit-code contract feeds the gate); broadened gate → Task 3 (same space/geometry/bars, vote-only delta, hy/ig=0 cited); calibration → Task 4 (counterfactuals without reruns, recommend-don't-change); packet → Task 5 (8 mandated sections, citation rule, no-commit). Owner-accept questions from the original loop (dd-cap, sensitivity bar, promotion) each have exactly one owner section.
2. Placeholder scan: commands, weights, thresholds, file paths, JSON keys, and section lists are all literal. The two conditional branches (coverage-drop STOP in Task 3, citation-or-remove in Task 5) have defined actions. The credentialed-env handoff is a procedure with exact commands + expected bounds, not a deferral excuse — and the gate proceeds meaningfully without it (deep legs only).
3. Type consistency: `gold_seed_v2.json` / `gold_curve_search_v2.json` / `gold_hy_ig_duel.json` / `gold_depth_handoff.md` / `gold_calibration_note.md` / `gold_promotion_packet.md` named identically in tasks, ledger, and out-of-scope triggers; `SdcaCompositeWeights` kwargs match Plan-1/2 field names; counterfactual bar sets are literal value lists; hy_oas/ig_oas are 0.0 in every v2 weight vector by construction.
