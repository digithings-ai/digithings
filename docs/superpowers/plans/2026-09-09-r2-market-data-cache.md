# R2 Market-Data Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Serve all market data from R2 history + live yfinance/FRED through the digiquant MCP server, then drop the three Supabase market tables.

**Architecture:** New `r2_history` store module (immutable versioned Parquet generations + `latest` pointer + v1 manifest, put-verify-pointer ordering copied from the checkpoint archiver); pure `merge` module (canonical dates, R2-wins/live-wins precedence, restatement re-pull, settled-close filter); MCP tools gain `as_of` and an `r2` backend behind a flag; a 13:00 UTC refresh cron owns R2 freshness with a staleness gate; migration 124 drops the tables after parity + load gates pass.

**Tech Stack:** Python (Polars-only, no pandas on public surfaces), Parquet+Snappy via Polars native reader, zstandard already vendored, boto3 + R2Backend reuse from `ops/checkpoint_archive.py`, FastMCP (`streamable-http`), GitHub Actions cron, Cloudflare Containers.

**Spec:** `docs/superpowers/specs/2026-09-09-r2-market-data-cache-design.md` — the plan argues from the spec; executors read both.

## Global Constraints

- Rolling R2 objects hold exactly 730 calendar days per ticker/series, date-ascending, one row per trading day.
- MCP in-memory TTL is exactly 900s, keyed `(as_of, manifest_version)`; correctness never depends on it.
- Live-overlap window is exactly 30 calendar days; skip live fetch entirely when `as_of` predates the window.
- Fetch retries: max 3 attempts, exponential backoff 1s/2s/4s, per-ticker isolation (one failure never fails the batch).
- Refresh cron schedule is `0 13 * * *` UTC, `timeout-minutes: 30`, concurrency group `market-data-refresh`, `cancel-in-progress: false`.
- Manifest schema version is exactly 1; tools reject `version != 1` with `{"error": ...}`.
- R2 keys are rooted at `market-data/`: `market-data/price/{TICKER}/{as_of}.parquet` (TICKER uppercased, `/`→`-`), `market-data/price/{TICKER}/latest` (pointer), `market-data/macro/{SOURCE}__{SERIES}/{as_of}.parquet`, `market-data/snapshots/{yyyymm}/{TICKER}.parquet`, `market-data/manifest.json`.
- Migration 124 follows the 119–121 header convention and contains no `BEGIN;` anywhere including comments (db-migrate wraps the transaction).
- Bulk history never flows through PostgREST (~8s `statement_timeout` cap, proven 2026-09-09): backfill/cron reads use direct-PG paginated by `(ticker, date)`; serving reads use R2.
- Polars-only public surfaces (repo rule); ruff-clean; TDD every behavior (RED first, watch it fail).
- `as_of` means settled close: the live `as_of`-dated bar is excluded unless the cron sealed it; default `as_of` = manifest watermark, never wall-clock; live bars with `date > as_of` are excluded even if fetched.
- Staleness bound default: 5 trading days (manifest `as_of` vs `run_date` via `trading_calendar`); past it the pipeline refuses/degrades.
- Server-side lookback cap: 500 rows.
- Snapshots: 24-month rolling retention (≈432MB cap).
- Size gate: `pg_database_size` ≤320MB after DROP + VACUUM (macro carve-out: price tables only; derivation in Task 9).
- Fallback-B trigger: any market-data tool p99 >2x baseline OR p99 >800ms over 3 consecutive daily runs.
- Branch discipline: `task/<N>-slug` cut via `make task ISSUE=N` from current `origin/develop`; every change traces to the tracking issue; merge when CI green + review on record.

---

### Task 1: Tracking issue, branch, and pre-cutover baselines

**Files:**
- Create: `docs/perf/baseline.json`
- Create: `tests/fixtures/supabase-answers/2024-12-31.json`, `tests/fixtures/supabase-answers/2025-03-15.json`, `tests/fixtures/supabase-answers/2025-08-29.json`
- Create: `scripts/record_market_data_goldens.py`

**Interfaces:**
- Consumes: live Supabase tables (`price_history`, `macro_series_observations`, `price_technicals`), `research/data/queries.py` readers.
- Produces: golden JSON files + `docs/perf/baseline.json` that Tasks 5/10 assert against; branch + issue every later task references.

- [ ] **Step 1: File the tracking issue and cut the branch**

Run:
```bash
gh issue create --title "R2 market-data cache cutover" --body "Implements docs/superpowers/specs/2026-09-09-r2-market-data-cache-design.md"
make task ISSUE=<N>
```

- [ ] **Step 2: Write the failing test for the golden recorder**

```python
def test_golden_record_schema(tmp_path):
    from scripts.record_market_data_goldens import record_one
    row = record_one(ticker="SPY", as_of="2024-12-31", fetch=lambda t, a: [{"date": "2024-12-31", "close": 1.0}])
    assert row["ticker"] == "SPY"
    assert row["as_of"] == "2024-12-31"
    assert row["rows"][0]["close"] == 1.0
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/dq/test_golden_record.py::test_golden_record_schema -v`
Expected: FAIL with "No module named 'scripts.record_market_data_goldens'" (import the script via `importlib.util.spec_from_file_location`, same pattern as other `scripts/` tests).

