# Supabase → R2 Market-Data Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Retire the Supabase market-data read path (`price_history`, `price_technicals`) for all DigiQuant scripts, the dashboard, and digiquant-web, making the R2 store the single source of truth for historical bars while keeping same-day execution pricing correct.

**Architecture:** Scripts and CI consume the existing R2 seam (`digiquant.research.data.queries.r2_close_rows` / `r2_ohlcv_rows`, R2-only helpers gated by callers on `r2_backend_enabled()`), selected by `DIGIQUANT_MARKET_DATA_BACKEND=r2` (today set to `supabase` at `.github/digiquant-pipeline.yml:42`). Browser surfaces (dashboard static export, digiquant-web) cannot reach R2 directly, so a read-only Worker API (`/v1/market/*` on `graph.digithings.ai` in `cloudflare/digithings-stack-cloudflare`) reads the R2 manifest + parquet generations and serves CORS-enabled JSON. Writers are retired only after every reader is proven on R2; Supabase tables stay intact (readable, unwritten) until a separate deliberate drop (mirrors the deferred `124`/`900` drop pattern).

**Tech Stack:** Python 3.12 + Polars (digiquant), pytest; TypeScript + vitest (Cloudflare worker, dashboard, digiquant-web); R2 (S3-compatible), `hyparquet` (pure-JS parquet reader in the Worker); GitHub Actions.

**Spec:** https://github.com/digithings-ai/digithings/issues/4013 (owner decision comment: https://github.com/digithings-ai/digithings/issues/4013#issuecomment-5656541815) and `docs/superpowers/specs/2026-09-09-r2-market-data-cache-design.md`.

## Global Constraints

