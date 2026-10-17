# Gold macro inputs (Plan 1: backfill + stage + wire) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Backfill, stage, and wire six already-manifested FRED macro series (GVZCLS, WALCL, BAMLH0A0HYM2, BAMLC0A0CM, T5YIE, NFCI) as first-class SDCA extra indicators, and run a gold macro-expansion experiment on the `task/4804-sdca-strategy-for-gold--gld` branch.

**Architecture:** No new pipeline or store. Supabase `macro_series_observations` + the 2×-daily R2 refresh cron (which reads the same `macro_series.yaml`) remain the system of record; local FRED-shaped CSVs are research staging via the existing `export_sdca_macro.py` first-hit-wins chain. New indicators follow the exact m2/dxy plugin pattern in `indicator_catalog.py` / `optimize.py` with zero-weight defaults, so BTC behavior is byte-identical.

**Tech Stack:** Python, Polars (never pandas), Pydantic v2 (frozen/strict), pytest (`-m unit`), ruff (line length 100), FRED API / fredgraph.csv fallback.

**Spec:** `digiquant/src/digiquant/strategies/sdca/METHOD.md` (per-asset checklist steps 3–6, gold done through attribution with gate NOT cleared: fold 1 OOS −11.19%, sensitivity 3.86 vs 2.0 cap); gold scripts `digiquant/scripts/run_gold_{frozen_index,curve_search,attribution}.py`; component docs `digiquant/AGENTS.md`, `digiquant/ARCHITECTURE.md` (market-data reads: R2; Gloomberb enrichment-only — not used here).

## Global Constraints