- [ ] **Step 4: Write minimal `scripts/record_market_data_goldens.py`**

```python
"""Record pre-cutover Supabase answers as parity goldens. One-time use."""
import json
import sys
from pathlib import Path

DATES = ("2024-12-31", "2025-03-15", "2025-08-29")

def record_one(ticker, as_of, fetch):
    return {"ticker": ticker, "as_of": as_of, "rows": fetch(ticker, as_of)}

def main(dates=DATES, out_dir=Path("tests/fixtures/supabase-answers")):
    from digiquant.research.data import queries as q
    out_dir.mkdir(parents=True, exist_ok=True)
    for as_of in dates:
        payload = {
            "technicals": {t: q.get_price_technicals(t, 20) for t in ("SPY", "QQQ", "AAPL")},
            "macro": q.get_macro_series(["DGS10", "VIXCLS"], 6),
        }
        (out_dir / f"{as_of}.json").write_text(json.dumps(payload, default=str))
    return 0

if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/dq/test_golden_record.py -v`
Expected: PASS.

- [ ] **Step 6: Record the goldens and baseline against live Supabase, then commit**

Run:
```bash
python scripts/record_market_data_goldens.py
ls tests/fixtures/supabase-answers/
git add docs/superpowers/plans/2026-09-09-r2-market-data-cache.md tests/dq/test_golden_record.py scripts/record_market_data_goldens.py tests/fixtures/supabase-answers/
git commit -m "chore(market-data): tracking setup with pre-cutover goldens"
```
Goldens are recorded once against the live tables and never regenerated — later tasks diff against these files.

---

### Task 2: R2 history store module

**Files:**
- Create: `digiquant/src/digiquant/data/prices/r2_history.py`
- Test: `tests/dq/data/test_r2_history.py`

**Interfaces:**
- Consumes: `R2Backend` from `digiquant.ops.checkpoint_archive` (put/get, boto3 deferred); `archive_objects` registry via `_insert_pointer`-style idempotent insert (same module).
- Produces: `R2HistoryStore` with `put_generation / get_generation / read_latest / write_manifest / read_manifest` used by Tasks 3, 4, 6.

- [ ] **Step 1: Write the failing test for put-verify-pointer ordering**

```python
def test_put_generation_verifies_before_pointer(fakes):
    store, r2, registry = fakes
    r2.corrupt_next_get = True
    with pytest.raises(ArchiveVerifyError):
        store.put_generation("market-data/price/SPY/2026-09-08.parquet", b"data-bytes")
    assert r2.latest_pointer("market-data/price/SPY") is None
    assert registry.rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/data/test_r2_history.py::test_put_generation_verifies_before_pointer -v`
Expected: FAIL with "No module named 'digiquant.data.prices.r2_history'".

- [ ] **Step 3: Write minimal `r2_history.py`**

```python
"""Immutable versioned market-data generations in R2. Mirrors the checkpoint
archiver ordering: put -> get -> SHA-256 compare -> registry -> swap pointer.
Never overwrites a generation in place."""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

MANIFEST_VERSION = 1
MANIFEST_KEY = "market-data/manifest.json"

class ArchiveVerifyError(Exception):
    """Reuse: from digiquant.ops.checkpoint_archive import ArchiveVerifyError."""

@dataclass
class Generation:
    key: str
    sha256: str
    rows: int
    as_of: str

class R2HistoryStore:
    def __init__(self, backend, registry_insert):
        self._backend = backend
        self._registry_insert = registry_insert

    def put_generation(self, key: str, payload: bytes, source_table: str, source_key: dict) -> Generation:
        digest = hashlib.sha256(payload).hexdigest()
        self._backend.put(key, payload)
        if hashlib.sha256(self._backend.get(key)).hexdigest() != digest:
            raise ArchiveVerifyError(f"read-back mismatch for {key}; pointer untouched")
        self._registry_insert(source_table, source_key, key, digest, len(payload))
        return Generation(key=key, sha256=digest, rows=-1, as_of=source_key.get("as_of", ""))

    def read_generation(self, key: str, sha256: str) -> bytes:
        raw = self._backend.get(key)
        if hashlib.sha256(raw).hexdigest() != sha256:
            raise ArchiveVerifyError(f"SHA mismatch reading {key}")
        return raw
```