- Polars only — never pandas. Pydantic v2. `ruff` line length 100; `ruff check` + `ruff format --check` clean on every touched Python file.
- Issue linkage: every PR body carries `Refs #4013` (Task 12 carries `Fixes #4013`). Branch base `develop`; `task/<N>-slug` or `{feat,fix,chore}/…` naming per `BRANCHING.md`.
- Review coverage: `reviewed:agent` label + an `<!-- in-session-review -->` findings comment on every PR before merge (repo policy). Do not merge PRs into `main` — promotions are a human gate.
- Do not touch `digikey/`, `digiquant/brokers/`, or live-trading paths. New public read-only route on an existing Worker domain = note in the PR's Human Gate section.
- Worktree per task: `git worktree add -b <branch> .worktrees/task-XXXX origin/develop` (never work in the main checkout; do not disturb other sessions' `.worktrees/*`).
- Python tests run with `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest … -o pythonpath=$PWD/digiquant/src` (pytest.ini `pythonpath` otherwise resolves `digiquant` to the main worktree).
- Worker/web tests: `/Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run` from the package dir; worker typecheck via `npm run typecheck`.
- No production writes in this migration. Cuts over by merging PRs and flipping the env flag; never edit prod data.
- **No placeholder APIs:** all function names below exist on `origin/develop` (facts verified at `b6c22bf62`). If a signature has drifted, stop and follow the existing pattern at `commit_io.py:198-220`.

## Decisions (owner input requested — defaults proceed unless vetoed)

| # | Decision | Default in this plan | Owner action |
|---|----------|----------------------|--------------|
| D1 | Browser read-path auth | Public read-only on `graph.digithings.ai/v1/market/*` (parity: `price_history` is anon-readable today) + CORS allowlist | confirm or request edge auth |
| D2 | `FEDPROB/*` macro (no R2 generation) | Keep on Supabase; unchanged | later: add to R2 refresh |
| D3 | At-open same-day opens | Date-conditional: R2 for `d <= seal`, existing Supabase read for today; intraday `fetch-quotes --supabase` stays (scoped exception) | later: direct provider fetch at 09:35 ET to retire it |
| D4 | Evening freshness | Add second refresh cron `30 21 * * *` so the 22:00 UTC metrics job sees the settled day | confirm schedule |
| D5 | Implementer | Subagent-driven execution (implementer + task reviewer per task), one PR per phase cluster | confirm |

Ruling rationale: D3 is forced by physics — sealed R2 generations contain no unformed same-day bar (`r2_close_rows` docstring), and inventing a provider fetch inside `execute_at_open` adds a new execution-time network dependency that deserves its own review. D4 guarantees `seal >= run_date` for the 22:00 UTC metrics job without touching the execution path.

---

## Phase A — Script read path (no behavior change until a flag flips)

### Task 1: In-memory R2 market fixture for parity tests

**Files:**
- Create: `tests/fixtures/r2_market.py`
- Test: `tests/dq/research/test_r2_market_fixture.py`

**Interfaces:**
- Produces: `MemoryR2` (dict-backed `R2HistoryStore` surface: `read_manifest`, `read_latest`, `get_generation`), `build_r2_market(rows_by_ticker: dict[str, list[dict]], *, as_of: str) -> MemoryR2`, and pytest fixture `r2_market` — a builder `(rows_by_ticker, *, as_of) -> MemoryR2` that installs the store by patching `digiquant.mcp_server._get_r2_store` and setting `DIGIQUANT_MARKET_DATA_BACKEND=r2`. Later tasks call it as `r2_market({...}, as_of=...)`.
- Consumes: `digiquant.data.prices.r2_history` constants (`MANIFEST_KEY`, `generation_key`, `latest_pointer_key`, `normalize_ticker`, `SOURCE_TABLE_PRICE`); `digiquant.research.data.queries.r2_close_rows`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/research/test_r2_market_fixture.py
from digiquant.research.data.queries import r2_close_rows, r2_manifest_seal
from tests.fixtures.r2_market import build_r2_market


def test_fixture_serves_close_rows_and_seal(monkeypatch) -> None:
    store = build_r2_market(
        {"SPY": [{"date": "2026-09-10", "close": 100.0}, {"date": "2026-09-11", "close": 101.0}]},
        as_of="2026-09-11",
    )
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
    monkeypatch.setattr("digiquant.mcp_server._get_r2_store", lambda: store)
    rows = r2_close_rows(tickers=["SPY"], since="2026-09-10", until="2026-09-11")
    assert [(r["date"], r["ticker"], r["close"]) for r in rows] == [
        ("2026-09-10", "SPY", 100.0),
        ("2026-09-11", "SPY", 101.0),
    ]
    assert r2_manifest_seal() == ("2026-09-11", 1)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_r2_market_fixture.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL — `ModuleNotFoundError: tests.fixtures.r2_market`

- [ ] **Step 3: Write the fixture**

```python
# tests/fixtures/r2_market.py
"""In-memory R2 market-data store for parity tests (#4013)."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Any

import polars as pl
import pytest

from digiquant.data.prices.r2_history import (
    MANIFEST_KEY,
    SOURCE_TABLE_PRICE,
    generation_key,
    latest_pointer_key,
    normalize_ticker,
)


class MemoryR2:
    """Dict-backed stand-in for R2HistoryStore's read surface."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.manifest: dict[str, Any] = {"version": 1, "as_of": "1970-01-01", "datasets": {}}

    def read_manifest(self) -> dict[str, Any]:
        return json.loads(json.dumps(self.manifest))  # defensive copy

    def read_latest(self, pointer_key: str) -> str:
        return self.objects[pointer_key].decode("utf-8")

    def get_generation(self, key: str, sha256: str) -> bytes:
        payload = self.objects[key]
        assert hashlib.sha256(payload).hexdigest() == sha256, f"sha mismatch for {key}"
        return payload


def build_r2_market(rows_by_ticker: dict[str, list[dict[str, Any]]], *, as_of: str) -> MemoryR2:
    store = MemoryR2()
    store.manifest["as_of"] = as_of
    for ticker, rows in rows_by_ticker.items():
        frame = pl.DataFrame(rows).with_columns(pl.col("date").str.to_date())
        buf = io.BytesIO()
        frame.write_parquet(buf)
        payload = buf.getvalue()
        sha = hashlib.sha256(payload).hexdigest()
        key = generation_key(ticker, as_of)
        store.objects[key] = payload
        store.objects[latest_pointer_key(ticker)] = key.encode("utf-8")
        store.manifest["datasets"][normalize_ticker(ticker)] = {
            "object": key,
            "sha256": sha,
            "rows": frame.height,
            "source_table": SOURCE_TABLE_PRICE,
            "as_of": as_of,
        }
    store.objects[MANIFEST_KEY] = json.dumps(store.manifest).encode("utf-8")
    return store


@pytest.fixture
def r2_market(monkeypatch: pytest.MonkeyPatch):
    created: list[MemoryR2] = []

    def _build(rows_by_ticker: dict[str, list[dict[str, Any]]], *, as_of: str) -> MemoryR2:
        store = build_r2_market(rows_by_ticker, as_of=as_of)
        created.append(store)
        monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "r2")
        monkeypatch.setattr("digiquant.mcp_server._get_r2_store", lambda: store)
        return store

    return _build
```

Note: `_r2_manifest()` reads via `digiquant.mcp_server._read_manifest()` → `_get_r2_store().read_manifest()`; patching `_get_r2_store` is sufficient because it is looked up at call time inside `mcp_server`. If the seam reads the manifest through a module-level cached store in a later commit, patch `digiquant.mcp_server._read_manifest` instead — assert the test still passes first.

- [ ] **Step 4: Run test to verify it passes**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_r2_market_fixture.py -q -o pythonpath=$PWD/digiquant/src`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/r2_market.py tests/dq/research/test_r2_market_fixture.py
git commit -m "test(digiquant): add in-memory R2 market fixture for migration parity (#4013)"
```

---

### Task 2: Migrate the research-metrics trio (performance, attribution, finalize)

**Files:**
- Modify: `digiquant/scripts/research/refresh_performance_metrics.py` (reads at L119-124, L255-263, L473-478)
- Modify: `digiquant/scripts/research/refresh_attribution.py` (`_window_return` L85-94)
- Modify: `digiquant/scripts/research/finalize_period_accounting.py` (`_mark_from_close` L154-161)
- Test: `tests/dq/research/test_metrics_r2_reads.py`

**Interfaces:**
- Consumes: `r2_backend_enabled`, `r2_close_rows` from `digiquant.research.data.queries`; Task 1's `r2_market`.
- Produces: each helper keeps its exact current signature and return type, gaining an R2 branch. `_prev_trading_date(sb, ref_ticker, as_of) -> Optional[str]`; `_fetch_closes(sb, ticker, dates) -> Dict[str, float]`; `_window_return(client, ticker, start_iso, end_iso) -> float | None`; `_mark_from_close(*, client, symbol, as_of, observed_at) -> MarkObservation | None`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/dq/research/test_metrics_r2_reads.py
from datetime import date

from digiquant.scripts.research import finalize_period_accounting as fpa
from digiquant.scripts.research import refresh_attribution as ra
from digiquant.scripts.research import refresh_performance_metrics as rpm


def test_window_return_uses_r2_when_enabled(r2_market) -> None:
    r2_market({"GLD": [
        {"date": "2026-09-03", "close": 250.0},
        {"date": "2026-09-10", "close": 260.0},
    ]}, as_of="2026-09-10")
    assert ra._window_return(None, "GLD", "2026-09-03", "2026-09-10") == (260.0 / 250.0 - 1)


def test_fetch_closes_filters_to_requested_dates(r2_market) -> None:
    r2_market({"XLF": [
        {"date": "2026-09-09", "close": 50.0},
        {"date": "2026-09-10", "close": 51.0},
        {"date": "2026-09-11", "close": 52.0},
    ]}, as_of="2026-09-11")
    out = rpm._fetch_closes(None, "XLF", ["2026-09-10", "2026-09-11"])
    assert out == {"2026-09-10": 51.0, "2026-09-11": 52.0}


def test_prev_trading_date_uses_r2(r2_market) -> None:
    r2_market({"SPY": [
        {"date": "2026-09-09", "close": 100.0},
        {"date": "2026-09-10", "close": 101.0},
    ]}, as_of="2026-09-11")
    assert rpm._prev_trading_date(None, "SPY", "2026-09-11") == "2026-09-10"


def test_mark_from_close_uses_r2(r2_market) -> None:
    r2_market({"GLD": [{"date": "2026-09-10", "close": 260.0}]}, as_of="2026-09-10")
    mark = fpa._mark_from_close(client=None, symbol="GLD", as_of=date(2026, 9, 10),
                                observed_at=fpa.datetime(2026, 9, 10, 22, 0, tzinfo=fpa.timezone.utc))
    assert mark is not None and float(mark.price) == 260.0
```

(Reuse the real `MarkObservation` field name for price — read `finalize_period_accounting.py` L154-166 before writing the assertion; the existing Supabase branch builds it two lines below the read shown in the fact sheet.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_metrics_r2_reads.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL — `TypeError`/`AttributeError` because each helper ignores the flag and calls `client.table` on `None` (or reads Supabase).

- [ ] **Step 3: Add the R2 branch to each helper**

Pattern (mirrors `commit_io.py:198-220`). Import at the top of each script:
`from digiquant.research.data.queries import r2_backend_enabled, r2_close_rows`

`refresh_attribution._window_return` — replace the Supabase read block with:

```python
    if r2_backend_enabled():
        rows = r2_close_rows(tickers=[ticker], since=start_iso, until=end_iso)
        closes = [float(r["close"]) for r in rows if r.get("close") is not None]
        if len(closes) < 2 or closes[0] <= 0:
            return None
        return closes[-1] / closes[0] - 1.0
    resp = (
        client.table("price_history")
        ...  # unchanged
```

`refresh_performance_metrics._fetch_closes` — first lines of the body:

```python
    if not dates:
        return {}
    if r2_backend_enabled():
        wanted = set(str(d)[:10] for d in dates)
        rows = r2_close_rows(tickers=[ticker], since=min(wanted), until=max(wanted))
        return {
            str(r["date"])[:10]: float(r["close"])
            for r in rows
            if str(r["date"])[:10] in wanted and r.get("close") is not None
        }
```

`refresh_performance_metrics` benchmark window (L255-263) — before the Supabase block:

```python
    if len(nav_rows) >= 2 and r2_backend_enabled():
        benchmark_closes = [
            float(r["close"])
            for r in r2_close_rows(
                tickers=[benchmark_ticker],
                since=str(nav_rows[0]["date"]),
                until=str(nav_rows[-1]["date"]),
            )
            if r.get("close") is not None
        ]
    elif len(nav_rows) >= 2:
        ...  # unchanged Supabase block appending to benchmark_closes
```

`refresh_performance_metrics._prev_trading_date` — before the Supabase read:

```python
    if r2_backend_enabled():
        floor = (date.fromisoformat(as_of) - timedelta(days=_PREV_TRADING_LOOKBACK_DAYS)).isoformat()
        rows = r2_close_rows(tickers=[ref_ticker], since=floor, until=as_of)
        dates = [str(r["date"])[:10] for r in rows if str(r["date"])[:10] < as_of]
        return max(dates) if dates else None
```

Define `_PREV_TRADING_LOOKBACK_DAYS = 14` next to the module constants (the Supabase branch's implicit horizon is "latest before as_of"; 14 days covers holidays).

`finalize_period_accounting._mark_from_close` — before the Supabase read:

```python
    if r2_backend_enabled():
        rows = r2_close_rows(tickers=[symbol], since=as_of, until=as_of)
        closes = [float(r["close"]) for r in rows if r.get("close") is not None]
        if not closes:
            return None
        return <MarkObservation built exactly as the Supabase branch builds it, using closes[0]>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_metrics_r2_reads.py -q -o pythonpath=$PWD/digiquant/src`
Expected: PASS (4 passed)

- [ ] **Step 5: Lint + full-script regression**

```bash
.venv/bin/ruff check digiquant/scripts/research/refresh_performance_metrics.py \
  digiquant/scripts/research/refresh_attribution.py \
  digiquant/scripts/research/finalize_period_accounting.py tests/dq/research/test_metrics_r2_reads.py
.venv/bin/ruff format --check <same files>
PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research -q -o pythonpath=$PWD/digiquant/src
```
Expected: ruff clean; suite green (ignore `test_phase12.py::TestPhase1AltData::test_fan_out_produces_all_segments`, a known order-dependent failure).

- [ ] **Step 6: Commit**

```bash
git add digiquant/scripts/research/refresh_performance_metrics.py digiquant/scripts/research/refresh_attribution.py \
  digiquant/scripts/research/finalize_period_accounting.py tests/dq/research/test_metrics_r2_reads.py
git commit -m "feat(digiquant): read metrics/attribution/finalizer closes from R2 when enabled (#4013)"
```

---

### Task 3: Migrate the execution/backfill cluster (with same-day guard)

**Files:**
- Modify: `digiquant/scripts/research/execute_at_open.py` (`_fetch_open` L233-240, `_open_marks` L479-486)
- Modify: `digiquant/scripts/research/backfill_execution_prices.py` (`_fetch_open` L51-58)
- Modify: `digiquant/scripts/research/position_entry_from_events.py` (`_close_on_or_after` L56-63)
- Modify: `digiquant/scripts/research/fill-entry-prices.py` (`lookup_close` L53-61)
- Test: `tests/dq/research/test_execution_r2_reads.py`

**Interfaces:**
- Consumes: `r2_backend_enabled`, `r2_close_rows`, `r2_ohlcv_rows`, `r2_manifest_seal` (all from `digiquant.research.data.queries`).
- Produces: same signatures; R2 branch active only for `d <= seal` (same-day stays on the existing Supabase read — Decision D3).

- [ ] **Step 1: Write the failing tests**

```python
# tests/dq/research/test_execution_r2_reads.py
from digiquant.scripts.research import backfill_execution_prices as bep
from digiquant.scripts.research import execute_at_open as eao
from digiquant.scripts.research import fill_entry_prices as fep
from digiquant.scripts.research import position_entry_from_events as pfe


def test_fetch_open_uses_r2_for_sealed_dates(r2_market) -> None:
    r2_market({"GLD": [{"date": "2026-09-10", "open": 250.0, "high": 251.0,
                        "low": 249.0, "close": 260.0, "volume": 1000}]}, as_of="2026-09-10")
    assert eao._fetch_open(None, "GLD", "2026-09-10") == 250.0


def test_fetch_open_defers_unsealed_dates_to_supabase(r2_market) -> None:
    r2_market({"GLD": [{"date": "2026-09-09", "open": 240.0, "high": 241.0,
                        "low": 239.0, "close": 250.0, "volume": 1000}]}, as_of="2026-09-09")
    supabase = FakeSupabaseClient(canned_reads={"price_history": [{"open": 999.0}]})
    assert eao._fetch_open(supabase, "GLD", "2026-09-10") == 999.0  # today -> Supabase


def test_backfill_and_fill_helpers_use_r2(r2_market) -> None:
    r2_market({
        "XLV": [{"date": "2026-09-10", "open": 150.0, "high": 151.0,
                 "low": 149.0, "close": 152.0, "volume": 10}],
    }, as_of="2026-09-10")
    assert bep._fetch_open(None, "XLV", "2026-09-10") == 150.0
    assert fep.lookup_close(None, "XLV", "2026-09-10") == 152.0


def test_close_on_or_after_walks_forward_in_r2(r2_market) -> None:
    r2_market({"EWZ": [
        {"date": "2026-09-09", "close": 30.0},
        {"date": "2026-09-10", "close": 31.0},
    ]}, as_of="2026-09-10")
    assert pfe._close_on_or_after(None, "EWZ", "2026-09-09") == 30.0
    assert pfe._close_on_or_after(None, "EWZ", "2026-09-09T12:00:00") == 30.0
```

Add `from tests.dq.research.test_supabase_io import FakeSupabaseClient` to the test file. The string `"2026-09-09T12:00:00"` documents that callers may pass a timestamp; the helper must slice to `[:10]` before R2 lookups.

- [ ] **Step 2: Run tests to verify they fail**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_execution_r2_reads.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL — helpers call `sb.table` on `None`.

- [ ] **Step 3: Implement the date-conditional branches**

Both `_fetch_open` implementations (execute_at_open + backfill_execution_prices) get the same head:

```python
def _fetch_open(sb, ticker: str, d: str) -> Optional[float]:
    day = str(d)[:10]
    if r2_backend_enabled():
        seal, _ = r2_manifest_seal()
        if day <= seal.isoformat():
            rows = r2_ohlcv_rows(tickers=[ticker], since=day, until=day)
            if rows and rows[0].get("open") is not None:
                return float(rows[0]["open"])
            return None
    # same-day (or unsealed) prices come from the intraday Supabase writer (#4013 D3)
    res = (
        sb.table("price_history")
        ...  # unchanged
```

`execute_at_open._open_marks` — same guard, batched:

```python
    if r2_backend_enabled():
        seal, _ = r2_manifest_seal()
        if str(d)[:10] <= seal.isoformat():
            rows = r2_ohlcv_rows(tickers=sorted(set(tickers)), since=str(d)[:10], until=str(d)[:10])
            return {
                str(r["ticker"]): Decimal(str(r["open"]))
                for r in rows
                if r.get("open") is not None
            }
```

`position_entry_from_events._close_on_or_after`:

```python
    if r2_backend_enabled():
        since = str(iso)[:10]
        until = (date.fromisoformat(since) + timedelta(days=12)).isoformat()
        rows = r2_close_rows(tickers=[t], since=since, until=until)
        for row in rows:
            if row.get("close") is not None:
                return float(row["close"])
        return None
```

`fill-entry-prices.lookup_close`:

```python
    if r2_backend_enabled():
        day = str(entry_date)[:10]
        rows = r2_close_rows(tickers=[ticker], since=day, until=day)
        return float(rows[0]["close"]) if rows and rows[0].get("close") is not None else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_execution_r2_reads.py -q -o pythonpath=$PWD/digiquant/src`
Expected: PASS (4 passed)

- [ ] **Step 5: Regression + lint**

```bash
PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_execute_at_open.py tests/dq/research/test_execute_at_open_venue.py -q -o pythonpath=$PWD/digiquant/src
.venv/bin/ruff check digiquant/scripts/research/execute_at_open.py digiquant/scripts/research/backfill_execution_prices.py \
  digiquant/scripts/research/position_entry_from_events.py digiquant/scripts/research/fill-entry-prices.py tests/dq/research/test_execution_r2_reads.py
.venv/bin/ruff format --check <same files>
```
Expected: 72 passed; ruff clean above. Known caveat: `position_entry_from_events` is imported by other scripts — run `pytest tests/dq/research tests/dq/portfolio -q` if time allows.

- [ ] **Step 6: Commit**

```bash
git add digiquant/scripts/research/execute_at_open.py digiquant/scripts/research/backfill_execution_prices.py \
  digiquant/scripts/research/position_entry_from_events.py digiquant/scripts/research/fill-entry-prices.py \
  tests/dq/research/test_execution_r2_reads.py
git commit -m "feat(digiquant): R2 branches for execution/backfill price reads, same-day stays live (#4013)"
```

---

### Task 4: Migrate `verify_nav_replay.py` price fetch

**Files:**
- Modify: `digiquant/scripts/research/verify_nav_replay.py` (`_fetch_table` L125-190; call L510-521)
- Test: `tests/dq/research/test_verify_nav_r2.py`

**Interfaces:**
- Consumes: `r2_ohlcv_rows`, `r2_backend_enabled`; the existing `_rows_from_inception`, `_fetch_table`, and the #3995 envelope repair + #4002 grid alignment must all keep working (they operate on row dicts, so rows sourced from R2 flow through unchanged).
- Produces: `_fetch_price_rows(sb, house_id, book_tickers, inception) -> list[dict]` — a new thin helper that returns R2 rows when the flag is on, else the current `_fetch_table(...)` call. `main()` calls the helper.

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/research/test_verify_nav_r2.py
from datetime import date

from digiquant.scripts.research import verify_nav_replay as vnr


def test_price_rows_come_from_r2_when_enabled(r2_market) -> None:
    r2_market({"GLD": [{"date": "2026-09-10", "open": 250.0, "high": 251.0, "low": 249.0,
                        "close": 260.0, "volume": 1000}]}, as_of="2026-09-10")
    rows = vnr._fetch_price_rows(None, "house-id", ["GLD"], date(2026, 9, 1))
    assert rows and rows[0]["ticker"] == "GLD" and rows[0]["close"] is not None


def test_price_rows_fall_back_to_supabase_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("DIGIQUANT_MARKET_DATA_BACKEND", "supabase")
    calls: list[tuple] = []

    def fake_fetch(*args, **kwargs):
        calls.append((args, kwargs))
        return [{"date": "2026-09-10", "ticker": "GLD", "open": 1, "high": 1, "low": 1,
                 "close": 1, "volume": 1}]

    monkeypatch.setattr(vnr, "_fetch_table", fake_fetch)
    rows = vnr._fetch_price_rows(object(), "house-id", ["GLD"], date(2026, 9, 1))
    assert rows and calls and calls[0][0][1] == "price_history"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_verify_nav_r2.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL — `AttributeError: module … has no attribute '_fetch_price_rows'`

- [ ] **Step 3: Implement the helper and wire `main()`**

```python
def _fetch_price_rows(
    sb: SupabaseClient, house_id: str, book_tickers: list[str], inception: date
) -> list[dict[str, Any]]:
    """OHLCV rows for the replay: sealed R2 generations under the R2 backend, else Supabase."""
    if r2_backend_enabled():
        rows = r2_ohlcv_rows(
            tickers=book_tickers, since=inception.isoformat(), until=date.today().isoformat()
        )
        return _rows_from_inception(rows, inception)
    return _rows_from_inception(
        _fetch_table(
            sb,
            "price_history",
            house_id,
            "date,ticker,open,high,low,close,volume",
            workspace_scoped=False,
            tickers=book_tickers,
        ),
        inception,
    )
```

In `main()`, replace the L510-521 block body with:

```python
        price_rows = (
            _fetch_price_rows(sb, house_id, book_tickers, args.inception_date)
            if book_tickers
            else []
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_verify_nav_r2.py tests/dq/research/test_verify_nav_fetch.py -q -o pythonpath=$PWD/digiquant/src`
Expected: all pass — the #3990 unscoped-fetch tests still pin the Supabase path, the #3995 envelope repair and #4002 grid tests keep running against the same row shapes.

- [ ] **Step 5: Commit**

```bash
git add digiquant/scripts/research/verify_nav_replay.py tests/dq/research/test_verify_nav_r2.py
git commit -m "feat(digiquant): source replay bars from R2 when the backend flag is on (#4013)"
```

---

### Task 5: Migrate `backfill_context.py` (technicals seam)

**Files:**
- Modify: `digiquant/scripts/research/backfill_context.py` (`fetch_context` L61-150)
- Test: `tests/dq/research/test_backfill_context_r2.py`

**Interfaces:**
- Consumes: `r2_close_rows`, `r2_ohlcv_rows`, `get_price_technicals` (backend-branched internally — do **not** add a flag check around it), `r2_backend_enabled`.
- Produces: `fetch_context(as_of_date)` returns the same dict; under R2 the latest SPY close date comes from `r2_close_rows`, price rows from `r2_ohlcv_rows`, and technicals per ticker from `get_price_technicals(client=sb, ticker=t, lookback=1, as_of=latest_price_date)`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/research/test_backfill_context_r2.py
from digiquant.scripts.research import backfill_context as bc


def test_latest_price_date_and_technicals_from_r2(r2_market, monkeypatch) -> None:
    r2_market({
        "SPY": [{"date": "2026-09-10", "open": 100.0, "high": 101.0, "low": 99.0,
                 "close": 100.5, "volume": 10}],
    }, as_of="2026-09-10")
    monkeypatch.setattr(bc, "CORE_TICKERS", {"SPY"})
    ctx = bc.fetch_context("2026-09-10")
    assert ctx["latest_price_date"] == "2026-09-10"
    assert ctx["prices"] and ctx["prices"][0]["ticker"] == "SPY"
```

(Read `fetch_context`'s returned dict keys at L110-150 before writing this assertion; keep the real key names.)

- [ ] **Step 2: Run test to verify it fails**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_backfill_context_r2.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL — `_sb()` is called and tries to build a Supabase client, or `client.table` on fake rows returns nothing.

- [ ] **Step 3: Implement the R2 branch**

At the top of `fetch_context`:

```python
    if r2_backend_enabled():
        return _fetch_context_r2(as_of_date)
```

New helper (same file):

```python
def _fetch_context_r2(as_of_date: str) -> dict[str, Any]:
    """R2 branch of :func:`fetch_context` (#4013)."""
    floor = (date.fromisoformat(as_of_date) - timedelta(days=7)).isoformat()
    spy = r2_close_rows(tickers=["SPY"], since=floor, until=as_of_date)
    latest_price_date = max((str(r["date"])[:10] for r in spy), default=None)
    prices: list[dict] = []
    technicals: dict[str, dict] = {}
    if latest_price_date:
        rows = r2_ohlcv_rows(tickers=sorted(CORE_TICKERS), since=latest_price_date,
                             until=latest_price_date)
        prices = [r for r in rows if r.get("ticker") in CORE_TICKERS]
        for ticker in sorted(CORE_TICKERS):
            res = get_price_technicals(client=None, ticker=ticker, lookback=1,
                                       as_of=date.fromisoformat(latest_price_date))
            latest = res.get("latest") or {}
            if latest:
                technicals[ticker] = latest
    return {<the same keys the Supabase body returns>, "latest_price_date": latest_price_date,
            "prices": prices, "technicals": technicals}
```

(Key names must match the Supabase body exactly — copy the return literal from L110-150.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_backfill_context_r2.py -q -o pythonpath=$PWD/digiquant/src`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add digiquant/scripts/research/backfill_context.py tests/dq/research/test_backfill_context_r2.py
git commit -m "feat(digiquant): backfill_context reads bars/technicals from R2 when enabled (#4013)"
```

---

## Phase B — Freshness and cutover

### Task 6: Evening R2 refresh + freshness assertion (D4)

**Files:**
- Modify: `.github/workflows/pipeline-market-data-refresh.yml` (cron list; job env)
- Create: `digiquant/src/digiquant/research/data/freshness.py`
- Test: `tests/scripts/test_market_data_refresh_workflow.py` (extend), `tests/dq/research/test_freshness.py` (new)

**Interfaces:**
- Produces: `assert_market_data_fresh(*, max_age_days: int = 1, min_tickers: int = 100) -> None` raising `RuntimeError` with the seal date + counts when `date.today() - seal > max_age_days` or `ticker_count < min_tickers`; consumed by Task 7's cutover (step-level assertions) and available to any script.
- Consumes: `r2_manifest_seal()`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/dq/research/test_freshness.py
from datetime import date

import pytest

from digiquant.research.data.freshness import assert_market_data_fresh


def test_fresh_seal_passes(r2_market) -> None:
    r2_market({f"T{i}": [{"date": "2026-09-13", "close": 1.0}] for i in range(120)},
              as_of="2026-09-13")
    assert_market_data_fresh(max_age_days=0, min_tickers=100)  # seeded "today" via monkeypatch


def test_stale_seal_raises(r2_market, monkeypatch) -> None:
    r2_market({"SPY": [{"date": "2026-09-01", "close": 1.0}]}, as_of="2026-09-01")
    monkeypatch.setattr("digiquant.research.data.freshness.date", _FixedDate)
    with pytest.raises(RuntimeError, match="stale"):
        assert_market_data_fresh(max_age_days=1, min_tickers=1)
```

`_FixedDate` = a tiny shim subclassing `date` overriding `today()` to return `date(2026, 9, 13)` (define it in the test file).

- [ ] **Step 2: Run to verify failure, then implement**

```python
# digiquant/src/digiquant/research/data/freshness.py
"""R2 market-data freshness gate (#4013): a silent universe drop must fail loud."""

from __future__ import annotations

from datetime import date

from digiquant.research.data.queries import r2_manifest_seal


def assert_market_data_fresh(*, max_age_days: int = 1, min_tickers: int = 100) -> None:
    seal, tickers = r2_manifest_seal()
    age = (date.today() - seal).days
    if age > max_age_days:
        raise RuntimeError(f"R2 market data is stale: seal {seal.isoformat()} is {age}d old")
    if tickers < min_tickers:
        raise RuntimeError(f"R2 market data universe collapsed: {tickers} tickers < {min_tickers}")
```

- [ ] **Step 3: Add the evening cron + pin it**

In `.github/workflows/pipeline-market-data-refresh.yml`, change the schedule list to:

```yaml
  schedule:
    - cron: "0 13 * * *"    # morning: crypto + previous-settled equity bars
    - cron: "30 21 * * *"   # evening: settled US close before the 22:00 research-metrics run (#4013 D4)
```

Extend `tests/scripts/test_market_data_refresh_workflow.py::test_workflow_schedule_and_dispatch`:

```python
    assert {entry["cron"] for entry in on["schedule"]} == {"0 13 * * *", "30 21 * * *"}
```

- [ ] **Step 4: Verify**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/dq/research/test_freshness.py tests/scripts/test_market_data_refresh_workflow.py -q -o pythonpath=$PWD/digiquant/src`
Expected: PASS. Also `actionlint .github/workflows/pipeline-market-data-refresh.yml` → exit 0.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/research/data/freshness.py tests/dq/research/test_freshness.py \
  .github/workflows/pipeline-market-data-refresh.yml tests/scripts/test_market_data_refresh_workflow.py
git commit -m "feat(digiquant): evening R2 refresh cron + market-data freshness gate (#4013)"
```

---

### Task 7: Cut over the backend flag (the actual flip)

**Files:**
- Modify: `.github/digiquant-pipeline.yml:42` (`DIGIQUANT_MARKET_DATA_BACKEND: "supabase"` → `"r2"`; update the L32-41 comment to say the flip landed)
- Modify: `.github/workflows/pipeline-research-metrics.yml` — add `DIGIQUANT_MARKET_DATA_BACKEND: r2` to each of the five step `env:` blocks (L95-101, L112-117, L126-133, L148-153, L159-166); no job-level env exists
- Modify: `.github/workflows/pipeline-digiquant-prices.yml` — add the same flag to the at-open job env (L286-291); the date-conditional guard from Task 3 keeps same-day on Supabase
- Test: `tests/scripts/test_digiquant_pipeline_env.py` (new)

**Interfaces:**
- Consumes: all Phase A branches; Task 6's freshness gate.
- Produces: `DIGIQUANT_MARKET_DATA_BACKEND=r2` on every workflow that runs migrated readers; rollback = revert the one fragment line (documented in the PR body).

- [ ] **Step 1: Write the pin test**

```python
# tests/scripts/test_digiquant_pipeline_env.py
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_shared_pipeline_env_flags_r2() -> None:
    spec = yaml.safe_load((REPO_ROOT / ".github" / "digiquant-pipeline.yml").read_text())
    assert spec["env"]["DIGIQUANT_MARKET_DATA_BACKEND"] == "r2"


def test_research_metrics_steps_set_the_backend() -> None:
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-research-metrics.yml").read_text()
    )
    for step in spec["jobs"]["refresh"]["steps"]:
        env = step.get("env") or {}
        if "run" in step and "python digiquant/scripts/research/" in step["run"]:
            assert env.get("DIGIQUANT_MARKET_DATA_BACKEND") == "r2", step.get("name")
```

- [ ] **Step 2: Run to verify failure**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/scripts/test_digiquant_pipeline_env.py -q -o pythonpath=$PWD/digiquant/src`
Expected: FAIL on the `"r2"` assertions.

- [ ] **Step 3: Apply the flag edits**

Three YAML edits as listed in **Files** above. Keep `.github/digiquant-pipeline.yml`'s comment truthful — replace "flip … is safe" prose with "set to r2 2026-09-14 (#4013); supersedes the Supabase market-data writer path".

- [ ] **Step 4: Verify**

```bash
PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/scripts/test_digiquant_pipeline_env.py -q -o pythonpath=$PWD/digiquant/src
actionlint .github/workflows/pipeline-research-metrics.yml .github/workflows/pipeline-digiquant-prices.yml
```
Expected: 2 passed; actionlint exit 0.

- [ ] **Step 5: Cutover evidence (on the PR, before merge)**

Dispatch `pipeline-research-metrics.yml` on the PR branch for a known-good past date and confirm the run is green with `DIGIQUANT_MARKET_DATA_BACKEND` echoed in the run log, and that `nav_history`/`portfolio_metrics` rows for that date are byte-identical to the previous Supabase run (read-only SELECT comparison). Paste the run URL into the PR's Testing Evidence.

- [ ] **Step 6: Commit**

```bash
git add .github/digiquant-pipeline.yml .github/workflows/pipeline-research-metrics.yml \
  .github/workflows/pipeline-digiquant-prices.yml tests/scripts/test_digiquant_pipeline_env.py
git commit -m "feat(ci): flip market-data backend to r2 for research and at-open jobs (#4013)"
```

---

## Phase C — Browser read path

### Task 8: Worker market-data endpoints (`/v1/market/*`)

**Files:**
- Modify: `cloudflare/digithings-stack-cloudflare/wrangler.toml` (add R2 binding; no new route — reuse `graph.digithings.ai`)
- Modify: `cloudflare/digithings-stack-cloudflare/src/index.ts` (route branch + `ctx` param)
- Create: `cloudflare/digithings-stack-cloudflare/src/market-data.ts`
- Modify: `cloudflare/digithings-stack-cloudflare/package.json` (add `hyparquet`)
- Test: `cloudflare/digithings-stack-cloudflare/src/market-data.test.ts`

**Interfaces:**
- Produces: `GET /v1/market/tickers` → `{"as_of": "YYYY-MM-DD", "tickers": ["GLD", …]}`; `GET /v1/market/closes?tickers=A,B&from=YYYY-MM-DD&to=YYYY-MM-DD` → `{"as_of": "…", "rows": [{"date", "ticker", "close"}]}`. Pure helpers exported for tests: `manifestTickers(manifest)`, `resolvePointer(manifest, ticker)`, `shapeCloses(rows)`, `corsHeaders(origin, allowlist)`.
- Consumes: R2 binding `MARKET_DATA` (same bucket as the Python store — `digithings-archive`; confirmed by `wrangler.toml:105` comment), `manifest` at key `market-data/manifest.json`, per-ticker parquet at `market-data/price/{TICKER}/{as_of}.parquet` with pointer object `…/latest`.

- [ ] **Step 1: Write the failing tests** (pure helpers — no miniflare in this repo)

```ts
// src/market-data.test.ts
import { describe, expect, it } from "vitest";
import { corsHeaders, manifestTickers, resolvePointer, shapeCloses } from "./market-data";

const MANIFEST = {
  version: 1,
  as_of: "2026-09-11",
  datasets: {
    GLD: { object: "market-data/price/GLD/2026-09-11.parquet", sha256: "a".repeat(64) },
    SPY: { object: "market-data/price/SPY/2026-09-11.parquet", sha256: "b".repeat(64) },
    "fred__DGS10": { object: "market-data/macro/fred__DGS10/2026-09-11.parquet", sha256: "c".repeat(64) },
  },
};

describe("market-data helpers", () => {
  it("lists only price datasets", () => {
    expect(manifestTickers(MANIFEST).sort()).toEqual(["GLD", "SPY"]);
  });

  it("resolves a ticker entry case-insensitively", () => {
    expect(resolvePointer(MANIFEST, "gld")?.object).toContain("/GLD/");
    expect(resolvePointer(MANIFEST, "BRK/B")).toBeUndefined();
  });

  it("shapes and sorts close rows", () => {
    expect(
      shapeCloses([
        { date: "2026-09-11", ticker: "GLD", close: 260 },
        { date: "2026-09-10", ticker: "GLD", close: 250 },
      ]),
    ).toEqual([
      { date: "2026-09-10", ticker: "GLD", close: 250 },
      { date: "2026-09-11", ticker: "GLD", close: 260 },
    ]);
  });

  it("emits CORS only for allow-listed origins", () => {
    expect(corsHeaders("https://digiquant.io", ["https://digiquant.io"])["Access-Control-Allow-Origin"]).toBe(
      "https://digiquant.io",
    );
    expect(corsHeaders("https://evil.example", ["https://digiquant.io"])["Access-Control-Allow-Origin"]).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd cloudflare/digithings-stack-cloudflare && /Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run`
Expected: FAIL — `./market-data` not found.

- [ ] **Step 3: Implement `src/market-data.ts`**

```ts
// src/market-data.ts — read-only R2 market data for the dashboard/digiquant-web (#4013)
import { parquetReadObjects } from "hyparquet";

const MANIFEST_KEY = "market-data/manifest.json";
const DEFAULT_ORIGINS = "https://digiquant.io,https://digithings.ai,http://localhost:3005";

export type Manifest = { version?: number; as_of?: string; datasets?: Record<string, any> };

export function manifestTickers(manifest: Manifest): string[] {
  return Object.entries(manifest.datasets ?? {})
    .filter(([, entry]) => typeof entry?.object === "string" && entry.object.startsWith("market-data/price/"))
    .map(([ticker]) => ticker);
}

export function resolvePointer(manifest: Manifest, ticker: string): { object: string; sha256: string } | undefined {
  const norm = ticker.trim().toUpperCase().replace("/", "-");
  const entry = (manifest.datasets ?? {})[norm] ?? (manifest.datasets ?? {})[ticker];
  if (!entry?.object || !entry?.sha256) return undefined;
  return { object: String(entry.object), sha256: String(entry.sha256) };
}

export function shapeCloses(rows: Array<Record<string, unknown>>) {
  return rows
    .map((r) => ({ date: String(r.date).slice(0, 10), ticker: String(r.ticker), close: Number(r.close) }))
    .filter((r) => Number.isFinite(r.close))
    .sort((a, b) => (a.date === b.date ? a.ticker.localeCompare(b.ticker) : a.date.localeCompare(b.date)));
}

export function corsHeaders(origin: string | null, allowlist: string[]): Record<string, string> {
  const headers: Record<string, string> = { Vary: "Origin" };
  if (origin && allowlist.map((o) => o.trim()).includes(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers["Access-Control-Allow-Methods"] = "GET, OPTIONS";
    headers["Access-Control-Max-Age"] = "86400";
  }
  return headers;
}

async function sha256Hex(bytes: ArrayBuffer): Promise<string> {
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

export async function handleMarketData(
  request: Request,
  env: { MARKET_DATA: R2Bucket; MARKET_DATA_ALLOWED_ORIGINS?: string },
  url: URL,
): Promise<Response> {
  const allowlist = (env.MARKET_DATA_ALLOWED_ORIGINS ?? DEFAULT_ORIGINS).split(",");
  const cors = corsHeaders(request.headers.get("Origin"), allowlist);
  if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors });

  const manifestObj = await env.MARKET_DATA.get(MANIFEST_KEY);
  if (!manifestObj) return Response.json({ error: "manifest missing" }, { status: 503, headers: cors });
  const manifest = (await manifestObj.json()) as Manifest;

  if (url.pathname === "/v1/market/tickers") {
    return Response.json(
      { as_of: manifest.as_of ?? null, tickers: manifestTickers(manifest).sort() },
      { headers: { ...cors, "Cache-Control": "public, max-age=300" } },
    );
  }

  const tickers = (url.searchParams.get("tickers") ?? "").split(",").map((t) => t.trim()).filter(Boolean);
  const from = url.searchParams.get("from") ?? "1970-01-01";
  const to = url.searchParams.get("to") ?? manifest.as_of ?? "9999-12-31";
  if (!tickers.length) return Response.json({ error: "tickers required" }, { status: 400, headers: cors });

  const rows: Array<Record<string, unknown>> = [];
  for (const ticker of tickers.slice(0, 25)) {
    const pointer = resolvePointer(manifest, ticker);
    if (!pointer) continue;
    const object = await env.MARKET_DATA.get(pointer.object);
    if (!object) continue;
    const bytes = await object.arrayBuffer();
    if ((await sha256Hex(bytes)) !== pointer.sha256) {
      return Response.json({ error: `sha mismatch for ${ticker}` }, { status: 502, headers: cors });
    }
    const parsed = await parquetReadObjects({ file: bytes, columns: ["date", "ticker", "close"] });
    rows.push(...(parsed as Array<Record<string, unknown>>).filter((r) => {
      const d = String(r.date).slice(0, 10);
      return d >= from && d <= to;
    }));
  }
  return Response.json(
    { as_of: manifest.as_of ?? null, rows: shapeCloses(rows) },
    { headers: { ...cors, "Cache-Control": "public, max-age=300" } },
  );
}
```

Verify the `hyparquet` API surface first (`npm view hyparquet` + its README): if `parquetReadObjects({ file, columns })` is not the current export, use the equivalent column-projected reader from the installed version and adjust the test import accordingly. Pin the resolved version in `package.json` (`"hyparquet": "^1"`).

- [ ] **Step 4: Add the R2 binding + route branch**

`wrangler.toml` (top level, after `compatibility_flags`):

```toml
[[r2_buckets]]
binding = "MARKET_DATA"
bucket_name = "digithings-archive"
```

`src/index.ts`: add to the `Env` type `MARKET_DATA: R2Bucket; MARKET_DATA_ALLOWED_ORIGINS?: string;` and branch in `fetch` (before the `isMcpHostname` branch):

```ts
    if (url.pathname === "/v1/market/tickers" || url.pathname === "/v1/market/closes") {
      return handleMarketData(request, workerEnv, url);
    }
```

The default export's `fetch` already receives `(request, workerEnv)`; add the third `ctx` parameter only if the Cache API is added later (not required now — `Cache-Control` is set).

- [ ] **Step 5: Verify**

```bash
cd cloudflare/digithings-stack-cloudflare
/Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run
npm run typecheck
```
Expected: all tests pass (new + existing `env-vars-pin` and `ports`); typecheck exit 0. Optional end-to-end: `npx wrangler dev` + `curl 'http://localhost:8787/v1/market/tickers'` (requires R2 creds — skip if unavailable and note it in the PR).

- [ ] **Step 6: Commit + PR (human-gate note)**

```bash
git add cloudflare/digithings-stack-cloudflare
git commit -m "feat(worker): read-only /v1/market R2 endpoints for browser surfaces (#4013)"
```

PR body must check the **new network exposure** human-gate box (new public read-only route on `graph.digithings.ai`) and state D1's public-read-only decision.

---

### Task 9: Dashboard swap to the market-data API

**Files:**
- Create: `cloudflare/dashboard/lib/market-data.ts`
- Modify: `cloudflare/dashboard/lib/queries.ts` (`fetchComparablePriceHistory` L1577-1613; position price fill L1116-1137)
- Modify: `cloudflare/dashboard/lib/observability-queries.ts` (holding marks L981-993)
- Modify: `cloudflare/dashboard/.env.local.example` (add `NEXT_PUBLIC_MARKET_DATA_URL`)
- Test: `cloudflare/dashboard/lib/market-data.test.ts` (new), existing `queries`/`observability-queries` tests stay green

**Interfaces:**
- Produces: `fetchMarketCloses(tickers: string[], minDate: string, maxDate: string): Promise<{date,ticker,close}[]>` and `fetchMarketTickers(): Promise<string[]>`; both return empty/`[]` when `NEXT_PUBLIC_MARKET_DATA_URL` is unset. Consumers map results into the existing `BenchmarkHistoryMap` / holding-mark shapes — signatures unchanged.
- Consumes: Task 8 endpoints.

- [ ] **Step 1: Write the failing test**

```ts
// lib/market-data.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchMarketCloses } from "./market-data";

describe("fetchMarketCloses", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("maps worker rows and passes the window", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", "https://graph.digithings.ai");
    const fetchMock = vi.fn(async (url: string) => ({
      ok: true,
      json: async () => ({ as_of: "2026-09-11", rows: [{ date: "2026-09-10", ticker: "GLD", close: 250 }] }),
    }));
    vi.stubGlobal("fetch", fetchMock);
    const rows = await fetchMarketCloses(["GLD"], "2026-09-01", "2026-09-11");
    expect(rows).toEqual([{ date: "2026-09-10", ticker: "GLD", close: 250 }]);
    expect(String(fetchMock.mock.calls[0][0])).toContain("/v1/market/closes?tickers=GLD&from=2026-09-01&to=2026-09-11");
  });

  it("returns [] when unconfigured", async () => {
    vi.stubEnv("NEXT_PUBLIC_MARKET_DATA_URL", "");
    expect(await fetchMarketCloses(["GLD"], "2026-09-01", "2026-09-11")).toEqual([]);
  });
});
```

- [ ] **Step 2: Run to verify failure, then implement `lib/market-data.ts`**

```ts
const BASE = process.env.NEXT_PUBLIC_MARKET_DATA_URL ?? "";

export async function fetchMarketCloses(tickers: string[], minDate: string, maxDate: string) {
  if (!BASE || tickers.length === 0) return [];
  const url = `${BASE}/v1/market/closes?tickers=${encodeURIComponent(tickers.join(","))}&from=${minDate}&to=${maxDate}`;
  const res = await fetch(url);
  if (!res.ok) {
    console.error("fetchMarketCloses:", res.status);
    return [];
  }
  const body = (await res.json()) as { rows?: Array<{ date: string; ticker: string; close: number }> };
  return body.rows ?? [];
}
```

- [ ] **Step 3: Swap the three read sites**

`fetchComparablePriceHistory` — before the Supabase pagination loop:

```ts
  if (process.env.NEXT_PUBLIC_MARKET_DATA_URL) {
    const rows = await fetchMarketCloses(norm, minDate, maxDate);
    const out: BenchmarkHistoryMap = {};
    for (const row of rows) (out[row.ticker] ??= []).push({ date: row.date, price: row.close });
    return out;
  }
```

Holding marks (observability-queries.ts:981) — same shape:

```ts
    openTickers.length && process.env.NEXT_PUBLIC_MARKET_DATA_URL
      ? fetchMarketCloses(openTickers, markWindowFloor, markWindowCeiling).then((rows) => ({ rows, ok: true as const }))
      : <existing Supabase safeSelect>
```

Use the existing local date-window variables in `getPerformanceBundle` for `markWindowFloor/Ceiling` (the function already computes `navWindow[0].date` / `navWindow.at(-1)!.date`); do not invent new ones.

Position price fill (queries.ts:1116) — replace the `querySupabase` call with `fetchMarketCloses(posTickers, <90-day floor>, <today>)` when configured; keep the Supabase branch otherwise.

- [ ] **Step 4: Verify**

```bash
cd cloudflare/dashboard
/Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run lib/market-data.test.ts lib/queries.test.ts lib/observability-queries.test.ts
npm run lint
npm run build
```
Expected: tests pass; lint clean; `next build && check:static-export` succeeds (static export forbids server-only APIs — this design keeps everything client-side).

- [ ] **Step 5: Commit**

```bash
git add cloudflare/dashboard
git commit -m "feat(dashboard): read comparable closes and holding marks from the R2 market API (#4013)"
```

---

### Task 10: digiquant-web benchmark swap

**Files:**
- Create: `cloudflare/digiquant-web/lib/live/market-data.ts` (small client, same shape as Task 9 but mapping to `{date, price}`)
- Modify: `cloudflare/digiquant-web/lib/live/useLivePortfolio.ts` (L98-118)
- Test: `cloudflare/digiquant-web/lib/live/market-data.test.ts` (new)

**Interfaces:**
- Produces: `fetchBenchmarkHistory(ticker: string, fromDate: string): Promise<{date: string; price: number}[]>`; empty when `NEXT_PUBLIC_MARKET_DATA_URL` is unset.
- Consumes: Task 8 `/v1/market/closes`.

- [ ] **Step 1: Write the failing test** (mirror Task 9's shape, mapping to `{date, price}`), run it red, implement the client.
- [ ] **Step 2: Swap the read** — in `useLivePortfolio.ts`, replace the `client.from("price_history")` block with:

```ts
            const history = await fetchBenchmarkHistory(LANDING_BENCHMARK_TICKER, firstDate);
            if (!cancelled) setBenchmarkHistory(history);
```

- [ ] **Step 3: Verify** — `cd cloudflare/digiquant-web && /Users/chrisstefan/Code/digithings/node_modules/.bin/vitest run && npm run lint` (add `npm run build` if the package has one). Expected green.
- [ ] **Step 4: Commit** — `git commit -m "feat(digiquant-web): benchmark history from the R2 market API (#4013)"`

---

## Phase D — Writer retirement, docs, and close-out

### Task 11: Retire the technicals Supabase writer

**Files:**
- Modify: `.github/workflows/pipeline-digiquant-prices.yml` (delete the `Compute technicals -> upsert price_technicals` step L148-157; adjust the `run_writers` input description L88-96 and the L148 comment)
- Test: `tests/scripts/test_digiquant_prices_workflow.py` (new pin test)

**Interfaces:**
- Consumes: Task 5 (`backfill_context` now reads technicals from the seam) and the existing R2 recompute-on-read (`_r2_price_technicals`).
- Produces: the step no longer exists; `fetch-quotes --supabase` **stays** (D3 same-day exception) with a comment pointing at `execute_at_open._fetch_open`.

- [ ] **Step 1: Write the pin test**

```python
# tests/scripts/test_digiquant_prices_workflow.py
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _steps() -> list[dict]:
    spec = yaml.safe_load(
        (REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml").read_text()
    )
    return [step for job in spec["jobs"].values() for step in job.get("steps", [])]


def test_technicals_writer_is_gone() -> None:
    assert not [s for s in _steps() if "compute-technicals" in str(s.get("run", ""))]


def test_intraday_quotes_writer_stays_for_same_day_opens() -> None:
    quote_steps = [s for s in _steps() if "fetch-quotes" in str(s.get("run", ""))]
    assert quote_steps, "fetch-quotes --supabase is the documented same-day open source (#4013 D3)"
```

- [ ] **Step 2: Red → edit the workflow → green**

Run: `PYTHONPATH=$PWD/digiquant/src .venv/bin/python -m pytest tests/scripts/test_digiquant_prices_workflow.py -q -o pythonpath=$PWD/digiquant/src` (fails), then delete the step, update the input description to list only `fetch-macro fred/yahoo, sector refresh`, re-run (passes). `actionlint .github/workflows/pipeline-digiquant-prices.yml` → exit 0.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/pipeline-digiquant-prices.yml tests/scripts/test_digiquant_prices_workflow.py
git commit -m "chore(ci): retire the Supabase technicals writer (#4013)"
```

---

### Task 12: Docs, rollback notes, close-out

**Files:**
- Modify: `digiquant/ARCHITECTURE.md` (R2 backend section ~L316-340 and the market-data readers area): state R2 is the read path; note the two remaining Supabase touchpoints (at-open same-day opens, `FEDPROB/*`)
- Modify: `digiquant/src/digiquant/research/docs/RUNBOOK.md` (L51 area): env flag, evening refresh, freshness gate
- Modify: `cloudflare/dashboard/lib/TABLES.md`: mark `price_history` reads as API-backed
- Modify: `docs/ops/HOUSE_BOOK_SCOPE.md` only if it names `price_history` as a reader source (check; skip otherwise)
- Test: `make doc-check`

**Interfaces:** none (docs).

- [ ] **Step 1: Apply the doc edits** with exact new text: ARCHITECTURE gains a short subsection "Market-data reads: R2 (`DIGIQUANT_MARKET_DATA_BACKEND=r2`)" listing the seam fns, the flag location, the freshness gate, and the D3 exception; RUNBOOK gains the flag + evening cron + `assert_market_data_fresh` note.
- [ ] **Step 2: Verify** — `python3 scripts/check_doc_links.py` (expect OK, count updated).
- [ ] **Step 3: Commit + closing PR**

```bash
git add digiquant/ARCHITECTURE.md digiquant/src/digiquant/research/docs/RUNBOOK.md cloudflare/dashboard/lib/TABLES.md
git commit -m "docs(digiquant): R2 is the market-data read path; scoped Supabase exceptions (#4013)"
```

Open the final PR with `Fixes #4013`, a rollout/rollback section (revert `.github/digiquant-pipeline.yml` line 42 → `supabase`; Worker route is additive; dashboard falls back to Supabase when `NEXT_PUBLIC_MARKET_DATA_URL` is unset), and the deferred-drop note: **do not** drop `price_history`/`price_technicals`; that is a separate deliberate migration after a soak period, mirroring `124`/`900`.

---

## Rollout & Rollback Summary

| Step | Action | Rollback |
|------|--------|----------|
| A (T1-T5) | Merge reader branches (no-op while flag = supabase) | revert PRs |
| B (T6) | Merge evening cron + freshness gate | remove the `30 21 * * *` entry |
| B (T7) | Flip flag to `r2` | revert one line; both branches coexist |
| C (T8-T10) | Merge Worker + browser swaps (API returns 503 until T8 deploys; clients fall back when env unset) | unset `NEXT_PUBLIC_MARKET_DATA_URL`/`NEXT_PUBLIC_MARKET_DATA_URL` |
| D (T11-T12) | Retire technicals writer; docs | re-add the step |

## Self-Review (run before execution)

1. **Spec coverage:** nine scripts (T2-T5), freshness contract (T6), writer retirement (T11; `fetch-quotes` documented exception), browser surfaces (T8-T10), staging/final verification (T7 step 5, T12). Gaps: `FEDPROB/*` (D2, out of scope, documented), `price_history_tickers` universe view (dashboard L760 — replaced only if `fetchMarketTickers` is wired; if the dashboard needs it, T9 adds the call).
2. **Placeholder scan:** all code steps carry concrete code; the few `<…>` brackets are copy-instructions tied to exact line ranges, not "fill in later".
3. **Type consistency:** `r2_close_rows`/`r2_ohlcv_rows` keyword-only args (`tickers`, `since`, `until`) used consistently; `_fetch_price_rows` matches `_fetch_table`'s call order; worker `shapeCloses` output `{date,ticker,close}` matches both TS clients.
