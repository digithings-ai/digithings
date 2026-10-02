# Gold price family (Plan 2: stage + wire ratios) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stage five price-family CSVs (SLV, TLT, TIP, UUP, CPER) next to the gold book and wire two ratio indicators (`gdx_gld`, `gld_slv`) through the SDCA extras on branch `task/4804-sdca-strategy-for-gold--gld`, closing with a price-family expansion experiment.

**Architecture:** Same plugin pattern as Plan 1 (macro legs), this time following the `rs_eth` ratio precedent: second-leg closes loaded from sibling CSVs, `log(leg/asset)` rolling-z, no sign flip (gold fear-bid book). R2 sealed universe needs NO config change — all eight tickers already have watchlist rows, so the cron already seals them; this plan only verifies that. Local staging uses the existing `digiquant prices` CLI; no CLI code changes.

**Tech Stack:** Python, Polars (never pandas), Pydantic v2 (frozen/strict), pytest (`-m unit`), ruff (line length 100), yfinance via the existing CLI.

**Spec:** `digiquant/src/digiquant/strategies/sdca/METHOD.md` (per-asset checklist); Plan 1 (`docs/superpowers/plans/2026-09-30-gold-macro-inputs.md`, committed through `f5b331837`); component docs `digiquant/AGENTS.md`, `digiquant/ARCHITECTURE.md`; recon anchors below (verified 2026-09-30, post-Plan-1 tree).

## Global Constraints