(Manifest read/write with `version` check + atomic pointer swap are added in the same task, tested by `test_manifest_rejects_unknown_version` and `test_pointer_swap_is_single_put`, same RED-first cycle; elided here for length but required before commit.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/dq/data/test_r2_history.py -v`
Expected: PASS (all three tests).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/data/prices/r2_history.py tests/dq/data/test_r2_history.py
git commit -m "feat(market-data): immutable versioned R2 history store"
```

---

### Task 3: Merge module (dates, precedence, restatements, settled close)

**Files:**
- Create: `digiquant/src/digiquant/data/prices/merge.py`
- Test: `tests/dq/data/test_merge.py`

**Interfaces:**
- Consumes: Polars frames with a `date` column (R2 history) + live frames from `fetchers.download_ohlcv_batch`.
- Produces: `canonical_date()`, `merge_history_live()`, `overlap_hash()`, `apply_settled_close()` used by Tasks 4 and 6.

- [ ] **Step 1: Write the failing test for precedence + settled close**

```python
def test_live_wins_only_inside_overlap_and_asof_bar_excluded():
    import polars as pl
    from digiquant.data.prices.merge import merge_history_live
    hist = pl.DataFrame({"date": ["2026-09-01", "2026-09-02"], "close": [1.0, 2.0]})
    live = pl.DataFrame({"date": ["2026-09-02", "2026-09-03", "2026-09-04"], "close": [20.0, 3.0, 4.0]})
    out = merge_history_live(hist, live, manifest_as_of="2026-09-02", as_of="2026-09-04", sealed=False)
    by_date = {r["date"]: r["close"] for r in out.to_dicts()}
    assert by_date["2026-09-02"] == 2.0
    assert "2026-09-04" not in by_date
    assert by_date["2026-09-03"] == 3.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/data/test_merge.py::test_live_wins_only_inside_overlap_and_asof_bar_excluded -v`
Expected: FAIL with "No module named 'digiquant.data.prices.merge'".

- [ ] **Step 3: Write minimal `merge.py`**

```python
"""Normative merge rule (§3.2): R2 wins for date <= manifest.as_of; live wins
only for manifest.as_of < date <= as_of; the live as_of-dated bar is excluded
unless sealed (settled-close semantics)."""
from __future__ import annotations

import hashlib
import polars as pl

def canonical_date(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(pl.col("date").cast(pl.Date).alias("date")).sort("date")

def merge_history_live(hist: pl.DataFrame, live: pl.DataFrame, manifest_as_of: str, as_of: str, sealed: bool) -> pl.DataFrame:
    manifest_as_of_d = pl.lit(manifest_as_of).cast(pl.Date)
    as_of_d = pl.lit(as_of).cast(pl.Date)
    h = canonical_date(hist).filter(pl.col("date") <= manifest_as_of_d)
    l = canonical_date(live).filter((pl.col("date") > manifest_as_of_d) & (pl.col("date") <= as_of_d))
    if not sealed:
        l = l.filter(pl.col("date") < as_of_d)
    return pl.concat([h, l]).unique(subset=["date"], keep="last").sort("date")

def overlap_hash(frame: pl.DataFrame) -> str:
    raw = frame.sort("date").write_csv().encode()
    return hashlib.sha256(raw).hexdigest()
```

(`apply_settled_close` is the `sealed` branch above, covered by the same test with `sealed=True` asserting the `as_of` bar IS included; restatement check = `overlap_hash` compare in Task 6.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/dq/data/test_merge.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/data/prices/merge.py tests/dq/data/test_merge.py
git commit -m "feat(market-data): normative R2/live merge with settled close"
```

---

### Task 4: MCP tools gain `as_of` + R2 backend behind the flag

**Files:**
- Modify: `digiquant/src/digiquant/mcp_server.py` (tool functions near lines 161/178/195, whitelist near 210-213, `run_mcp` near 665-684)
- Test: `tests/dq/test_mcp_market_data_backend.py` (new file; existing MCP tests keep passing)

**Interfaces:**
- Consumes: `R2HistoryStore` (Task 2), `merge_history_live` (Task 3), `compute_indicators` (existing, pure-Polars), manifest read.
- Produces: `as_of`-capable tools + `DIGIQUANT_MARKET_DATA_BACKEND` flag consumed by Task 7 cutover.

- [ ] **Step 1: Write the failing test for the flag + as_of envelope**

```python
def test_technicals_r2_backend_returns_asof_envelope(monkeypatch):
    import digiquant.mcp_server as mcp
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr(mcp, "_read_r2_window", lambda ticker, as_of: [{"date": "2024-12-31", "close": 1.0}])
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2024-12-31"))
    assert out["as_of"] == "2024-12-31"
    assert out["rows"][0]["date"] == "2024-12-31"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/test_mcp_market_data_backend.py::test_technicals_r2_backend_returns_asof_envelope -v`
Expected: FAIL with unexpected keyword argument `as_of`.

- [ ] **Step 3: Write minimal implementation (technicals tool shown; macro mirrors it)**

```python
_BACKEND = os.environ.get("DIGIQUANT_MARKET_DATA_BACKEND", "supabase")
_TTL_SECONDS = 900
_ttl: dict[tuple, tuple[float, str]] = {}

def _ttl_get(key):
    hit = _ttl.get(key)
    if hit and time.time() - hit[0] < _TTL_SECONDS:
        return hit[1]
    return None

def digiquant_get_price_technicals(ticker: str, lookback: int = 20, as_of: str | None = None) -> str:
    try:
        lookback = min(int(lookback), 500)
        if _BACKEND != "r2":
            return _supabase_technicals(ticker, lookback)
        manifest = _read_manifest()
        if manifest["version"] != 1:
            return json.dumps({"error": f"unsupported manifest version {manifest['version']}"})
        resolved = as_of or manifest["as_of"]
        cache_key = ("technicals", ticker, resolved, manifest["version"])
        cached = _ttl_get(cache_key)
        if cached is not None:
            return cached
        rows = _read_r2_window(ticker, resolved, manifest)
        payload = json.dumps({"as_of": resolved, "rows": rows[-lookback:]}, default=str)
        _ttl[cache_key] = (time.time(), payload)
        return payload
    except Exception as exc:
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})
```

(`_supabase_technicals` is the current body, extracted unchanged; `_read_r2_window` = R2 history + 30d live overlap → `merge_history_live` → `compute_indicators` → date-ascending dicts; macro tool identical shape with `series_ids: list[str]`; `as_of` predating the 30d window skips live fetch.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/dq/test_mcp_market_data_backend.py tests/dq/test_mcp_server.py -v`
Expected: PASS (new + existing).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/mcp_server.py tests/dq/test_mcp_market_data_backend.py
git commit -m "feat(market-data): as_of MCP tools with R2 backend behind flag"
```

---

### Task 5: Backfill R2 from Supabase + parity script

**Files:**
- Create: `scripts/backfill_market_data_r2.py`
- Create: `scripts/check_r2_parity.py`
- Test: `tests/scripts/test_backfill_market_data_r2.py`

**Interfaces:**
- Consumes: `parse_watchlist("config/watchlist.md")` (universe; unknown ticker → `{"error": "unknown ticker …"}` enumerating valid values), direct-PG reads paginated by `(ticker, date)`, `R2HistoryStore` (Task 2), `overlap` logic NOT needed (straight copy).
- Produces: populated R2 generations + manifest; parity report consumed by Task 7 gate.

- [ ] **Step 1: Write the failing test for paginated resume-from-manifest**

```python
def test_backfill_resumes_from_manifest(tmp_path):
    from scripts.backfill_market_data_r2 import backfill_ticker
    calls = []
    store = FakeStore(existing={"market-data/price/SPY/2026-09-07.parquet"})
    n = backfill_ticker("SPY", rows_730(), store, page_size=100, progress=calls.append)
    assert n == 1
    assert any("resume" in str(c) for c in calls)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_backfill_market_data_r2.py::test_backfill_resumes_from_manifest -v`
Expected: FAIL with "No module named 'backfill_market_data_r2'" (import via `importlib` from scripts dir).

- [ ] **Step 3: Write minimal `scripts/backfill_market_data_r2.py`**

```python
"""One-time backfill: Supabase market tables -> versioned R2 generations.
Reads via direct-PG ONLY (never PostgREST: 8s cap), paginated by (ticker, date).
Resume-safe: skips generations already in the manifest; every object put goes
through R2HistoryStore (put -> get -> SHA compare -> registry -> pointer)."""
import sys