- Polars only; never pandas (the yfinance conversion boundary in `fetchers.py` is the sole allowlist, untouched here).
- Pydantic v2 everywhere; new model fields are `float = Field(0.0, ge=0.0)`; models stay `frozen=True, strict=True`.
- ruff line length 100: `ruff check digiquant/ && ruff format --check digiquant/` green after every code task.
- Research-only: no `settings.json` entry, no Supabase push, no `gld` slug anywhere outside `.scratch/` and the new experiment script. Nothing touches `digiquant/brokers/`, `digikey/`, or live order paths.
- BTC-isolation invariant: `load_sdca_extra_z` auto-enable is NOT extended (new weights default 0.0); Task 4 ships a regression test proving BTC vectors are unchanged.
- Sign convention (gold is the fear bid; +z votes buy): all six new legs use NO sign flip except none — rising gold vol, balance-sheet growth, widening spreads, rising breakevens, tighter conditions all vote +z. Documented per function; the walk-forward gate (out of scope, later plan) decides.
- Worktree root for every command: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`. Interpreter: `python3` after the Task 0 check passes (prior `.scratch/` outputs prove a working interpreter with polars/pydantic/pytest).

---

### Task 0: Branch hygiene + rebase + green baseline

**Files:**
- Revert (tracked, uncommitted): `apps/digiquant-web/app/strategies/[id]/page.tsx`, `apps/digiquant-web/components/tearsheet/tearsheet-view.tsx`
- Leave alone (untracked, gitignored, local-only): `apps/digiquant-web/public/strategies/gld_sdca_candidate.json`, `digiquant/.scratch/`, `digiquant/data/price-history/*.csv`

**Interfaces:**
- Consumes: nothing.
- Produces: rebased branch on `origin/develop`, green baseline for Tasks 1–6.

- [ ] **Step 1: Confirm the dirty hunks are only the preview shim**

Run: `git status --short` and `git diff --stat`
Expected: exactly 2 modified files (`page.tsx`, `tearsheet-view.tsx`) plus `??` lines for `public/strategies/`, `.scratch/`, and price-history CSVs. The diff hunks are the `gld_sdca_candidate` PUBLISHED entry (+5) and the static-JSON fallback block (+16/−3, carrying `REVERT BEFORE OPENING THE TASK PR`).

- [ ] **Step 2: Revert the shim**

```bash
git checkout -- "apps/digiquant-web/app/strategies/[id]/page.tsx" "apps/digiquant-web/components/tearsheet/tearsheet-view.tsx"
git status --short
```

Expected: no `M` lines remain; only `??` untracked lines. The on-disk preview JSON stays usable for local file viewing; the web route just no longer serves it until promotion.

- [ ] **Step 3: Rebase onto origin/develop**

```bash
git fetch origin
git rebase origin/develop
```

Expected: `Successfully rebased and updated refs/heads/task/4804-sdca-strategy-for-gold--gld`. Rationale: branch was 7 behind (includes #4811/#4810 runner fixes, #4800 gloomberb macro page adapter, ADR-0030, #4805 zero-rebuild). Conflict risk is low (gold scripts are new files; reverted web files now match develop). If a conflict appears in a web file, resolve with `git checkout --theirs -- <file>` (develop wins; gold web work is reverted by design), then `git rebase --continue`. Never `git push --force` anywhere except this task branch if it later gains a remote — and only after owner sign-off.

- [ ] **Step 4: Verify interpreter + green baseline**

```bash
python3 -c "import polars, pydantic, pytest; print('ok')"
pytest tests/dq/test_export_sdca_macro.py tests/dq/strategies/sdca/ -m unit -q
ruff check digiquant/ && ruff format --check digiquant/
```

Expected: `ok`, all tests pass, ruff clean. No commit (no files changed — revert + rebase only; the rebase replays the 3 existing gold commits `0af3dc7c5`, `3e7fe4649`, `1c8988b03`).

---

### Task 1: Backfill + stage the six macro CSVs

**Files:**
- Create (gitignored staging, never committed): `digiquant/data/price-history/{GVZCLS,WALCL,BAMLH0A0HYM2,BAMLC0A0CM,T5YIE,NFCI}.csv`
- Create (untracked ledger, never committed): `digiquant/.scratch/gold_macro_sources.json`

**Interfaces:**
- Consumes: `export_sdca_macro.export_series` (first-hit-wins: supabase → FRED API → fredgraph).
- Produces: six FRED-shaped `observation_date,<SERIES>` CSVs plus a source ledger recording which tier served each series.

- [ ] **Step 1: Check which source tiers are available**

```bash
python3 -c "import os; print('FRED_API_KEY:', 'set' if os.environ.get('FRED_API_KEY') else 'MISSING'); print('SUPABASE:', 'set' if (os.environ.get('CORE_SUPABASE_URL') or os.environ.get('SUPABASE_URL')) and (os.environ.get('CORE_SUPABASE_SERVICE_KEY') or os.environ.get('SUPABASE_SERVICE_ROLE_KEY')) else 'MISSING')"
```

Expected: one line per key, `set` or `MISSING`. Any combination works: with neither set, every series falls through to keyless fredgraph.csv (fine for research staging; Supabase/R2 catch up via the 2×-daily cron which reads the same manifest).

- [ ] **Step 2: Run the export for the six series**

```bash
PYTHONPATH=digiquant/src python3 digiquant/scripts/export_sdca_macro.py --cache-dir digiquant/data/price-history --series GVZCLS,WALCL,BAMLH0A0HYM2,BAMLC0A0CM,T5YIE,NFCI
```

Expected: six log lines `INFO: <ID>: <n> rows via <supabase|fred_api|fredgraph> → .../<ID>.csv`, each with n > 0 (`write_observation_csv` raises on empty, so success implies non-empty). This command fails today with `unknown series ...; known: ['DTWEXBGS', 'M2SL']` — that failure is the Task 2 entry condition. If it fails, skip to Task 2 and return here after.

- [ ] **Step 3: Write the source ledger**

```bash
PYTHONPATH=digiquant/src python3 -c "
import json
from pathlib import Path
import polars as pl
root = Path('digiquant/data/price-history')
ledger = {}
for sid in ['GVZCLS','WALCL','BAMLH0A0HYM2','BAMLC0A0CM','T5YIE','NFCI']:
    f = pl.read_csv(root / f'{sid}.csv')
    d = f['observation_date'].to_list()
    ledger[sid] = {'rows': len(f), 'first': str(d[0])[:10], 'last': str(d[-1])[:10]}
Path('digiquant/.scratch/gold_macro_sources.json').write_text(json.dumps(ledger, indent=2))
print(json.dumps(ledger, indent=2))
"
```

Expected: printed JSON with six entries; sanity bounds a human can eyeball — GVZCLS starts ~2008, WALCL weekly ~2002+, spreads/breakevens ~1990s+, NFCI weekly ~1971+. No commit: both outputs are gitignored staging. If any series looks truncated (e.g. fredgraph one-page limits), note it in the ledger and move on — backfill depth is verified again in Task 5 coverage stats.

---

### Task 2: Extend SERIES_FILES + export tests

**Files:**
- Modify: `digiquant/scripts/export_sdca_macro.py:43-46`
- Modify: `tests/dq/test_export_sdca_macro.py:56-57`

**Interfaces:**
- Consumes: nothing new.
- Produces: `SERIES_FILES` with 8 entries; `--series` accepts the six new ids (unblocks Task 1 Step 2 on return).

- [ ] **Step 1: Write the failing test (extend the pin + add a staging test)**

Edit `tests/dq/test_export_sdca_macro.py`: replace `test_series_files_match_load_sdca_extra_sources` (lines 56–57) with:

```python
def test_series_files_match_load_sdca_extra_sources() -> None:
    assert mod.SERIES_FILES == {
        "M2SL": "M2SL.csv",
        "DTWEXBGS": "DTWEXBGS.csv",
        "GVZCLS": "GVZCLS.csv",
        "WALCL": "WALCL.csv",
        "BAMLH0A0HYM2": "BAMLH0A0HYM2.csv",
        "BAMLC0A0CM": "BAMLC0A0CM.csv",
        "T5YIE": "T5YIE.csv",
        "NFCI": "NFCI.csv",
    }


def test_export_series_writes_gvz_staging_csv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mod, "rows_from_supabase", lambda _sid: [("2024-01-02", 18.5)])
    dest, source, n = mod.export_series("GVZCLS", tmp_path)
    assert source == "supabase"
    assert n == 1
    assert dest.name == "GVZCLS.csv"
    assert dest.read_text(encoding="utf-8").splitlines()[0] == "observation_date,GVZCLS"
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/dq/test_export_sdca_macro.py -m unit -v`
Expected: FAIL on the pin test (`SERIES_FILES` still has 2 entries) with an assertion diff showing the 6 missing ids.

- [ ] **Step 3: Implement (SERIES_FILES only)**

In `digiquant/scripts/export_sdca_macro.py:43-46`, replace the dict with:

```python
SERIES_FILES: dict[str, str] = {
    "M2SL": "M2SL.csv",
    "DTWEXBGS": "DTWEXBGS.csv",
    "GVZCLS": "GVZCLS.csv",
    "WALCL": "WALCL.csv",
    "BAMLH0A0HYM2": "BAMLH0A0HYM2.csv",
    "BAMLC0A0CM": "BAMLC0A0CM.csv",
    "T5YIE": "T5YIE.csv",
    "NFCI": "NFCI.csv",
}
```

Nothing else in this file changes — `export_series`, `write_observation_csv`, and the `--series` argparse path are already generic over `SERIES_FILES` keys (unknown ids still hit `parser.error`).

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/dq/test_export_sdca_macro.py -m unit -v`
Expected: all 8 tests PASS (6 pre-existing + 2 new/updated).

- [ ] **Step 5: Lint + return to Task 1 Step 2, then commit**

Run: `ruff check digiquant/scripts/export_sdca_macro.py tests/dq/test_export_sdca_macro.py && ruff format --check digiquant/scripts/export_sdca_macro.py tests/dq/test_export_sdca_macro.py`
Expected: clean. Then complete Task 1 Steps 2–3 (staging + ledger) before committing, so the commit message can record per-series sources:

```bash
git add digiquant/scripts/export_sdca_macro.py tests/dq/test_export_sdca_macro.py
git commit -m "Add gold macro staging series to export_sdca_macro (#4804)"
```

---

### Task 3: Weights model + sources model + name maps

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/indicator_catalog.py` (weights, sources, tuples, maps, both parse helpers)
- Create: `tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py` (model-level tests; behavior tests land in Task 4)

**Interfaces:**
- Consumes: existing `SdcaCompositeWeights` / `ExtraIndicatorSources` patterns.
- Produces: six new weight fields (`gvz`, `walcl`, `hy_oas`, `ig_oas`, `breakeven_5y`, `nfci`, all default 0.0), twelve new source fields, extended `MACRO_INDICATOR_NAMES`, `WEIGHT_PARAM_BY_NAME`, `INDICATOR_DISPLAY_NAMES`, `extra_items`, `composite_weights_from_params`, `parse_indicator_weights_json`.

- [ ] **Step 1: Write the failing model tests**

Create `tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py` with:

```python
"""Gold macro legs: model fields, maps, and guards (#4804)."""

from __future__ import annotations

import pytest

from digiquant.strategies.sdca.indicator_catalog import (
    MACRO_INDICATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    composite_weights_from_params,
    indicator_display_name,
)

pytestmark = pytest.mark.unit

NEW_MACRO = ("gvz", "walcl", "hy_oas", "ig_oas", "breakeven_5y", "nfci")


def test_new_macro_weights_default_zero() -> None:
    w = SdcaCompositeWeights()
    for name in NEW_MACRO:
        assert getattr(w, name) == 0.0
    assert w.enabled_extras() == {}


def test_new_macro_names_in_macro_tuple_and_param_map() -> None:
    for name in NEW_MACRO:
        assert name in MACRO_INDICATOR_NAMES
        assert WEIGHT_PARAM_BY_NAME[name] == f"{name}_weight"
    assert indicator_display_name("gvz") == "gold volatility (GVZ)"
    assert indicator_display_name("breakeven_5y") == "5Y breakeven"


def test_composite_weights_from_params_reads_new_legs() -> None:
    w = composite_weights_from_params({"gvz_weight": 0.5, "nfci_weight": 0.25})
    assert w.gvz == 0.5
    assert w.nfci == 0.25
    assert w.walcl == 0.0


def test_empty_sources_carry_no_new_series() -> None:
    sources = ExtraIndicatorSources()
    for name in NEW_MACRO:
        assert getattr(sources, f"{name}_dates") is None
        assert getattr(sources, f"{name}_values") is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py -m unit -v`
Expected: FAIL — `SdcaCompositeWeights()` rejects unexpected... actually first failure is `AttributeError` on `w.gvz` (field does not exist yet). Either error shape confirms the fields are missing.

- [ ] **Step 3: Implement model changes**

In `indicator_catalog.py`, apply these six edits (all mirror the existing m2/dxy lines):

1. Line 43: `MACRO_INDICATOR_NAMES: tuple[str, ...] = ("m2", "rs_eth", "dxy")` → `("m2", "rs_eth", "dxy", "gvz", "walcl", "hy_oas", "ig_oas", "breakeven_5y", "nfci")`.
2. Lines 51–59 `WEIGHT_PARAM_BY_NAME`: add `"gvz": "gvz_weight"`, `"walcl": "walcl_weight"`, `"hy_oas": "hy_oas_weight"`, `"ig_oas": "ig_oas_weight"`, `"breakeven_5y": "breakeven_5y_weight"`, `"nfci": "nfci_weight"`.
3. Lines 62–70 `INDICATOR_DISPLAY_NAMES`: add `"gvz": "gold volatility (GVZ)"`, `"walcl": "Fed balance sheet"`, `"hy_oas": "HY credit spread"`, `"ig_oas": "IG credit spread"`, `"breakeven_5y": "5Y breakeven"`, `"nfci": "financial conditions (NFCI)"`.
4. `SdcaCompositeWeights` (after line 86 `dxy`): add six fields `gvz`, `walcl`, `hy_oas`, `ig_oas`, `breakeven_5y`, `nfci`, each `float = Field(0.0, ge=0.0)`. The `_at_least_one_positive` validator is unchanged (sums all values via `model_dump()`).
5. `extra_items` (lines 97–105): append `("gvz", self.gvz)`, `("walcl", self.walcl)`, `("hy_oas", self.hy_oas)`, `("ig_oas", self.ig_oas)`, `("breakeven_5y", self.breakeven_5y)`, `("nfci", self.nfci)`.
6. `ExtraIndicatorSources` (after line 126): add twelve fields `gvz_dates/values`, `walcl_dates/values`, `hy_oas_dates/values`, `ig_oas_dates/values`, `breakeven_5y_dates/values`, `nfci_dates/values`, each `pl.Series | None = None`.
7. `composite_weights_from_params` (lines 131–139): add `gvz=float(params.get("gvz_weight", 0.0))` and the same pattern for the other five.
8. `parse_indicator_weights_json` (lines 150–158): add `gvz=float(payload.get("gvz", 0.0))` and the same pattern for the other five, mirroring the existing per-field lines.

- [ ] **Step 4: Run to verify it passes**

Run: `pytest tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py tests/dq/strategies/sdca/test_indicator_catalog.py -m unit -v` (second path only if it exists; `ls` it first — pre-existing suite must stay green under the extended tuples).
Expected: PASS throughout. If any pre-existing test pins `MACRO_INDICATOR_NAMES == ("m2", "rs_eth", "dxy")` exactly, update that pin to the new 9-tuple (same-file edit, same commit).

- [ ] **Step 5: Lint + commit**

Run: `ruff check digiquant/src/digiquant/strategies/sdca/indicator_catalog.py tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py && ruff format --check <same two files>`
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/indicator_catalog.py tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py
git commit -m "Add gold macro legs to SDCA weights and sources (#4804)"
```

---

### Task 4: z-transforms + build branches + loader + drop guards

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/indicator_catalog.py` (one private helper, six public z-functions, six `build_extra_indicators` branches)
- Modify: `digiquant/src/digiquant/strategies/sdca/optimize.py` (`load_sdca_extra_sources`, `drop_extras_missing_sources`; `load_sdca_extra_z` deliberately untouched)
- Modify: `tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py` (behavior tests appended)

**Interfaces:**
- Consumes: Task 3 fields; `align_to_dates`, `causal_rolling_z`, `_require_pair`, `m2_liquidity_z` body (mirrored for WALCL YoY).
- Produces: materializable `gvz/walcl/hy_oas/ig_oas/breakeven_5y/nfci` extras; sibling-CSV loading for the six new files; missing-source zeroing. BTC vectors provably unchanged (new weights default 0, auto-enable untouched).

- [ ] **Step 1: Write the failing behavior tests (append to the Task 3 file)**

First extend the header import block of `tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py` with:

```python
from datetime import date, timedelta
from pathlib import Path

import math

import polars as pl
```

Then append exactly this to the end of the file (all names real: `drop_extras_missing_sources` lives in `optimize.py`, z-functions and `build_extra_indicators` in `indicator_catalog.py`; `SdcaCompositeWeights`, `ExtraIndicatorSources`, `NEW_MACRO`, `pytest` are already imported at the top from Task 1):

```python
from digiquant.strategies.sdca.indicator_catalog import (
    breakeven_5y_z,
    build_extra_indicators,
    extra_z_vectors,
    gvz_z,
    hy_oas_z,
    walcl_liquidity_z,
)
from digiquant.strategies.sdca.optimize import (
    drop_extras_missing_sources,
    load_sdca_extra_sources,
)


def _daily(n: int) -> pl.Series:
    start = date(2020, 1, 1)
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def test_gvz_rising_level_votes_positive() -> None:
    dates = _daily(300)
    src = pl.Series("v", [10.0 + 0.05 * i for i in range(300)], dtype=pl.Float64)
    z = gvz_z(dates, dates, src, window=30, min_samples=10)
    assert z[-1] > 1.0


def test_walcl_accelerating_growth_votes_positive() -> None:
    dates = _daily(500)
    src = pl.Series("v", [math.exp(2e-6 * i * i) for i in range(500)], dtype=pl.Float64)
    z = walcl_liquidity_z(dates, dates, src, window=30, min_samples=10)
    assert z[-1] > 0.0


def test_spread_and_breakeven_levels_vote_positive_when_rising() -> None:
    dates = _daily(300)
    src = pl.Series("v", [1.0 + 0.01 * i for i in range(300)], dtype=pl.Float64)
    assert hy_oas_z(dates, dates, src, window=30, min_samples=10)[-1] > 1.0
    assert breakeven_5y_z(dates, dates, src, window=30, min_samples=10)[-1] > 1.0


def test_positive_weight_without_source_raises() -> None:
    dates = _daily(300)
    price = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    weights = SdcaCompositeWeights(valuation=1.0, gvz=0.5)
    with pytest.raises(ValueError, match="gvz"):
        build_extra_indicators(dates, price, weights, ExtraIndicatorSources())


def test_drop_extras_zeroes_new_legs_without_sources() -> None:
    weights = SdcaCompositeWeights(
        valuation=1.0, gvz=0.5, walcl=0.5, hy_oas=0.25,
        ig_oas=0.25, breakeven_5y=0.25, nfci=0.25,
    )
    dropped = drop_extras_missing_sources(weights, ExtraIndicatorSources())
    assert dropped.valuation == 1.0
    for name in NEW_MACRO:
        assert getattr(dropped, name) == 0.0


def test_loader_picks_up_new_sibling_csvs(tmp_path: Path) -> None:
    root = tmp_path
    (root / "GVZCLS.csv").write_text(
        "observation_date,GVZCLS\n2024-01-02,18.5\n2024-01-03,19.0\n", encoding="utf-8"
    )
    sources = load_sdca_extra_sources(root)
    assert sources.gvz_dates is not None and len(sources.gvz_dates) == 2
    assert sources.m2_dates is None and sources.dxy_dates is None


def test_btc_vectors_unchanged_without_new_weights() -> None:
    dates = _daily(400)
    price = pl.Series("p", [100.0 + 0.1 * i for i in range(400)], dtype=pl.Float64)
    sources = ExtraIndicatorSources()
    before = extra_z_vectors(
        dates, price, SdcaCompositeWeights(valuation=1.0, m2=0.0), sources
    )
    after = extra_z_vectors(
        dates, price, SdcaCompositeWeights(valuation=1.0, m2=0.0), sources
    )
    assert before == after
    assert all(k not in before for k in NEW_MACRO)
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py -m unit -v`
Expected: FAIL at import (`gvz_z` etc. do not exist yet) — `ImportError`, which is the correct entry condition.

- [ ] **Step 3: Implement the z-functions (catalog, after `dxy_z` at line 236)**

```python
def _macro_level_z(
    dates: pl.Series,
    src_dates: pl.Series,
    src_values: pl.Series,
    name: str,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Level rolling-z for fear-bid macro legs. Rising series → +z (buy gold)."""
    aligned = align_to_dates(dates, src_dates, src_values, forward_fill=True)
    return causal_rolling_z(aligned, window=window, min_samples=min_samples).alias(name)


def gvz_z(
    dates: pl.Series,
    gvz_dates: pl.Series,
    gvz_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """Gold implied-vol level z. Spiking GVZ = stress = gold bid → +z (no flip)."""
    return _macro_level_z(dates, gvz_dates, gvz_values, "gvz", window=window, min_samples=min_samples)


def walcl_liquidity_z(
    dates: pl.Series,
    walcl_dates: pl.Series,
    walcl_values: pl.Series,
    *,
    roc_days: int = 365,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """YoY Fed-balance-sheet growth, rolling-z. Expanding sheet → +z (buy).

    Mirrors ``m2_liquidity_z``: WALCL trends monotonically, so a level-z is
    meaningless and growth is the vote.
    """
    aligned = align_to_dates(dates, walcl_dates, walcl_values, forward_fill=True)
    roc = aligned / aligned.shift(roc_days) - 1.0
    return causal_rolling_z(roc, window=window, min_samples=min_samples).alias("walcl")


def hy_oas_z(
    dates: pl.Series,
    hy_dates: pl.Series,
    hy_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """HY spread level z. Widening = stress = gold bid → +z (no flip)."""
    return _macro_level_z(dates, hy_dates, hy_values, "hy_oas", window=window, min_samples=min_samples)


def ig_oas_z(
    dates: pl.Series,
    ig_dates: pl.Series,
    ig_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """IG spread level z. Same fear-bid sign convention as ``hy_oas_z``."""
    return _macro_level_z(dates, ig_dates, ig_values, "ig_oas", window=window, min_samples=min_samples)


def breakeven_5y_z(
    dates: pl.Series,
    be_dates: pl.Series,
    be_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """5Y breakeven level z. Rising inflation compensation → +z (no flip)."""
    return _macro_level_z(
        dates, be_dates, be_values, "breakeven_5y", window=window, min_samples=min_samples
    )


def nfci_z(
    dates: pl.Series,
    nfci_dates: pl.Series,
    nfci_values: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """NFCI level z. Positive (tight) conditions = stress bid → +z (no flip)."""
    return _macro_level_z(dates, nfci_dates, nfci_values, "nfci", window=window, min_samples=min_samples)
```

- [ ] **Step 4: Implement the six build branches (catalog, after the `dxy` branch at lines 297–311)**

Six blocks mirroring the dxy block exactly, one per leg. Example (repeat for `walcl`/`walcl_liquidity_z`, `hy_oas`/`hy_oas_z`, `ig_oas`/`ig_oas_z`, `breakeven_5y`/`breakeven_5y_z`, `nfci`/`nfci_z`):

```python
    if "gvz" in enabled:
        gvz_dates = _require_pair(sources.gvz_dates, sources.gvz_values, "gvz")
        extras.append(
            IndicatorWeight(
                name="gvz",
                z=gvz_z(
                    dates,
                    gvz_dates,
                    sources.gvz_values,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["gvz"],
            )
        )
```

The `walcl` block passes `roc_days=roc_days` through like the m2 block does.

- [ ] **Step 5: Implement the loader + drop guards (optimize.py)**

In `load_sdca_extra_sources` (lines 176–194): after the `dxy_path` line add six sibling resolutions and thread all twelve series into the returned `ExtraIndicatorSources`:

```python
    gvz_path = _first_existing(base, ("GVZCLS.csv", "GVZCLS.parquet"))
    walcl_path = _first_existing(base, ("WALCL.csv", "WALCL.parquet"))
    hy_path = _first_existing(base, ("BAMLH0A0HYM2.csv", "BAMLH0A0HYM2.parquet"))
    ig_path = _first_existing(base, ("BAMLC0A0CM.csv", "BAMLC0A0CM.parquet"))
    be5y_path = _first_existing(base, ("T5YIE.csv", "T5YIE.parquet"))
    nfci_path = _first_existing(base, ("NFCI.csv", "NFCI.parquet"))
```

each followed by `xxx_dates, xxx_values = load_date_value_frame(xxx_path) if xxx_path else (None, None)`, and the six pairs added to the constructor call. In `drop_extras_missing_sources` (lines 197–209): after the dxy guard add six guards in the same shape:

```python
    if payload["gvz"] > 0.0 and sources.gvz_dates is None:
        payload["gvz"] = 0.0
```

(repeated for `walcl`, `hy_oas`, `ig_oas`, `breakeven_5y`, `nfci`). Do NOT touch `load_sdca_extra_z` auto-enable (lines 231–236 stay m2/rs_eth/dxy only) — that is the BTC-isolation invariant.

- [ ] **Step 6: Run to verify it passes**

Run: `pytest tests/dq/strategies/sdca/ -m unit -q`
Expected: PASS — new behavior tests green and the whole pre-existing SDCA engine suite (backtest, optimize, walk-forward, generic_valuation, asset_profile, presets) unbroken.

- [ ] **Step 7: Lint + commit**

Run: `ruff check digiquant/src/digiquant/strategies/sdca/ tests/dq/strategies/sdca/ && ruff format --check digiquant/src/digiquant/strategies/sdca/ tests/dq/strategies/sdca/`
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/indicator_catalog.py digiquant/src/digiquant/strategies/sdca/optimize.py tests/dq/strategies/sdca/test_sdca_gold_macro_indicators.py
git commit -m "Wire six gold macro legs through SDCA extras (#4804)"
```

---

### Task 5: Gold macro-expansion experiment (research-only script)

**Files:**
- Create: `digiquant/scripts/run_gold_macro_expansion.py`
- Create (untracked, never committed): `digiquant/.scratch/gold_macro_expansion.json`

**Interfaces:**
- Consumes: Task 1 CSVs via `load_sdca_extra_sources(DATA_PATH.parent)`; `extra_z_vectors` (materialize all six at once); `extra_indicators_for_window` + `build_risk_index` per candidate; `resolve_sdca_risk_model("generic_valuation", ...)` frozen rails (same as `run_gold_frozen_index.py:52-54`).
- Produces: per-candidate index stats (coverage, buy-zone share, mean risk), new-leg correlation matrix, and a byte-reproduction check of `gold_seed.json` risk.

- [ ] **Step 1: Write the script**

Create `digiquant/scripts/run_gold_macro_expansion.py` with exactly this content (docstring records research-only status and the seed-reproduction gate):

```python
#!/usr/bin/env python3
"""Gold macro-expansion experiment — candidate index stats for six new legs (#4804).

Materializes gvz/walcl/hy_oas/ig_oas/breakeven_5y/nfci z-vectors on the gold
calendar, then scores candidate weight sets on index stats only (coverage,
buy-zone share, mean risk) plus a new-leg correlation matrix. No backtest, no
gate run — the winner graduates to a full curve-search in a later plan.

Sanity gate: the `seed` candidate must reproduce `.scratch/gold_seed.json`
risk byte-identically (max abs diff == 0.0); anything else means the loader
or blend changed under the published seed.

Research-only; writes `.scratch/gold_macro_expansion.json`. Touches nothing
outside `.scratch/`.

Usage (gold worktree has no venv; research venv + src on PYTHONPATH):
    PYTHONPATH=digiquant/src python3 \\
        digiquant/scripts/run_gold_macro_expansion.py
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from digiquant.strategies.sdca.indicator_catalog import (
    SdcaCompositeWeights,
    extra_indicators_for_window,
    extra_z_vectors,
)
from digiquant.strategies.sdca.optimize import (
    load_sdca_extra_sources,
    load_sdca_ohlcv,
)
from digiquant.strategies.sdca.providers import resolve_sdca_risk_model
from digiquant.strategies.sdca.risk_index import build_risk_index

DIGIQUANT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = DIGIQUANT_ROOT / "data" / "price-history" / "GLD-USD.csv"
SEED_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_seed.json"
OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_macro_expansion.json"

FULL = SdcaCompositeWeights(
    valuation=1.0,
    m2=0.5,
    dxy=0.5,
    gvz=0.5,
    walcl=0.5,
    hy_oas=0.25,
    ig_oas=0.25,
    breakeven_5y=0.25,
    nfci=0.25,
)
CANDIDATES: dict[str, SdcaCompositeWeights] = {
    "seed": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5),
    "kitchen_sink": FULL,
    "vol_and_liquidity": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, gvz=0.5, walcl=0.5),
    "credit_stress": SdcaCompositeWeights(
        valuation=1.0, m2=0.5, dxy=0.5, hy_oas=0.5, ig_oas=0.5, nfci=0.5
    ),
    "inflation_bid": SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, breakeven_5y=0.5),
    "drop_m2": SdcaCompositeWeights(valuation=1.0, dxy=0.5, gvz=0.5, walcl=0.5),
    "drop_dxy": SdcaCompositeWeights(valuation=1.0, m2=0.5, gvz=0.5, walcl=0.5),
}


def _stats(risk: list[float | None]) -> dict[str, float]:
    valid = [v for v in risk if v is not None]
    buy_zone = sum(1 for v in valid if v < 25.0)
    return {
        "coverage": len(valid),
        "buy_zone_share": buy_zone / max(len(valid), 1),
        "mean_risk": sum(valid) / max(len(valid), 1),
    }


def main() -> None:
    dates, prices = load_sdca_ohlcv(symbols=["GLD-USD"], data_path=DATA_PATH, data_dir=None)
    date_s = pl.Series("date", dates, dtype=pl.Date)
    price_s = pl.Series("price", prices, dtype=pl.Float64)
    model = resolve_sdca_risk_model(
        "generic_valuation", dates=date_s, price=price_s, form="log_quadratic"
    )
    sources = load_sdca_extra_sources(DATA_PATH.parent)
    present = [k for k in ("gvz", "walcl", "hy_oas", "ig_oas", "breakeven_5y", "nfci")
               if getattr(sources, f"{k}_dates") is not None]
    print(f"new legs present: {present}")
    missing = set(FULL.enabled_extras()) - {"valuation"} - set(present) - {"m2", "dxy"}
    if missing:
        raise SystemExit(f"missing staged series for {sorted(missing)} — rerun Task 1")

    vectors = extra_z_vectors(date_s, price_s, FULL, sources)
    print(f"materialized: {sorted(vectors)}")

    seed_risk = json.loads(SEED_PATH.read_text())["risk"]
    report: dict[str, object] = {"candidates": {}, "correlations": {}}
    for name, weights in CANDIDATES.items():
        extras = extra_indicators_for_window(dates, dates, vectors, weights)
        index = build_risk_index(date_s, price_s, model, extras, valuation_weight=weights.valuation)
        risk = index["risk"].to_list()
        entry = _stats(risk)
        entry["legs"] = sorted(weights.enabled_extras())
        report["candidates"][name] = entry  # type: ignore[index]
        print(f"{name}: {entry}")
        if name == "seed":
            diff = max(
                abs(a - b)
                for a, b in zip(risk, seed_risk, strict=True)
                if a is not None and b is not None
            )
            report["seed_repro_max_abs_diff"] = diff
            print(f"seed repro max abs diff: {diff}")
            if diff != 0.0:
                raise SystemExit("seed no longer reproduces gold_seed.json — stop and investigate")

    names = ["m2", "dxy", "gvz", "walcl", "hy_oas", "ig_oas", "breakeven_5y", "nfci"]
    frame = pl.DataFrame({k: vectors[k] for k in names if k in vectors}).drop_nulls()
    corr = frame.correlation()
    matrix = {
        row: {col: round(val, 3) for col, val in zip(corr.columns, corr.row(i), strict=True)}
        for i, row in enumerate(corr.columns)
    }
    report["correlations"] = matrix
    print(json.dumps(matrix, indent=2))

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(report, indent=2))
    print(f"wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=digiquant/src python3 digiquant/scripts/run_gold_macro_expansion.py`
Expected: `new legs present` lists all six; seven candidate lines; `seed repro max abs diff: 0.0`; a correlation matrix; `wrote .../gold_macro_expansion.json`. Any `SystemExit` (missing series or repro diff != 0.0) stops the plan — do not work around it, investigate.

- [ ] **Step 3: Read the matrix for collinearity red flags**

Open `.scratch/gold_macro_expansion.json`. Any new leg with |r| > 0.7 against `m2`, `dxy`, or another new leg is flagged collinear — record the flag in the commit message body and in the Task 6 doc note (the later gate plan decides whether to drop it; this plan changes nothing).

- [ ] **Step 4: Lint + commit the script (output stays untracked)**

Run: `ruff check digiquant/scripts/run_gold_macro_expansion.py && ruff format --check digiquant/scripts/run_gold_macro_expansion.py`
Expected: clean.

```bash
git add digiquant/scripts/run_gold_macro_expansion.py
git commit -m "Add gold macro-expansion experiment script (#4804)"
```

---

### Task 6: Doc touch-up + full verification

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (named-indicators list only)
- Verify: full unit selection + ruff + `git status` clean of everything except gitignored staging

**Interfaces:**
- Consumes: Tasks 0–5.
- Produces: committed branch with docs matching the new interface; evidence log for the review.

- [ ] **Step 1: Update the named-indicators list in ARCHITECTURE.md**

Run: `grep -n "rs_eth\|EXTRA_INDICATOR_NAMES\|M2 / rs_eth / DXY\|M2,.*DXY" digiquant/ARCHITECTURE.md | head`
Expected: the section enumerating the macro extras (m2 / rs_eth / dxy) with their votes. Extend that enumeration in place with the six new legs using the exact display names from Task 3 (`gold volatility (GVZ)`, `Fed balance sheet`, `HY credit spread`, `IG credit spread`, `5Y breakeven`, `financial conditions (NFCI)`) and one line each stating the fear-bid sign convention (rising → +z, no flip; WALCL votes YoY growth like M2). Touch nothing else in the file. If the grep finds no such section, skip the edit and note its absence in the commit message instead of inventing a new section.

- [ ] **Step 2: Full verification pass**

```bash
pytest tests/dq/strategies/sdca/ tests/dq/test_export_sdca_macro.py -m unit -q
ruff check digiquant/ && ruff format --check digiquant/
git status --short
```

Expected: all green; `git status` shows only the plan's commits ahead plus `??` gitignored staging (CSVs, `.scratch/`, preview JSON). Staged CSVs must NOT appear as anything but ignored — if a new CSV shows as `??` non-ignored, stop: `git check-ignore` it and extend the ignore rule in the same commit rather than committing data.

- [ ] **Step 3: Commit the doc edit**

```bash
git add digiquant/ARCHITECTURE.md
git commit -m "Document gold macro legs in ARCHITECTURE.md (#4804)"
```

- [ ] **Step 4: Write the evidence log**

Append a dated entry to `.scratch/gold_macro_expansion.json`? No — JSON stays machine-readable. Instead print and record in the session: final `git log --oneline -8`, per-series source ledger from Task 1, Task 5 candidate table, and collinearity flags. This is the handoff to the review (`/review`) and the later gate/curve-search plan.

---

## Out of scope (later plans)

- Price-family extension (SLV/IAU/CPER/TIP/UUP/TLT tickers, GDX/GLD and gold/silver ratios, R2 universe additions) — Plan 2.
- Gloomberb enrichment persistence (snapshot-store design; GLD options-skew compute, 13F, econ calendar, news labeling; Fed transcripts unavailable, 13F holders branch broken upstream) — Plan 3. Note #4800 (gloomberb macro page adapter, in the 7-behind) may change the enrichment surface; re-check it when scoping Plan 3.
- Full walk-forward gate re-run with the winning macro set, dd-cap / sensitivity-bar calibration, and any `settings.json` promotion — Plan 4. The seed-reproduction gate in Task 5 is the tripwire that keeps this plan honest until then.

## Self-review

1. Spec coverage: hygiene (user-confirmed) → Task 0; backfill+stage → Task 1 (Task 2 unblocks it); SERIES_FILES → Task 2; weights/sources/maps → Task 3; z/branches/loader/drop → Task 4; experiment+collinearity → Task 5; docs+verify → Task 6. Every pool item in the macro family (GVZ, WALCL, HY/IG, 5y BE, NFCI, plus already-staged M2/DXY) has an owner. Fed transcripts and COT were cut at recon (unavailable) — correctly absent.
2. Placeholder scan: every step names exact files, lines, commands, expected outputs, and literal code. The two conditional branches (Task 1 missing-key fallthrough, Task 6 missing ARCH section) are explicit either/or instructions with defined actions, not open TODOs. No TBD/TODO/similar-to.
3. Type consistency: `gvz/walcl/hy_oas/ig_oas/breakeven_5y/nfci` spelled identically across weights, sources (`<name>_dates/<name>_values`), SERIES_FILES keys, CSV stems, z-function names (except `walcl_liquidity_z`, mirroring `m2_liquidity_z`), `WEIGHT_PARAM_BY_NAME` (`<name>_weight`), and the Task 5 script. `extra_z_vectors` keys come from `IndicatorWeight.name`, which the build branches set to the same ids `extra_indicators_for_window` looks up. `drop_extras_missing_sources` guards use `sources.<name>_dates`, matching the loader's constructor args.
