# Gold enrichment snapshots (Plan 3: persistence + pulls) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first gloomberb enrichment snapshot store (JSON, gitignored, provenance-stamped) and wire five gold pulls through it — GLD options skew, GLD 13F, econ calendar, gold news, LBMA-fix probe — plus a weekly refresh workflow, on branch `task/4804-sdca-strategy-for-gold--gld`.

**Architecture:** No new pipeline, no store migration, no changes to the gloomberb client/models/MCP surface. Pulls go through the existing in-process dispatcher (`build_digifetch_tool_dispatcher`, anon client, free tools only) and persist its attribution-enveloped JSON plus a provenance header. Snapshots are enrichment-only by construction: consumers read labeled snapshots, never a source of record; the 15-minute delay and §5.2 caps are recorded per snapshot. Macro content stays with the R2/Supabase path (#4809 owns it — Task 0 confirms the boundary).

**Tech Stack:** Python, stdlib json/hashlib, Pydantic v2 (only via existing gloomberb models — no new models), pytest (`-m unit`, offline: injected fakes/Monkeypatched dispatcher, never live), ruff (line length 100), GitHub Actions (existing cron patterns only).

**Spec:** Recon B (gloomberb layer inventory, same session): package `digiquant/src/digiquant/data/gloomberb/` (`client.py`, `models.py`, `entitlements.py`, `agent_tools.py`, `attribution.py`, `normalizers.py`); MCP surface `mcp_server.py:884-1566`; component doc `digiquant/AGENTS.md` § "Gloomberb market-data client (#4069)"; runbook `docs/ops/gloomberb-session-cookie.md`. Landed develop work to re-check in Task 0: #4809 (gloomberb macro ingest), #4800 (macro page adapter).

## Global Constraints

- Enrichment-only, always: snapshots carry `fetched_at`, `delay_notice` ("Free-tier data delayed up to 15 minutes"), and attribution; nothing here feeds a pipeline, index, or gate. No `settings.json`, no Supabase writes, no R2 writes from this plan.
- Anon tools only: no `GLOOMBERB_SESSION_COOKIE` required or read; session/Pro-gated tools (transcripts, holders, analyst_research, screener, short_interest, equity_diagnostic, statements) are out of scope. Fed transcripts are unavailable (earnings-only + gated) — not attempted.
- §5.2 caps are reject-don't-clamp: never invent `range`/`limit` values beyond the models' bounds; `price_history` is NOT pulled (caps + delay disqualify it; native history owns prices).
- `econ_series` has `limit<=1000` and no offset: one snapshot holds at most one 1000-row tail page; backfill depth comes from repeated pulls over time, never from a single call. Never full-replace a longer history with one page (merge, don't overwrite — Task 1 implements newest-page merge for series snapshots).
- Offline tests only: never hit `api.gloom.sh` in pytest (no `GLOOMBERB_LIVE_SMOKE`); fake the dispatcher/client boundary with canned JSON.
- ruff line length 100 on touched files only. Research-only branch; nothing touches `brokers/`, `digikey/`, live paths.
- Worktree root: `/Users/chrisstefan/Code/digithings/.worktrees/task/4804-sdca-strategy-for-gold--gld`. Interpreter: `.venv/bin/python` (never bare); `PYTHONPATH=digiquant/src` for scripts. Sequential tasks.

---

### Task 0: Landed-surface read (no code)

**Files:** None modified. Read: #4809's macro-ingest code path, #4800's adapter, the options/13f/news/calendar input+output models.

**Interfaces:**
- Consumes: nothing.
- Produces: a boundary verdict (what #4809 persists, where, in what format) + confirmed model field lists for Tasks 2–3, recorded in the report.

- [ ] **Step 1: Map what #4809 persists**

Run: `git log --oneline origin/develop -15 -- digiquant/src/digiquant/data/gloomberb/ | head`; `grep -rn "econ_series\|R2StoreAdapter\|macro_series_observations" digiquant/src/digiquant/data/gloomberb/*.py digiquant/src/digiquant/data/prices/*.py | grep -vi test | head -30`
Expected: the exact writer path #4809 added (client method → store call), the store written (R2 generation? Supabase upsert?), the trigger (cron? manual?), and the series scope (all manifest? subset?). Record: module:line per hop. If #4809 persists NOTHING to disk/store (client-only), record that explicitly — the plan proceeds unchanged.

- [ ] **Step 2: Record the gold-pull model fields**

Read (exact paths): `digiquant/src/digiquant/data/gloomberb/agent_tools.py:133` (`build_gloomberb_client`), `:381` (`build_digifetch_tool_dispatcher` — confirm the `(name, dict) -> str` contract and the unknown-name error string), `models.py` options-chain output model (list every field of one option leg: strike/expiry/side/bid/ask/volume/openInterest/iv/greeks — whichever exist), `models.py:691-700` (13F input: `what` values, `tickers`/`quarter` shape), news input (feed/ticker/limit bounds), `digifetch_econ_calendar` (confirm no params).
Expected: a field table per pull in the report. If the options legs carry NO iv/greeks, record that — Task 2's skew metrics are then OI/volume-ratio based only (no invented greeks).

- [ ] **Step 3: Confirm the attribution/delay strings to stamp**

Read: `attribution.py:21-23` (exact `GLOOMBERB_ATTRIBUTION` + `GLOOMBERB_DELAY_NOTICE` text) and `normalizers.py:635-666` (`stale` vs `delayed` distinction).
Expected: exact strings quoted in the report; Task 1 stamps them verbatim.

- [ ] **Step 4: Report (no commit)**

Report file lists: #4809 boundary verdict, per-pull field tables, exact stamp strings, and any surface surprise (e.g. a #4809 snapshot dir already exists — if so, STOP with NEEDS_CONTEXT: design collision, do not duplicate it).

---

### Task 1: Snapshot store module + tests

**Files:**
- Create: `digiquant/src/digiquant/data/enrichment/__init__.py`, `digiquant/src/digiquant/data/enrichment/snapshots.py`
- Create: `tests/dq/data/test_enrichment_snapshots.py`

**Interfaces:**
- Consumes: dispatcher JSON strings (opaque `str` — the store never parses payloads, only wraps them).
- Produces: `snapshot_root()` / `write_snapshot()` / `load_latest()` / `prune_tool()` / `merge_series_page()` with the exact semantics below. Task 2+ consume these.

- [ ] **Step 1: Write the failing tests**

Create `tests/dq/data/test_enrichment_snapshots.py` with:

```python
"""Unit tests for the gloomberb enrichment snapshot store (#4804)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from digiquant.data.enrichment.snapshots import (
    load_latest,
    merge_series_page,
    prune_tool,
    snapshot_root,
    write_snapshot,
)

pytestmark = pytest.mark.unit


def test_write_then_load_latest_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    path = write_snapshot("digifetch_news", {"ticker": "GLD"}, '{"data": []}', fetched_at="2026-09-30T12:00:00Z")
    assert path.parent.name == "digifetch_news"
    latest = load_latest("digifetch_news")
    assert latest is not None
    doc = json.loads(Path(latest).read_text(encoding="utf-8"))
    assert doc["tool"] == "digifetch_news"
    assert doc["params"] == {"ticker": "GLD"}
    assert doc["fetched_at"] == "2026-09-30T12:00:00Z"
    assert doc["source"] == "gloomberb"
    assert "delay" in doc["delay_notice"].lower()
    assert "gloomberb" in doc["attribution"].lower()
    assert json.loads(doc["payload"]) == {"data": []}


def test_load_latest_missing_tool_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    assert load_latest("digifetch_nope") is None


def test_prune_tool_keeps_newest_n(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    for day in ("01", "02", "03"):
        write_snapshot("digifetch_news", {"ticker": "GLD"}, "{}", fetched_at=f"2026-09-{day}T12:00:00Z")
    removed = prune_tool("digifetch_news", keep=2)
    assert removed == 1
    assert len(list((snapshot_root() / "digifetch_news").glob("*.json"))) == 3  # 2 pages + latest.json


def test_merge_series_page_appends_newer_obs_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    first = [{"date": "2024-01-01", "value": 1.0}, {"date": "2024-01-02", "value": 2.0}]
    page = [{"date": "2024-01-02", "value": 2.0}, {"date": "2024-01-03", "value": 3.0}]
    merged = merge_series_page(first, page)
    assert [r["date"] for r in merged] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    with pytest.raises(ValueError, match="empty page"):
        merge_series_page(first, [])
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/data/test_enrichment_snapshots.py -m unit -v`
Expected: FAIL at import (`digiquant.data.enrichment` does not exist).

- [ ] **Step 3: Implement the store**

Create `digiquant/src/digiquant/data/enrichment/__init__.py` (re-export the five functions) and `snapshots.py` with exactly this behavior:

```python
"""Gloomberb enrichment snapshot store (research staging, #4804).

Snapshots are enrichment-only by construction: each file wraps one
dispatcher JSON payload with provenance (tool, params, fetched_at, source,
delay notice, attribution). Nothing here is a source of record — pipeline
inputs stay on the R2/Supabase path.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SNAPSHOT_VERSION = 1
DEFAULT_KEEP_PER_TOOL = 30


def snapshot_root() -> Path:
    """Root dir, overridable via DIGIQUANT_ENRICHMENT_DIR (tests)."""
    override = (os.environ.get("DIGIQUANT_ENRICHMENT_DIR") or "").strip()
    if override:
        return Path(override)
    return Path("digiquant") / "data" / "enrichment" / "snapshots"


def _params_hash(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def write_snapshot(tool: str, params: dict, payload_json: str, *, fetched_at: str) -> Path:
    """Persist one dispatcher payload. Returns the page path; refreshes latest.json."""
    from digiquant.data.gloomberb.attribution import (
        GLOOMBERB_ATTRIBUTION,
        GLOOMBERB_DELAY_NOTICE,
    )

    tool_dir = snapshot_root() / tool
    tool_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "snapshot_version": SNAPSHOT_VERSION,
        "tool": tool,
        "params": params,
        "fetched_at": fetched_at,
        "source": "gloomberb",
        "delay_notice": GLOOMBERB_DELAY_NOTICE,
        "attribution": GLOOMBERB_ATTRIBUTION,
        "payload": payload_json,
    }
    day = fetched_at[:10]
    page = tool_dir / f"{day}__{_params_hash(params)}.json"
    page.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (tool_dir / "latest.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return page


def load_latest(tool: str) -> str | None:
    """Newest snapshot path for ``tool`` (latest.json pointer), or None."""
    pointer = snapshot_root() / tool / "latest.json"
    return str(pointer) if pointer.is_file() else None


def prune_tool(tool: str, *, keep: int = DEFAULT_KEEP_PER_TOOL) -> int:
    """Delete oldest dated pages beyond ``keep`` (latest.json never pruned). Returns removed count."""
    pages = sorted((snapshot_root() / tool).glob("[0-9]*__*.json"))
    doomed = pages[: max(len(pages) - keep, 0)]
    for path in doomed:
        path.unlink()
    return len(doomed)


def merge_series_page(
    history: list[dict], page: list[dict], *, date_key: str = "date"
) -> list[dict]:
    """Newest-page merge for capped series (econ_series limit<=1000, no offset).

    Appends observations strictly newer than history's max date; drops
    duplicates by date (page wins on re-statement); never deletes history
    (no full-replace with one page). Empty page raises.
    """
    if not page:
        raise ValueError("refusing to merge an empty page into series history")
    have = {row[date_key]: row for row in history}
    for row in page:
        have[row[date_key]] = row
    return [have[day] for day in sorted(have)]
```

Note: the prune test counts 3 files (2 pages + latest.json) — implementation matches (latest.json excluded from the glob by the `[0-9]*__*` pattern).

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/bin/python -m pytest tests/dq/data/test_enrichment_snapshots.py -m unit -v`
Expected: 4/4 PASS.

- [ ] **Step 5: Lint + commit**

Ruff check + format-check the three new files.
Expected: clean.

```bash
git add digiquant/src/digiquant/data/enrichment/ tests/dq/data/test_enrichment_snapshots.py
git commit -m "Add gloomberb enrichment snapshot store (#4804)"
```

---

### Task 2: GLD options-skew pull + skew snapshot

**Files:**
- Create: `digiquant/scripts/pull_gold_enrichment.py` (dispatcher + store wiring; subcommands per pull)
- Modify: `tests/dq/data/test_enrichment_snapshots.py` — NO (store tests stay closed). New: `tests/dq/data/test_gold_enrichment_pulls.py` (offline: monkeypatched dispatcher returning Task-0-recorded fixture shapes)
- Create (gitignored): `digiquant/data/enrichment/snapshots/digifetch_options_chain/...`

**Interfaces:**
- Consumes: Task 1 store; Task 0 options-leg field table; `build_digifetch_tool_dispatcher` / `build_gloomberb_client` from `agent_tools.py`.
- Produces: `snapshot_options_skew()` returning the snapshot path + skew metrics dict; CLI `pull-gold-enrichment options-skew [--expiration EPOCH]`.

- [ ] **Step 1: Pin the options-leg fields from Task 0**

Open the Task 0 report's options field table. The skew metrics below are written against legs carrying at minimum `strike`, `expiration`, `side` (call/put), `openInterest`, `volume` (bid/ask/iv if present are bonus). If Task 0 recorded that any of the minimum five is ABSENT, STOP with NEEDS_CONTEXT (table vs code) — do not invent fields.

- [ ] **Step 2: Write the failing pull tests (offline, canned dispatcher JSON)**

Create `tests/dq/data/test_gold_enrichment_pulls.py` with tests that monkeypatch `build_digifetch_tool_dispatcher` (patch where the pull script imports it) to return a canned options-chain JSON string built from the Task-0 field table (two expiries × two strikes × call/put with distinct OI/volume), then assert: (a) `snapshot_options_skew()` returns a path under a `digifetch_options_chain` tool dir; (b) the metrics dict has per-expiry `put_call_oi` and `put_call_volume` ratios equal to the canned values; (c) the snapshot file's provenance header has `tool == "digifetch_options_chain"` and a non-empty `delay_notice`. Use `DIGIQUANT_ENRICHMENT_DIR` → tmp_path (same seam as the store tests) and `fetched_at` fixed string. No network, no client construction.

- [ ] **Step 3: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/data/test_gold_enrichment_pulls.py -m unit -v`
Expected: FAIL at import (`pull_gold_enrichment` module does not exist).

- [ ] **Step 4: Implement the pull script (options-skew subcommand first)**

Create `digiquant/scripts/pull_gold_enrichment.py`:

```python
#!/usr/bin/env python3
"""Gold enrichment pulls → snapshot store (research staging, #4804).

Each subcommand calls one free/anon digifetch tool through the in-process
dispatcher and persists the attribution-enveloped JSON via
``digiquant.data.enrichment.snapshots``. Enrichment-only: 15-minute delay,
§5.2 caps; never a pipeline input.

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/pull_gold_enrichment.py options-skew
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/pull_gold_enrichment.py options-skew --expiration 1798761600
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from digiquant.data.enrichment.snapshots import write_snapshot  # noqa: E402


def _dispatcher():
    from digiquant.data.gloomberb.agent_tools import build_digifetch_tool_dispatcher

    return build_digifetch_tool_dispatcher()


def _now_utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def snapshot_options_skew(
    symbol: str = "GLD", expiration: int | None = None, *, fetched_at: str | None = None
) -> tuple[str, dict]:
    """Snapshot the GLD chain and compute per-expiry put/call OI + volume ratios.

    Metrics use only OI/volume/strike/side/expiration (no greeks — the free
    tier does not return them; see Task 0 field table). Ratios > 1 mean
    put-heavy positioning for that expiry.
    """
    params: dict = {"symbol": symbol}
    if expiration is not None:
        params["expiration"] = expiration
    raw = _dispatcher()("digifetch_options_chain", params)
    legs = json.loads(raw)["data"]["contracts"]  # shape per Task 0 table; KeyError surfaces drift
    by_expiry: dict[str, dict] = {}
    for leg in legs:
        bucket = by_expiry.setdefault(str(leg["expiration"]), {"call_oi": 0.0, "put_oi": 0.0, "call_vol": 0.0, "put_vol": 0.0})
        side = "put" if leg["side"].lower().startswith("put") else "call"
        bucket[f"{side}_oi"] += float(leg.get("openInterest") or 0.0)
        bucket[f"{side}_vol"] += float(leg.get("volume") or 0.0)
    metrics = {
        exp: {
            "put_call_oi": (b["put_oi"] / b["call_oi"]) if b["call_oi"] else None,
            "put_call_volume": (b["put_vol"] / b["call_vol"]) if b["call_vol"] else None,
        }
        for exp, b in sorted(by_expiry.items())
    }
    path = write_snapshot("digifetch_options_chain", params, raw, fetched_at=fetched_at or _now_utc())
    (path.parent / f"{path.stem}.metrics.json").write_text(json.dumps(metrics, indent=2))
    return str(path), metrics


def main() -> None:
    parser = argparse.ArgumentParser(description="Gold enrichment pulls → snapshot store")
    sub = parser.add_subparsers(dest="command", required=True)
    p_skew = sub.add_parser("options-skew")
    p_skew.add_argument("--expiration", type=int, default=None, help="Epoch seconds (default: all expiries)")
    args = parser.parse_args()
    if args.command == "options-skew":
        path, metrics = snapshot_options_skew(expiration=args.expiration)
        print(f"snapshot: {path}")
        print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
```

Shape risk (explicit): `json.loads(raw)["data"]["contracts"]` and leg keys (`expiration`, `side`, `openInterest`, `volume`) MUST match the Task-0 table. If the live envelope nests differently, the KeyError is the signal — fix the access path to the table (one-line), do not reshape anything else. The `.metrics.json` sidecar sits next to the page (not inside the store's page/latest scheme — document that in the report).

- [ ] **Step 5: Run to verify it passes (offline only)**

Run: `.venv/bin/python -m pytest tests/dq/data/test_gold_enrichment_pulls.py -m unit -v`
Expected: PASS. Do NOT run the script live in this task (live pulls happen in Task 4's cadence verification with explicit owner-visible output, or not at all — the tests prove the wiring).

- [ ] **Step 6: Lint + commit**

Ruff check + format-check the script + test file.
Expected: clean.

```bash
git add digiquant/scripts/pull_gold_enrichment.py tests/dq/data/test_gold_enrichment_pulls.py
git commit -m "Add GLD options-skew enrichment pull (#4804)"
```

---

### Task 3: 13F + calendar + news + LBMA probe pulls

**Files:**
- Modify: `digiquant/scripts/pull_gold_enrichment.py` (four new subcommands, same dispatcher+store pattern)
- Modify: `tests/dq/data/test_gold_enrichment_pulls.py` (canned-dispatcher tests per subcommand)

**Interfaces:**
- Consumes: Task 1 store; Task 0 field tables for 13F/news/calendar/econ_series.
- Produces: `snapshot_13f_gld()`, `snapshot_econ_calendar()`, `snapshot_gold_news()`, `probe_lbma_series()` + CLI subcommands `13f-gld`, `econ-calendar`, `gold-news`, `probe-lbma`.

- [ ] **Step 1: Write the failing tests (one per subcommand, canned JSON)**

Extend the Task 2 test file (header imports only — no mid-file imports):

- `test_snapshot_13f_gld`: dispatcher returns canned `digifetch_13f_funds` JSON (`what="tickers"`, `tickers=["GLD"]` shape per Task-0 table, two holder rows). Assert path tool dir is `digifetch_13f_funds`, header `params` equals the call params, `delay_notice` non-empty.
- `test_snapshot_econ_calendar`: canned calendar JSON (two event rows). Assert `tool == "digifetch_econ_calendar"`, params `{}`.
- `test_snapshot_gold_news`: canned news JSON (two stories). Assert `tool == "digifetch_news"`, params contain `ticker == "GLD"`.
- `test_probe_lbma_hit_and_miss`: monkeypatch the dispatcher to return a 2-obs series for id `GOLDPMGBD228NLBM` and an error envelope for `BOGUS-ID-XYZ`; assert `probe_lbma_series()` returns `{"GOLDPMGBD228NLBM": <path>, "BOGUS-ID-XYZ": None}` and only the hit was snapshotted.

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/data/test_gold_enrichment_pulls.py -m unit -v`
Expected: FAIL at import of the four new function names.

- [ ] **Step 3: Implement the four subcommands**

Append to `pull_gold_enrichment.py` (same `_dispatcher()`/`write_snapshot`/`_now_utc` pattern; params shapes MUST match the Task-0 tables — `what` values, `tickers` list form, news `feed`/`limit` bounds):

```python
def snapshot_13f_gld(*, fetched_at: str | None = None) -> str:
    """GLD institutional map via 13F funds tickers-branch (anon).

    Known upstream caveat: the funds ``holders`` branch 400s on every period
    format probed — this pull uses ``what="tickers"`` only and never calls it.
    """
    params = {"what": "tickers", "tickers": ["GLD"]}
    raw = _dispatcher()("digifetch_13f_funds", params)
    return str(write_snapshot("digifetch_13f_funds", params, raw, fetched_at=fetched_at or _now_utc()))


def snapshot_econ_calendar(*, fetched_at: str | None = None) -> str:
    """Econ calendar window (~105 rows, no params)."""
    params: dict = {}
    raw = _dispatcher()("digifetch_econ_calendar", params)
    return str(write_snapshot("digifetch_econ_calendar", params, raw, fetched_at=fetched_at or _now_utc()))


def snapshot_gold_news(limit: int = 50, *, fetched_at: str | None = None) -> str:
    """Gold news tape (ticker feed)."""
    params = {"feed": "ticker", "ticker": "GLD", "limit": limit}
    raw = _dispatcher()("digifetch_news", params)
    return str(write_snapshot("digifetch_news", params, raw, fetched_at=fetched_at or _now_utc()))


LBMA_CANDIDATES = ("GOLDPMGBD228NLBM", "GOLDAMGBD228NLBM")


def probe_lbma_series(*, fetched_at: str | None = None) -> dict[str, str | None]:
    """Probe the upstream econ catalog for LBMA fix series; snapshot hits only.

    Misses (error envelopes) are recorded as None and never snapshotted.
    A hit here is enrichmentonly — promoting it to the native FRED manifest
    is a Plan-4 candidate, not this task.
    """
    out: dict[str, str | None] = {}
    for series_id in LBMA_CANDIDATES:
        params = {"series_id": series_id, "limit": 5, "sort_order": "desc"}
        raw = _dispatcher()("digifetch_econ_series", params)
        try:
            obs = json.loads(raw)["data"]["observations"]
        except (KeyError, TypeError):
            obs = []
        if obs:
            out[series_id] = str(
                write_snapshot("digifetch_econ_series", params, raw, fetched_at=fetched_at or _now_utc())
            )
        else:
            out[series_id] = None
    return out
```

Envelope-shape risk (explicit, same rule as Task 2): `["data"]["observations"]` and the error-envelope shape MUST match the Task-0 tables. The canned tests define the contract; if live envelopes differ, the live failure (not a test edit) is the signal — report it, do not reshape. CLI: register four subcommands (`13f-gld`, `econ-calendar`, `gold-news --limit`, `probe-lbma` printing the hit/miss dict).

- [ ] **Step 4: Run to verify it passes (offline only)**

Run: `.venv/bin/python -m pytest tests/dq/data/test_gold_enrichment_pulls.py -m unit -v`
Expected: PASS (all subcommand tests green; no live calls).

- [ ] **Step 5: Lint + commit**

Ruff check + format-check the script + test file.
Expected: clean.

```bash
git add digiquant/scripts/pull_gold_enrichment.py tests/dq/data/test_gold_enrichment_pulls.py
git commit -m "Add gold 13F/calendar/news/LBMA enrichment pulls (#4804)"
```

---

### Task 4: Refresh script + weekly workflow

**Files:**
- Create: `digiquant/scripts/refresh_gold_enrichment.py`
- Create: `.github/workflows/enrich-gold-refresh.yml`
- Create: `tests/scripts/test_enrich_gold_refresh_workflow.py` (yaml-shape pin, offline)

**Interfaces:**
- Consumes: Task 2–3 pull functions; Task 1 `prune_tool`; existing cron template `.github/workflows/pipeline-market-data-refresh.yml` (read first, mirror schedule/secret style).
- Produces: idempotent refresh entrypoint + scheduled workflow (weekly + manual dispatch).

- [ ] **Step 1: Write the failing workflow pin test**

Create `tests/scripts/test_enrich_gold_refresh_workflow.py`:

```python
"""Pin the gold-enrichment refresh workflow shape (#4804)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit


def _workflow() -> dict:
    path = (
        Path(__file__).resolve().parents[2]
        / ".github"
        / "workflows"
        / "enrich-gold-refresh.yml"
    )
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_workflow_has_weekly_schedule_and_dispatch() -> None:
    wf = _workflow()
    triggers = wf[True]  # PyYAML parses `on:` as boolean True
    assert "workflow_dispatch" in triggers
    schedules = triggers["schedule"]
    assert any("cron" in entry for entry in schedules)


def test_workflow_runs_refresh_script_offline_safe() -> None:
    wf = _workflow()
    steps = [step for job in wf["jobs"].values() for step in job["steps"]]
    run_steps = [s.get("run", "") for s in steps if "run" in s]
    assert any("refresh_gold_enrichment.py" in cmd for cmd in run_steps)
    assert not any("GLOOMBERB_SESSION_COOKIE" in cmd for cmd in run_steps)
```

(`pyyaml` availability: check with `.venv/bin/python -c "import yaml"` first; if missing, use `tomllib`-style stdlib fallback — no, yaml has no stdlib equivalent. If missing, write the pin with a hand-rolled substring check on the raw text instead (assert `"workflow_dispatch" in text`, `"cron:" in text`, `"refresh_gold_enrichment.py" in text`, `"GLOOMBERB_SESSION_COOKIE" not in text`). Decide by the import probe; record the choice in the report.)

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/scripts/test_enrich_gold_refresh_workflow.py -m unit -v`
Expected: FAIL (workflow file does not exist).

- [ ] **Step 3: Implement the refresh script**

Create `digiquant/scripts/refresh_gold_enrichment.py`:

```python
#!/usr/bin/env python3
"""Refresh gold enrichment snapshots (idempotent, anon tools only, #4804).

Pulls options-skew + calendar + news on every run (fast-moving), 13F + LBMA
probe only with --include-slow (slow-moving). Prunes each tool dir to the
keep bound afterwards. Exit 0 with per-pull status lines; a single pull
failing prints a warning and continues (exit 1 only if ALL pulls fail).

Usage:
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/refresh_gold_enrichment.py
    PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/refresh_gold_enrichment.py --include-slow --keep 60
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from pull_gold_enrichment import (  # noqa: E402
    probe_lbma_series,
    snapshot_13f_gld,
    snapshot_econ_calendar,
    snapshot_gold_news,
    snapshot_options_skew,
)

from digiquant.data.enrichment.snapshots import prune_tool  # noqa: E402

TOOLS = (
    "digifetch_options_chain",
    "digifetch_econ_calendar",
    "digifetch_news",
    "digifetch_13f_funds",
    "digifetch_econ_series",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh gold enrichment snapshots")
    parser.add_argument("--include-slow", action="store_true")
    parser.add_argument("--keep", type=int, default=30)
    args = parser.parse_args()

    ok = total = 0

    def attempt(name: str, fn) -> None:
        nonlocal ok, total
        total += 1
        try:
            result = fn()
            ok += 1
            print(f"ok {name}: {result}")
        except Exception as exc:  # noqa: BLE001 — one pull must not kill the refresh
            print(f"FAIL {name}: {type(exc).__name__}: {exc}")

    attempt("options-skew", snapshot_options_skew)
    attempt("econ-calendar", snapshot_econ_calendar)
    attempt("gold-news", snapshot_gold_news)
    if args.include_slow:
        attempt("13f-gld", snapshot_13f_gld)
        attempt("probe-lbma", probe_lbma_series)
    for tool in TOOLS:
        print(f"prune {tool}: removed {prune_tool(tool, keep=args.keep)}")
    print(f"{ok}/{total} pulls ok")
    return 0 if ok else 1


if __name__ == "__main__":
    main()
```

(`from pull_gold_enrichment import ...` works because the script dir is on `sys.path` — same seam `export_sdca_macro.py` uses for `_env`. If the import fails in the test env, the fallback is `importlib` file-location loading like `tests/dq/test_export_sdca_macro.py:11-15` — record either way.)

- [ ] **Step 4: Implement the workflow (mirror the market-data cron)**

Read `.github/workflows/pipeline-market-data-refresh.yml` first; mirror its checkout/python-setup/secret style with these deltas: name `enrich-gold-refresh`; `on: schedule: [cron: "0 9 * * 1"]` (weekly Monday 09:00 UTC) + `workflow_dispatch`; one job running the refresh script with `--include-slow` on schedule and without it on dispatch? Keep it simple and explicit: the `run:` step always passes `--include-slow` (weekly cadence makes slow pulls cheap); NO secrets (anon tools only — assert this in the test); NO Supabase/R2 writes.

- [ ] **Step 5: Run to verify it passes (no live execution)**

Run: `.venv/bin/python -m pytest tests/scripts/test_enrich_gold_refresh_workflow.py -m unit -v`
Expected: PASS. Do NOT execute the workflow or the refresh script live in this task.

- [ ] **Step 6: Lint + commit**

Ruff check + format-check the three files (script, workflow yml is not ruff-scoped — validate with the pin test only).
Expected: clean.

```bash
git add digiquant/scripts/refresh_gold_enrichment.py .github/workflows/enrich-gold-refresh.yml tests/scripts/test_enrich_gold_refresh_workflow.py
git commit -m "Add gold enrichment refresh cadence (#4804)"
```

---

### Task 5: README + ARCH row + full verification

**Files:**
- Create: `digiquant/data/enrichment/README.md` (committed docs for a gitignored dir)
- Modify: `digiquant/ARCHITECTURE.md` (new enrichment-snapshots row near the gloomberb section)
- Verify: unit selection + ruff + `git status`

**Interfaces:**
- Consumes: Tasks 0–4.
- Produces: consumer docs; evidence log.

- [ ] **Step 1: Write the README**

Create `digiquant/data/enrichment/README.md` stating: directory purpose (research staging for gloomberb enrichment snapshots; gitignored); per-tool layout (`snapshots/<tool>/<YYYY-MM-DD>__<params12>.json` + `latest.json` + options `.metrics.json` sidecars); provenance header fields; the enrichment-only rule with the delay notice; pull inventory (options-skew, 13f-gld, econ-calendar, gold-news, probe-lbma) with cadence (fast pulls every run, slow pulls `--include-slow`); how to run pulls manually (the two CLI commands); who consumes snapshots today (nobody yet — Plan 4 analysis; do not invent consumers); LBMA probe verdict from the Task 3 report (hit ids or all-miss — quote it).

- [ ] **Step 2: ARCHITECTURE.md enrichment row**

Grep the gloomberb section (the row naming `data/gloomberb/` + the enrichment-only rule). Add one row for `data/enrichment/` (snapshot store, JSON, gitignored, provenance-stamped) + one row for the two scripts (`pull_gold_enrichment.py`, `refresh_gold_enrichment.py`) + the workflow file, each tagged `(#4804)`. Touch nothing else. If the gloomberb section is absent (drift), skip with a commit-message note.

- [ ] **Step 3: Full verification pass**

```bash
.venv/bin/python -m pytest tests/dq/data/test_enrichment_snapshots.py tests/dq/data/test_gold_enrichment_pulls.py tests/scripts/test_enrich_gold_refresh_workflow.py tests/dq/strategies/sdca/ -m unit -q
ruff check digiquant/src/digiquant/data/enrichment/ digiquant/scripts/pull_gold_enrichment.py digiquant/scripts/refresh_gold_enrichment.py tests/dq/data/test_enrichment_snapshots.py tests/dq/data/test_gold_enrichment_pulls.py tests/scripts/test_enrich_gold_refresh_workflow.py
ruff format --check <same file list>
git status --short
```

Expected: all green (pre-existing drift elsewhere proven via `git stash` comparison if anything fails); `git status` shows only plan commits ahead plus `??` gitignored staging (snapshots must NOT appear committable — check-ignore + extend ignore rules instead of committing data if one does).

- [ ] **Step 4: Commit docs**

```bash
git add digiquant/data/enrichment/README.md digiquant/ARCHITECTURE.md
git commit -m "Document gold enrichment snapshots (#4804)"
```

- [ ] **Step 5: Evidence log**

Final report section: `git log --oneline` (plan commits), snapshot dir listing (`find digiquant/data/enrichment -type f | head -20` — expect only README until a live pull runs), Task-0 boundary verdict + field tables pointer, LBMA verdict, deferred items (Plan 4: snapshot consumers/labeling analysis; possible LBMA native-manifest promotion if probed hit).

---

## Out of scope (later plans)

- Price-family indicator legs from TLT/TIP/UUP/CPER (staged but unwired — Plan 2 declared scope).
- Full walk-forward gate re-run, dd-cap / sensitivity-bar calibration, `settings.json` promotion — Plan 4. Its inputs now include: 8 macro legs + 2 ratio legs (wired), full-depth HY/IG re-stage (deferred), hy/ig 0.86 collinearity decision (deferred), enrichment snapshots as labeling context (this plan).
- Live snapshot backfill (running the refresh for real) — operator action after merge, not this plan. The workflow is merged dormant; first live run happens post-merge via `workflow_dispatch`.
- Any new gloomberb client/model/MCP code, any session-cookie handling, any pipeline consumption of snapshots.

## Self-review

1. Spec coverage: landed-surface boundary → Task 0 (with collision STOP); store → Task 1 (merge-not-overwrite for capped series); skew pull → Task 2 (greeks honesty gate); 13F/calendar/news/LBMA → Task 3 (holders-branch avoidance, hit-only snapshots); cadence → Task 4 (anon-only assertion); docs+verify → Task 5. Every pool item from the gold inventory has an owner except Fed transcripts + COT (unavailable — correctly absent) and congress_trades (broken upstream — correctly absent).
2. Placeholder scan: store module is fully specified code; pull functions are fully specified code with two explicit envelope-shape risks carrying exact failure signals (KeyError → fix the access path to the Task-0 table). The Task-2 Step-1 field gate and Task-0 Step-4 collision STOP are defined branches, not open TODOs. No TBD/TODO/similar-to.
3. Type consistency: `write_snapshot(tool, params, payload_json, *, fetched_at) -> Path` used identically in Tasks 2–4; `(path, metrics)` vs `str` vs `dict[str, str | None]` returns match their tests; `prune_tool(tool, keep=)` matches Task 4; `DIGIQUANT_ENRICHMENT_DIR` seam identical in both test files; dispatcher `(name, dict) -> str` contract from the recon-held `agent_tools.py:381` signature.