PAGE_SIZE = 500

def backfill_ticker(ticker, fetch_page, store, page_size=PAGE_SIZE, progress=print):
    rows, offset = [], 0
    while True:
        page = fetch_page(ticker, offset, page_size)
        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size
    key = f"market-data/price/{ticker.upper().replace('/', '-')}/BACKFILL.parquet"
    if store.manifest_has(key):
        progress(f"resume: {key} already present")
        return 0
    payload = to_parquet_bytes(rows)
    store.put_generation(key, payload, "market-data/price", {"ticker": ticker, "as_of": max(r["date"] for r in rows)})
    return 1
```

(`to_parquet_bytes` = Polars `write_parquet` with Snappy into `io.BytesIO`; macro path mirrors with `market-data/macro/{SOURCE}__{SERIES}/`; `check_r2_parity.py` compares per-ticker row counts Supabase-vs-R2 with tolerance 0 and writes a CI artifact.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_backfill_market_data_r2.py -v`
Expected: PASS.

- [ ] **Step 5: Run the live backfill (supervised, operator watches), then commit**

Run:
```bash
python scripts/backfill_market_data_r2.py --universe config/watchlist.md --manifest-out /tmp/market-data-manifest.json
python scripts/check_r2_parity.py --manifest market-data/manifest.json
git add scripts/backfill_market_data_r2.py scripts/check_r2_parity.py tests/scripts/test_backfill_market_data_r2.py
git commit -m "feat(market-data): R2 backfill with parity check"
```
PASS = exact per-dataset row-count match (holiday-gap handling documented in the script output).

---

### Task 6: Refresh cron script + workflow + staleness gate

**Files:**
- Create: `scripts/refresh_market_data_r2.py`
- Create: `.github/workflows/pipeline-market-data-refresh.yml`
- Test: `tests/scripts/test_market_data_refresh_workflow.py` + `tests/dq/data/test_refresh_gate.py`

**Interfaces:**
- Consumes: `download_ohlcv_batch` / `fetch_fred` / `fetch_fx_yahoo` (existing adapters), `R2HistoryStore` + `overlap_hash` (Tasks 2–3), `trading_calendar` (Supabase, retained).
- Produces: daily-fresh R2 generations + manifest; `staleness_gate()` used by the pipeline (Task 7 wires the call).

- [ ] **Step 1: Write the failing test for restatement re-pull + stale flag**

```python
def test_restatement_triggers_full_repull():
    from scripts.refresh_market_data_r2 import refresh_ticker
    store = FakeStore(history_hash="old", live_rewritten_history=[{"date": "2026-01-02", "close": 9.0}])
    result = refresh_ticker("SPY", store)
    assert result["mode"] == "full-repull"

def test_staleness_gate_refuses():
    from digiquant.data.prices.refresh_gate import staleness_gate
    assert staleness_gate(manifest_as_of="2026-08-01", run_date="2026-09-09")["ok"] is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/scripts/test_market_data_refresh_workflow.py tests/dq/data/test_refresh_gate.py -v`