- Polars only; never pandas. Pydantic v2; new fields `float = Field(0.0, ge=0.0)`; models stay frozen/strict.
- ruff line length 100 on touched files only (broad `ruff format --check digiquant/` has pre-existing out-of-scope drift — do not touch unrelated files).
- Research-only: no `settings.json` entry, no Supabase push, no `gld` slug outside scripts/`.scratch`; nothing touches `digiquant/brokers/`, `digikey/`, or live order paths.
- BTC-isolation invariant: new weights default 0.0; `load_sdca_extra_z` auto-enable stays m2/rs_eth/dxy-only; the sidecar test (`EXTRA_INDICATOR_NAMES − GOLD_MACRO_NAMES`) must stay green — both new names join `GOLD_MACRO_NAMES` (same rationale as Ruling 6: gold-research additions postdating the BTC search).
- Book slug convention: price files use the `-USD` suffixed stem (`GLD-USD.csv`, `GDX-USD.csv` precedent); consumers pass the exact string. yfinance is asked for the suffixed form first; the probe rule in Task 1 settles what actually returns data.
- Sign convention (gold fear bid; +z votes buy): `gdx_gld` rising (miner participation confirms the bid) → +z, no flip; `gld_slv` rising (silver weak = stress) → +z, no flip. Both use `forward_fill=False` (daily-traded ETF legs, like `rs_eth`). The gate (later plan) decides.
- Worktree root for every command: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`. Interpreter: `.venv/bin/python` (never bare `python3`/`pytest`); `PYTHONPATH=digiquant/src` for scripts.
- No subagent dispatch from implementers; sequential tasks (later tasks consume earlier ones).

---

### Task 0: R2 universe verification (read-only)

**Files:** None modified. Reference: `digiquant/src/digiquant/research/config/watchlist.md` (rows: GDX:72, GLD:154, IAU:155, SLV:156, CPER:162, TLT:174, TIP:178, UUP:206).

**Interfaces:**
- Consumes: nothing.
- Produces: recorded evidence that the 2×-daily cron already seals all eight tickers (or a precise add-row edit if not).

- [ ] **Step 1: Confirm watchlist rows**

Run: `grep -n "^| *\(GDX\|GLD\|IAU\|SLV\|CPER\|TLT\|TIP\|UUP\) *|" digiquant/src/digiquant/research/config/watchlist.md`
Expected: eight rows (line numbers approximately as above). If any ticker is missing, add one row `| XXX | <short desc> | <category> |` matching the neighboring row format, verify it parses with `.venv/bin/python -c "from digiquant.data.prices.fetchers import parse_watchlist; print([t for t in parse_watchlist('digiquant/src/digiquant/research/config/watchlist.md') if t in ('GDX','GLD','IAU','SLV','CPER','TLT','TIP','UUP')])"` (run from worktree root; expect all eight listed), and commit the watchlist edit as `Stage gold price-family tickers in watchlist (#4804)`. If all eight are present (expected), no commit.

- [ ] **Step 2: Dry-run the R2 refresh planner**

Run: `PYTHONPATH=digiquant/src .venv/bin/python scripts/refresh_market_data_r2.py --dry-run 2>&1 | grep -iE "gdx|gld|slv|iau|cper|tip|uup|tlt" | head -30`
Expected: plan lines naming the price generations for the present tickers (keys `market-data/price/{TICKER}/{as_of}.parquet` per `r2_history.py:46-68`). If the script errors on missing required args (e.g. demands `--postgres-uri` even for dry-run), run `... --help`, record the requirement, and report DONE_WITH_CONCERNS — do NOT supply credentials, do NOT run a real refresh. The cron owns sealing; this task only verifies.

- [ ] **Step 3: Report**

No commit (unless the Step-1 row-add was needed). Report file records the grep output and dry-run lines. This unblocks Task 1 (local staging is independent of R2 either way).

---

### Task 1: Stage the five price CSVs

**Files:**
- Create (gitignored staging, never committed): `digiquant/data/price-history/{SLV-USD,TLT-USD,TIP-USD,UUP-USD,CPER-USD}.csv` (stems per the probe rule below)
- Create (untracked ledger, never committed): `digiquant/.scratch/gold_price_sources.json`

**Interfaces:**
- Consumes: `digiquant prices preload-history` (full-span overwrite, `cli/prices.py:755-768`).
- Produces: five OHLCV CSVs with `timestamp,open,high,low,close,volume,symbol` headers + a source ledger recording the fetch form per slug.

- [ ] **Step 1: Probe the fetch form per slug (book convention first)**

For each of `SLV-USD TLT-USD TIP-USD UUP-USD CPER-USD`, run from `digiquant/`:

```bash
cd digiquant && ../.venv/bin/python -m digiquant prices fetch-quotes --tickers <SLUG> --cache-dir /tmp/probe-<SLUG> --period 5d && wc -l /tmp/probe-<SLUG>/<SLUG>.csv; cd ..
```

Expected per slug: a CSV with a header + ≥1 data row. The `-USD` suffixed form is the hypothesis (GLD-USD/GDX-USD precedent). If a suffixed slug returns empty/errors (yfinance cannot resolve it), probe the plain ticker (`SLV`, …) the same way. Rule: use the suffixed stem if it returns data; else the plain stem. Record the winning form per slug — the next step and every consumer use exactly the recorded stems. Clean up `/tmp/probe-*` afterwards. If NEITHER form returns data for a slug, STOP with NEEDS_CONTEXT (exact error + both commands) — do not invent data, do not substitute a different ticker.

- [ ] **Step 2: Full-span staging with the winning forms**

For each winning `<STEM>` (expected: the five `-USD` stems):

```bash
cd digiquant && ../.venv/bin/python -m digiquant prices preload-history --tickers <STEM> --years 22 --cache-dir data/price-history; cd ..
```

Expected: `<STEM>.csv` in `digiquant/data/price-history/` with thousands of rows (SLV ~2006+, TLT ~2002+, TIP ~2003+, UUP ~2007+, CPER ~2010+). Rough row sanity: `wc -l` each file; any file under ~1000 rows is flagged suspicious (record, do not delete — Task 4 coverage stats re-verify).

- [ ] **Step 3: Write the source ledger**

```bash
.venv/bin/python -c "
import json
from pathlib import Path
import polars as pl
root = Path('digiquant/data/price-history')
ledger = {}
for stem in ['SLV-USD','TLT-USD','TIP-USD','UUP-USD','CPER-USD']:
    p = root / f'{stem}.csv'
    if not p.exists():
        alt = sorted(root.glob(stem.split('-')[0] + '*.csv'))
        ledger[stem] = {'missing': True, 'alternatives': [a.name for a in alt]}
        continue
    f = pl.read_csv(p)
    d = f['timestamp'].to_list()
    ledger[stem] = {'file': p.name, 'rows': len(f),
                    'first': str(d[0])[:10], 'last': str(d[-1])[:10]}
Path('digiquant/.scratch/gold_price_sources.json').write_text(json.dumps(ledger, indent=2))
print(json.dumps(ledger, indent=2))
"
```

Expected: printed JSON, five entries with rows/first/last (or explicit `missing` entries, which fail the task — a missing file after Step 2 is BLOCKED, not waived). No commit: staging + ledger are gitignored. Verify with `git status --short` (no new CSVs visible as committable) and `git check-ignore -v digiquant/data/price-history/SLV-USD.csv` (or whichever stem won).

---

### Task 2: Ratio weights model + sources model + name maps

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/indicator_catalog.py` (fields, tuples, maps, both parse helpers, `GOLD_MACRO_NAMES`)
- Create: `tests/dq/strategies/sdca/test_sdca_gold_price_family.py` (model-level tests; behavior tests land in Task 3)

**Interfaces:**
- Consumes: Plan-1 fields/maps (mirror the `rs_eth`/gold-leg pattern exactly).
- Produces: `gdx_gld` + `gld_slv` weight fields (default 0.0), `gdx_dates/gdx_close` + `slv_dates/slv_close` source fields, extended `MACRO_INDICATOR_NAMES`, `GOLD_MACRO_NAMES`, `WEIGHT_PARAM_BY_NAME`, `INDICATOR_DISPLAY_NAMES`, `extra_items`, both parse helpers.

- [ ] **Step 1: Write the failing model tests**

Create `tests/dq/strategies/sdca/test_sdca_gold_price_family.py` with:

```python
"""Gold price-family ratio legs: model fields, maps, and guards (#4804)."""

from __future__ import annotations

import pytest

from digiquant.strategies.sdca.indicator_catalog import (
    GOLD_MACRO_NAMES,
    MACRO_INDICATOR_NAMES,
    WEIGHT_PARAM_BY_NAME,
    ExtraIndicatorSources,
    SdcaCompositeWeights,
    composite_weights_from_params,
    indicator_display_name,
)

pytestmark = pytest.mark.unit

NEW_RATIOS = ("gdx_gld", "gld_slv")


def test_new_ratio_weights_default_zero() -> None:
    w = SdcaCompositeWeights()
    assert w.gdx_gld == 0.0
    assert w.gld_slv == 0.0
    assert w.enabled_extras() == {}


def test_new_ratio_names_in_tuples_and_param_map() -> None:
    for name in NEW_RATIOS:
        assert name in MACRO_INDICATOR_NAMES
        assert name in GOLD_MACRO_NAMES
        assert WEIGHT_PARAM_BY_NAME[name] == f"{name}_weight"
    assert indicator_display_name("gdx_gld") == "GDX/GLD participation"
    assert indicator_display_name("gld_slv") == "gold/silver ratio"


def test_composite_weights_from_params_reads_new_ratios() -> None:
    w = composite_weights_from_params({"gdx_gld_weight": 0.5, "gld_slv_weight": 0.25})
    assert w.gdx_gld == 0.5
    assert w.gld_slv == 0.25
    assert w.gvz == 0.0


def test_empty_sources_carry_no_ratio_series() -> None:
    sources = ExtraIndicatorSources()
    assert sources.gdx_dates is None and sources.gdx_close is None
    assert sources.slv_dates is None and sources.slv_close is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_sdca_gold_price_family.py -m unit -v`
Expected: FAIL at import or first attribute access (`gdx_gld` does not exist yet).

- [ ] **Step 3: Implement model changes (content-anchored; verify each anchor with grep first)**

In `indicator_catalog.py`, mirroring the existing `rs_eth`/gold-leg lines:

1. Append `"gdx_gld", "gld_slv"` to the `MACRO_INDICATOR_NAMES` tuple (multi-line post-Plan-1 format; keep ruff format clean).
2. Append both names to `GOLD_MACRO_NAMES` (same line shape as the existing six; the sidecar comment stays valid — these are gold-research additions postdating the BTC search under the same issue #4804).
3. `WEIGHT_PARAM_BY_NAME`: add `"gdx_gld": "gdx_gld_weight"`, `"gld_slv": "gld_slv_weight"`.
4. `INDICATOR_DISPLAY_NAMES`: add `"gdx_gld": "GDX/GLD participation"`, `"gld_slv": "gold/silver ratio"`.
5. `SdcaCompositeWeights`: add `gdx_gld: float = Field(0.0, ge=0.0)` and `gld_slv: float = Field(0.0, ge=0.0)` after the `nfci` field. The `_at_least_one_positive` validator is unchanged.
6. `extra_items`: append `("gdx_gld", self.gdx_gld)`, `("gld_slv", self.gld_slv)`.
7. `ExtraIndicatorSources`: add `gdx_dates: pl.Series | None = None`, `gdx_close: pl.Series | None = None`, `slv_dates: pl.Series | None = None`, `slv_close: pl.Series | None = None` (close-pairs like `eth_dates`/`eth_close`, NOT `_values` — these are price legs).
8. `composite_weights_from_params`: add `gdx_gld=float(params.get("gdx_gld_weight", 0.0))`, `gld_slv=float(params.get("gld_slv_weight", 0.0))`.
9. `parse_indicator_weights_json`: add `gdx_gld=float(payload.get("gdx_gld", 0.0))`, `gld_slv=float(payload.get("gld_slv", 0.0))`.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_sdca_gold_price_family.py tests/dq/strategies/sdca/test_indicator_catalog.py tests/dq/strategies/sdca/test_weight_search.py -m unit -v`
Expected: PASS throughout — including the sidecar test (new names must be in `GOLD_MACRO_NAMES`, else `search_names != catalog` fails; that failure means Step 3 edit #2 was missed).

- [ ] **Step 5: Lint + commit**

Run: `ruff check` + `ruff format --check` on exactly the two touched files (catalog + new test).
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/indicator_catalog.py tests/dq/strategies/sdca/test_sdca_gold_price_family.py
git commit -m "Add gold ratio legs to SDCA weights and sources (#4804)"
```

---

### Task 3: Ratio z-transforms + build branches + loader + drop guards

**Files:**
- Modify: `digiquant/src/digiquant/strategies/sdca/indicator_catalog.py` (two z-functions, two build branches)
- Modify: `digiquant/src/digiquant/strategies/sdca/optimize.py` (`load_sdca_extra_sources`, `drop_extras_missing_sources`, `SDCA_SHAPE_DEFAULTS`, `load_sdca_extra_z` docstring only)
- Modify: `tests/dq/strategies/sdca/test_sdca_gold_price_family.py` (behavior tests appended; header imports extended, never mid-file)

**Interfaces:**
- Consumes: Task 2 fields; `rs_eth_z` body (template); `align_to_dates`, `causal_rolling_z`, `_require_pair`.
- Produces: materializable `gdx_gld`/`gld_slv` extras; sibling-CSV loading (`GDX-USD.csv`, `SLV-USD.csv` or the Task-1-recorded stems); missing-source zeroing; shape-default entries. BTC vectors provably unchanged.

- [ ] **Step 1: Write the failing behavior tests**

Extend the Task 2 test file's header imports with `from datetime import date, timedelta`, `import polars as pl`, and the catalog/optimize names used below (merge into the existing import blocks — E402: no mid-file imports). Append:

```python
from digiquant.strategies.sdca.indicator_catalog import (
    extra_z_vectors,
    gdx_gld_z,
    gld_slv_z,
    build_extra_indicators,
)
from digiquant.strategies.sdca.optimize import (
    drop_extras_missing_sources,
    load_sdca_extra_sources,
)


def _daily(n: int) -> pl.Series:
    start = date(2020, 1, 1)
    return pl.Series("date", [start + timedelta(days=i) for i in range(n)], dtype=pl.Date)


def test_gdx_ripping_vs_flat_gld_votes_positive() -> None:
    dates = _daily(300)
    gld = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    gdx = pl.Series("v", [20.0 * (1.002**i) for i in range(300)], dtype=pl.Float64)
    z = gdx_gld_z(dates, gld, dates, gdx, window=30, min_samples=10)
    assert z[-1] > 1.0


def test_slv_crashing_vs_flat_gld_votes_positive() -> None:
    dates = _daily(300)
    gld = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    slv = pl.Series("v", [25.0 * (0.998**i) for i in range(300)], dtype=pl.Float64)
    z = gld_slv_z(dates, gld, dates, slv, window=30, min_samples=10)
    assert z[-1] > 1.0


def test_positive_ratio_weight_without_source_raises() -> None:
    dates = _daily(300)
    price = pl.Series("p", [100.0] * 300, dtype=pl.Float64)
    weights = SdcaCompositeWeights(valuation=1.0, gdx_gld=0.5)
    with pytest.raises(ValueError, match="gdx_gld"):
        build_extra_indicators(dates, price, weights, ExtraIndicatorSources())


def test_drop_extras_zeroes_ratios_without_sources() -> None:
    weights = SdcaCompositeWeights(valuation=1.0, gdx_gld=0.5, gld_slv=0.5)
    dropped = drop_extras_missing_sources(weights, ExtraIndicatorSources())
    assert dropped.valuation == 1.0
    assert dropped.gdx_gld == 0.0
    assert dropped.gld_slv == 0.0


def test_loader_picks_up_ratio_sibling_csvs(tmp_path: Path) -> None:
    (tmp_path / "GDX-USD.csv").write_text(
        "timestamp,open,high,low,close,volume,symbol\n"
        "2024-01-02,40,41,39,40.5,1000,GDX-USD\n"
        "2024-01-03,40.5,41.5,40,41.0,1100,GDX-USD\n",
        encoding="utf-8",
    )
    sources = load_sdca_extra_sources(tmp_path)
    assert sources.gdx_dates is not None and len(sources.gdx_dates) == 2
    assert sources.slv_dates is None


def test_btc_vectors_ignore_ratio_files_on_disk(tmp_path: Path) -> None:
    (tmp_path / "GDX-USD.csv").write_text(
        "timestamp,open,high,low,close,volume,symbol\n2024-01-02,40,41,39,40.5,1000,GDX-USD\n",
        encoding="utf-8",
    )
    sources = load_sdca_extra_sources(tmp_path)
    dates = _daily(400)
    price = pl.Series("p", [100.0 + 0.1 * i for i in range(400)], dtype=pl.Float64)
    vectors = extra_z_vectors(dates, price, SdcaCompositeWeights(valuation=1.0), sources)
    assert "gdx_gld" not in vectors and "gld_slv" not in vectors
```

(`Path` must be imported in the header block: `from pathlib import Path`.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/test_sdca_gold_price_family.py -m unit -v`
Expected: FAIL at import (`gdx_gld_z` does not exist yet).

- [ ] **Step 3: Implement the z-functions (catalog, after `nfci_z`)**

```python
def gdx_gld_z(
    dates: pl.Series,
    gld_price: pl.Series,
    gdx_dates: pl.Series,
    gdx_close: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """``log(GDX/GLD)`` rolling-z. Miner participation confirms the bid → +z (no flip)."""
    gdx = align_to_dates(dates, gdx_dates, gdx_close, forward_fill=False)
    ratio = (gdx / gld_price).log()
    return causal_rolling_z(ratio, window=window, min_samples=min_samples).alias("gdx_gld")


def gld_slv_z(
    dates: pl.Series,
    gld_price: pl.Series,
    slv_dates: pl.Series,
    slv_close: pl.Series,
    *,
    window: int = DEFAULT_ROLLING_WINDOW,
    min_samples: int = _MIN_SAMPLES,
) -> pl.Series:
    """``log(GLD/SLV)`` rolling-z. Silver weak vs gold = stress → +z (no flip)."""
    slv = align_to_dates(dates, slv_dates, slv_close, forward_fill=False)
    ratio = (gld_price / slv).log()
    return causal_rolling_z(ratio, window=window, min_samples=min_samples).alias("gld_slv")
```

(`forward_fill=False`: daily-traded ETF legs, same as `rs_eth_z`. Add both names to `__all__` alongside the Plan-1 z-exports.)

- [ ] **Step 4: Implement the two build branches (catalog, after the `nfci` branch)**

Two blocks mirroring the dxy block. Example (repeat for `gld_slv`/`gld_slv_z`/`slv_dates`/`slv_close`):

```python
    if "gdx_gld" in enabled:
        gdx_dates = _require_pair(sources.gdx_dates, sources.gdx_close, "gdx_gld")
        extras.append(
            IndicatorWeight(
                name="gdx_gld",
                z=gdx_gld_z(
                    dates,
                    btc_price,
                    gdx_dates,
                    sources.gdx_close,  # type: ignore[arg-type]
                    window=window,
                    min_samples=min_samples,
                ),
                weight=enabled["gdx_gld"],
            )
        )
```

(`btc_price` is the asset close — GLD here; the parameter name is inherited, do not rename it.)

- [ ] **Step 5: Implement the loader + drop guards + shape defaults (optimize.py)**

1. In `load_sdca_extra_sources`: after the NFCI resolution add
```python
    gdx_path = _first_existing(base, ("GDX-USD.csv", "GDX-USD.parquet"))
    slv_path = _first_existing(base, ("SLV-USD.csv", "SLV-USD.parquet"))
```
each followed by the `load_date_value_frame` conditional load, and thread `gdx_dates/gdx_close/slv_dates/slv_close` into the returned `ExtraIndicatorSources`. STEM RULE: if Task 1's ledger recorded a non-`-USD` winning stem for SLV (e.g. plain `SLV.csv`), use the recorded stem in the filename tuple instead of `"SLV-USD.csv"` (and say so in the report). GDX-USD.csv already exists under that stem — no fallback.
2. In `drop_extras_missing_sources`: add
```python
    if payload["gdx_gld"] > 0.0 and sources.gdx_dates is None:
        payload["gdx_gld"] = 0.0
    if payload["gld_slv"] > 0.0 and sources.slv_dates is None:
        payload["gld_slv"] = 0.0
```
3. Read `SDCA_SHAPE_DEFAULTS` (near the top of `optimize.py`, `"<name>_weight": 0.0` entries) and add `"gdx_gld_weight": 0.0, "gld_slv_weight": 0.0` in matching format.
4. `load_sdca_extra_z` docstring: extend the sibling list with the new files (docstring only — the auto-enable body stays m2/rs_eth/dxy-only; that is the BTC-isolation invariant).
5. Stage-A (`fit_weights.py` second-leg loading) and `asset_profile.py` allowlists are deliberately untouched: gold has no Stage-A flow and no asset profile (only `btc_v1`/`eth_research_v1`); gold scripts call the window functions directly without an allowlist. Record this skip in the report.

- [ ] **Step 6: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/dq/strategies/sdca/ tests/dq/test_export_sdca_macro.py -m unit -q`
Expected: PASS — new behavior tests green, whole engine suite unbroken (including the sidecar test via `GOLD_MACRO_NAMES`).

- [ ] **Step 7: Lint + commit**

Ruff check + format-check the three touched files.
Expected: clean.

```bash
git add digiquant/src/digiquant/strategies/sdca/indicator_catalog.py digiquant/src/digiquant/strategies/sdca/optimize.py tests/dq/strategies/sdca/test_sdca_gold_price_family.py
git commit -m "Wire gold ratio legs through SDCA extras (#4804)"
```

---

### Task 4: Gold price-family expansion experiment (research-only script)

**Files:**
- Create: `digiquant/scripts/run_gold_price_family_expansion.py`
- Create (untracked, never committed): `digiquant/.scratch/gold_price_family_expansion.json`

**Interfaces:**
- Consumes: Task 1 CSVs + Plan-1 macro CSVs via `load_sdca_extra_sources(DATA_PATH.parent)`; `extra_z_vectors` (materialize all eight non-valuation legs at once); `extra_indicators_for_window` + `build_risk_index` per candidate; frozen `generic_valuation/log_quadratic` rails (same as `run_gold_frozen_index.py:52-54`); `.scratch/gold_seed.json` for the repro gate.
- Produces: per-candidate index stats, full correlation matrix (macro + ratios), seed-reproduction check.

- [ ] **Step 1: Write the script**

Create `digiquant/scripts/run_gold_price_family_expansion.py` — same structure as `digiquant/scripts/run_gold_macro_expansion.py` (read that file first and mirror its imports, `_stats`, rails resolution, repro gate, matrix, and output handling exactly), with these substitutions:

- `OUT_PATH = DIGIQUANT_ROOT / ".scratch" / "gold_price_family_expansion.json"`, docstring names this experiment and issue #4804.
- `FULL = SdcaCompositeWeights(valuation=1.0, m2=0.5, dxy=0.5, gvz=0.5, walcl=0.5, hy_oas=0.25, ig_oas=0.25, breakeven_5y=0.25, nfci=0.25, gdx_gld=0.5, gld_slv=0.5)`.
- `CANDIDATES`: `seed` (identical to the macro script's seed: valuation=1.0, m2=0.5, dxy=0.5 — the repro gate compares against the same `gold_seed.json`), `ratio_pair` (seed + gdx_gld=0.5, gld_slv=0.5), `miners_only` (seed + gdx_gld=0.5), `metal_stress_only` (seed + gld_slv=0.5), `kitchen_sink` (= FULL), `drop_valuation_tilt` (FULL with valuation=0.5 — tests how much the rails carry once the vote broadens).
- Present-check: require both `gdx` and `slv` in sources (same `SystemExit("... rerun Task 1")` shape for what's missing).
- Correlation names: `["m2", "dxy", "gvz", "walcl", "hy_oas", "ig_oas", "breakeven_5y", "nfci", "gdx_gld", "gld_slv"]` (include only keys present in `vectors`; use the working polars API — the macro script uses `frame.corr()` after the Plan-1 `correlation()` fix, NOT `frame.correlation()`).
- Seed-repro gate identical: max abs diff vs `gold_seed.json` risk must equal 0.0 or `SystemExit`.

- [ ] **Step 2: Run it**

Run: `PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/run_gold_price_family_expansion.py`
Expected: `new legs present` lists gdx + slv (plus the six macro legs); six candidate lines; `seed repro max abs diff: 0.0`; a 10×10 correlation matrix; `wrote .../gold_price_family_expansion.json`. Any `SystemExit` stops the plan — report BLOCKED with the output, do not adjust.

- [ ] **Step 3: Read the matrix for collinearity red flags**

Open `.scratch/gold_price_family_expansion.json`. Any pair with |r| > 0.7 involving a ratio leg is flagged (expected watch-list: gdx_gld vs valuation — miners leverage the metal; gld_slv vs nfci/hy_oas — same stress vote). Record flags in the commit message body. The later gate plan decides drops; this plan changes nothing.

- [ ] **Step 4: Lint + commit the script (output stays untracked)**

Ruff check + format-check the new script.
Expected: clean.

```bash
git add digiquant/scripts/run_gold_price_family_expansion.py
git commit -m "Add gold price-family expansion experiment script (#4804)"
```

---

### Task 5: Doc touch-up + full verification

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (the `sdca/indicator_catalog.py` row extended in Plan 1 Task 6 — same row, append the two ratio legs)
- Verify: full unit selection + ruff + `git status` clean of everything except gitignored staging

**Interfaces:**
- Consumes: Tasks 0–4.
- Produces: docs matching the interface; evidence log for the review.

- [ ] **Step 1: Extend the catalog row in ARCHITECTURE.md**

Grep the row touched in Plan 1 (it names the six macro legs with `(#4804)` tags). Append `GDX/GLD participation` and `gold/silver ratio` with one line stating the ratio sign convention (`log(leg/asset)` rolling-z, rising → +z, no flip, `forward_fill=False` daily-ETF legs like `rs_eth`) and the sibling files (`GDX-USD.csv`, `SLV-USD.csv` or the Task-1-recorded stems). Touch nothing else. If the Plan-1 row is absent (rebase drift), skip with a commit-message note instead of inventing a section.

- [ ] **Step 2: Full verification pass**

```bash
.venv/bin/python -m pytest tests/dq/strategies/sdca/ tests/dq/test_export_sdca_macro.py tests/dq/data/test_prices_cli.py tests/dq/data/test_fetchers.py -m unit -q
ruff check digiquant/src/digiquant/strategies/sdca/ tests/dq/strategies/sdca/ digiquant/scripts/run_gold_price_family_expansion.py
ruff format --check digiquant/src/digiquant/strategies/sdca/ tests/dq/strategies/sdca/ digiquant/scripts/run_gold_price_family_expansion.py
git status --short
```

Expected: all green (broad-scope pre-existing drift, if any, must be shown to exist on files this plan did not touch — prove with `git stash` comparison if anything fails); `git status` shows only plan commits ahead plus `??` gitignored staging. New CSVs must NOT appear as committable — if one does, `git check-ignore` it and extend the ignore rule in the same commit rather than committing data.

- [ ] **Step 3: Commit the doc edit**

```bash
git add digiquant/ARCHITECTURE.md
git commit -m "Document gold ratio legs in ARCHITECTURE.md (#4804)"
```

- [ ] **Step 4: Write the evidence log**

Final report section: `git log --oneline` (plan commits), both ledgers (`.scratch/gold_price_sources.json`, `.scratch/gold_macro_sources.json`), Task 4 candidate table + collinearity flags, and deferred items for the gate plan (full-depth HY/IG re-stage; any |r|>0.7 ratio pairs).

---

## Out of scope (later plans)

- Gloomberb enrichment persistence (snapshot-store design; GLD options-skew compute, 13F, econ calendar, news labeling) — Plan 3. Note develop already carries #4809 (gloomberb macro ingest); re-check its surface when scoping Plan 3.
- TLT/TIP/UUP/CPER as *indicator* legs (staged but unwired — only SLV and GDX are consumed, via the two ratios). Wiring real-rate or liquidity-proxy legs from them is a future experiment proposal, not this plan.
- Full walk-forward gate re-run with the broadened vote, dd-cap / sensitivity-bar calibration, `settings.json` promotion — Plan 4.

## Self-review

1. Spec coverage: R2 verify → Task 0; stage five → Task 1 (probe rule settles the `-USD` question empirically); model → Task 2 (sidecar stays green via `GOLD_MACRO_NAMES`); behavior/loader/drop/defaults → Task 3; experiment+collinearity → Task 4; docs+verify → Task 5. TLT/TIP/UUP/CPER staged-but-unwired is declared out-of-scope above, not a gap.
2. Placeholder scan: every step names exact files, commands, expected outputs, literal code. Conditionals (missing watchlist row, probe fallback, absent ARCH row, stem rule) are explicit either/or instructions with defined actions.
3. Type consistency: `gdx_gld`/`gld_slv` spelled identically across weights, `WEIGHT_PARAM_BY_NAME` (`<name>_weight`), display names, `extra_items`, both parse helpers, z-functions, `IndicatorWeight` names, drop guards, `SDCA_SHAPE_DEFAULTS`, expansion script, ARCH row. Source fields follow the `rs_eth` close-pair convention (`gdx_dates/gdx_close`, `slv_dates/slv_close`), distinct from macro `_values` — matching what the loader and `_require_pair` consume.