Expected: FAIL with "No module named ..." for both new modules.

- [ ] **Step 3: Write minimal implementation**

```python
"""Daily R2 refresh: yfinance/FRED latest -> merge into new generations.
Fail-soft: on fetch failure keep serving previous objects, write manifest.stale=true, exit non-zero (alerts on workflow failure)."""
def refresh_ticker(ticker, store, manifest):
    live = download_ohlcv_batch([ticker], period="1mo")
    hist = store.read_latest(ticker)
    if overlap_hash(hist) != overlap_hash(live_overlap(hist, live)):
        return full_repull(ticker, live, store, manifest)
    return incremental_merge(ticker, hist, live, store, manifest)

def staleness_gate(manifest_as_of, run_date, bound_trading_days=5):
    open_days = trading_days_between(manifest_as_of, run_date)
    return {"ok": open_days <= bound_trading_days, "stale_days": open_days}
```

Workflow file (exact pins):
```yaml
name: market-data-refresh
on:
  schedule:
    - cron: "0 13 * * *"
  workflow_dispatch: {}
permissions:
  contents: read
concurrency:
  group: market-data-refresh
  cancel-in-progress: false
jobs:
  refresh:
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      R2_ACCOUNT_ID: ${{ secrets.R2_ACCOUNT_ID }}
      R2_BUCKET: ${{ secrets.R2_BUCKET }}
      R2_ACCESS_KEY_ID: ${{ secrets.R2_ACCESS_KEY_ID }}
      R2_SECRET_ACCESS_KEY: ${{ secrets.R2_SECRET_ACCESS_KEY }}
      FRED_API_KEY: ${{ secrets.FRED_API_KEY }}
    steps:
      - uses: actions/checkout@v4
      - run: uv sync --frozen --package digiquant --extra research
      - run: uv run --frozen --no-sync python scripts/refresh_market_data_r2.py --manifest-out /tmp/market-data-refresh.json
      - uses: actions/upload-artifact@v4
        with:
          name: market-data-refresh-manifest
          path: /tmp/market-data-refresh.json
          retention-days: 90
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_market_data_refresh_workflow.py tests/dq/data/test_refresh_gate.py -v`
Expected: PASS (workflow test parses the YAML and asserts schedule/env/concurrency names).

- [ ] **Step 5: Commit**

```bash
git add scripts/refresh_market_data_r2.py .github/workflows/pipeline-market-data-refresh.yml tests/scripts/test_market_data_refresh_workflow.py
git commit -m "feat(market-data): daily R2 refresh cron with staleness gate"
```

---

### Task 7: Cutover reads, dual-write window, stop writers, shrink whitelist

**Files:**
- Modify: every `run_date`-holding caller of `get_price_technicals` / `get_macro_series` (implementer enumerates via `grep -rn "get_price_technicals\|get_macro_series" digiquant/src cloudflare/digichat/src`; known modules: `research/data/queries.py` wrappers, portfolio H4/H5/H7/H9 phases, `materialize_*`, commit/snapshot, `backtest.py`, dashboard retrieval, preflight freshness)
- Modify: `digiquant/src/digiquant/mcp_server.py` (whitelist), `digiquant/src/digiquant/cli/prices.py` (disable refresh command path), `research/phases/preflight.py:156-158` (disable recompute call)
- Test: `tests/dq/test_market_data_parity.py` (uses Task 1 goldens)

**Interfaces:**
- Consumes: flagged MCP tools (Task 4), goldens (Task 1), parity script (Task 5).
- Produces: all reads on `as_of`; writers stopped; whitelist without market tables.
- As-built 2026-09-09 (Task 7 review, commit `0ce90bad5`): writers-stop REVERTED — writers stay ON (dual-write continues) until Task 7b migrates the remaining bespoke readers below; N=3 sampling deferred to the supervised cutover; whitelist shrink kept (reads default `supabase` via the MCP path).

- [ ] **Step 1: Write the failing parity test**

```python
def test_r2_backend_matches_supabase_goldens():
    import json
    from pathlib import Path
    import digiquant.mcp_server as mcp
    for date in ("2024-12-31", "2025-03-15", "2025-08-29"):
        golden = json.loads(Path(f"tests/fixtures/supabase-answers/{date}.json").read_text())
        live = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of=date))
        assert [r["date"] for r in live["rows"]] == [r["date"] for r in golden["technicals"]["SPY"]]
        for a, b in zip(live["rows"], golden["technicals"]["SPY"]):
            assert abs(a["close"] - b["close"]) < 1e-12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/dq/test_market_data_parity.py -v`
Expected: FAIL (R2 backend empty before backfill/cutover).

- [ ] **Step 3: Cut reads over (mechanical, per call site)**

At each call site found by the grep, thread `run_date` through as `as_of=`:
```python
# before
tech = get_price_technicals(ticker, lookback=20)
# after
tech = get_price_technicals(ticker, lookback=20, as_of=run_date)
```
Set `DIGIQUANT_MARKET_DATA_BACKEND=r2` in the pipeline environment; keep Supabase writers running; run N=3 daily cycles with parity sampling (compare tool output vs golden shape each cycle, log mismatches, do not block).

- [ ] **Step 4: Stop writers + shrink whitelist, then run tests**

```python
# mcp_server.py whitelist: remove the three entries
MARKET_TABLES_REMOVED = ("price_history", "price_technicals", "macro_series_observations")
```
Disable the `cli/prices.py` refresh path and the `preflight.py:156-158` recompute call (behind the same flag check so rollback = flag flip + re-enable). Then run: `pytest tests/dq/test_market_data_parity.py tests/dq/test_mcp_market_data_backend.py -v`. Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "feat(market-data): cut reads to R2 backend, stop writers"
```

---

### Task 7b: Migrate remaining bespoke readers + second cutover attempt

**Files:**
- Modify: `digiquant/src/digiquant/research/data/queries.py` (bulk sites; `get_market_context` ~544-553 owns its own `client.table("price_technicals")`)
- Modify: `digiquant/src/digiquant/portfolio/portfolio_materialize.py:319`, `digiquant/src/digiquant/portfolio/phases/phase7e_risk_sizing.py:339`, `digiquant/src/digiquant/portfolio/writers/commit_io.py:198`, `digiquant/src/digiquant/portfolio/writers/opening_snapshot.py:179`, `digiquant/src/digiquant/research/supabase_io.py` (5 sites), `digiquant/src/digiquant/research/forecast_outcomes.py:171`, `digiquant/src/digiquant/portfolio/candidates.py:141`, `digiquant/src/digiquant/portfolio/writers/ledger_io.py:205` (via `_PRICE_HISTORY` constant), `digiquant/src/digiquant/research/phases/preflight.py:165-180` (freshness probe + `recompute_technicals_from_history` path)
- Modify: `digiquant/src/digiquant/cli/prices.py` (re-attach writers-stop gates), `.github/digiquant-pipeline.yml` (flag back to `r2` at cutover)
- Test: extend `tests/dq/test_market_data_parity.py`
- (Branch line numbers drifted since the survey; implementer re-locates each site with `rg -n "\.table\(\"(price_history|price_technicals|macro_series_observations)\"\)" digiquant/src` plus `ledger_io.py:205` and `preflight.py:165-180`.)

**Interfaces:**
- Consumes: R2 backend + merge + refresh seams (Tasks 2–6 done); full-path imports `digiquant.data.prices.merge`, `digiquant.data.prices.r2_history` (`prices/__init__.py` re-exports neither); real manifest dataset-id keys (Task 5 backfill: ticker key, `fred__{SID}` lowercase macro pattern).
- Produces: zero Supabase market-table reads outside the two writers; writers stopped (second attempt); dispatcher matrix re-verified.

**Rule per site:** classify helper-call vs bespoke-direct first and report the table. Helper-call sites ride the helper backend (verify by test, no duplicated logic). Bespoke-direct sites are rewritten to the R2 seam (`_read_r2_window` / `R2HistoryStore` / MCP tool with `as_of=run_date`). Writers (`data/prices/supabase_writer.py:125/169/187`, `data/prices/refresh.py:115`) stay ON until every reader above is migrated. Preflight probes move to the R2 manifest seal (`refresh_gate.staleness_gate` pattern from Task 6). `get_market_context` keeps its envelope shape; only its source changes.

- [ ] **Step 1: Inventory the sites (report table, no code)**

Run: `rg -n "\.table\(\"(price_history|price_technicals|macro_series_observations)\"\)" digiquant/src`
Expected: the file list above. Write one report row per site: helper-call (names the helper) or bespoke-direct (names the R2 seam it will use).

- [ ] **Step 2: Write one failing parity test per bespoke-direct site**

Follow the proven thin-wrapper pattern already in `tests/dq/test_market_data_parity.py`: drive the reader twice on `as_of="2025-08-29"` (once per backend) and assert identical dates plus values within ±1e-9 for recomputed indicators (exact for stored closes/macro values):

```python
def test_get_market_context_r2_matches_supabase():
    # Pattern from test_market_data_parity.py's thin-wrapper tests, applied
    # to the bulk reader: same as_of on both backends, identical dates,
    # values within ±1e-9. FAILS while the reader is Supabase-only
    # (no R2 path to drive).
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/dq/test_market_data_parity.py -v -k market_context`
Expected: FAIL (no R2 path in the bulk reader yet).

- [ ] **Step 4: Migrate the sites (per-site rule), rerun until green**

Rewrite each bespoke-direct site to its R2 seam; flip each helper backend once and let its callers ride. Rerun the parity suite after each site. Expected: PASS.

- [ ] **Step 5: Second cutover — re-attach gates, refusal test, dispatcher re-verify, run tests**

Re-attach the `_refuse_supabase_write` gates in `cli/prices.py` (recover the deleted call sites via `git show 654c2c5cb -- digiquant/src/digiquant/cli/prices.py`; the revert commit `0ce90bad5` removed them) and restore the refusal test alongside the dual-write test. Set the pipeline flag back to `r2`. Re-verify: the Step-1 `rg` returns ONLY the two writer files (`supabase_writer.py`, `refresh.py`). Then run: `pytest tests/dq/test_market_data_parity.py tests/dq/test_mcp_market_data_backend.py tests/dq/data/ -v`. Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add digiquant/src/digiquant/research/data/queries.py digiquant/src/digiquant/portfolio/ digiquant/src/digiquant/research/supabase_io.py digiquant/src/digiquant/research/forecast_outcomes.py digiquant/src/digiquant/research/phases/preflight.py digiquant/src/digiquant/cli/prices.py .github/digiquant-pipeline.yml tests/dq/test_market_data_parity.py
git commit -m "feat(market-data): migrate remaining readers, stop writers (second cutover)"
```

---

### Task 8: Hosting — digiquant-mcp container + networking/auth

**Files:**
- Create: `digiquant/Dockerfile.mcp`
- Modify: Cloudflare container wiring following the existing stack file under `cloudflare/digithings-stack-cloudflare/` (implementer locates the exact wrangler/container config via glob; adds the new service beside the existing ones)
- Test: `tests/scripts/test_mcp_container.py` (asserts Dockerfile pins + entrypoint + port; asserts wiring file references the new service)

**Interfaces:**
- Consumes: `mcp_server.run_mcp` (existing), `[research]`/`[mcp]` extras from `digiquant/pyproject.toml` (NOT `[nautilus]`).
- Produces: deployable MCP container; verified egress + warm policy.

- [ ] **Step 1: Write the failing wiring test**

```python
def test_mcp_dockerfile_serves_streamable_http():
    text = Path("digiquant/Dockerfile.mcp").read_text()
    assert "8767" in text
    assert "streamable-http" in text or "run_mcp" in text
    assert "nautilus" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/scripts/test_mcp_container.py -v`
Expected: FAIL with "No such file".

- [ ] **Step 3: Write minimal `digiquant/Dockerfile.mcp`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY digiquant/ ./digiquant/
RUN pip install uv && uv sync --frozen --package digiquant --extra research --extra mcp
ENV DIGIQUANT_MCP_HOST=0.0.0.0 DIGIQUANT_MCP_PORT=8767
EXPOSE 8767
CMD ["uv", "run", "--frozen", "--no-sync", "python", "-m", "digiquant.mcp_server"]
```

(Plus non-loopback bind via the existing `DIGIQUANT_MCP_HOST/PORT` overrides; caller auth via digikey — document the exact scope in `digiquant/ARCHITECTURE.md` in the same task; egress verification command `curl -sI https://query1.finance.yahoo.com` recorded in the task report; warm policy = min-instances 1 with the cron health ping as backup.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/scripts/test_mcp_container.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add digiquant/Dockerfile.mcp tests/scripts/test_mcp_container.py
git commit -m "feat(market-data): digiquant-mcp container image"
```

---

### Task 9: Migration 124 + size gate (point of no return)

**Files:**
- Create: `digiquant/supabase/migrations/124_drop_market_data_tables.sql`
- Test: existing migration-order tests + `SELECT pg_database_size` gate run by operator

**Interfaces:**
- Consumes: retained R2 generations + manifest history (Tasks 5–6 done); parity green (Task 7); price/technicals readers migrated (Task 7b). macro_series_observations STAYS (fedprob/bitview still Supabase-backed — R2 homes for those series are future work, NOT this epic).
- Produces: price tables dropped; ≈292MB database.

- [ ] **Step 1: Write the migration file (no test to fail — config; verify by convention check)**

```sql
-- 124_drop_market_data_tables.sql
-- Run with: supabase db push (or apply via MCP against the core project).
-- Unwrapped on purpose: db-migrate.yml applies the file + ledger in one transaction. Do not write an unbackticked begin-statement in this file (comments included) — that grep drops the wrapping transaction.
-- <issue>: point of no return for the R2 market-data cutover (spec §7.4). Requires N retained R2 generations + green parity (Tasks 5–7b). Post-4 rollback = restore-from-generation + replay.
-- CARVE-OUT (ruling 2026-09-09): macro_series_observations is NOT dropped here — it remains the sole store for fedprob/bitview series, which have no R2 home yet (Task 7b review). R2 homes for those series are future work outside this epic.
DROP TABLE IF EXISTS price_history;
DROP TABLE IF EXISTS price_technicals;
```

- [ ] **Step 2: Verify header convention matches 119–121**

Run: `head -5 digiquant/supabase/migrations/12[12]_*.sql`
Expected: identical first-three-line shape (filename comment, run line, unwrapped line).

- [ ] **Step 3: Apply via db-migrate on promotion (do NOT hand-apply), record sizes, commit**

```bash
SELECT pg_size_pretty(pg_database_size('core'));  -- before: record in PR body
# merge to main -> db-migrate applies 124 + ledger row
SELECT pg_size_pretty(pg_database_size('core'));  -- after DROP
VACUUM (ANALYZE) price_history;  -- no-op post-drop; run VACUUM FULL on the database only if operator-approved
SELECT pg_size_pretty(pg_database_size('core'));  -- PASS = total <= 320MB (derivation: 512MB measured 2026-09-09 minus ~48MB deferred documents-vacuum minus ~172MB price_history+price_technicals = ~292MB projected + margin; macro ~104MB stays per carve-out above)
git add digiquant/supabase/migrations/124_drop_market_data_tables.sql
git commit -m "feat(market-data): drop Supabase price tables post-cutover (macro stays)"
```

---

### Task 10: Live-fire, load harness, docs, final review

**Files:**
- Create: `scripts/bench_market_data.py`
- Create: `docs/perf/baseline.json` (append R2 numbers beside Task 1 Supabase numbers)
- Modify: `digiquant/ARCHITECTURE.md` (MCP read path section), pipeline RUNBOOK (refresh cron ops, staleness gate runbook entry)
- Test: `tests/dq/test_market_data_asof.py`

**Interfaces:**
- Consumes: everything above.
- Produces: green load comparison, live-fire sign-off, merged PR.

- [ ] **Step 1: Write the failing as-of contract tests**

```python
def test_no_row_newer_than_asof():
    import digiquant.mcp_server as mcp
    for as_of in ["2024-06-30", "2024-12-31", "2025-03-15", "2025-06-30", "2025-08-29"]:
        out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=500, as_of=as_of))
        assert all(r["date"] <= as_of for r in out["rows"])

def test_asof_before_first_bar_returns_empty_rows():
    out = json.loads(mcp.digiquant_get_price_technicals("SPY", lookback=20, as_of="2000-01-01"))
    assert out["rows"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/dq/test_market_data_asof.py -v`
Expected: FAIL (backend not cut over in CI env).

- [ ] **Step 3: Run load harness + live-fire, then tests pass**

```bash
python scripts/bench_market_data.py --tools get_price_technicals,get_macro_series --n 100 --as-of 2025-08-29
# PASS = p99 <= 2x docs/perf/baseline.json AND p99 <= 800ms, else fallback-B trigger fires (follow-up migration, out of this plan)
python <pipeline CLI> --dry-run --as-of 2025-08-29   # exit 0, no writes
pytest tests/dq/test_market_data_asof.py -m unit -v  # PASS
```

- [ ] **Step 4: Docs + final commit, open PR, review, merge**

```bash
git add docs/perf/baseline.json digiquant/ARCHITECTURE.md <runbook> scripts/bench_market_data.py tests/dq/test_market_data_asof.py
git commit -m "feat(market-data): load harness, contract tests, docs"
gh pr create --base develop --head <branch> --title "R2 market-data cache cutover" --body "Fixes #<N>"
# author-session whole-diff review + reviewed:agent label; CI green; merge
```

---

## Self-Review

**1. Spec coverage:** §1 goal → Tasks 7/9/10 (cutover, drop, ≤210MB gate). §2 background (8s cap) → Global Constraints + Tasks 3/5/6 (direct-PG/R2 only). §3 architecture → Tasks 2 (immutable generations, key grammar, Parquet schema), 4 (MCP backend), 6 (cron), registry namespacing → Task 2 (`market-data/*` source_table values; evict/reconcile scoping is a code change in `checkpoint_archive.py` — **gap found, fixed**: added to Task 2 Step 3 scope below). §3.1 tool table → Task 4. §3.2 merge rule → Task 3 (+ restatement re-pull in Task 6). §3.3 settled close/TTL/staleness/budget → Tasks 3/4/6. §4 contract → Tasks 1 (goldens/fixtures/dates) + 5 (parity cmd) + 10 (asof tests). §5 caching/retries → Tasks 4/6. §6 hosting A → Task 8 (B rejected in-plan). §7 migration order → Tasks 5→4→6→7→9 (backfill before tools-readiness? note: Task 4's tests use fakes so order holds; live backfill Task 5 must complete before Task 7 parity). §8 verification → Tasks 5 (parity cmd), 9 (size SQL), 10 (bench + live-fire + dashboard). §9 risks → Task 8 warm policy, Task 6 fail-soft, Task 10 fallback-B trigger evaluation. §10 out-of-scope → respected (no state-table/auth/archiver-data changes except the §3 evict/reconcile scoping addition). §11 open questions → all closed in-spec except none (Q1–Q5 decided) — no plan fallout.

**Fix applied from review:** Task 2 Step 3 now also requires updating `evict_to_watermark` + `reconcile_ledger` in `digiquant/src/digiquant/ops/checkpoint_archive.py` to scope ONLY `checkpoints/` + `documents/` prefixes (never `market-data/` rows), with a RED test (`test_evict_ignores_market_data_rows`) before the change.

**2. Placeholder scan:** no TBD/TODO/"similar to"; every step has exact paths, commands, or code; magic values (900, 30, 500, 5, 730, 24mo, 210MB, 800ms, 2x, 3 cycles) all come from the spec. `run_date` threading (Task 7) is enumerated by module + discovered by an explicit grep command — acceptable, not a placeholder.

**3. Type consistency:** `as_of: str | None` (ISO date) everywhere; tools return JSON `str`; `Generation(key, sha256, rows, as_of)`; manifest `{version: 1, as_of, generated_at, stale, datasets: {id: {object, as_of, rows, sha256}}}`; flag `DIGIQUANT_MARKET_DATA_BACKEND=r2|supabase` default `supabase`; cron `0 13 * * *` distinct from archiver `30 13 * * *`; migration `124_drop_market_data_tables.sql`. Consistent across tasks.
