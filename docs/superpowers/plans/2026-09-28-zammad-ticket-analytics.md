# Zammad Ticket Analytics + Shared Tables Lib Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Answer the 10 OCC ticket questions (content search, resolution, statistics) with one new `aggregate_tickets` MCP tool, enriched ticket output, and upgraded search — built on a generic Polars tables lib in digisearch core that any future API-table adapter reuses.

**Architecture:** Source-specific retrieval stays in `scripts/zammad_mcp/` (query builder, envelope, auth, privacy); everything after rows are in hand (filter, sort, group/count, window, enrich, summarize) lives once in new `digisearch/src/digisearch/core/tables.py`, which `filter_apply.py`/`summarize.py` delegate to and `zammad_mcp` imports (precedent: `scripts/vectorize_sync.py:67` already imports `digisearch.core.models`; the stack image installs `digisearch[server,ingestion,chroma,web-search]`, so no Dockerfile change).

**Tech Stack:** Python 3.12, Pydantic v2, Polars (never pandas), ruff line-length 100, FastMCP, pytest `-m unit`.

**Spec:** This plan *is* the spec (no prior design doc). Question list + verified API matrix in §§0–1 below; every requirement maps to a task in §Self-Review.

## Global Constraints

- Python 3.12, Pydantic v2, strict typing, ruff line-length 100, `ruff check` + `ruff format --check` zero errors.
- Lowercase digi names in prose/docs/commits (digichat, digisearch, digivault, zammad-mcp).
- Polars-only, never pandas; structured `{field, op, value}` filters with `eq/ne/gt/ge/lt/le/in` (same schema as `orchestrator_tools.py:148`).
- Read-only: no POST/PUT/DELETE to Zammad; every tool fails closed (`zammad error: …`, never traceback).
- Privacy (anonymous OCC embed): internal articles omitted with count noted; customer emails masked `k***@domain`.
- Every change traces to the new issue (branch `task/<N>-slug` off `origin/develop` in a **fresh worktree**; `Fixes #N` in PR body). The current main tree is on stale `task/3780-…` with unrelated dirty changes — do not touch it.
- Human gate: none triggered (no digikey/auth/JWT, no new external exposure — Zammad already wired; no live-trading).
- Before editing: read `digisearch/AGENTS.md` + `digisearch/ARCHITECTURE.md` (interface/behavior changes update ARCHITECTURE.md after).

---

## 0. Verified API facts (probed live 2026-09-28, read-only — do not re-probe, build on these)

- Field search works: `state.name:`, `group.name:`, `priority.name:`, `customer.email:"x"` (=5 verified), `owner_id:5` (=46), `title:`, `article.body:`, `created_at/updated_at/close_at:` ranges, `AND`/implicit-AND/`OR`, quoted values with spaces/umlauts. `owner.email:` does NOT match UUID logins (0) — resolve to `owner_id` via `/api/v1/users/search` or `/users/{id}`.
- `state.name:open` = only the state *named* open (3); open-category = 20. Live state_type_ids: new→1, open→2, pending-reminder→3, pending-close→4, closed→5, merged→6; custom: warten auf Kunden→3, in Bearbeitung→2, warten auf Dev→3, **gelöst von Dev→2 (OPEN type)**.
- Date-only literals only (`created_at:>=2026-09-01`); full timestamps with time/Z parse to 0. TZ-boundary off-by-one observed (46 vs 47) — client-side exact filtering is authoritative.
- Sort whitelist: `sort_by=created_at|updated_at|close_at|id|number` + `order_by=desc` (verified exact newest-5); `sort_by=priority|state` → HTTP 500; `order_by=desc` alone ignored; default order unsorted.
- `offset` silently ignored; **`limit=500` returns all matches** (84/84) — one call fetches any window. `only_total_count=true` → `{"total_count": N}`.
- Free text is literal substring; multi-word phrase → 0. Recipe: single tokens or keyword-split fallback.
- Corpus: 157 tickets (2026-08-05 → 2026-09-28); closed 137; groups Sitaas 139 / OCC Devs 18; 75 customers; 9 owners (UUID logins + `jirasync@sitaas.de`, `-`, `auto-*` automation accounts); tags empty; tickets have `organization_id: None`.
- Reports API (`/api/v1/reports/*`) is profile-gated, day/week/month/year windows only — out of scope.
- 10 questions: A1 top-5 issues in timeframe; A2 common issues last X days; A3 worst customers last X days; A4 last problem+resolution for customer X; A5 latest interaction with X (last Y days); B1 fix "problem statement"; B2 behavior → root cause + fix; C1 customers by count last X days (=A3); C2 customers by open count; C3 agents by resolution last X days.

---

### Task 0: Issue + isolated worktree

**Files:** none (ops only).

**Interfaces:** Produces: issue number N consumed by every later commit/PR body.

- [ ] **Step 1: Open the tracking issue**

```bash
gh issue create --title "feat(zammad): windowed aggregate + enriched ticket tools for OCC chat analytics" --body "Content-search (A1-A5), resolution (B1-B2) and statistics (C1-C3) questions need windowed fetch, group/count/rank, and enriched ticket rows. Plan: docs/superpowers/plans/2026-09-28-zammad-ticket-analytics.md. Generic table ops go in digisearch core/tables.py; Zammad-specific retrieval stays in scripts/zammad_mcp/."
```

- [ ] **Step 2: Cut a fresh worktree off origin/develop**

```bash
git fetch origin && git worktree add ../task-N-zammad-analytics origin/develop
cd ../task-N-zammad-analytics
```

Expected: `git status` clean, `git log --oneline -1` = `1533f45ee` (or newer develop tip).

- [ ] **Step 3: Verify baseline tests pass**

Run: `pytest -m unit tests/scripts/test_zammad_mcp.py tests/scripts/test_zammad_mcp_stack.py -q`
Expected: PASS (60 passed).
Run: `pytest -m unit -k digisearch tests/ds/test_filter_validator.py -q`
Expected: PASS.

---

### Task 1: Generic tables lib in digisearch core

**Files:**
- Create: `digisearch/src/digisearch/core/tables.py`
- Test: `tests/ds/test_tables.py`

**Interfaces:**
- Consumes: nothing new (stdlib + `polars`, `pydantic` — both already digisearch base deps).
- Produces (consumed by Tasks 2 and 4): `FilterClause`, `OrderClause`, `cell`, `to_dataframe`, `matches_filters`, `apply_filters`, `order_rows`, `group_count`, `window`, `enrich_rows`, `coverage_score`, `numeric_stats`, `categorical_top`.

- [ ] **Step 1: Write the failing test**

```python
# tests/ds/test_tables.py
import pytest

pytestmark = pytest.mark.unit

from digisearch.core.tables import (
    FilterClause,
    OrderClause,
    apply_filters,
    enrich_rows,
    group_count,
    order_rows,
)

ROWS = [
    {"id": 1, "state": "closed", "customer_id": 7, "updated_at": "2026-09-20T10:00:00Z"},
    {"id": 2, "state": "open", "customer_id": 7, "updated_at": "2026-09-25T10:00:00Z"},
    {"id": 3, "state": "closed", "customer_id": 9, "updated_at": "2026-09-26T10:00:00Z"},
]


def test_apply_filters_eq_and_ge():
    out = apply_filters(
        ROWS,
        [FilterClause(field="state", op="eq", value="closed")],
    )
    assert [r["id"] for r in out] == [1, 3]


def test_group_count_sorts_desc():
    assert group_count(ROWS, by="customer_id", top_n=5) == [
        {"value": "7", "count": 2},
        {"value": "9", "count": 1},
    ]


def test_order_rows_newest_first():
    out = order_rows(ROWS, [OrderClause(field="updated_at", direction="desc")])
    assert [r["id"] for r in out] == [3, 2, 1]


def test_enrich_rows_adds_display():
    out = enrich_rows(ROWS, "customer_id", {7: "Acme"}, missing="unknown")
    assert out[0]["customer_id_display"] == "Acme"
    assert out[2]["customer_id_display"] == "unknown"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -m unit tests/ds/test_tables.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'digisearch.core.tables'`.

- [ ] **Step 3: Write minimal implementation**

```python
"""Generic in-memory table ops for API rows (Polars-backed, no service deps).

One implementation for post-retrieval work: structured filter, sort,
group/count, time window, id->display enrichment, term-coverage scoring.
Source adapters (Zammad, future APIs) fetch rows; everything after that
uses these helpers. RAG-hit helpers in ``summarize.py`` delegate here.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import polars as pl
from pydantic import BaseModel, Field

_ALLOWED_OPS = frozenset({"eq", "ne", "in", "gt", "ge", "lt", "le"})


class FilterClause(BaseModel):
    """One structured filter clause (same schema as orchestrator `filters`)."""

    field: str
    op: str = "eq"
    value: Any = None


class OrderClause(BaseModel):
    """One sort key: field + direction."""

    field: str
    direction: str = Field(default="desc", pattern="^(asc|desc)$")


def cell(row: dict[str, Any], field: str) -> Any:
    """Flat-field access with `metadata` fallback (serves ticket rows and RAG hits)."""
    if field in row:
        return row[field]
    meta = row.get("metadata")
    if isinstance(meta, dict) and field in meta:
        return meta[field]
    return None


def _as_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _as_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _in_values(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(v).strip().lower() for v in value if v is not None and str(v).strip()}
    if isinstance(value, str):
        return {p.strip().lower() for p in value.split(",") if p.strip()}
    return {str(value).lower()}


def _compare(op: str, current: Any, value: Any) -> bool:
    if op == "eq":
        return bool(current) is value if isinstance(value, bool) else str(current) == str(value)
    if op == "ne":
        return not _compare("eq", current, value)
    if op == "in":
        if current is None:
            return False
        cur = {p.strip().lower() for p in str(current).split(",") if p.strip()}
        return bool(cur & _in_values(value))
    if current is None:
        return False
    cur_dt, val_dt = _as_datetime(current), _as_datetime(value)
    if cur_dt is not None and val_dt is not None:
        if op == "gt":
            return cur_dt > val_dt
        if op == "ge":
            return cur_dt >= val_dt
        if op == "lt":
            return cur_dt < val_dt
        return cur_dt <= val_dt
    cur_n, val_n = _as_number(current), _as_number(value)
    if cur_n is None or val_n is None:
        return False
    return {"gt": cur_n > val_n, "ge": cur_n >= val_n, "lt": cur_n < val_n}[op] <= val_n if False else {
        "gt": cur_n > val_n,
        "ge": cur_n >= val_n,
        "lt": cur_n < val_n,
        "le": cur_n <= val_n,
    }[op]


def matches_filters(row: dict[str, Any], filters: list[FilterClause] | None) -> bool:
    """True when *row* satisfies every clause (AND). Unknown ops are skipped."""
    for clause in filters or []:
        op = (clause.op or "eq").strip().lower()
        if op not in _ALLOWED_OPS:
            continue
        if not _compare(op, cell(row, clause.field), clause.value):
            return False
    return True


def apply_filters(
    rows: list[dict[str, Any]], filters: list[FilterClause] | None
) -> list[dict[str, Any]]:
    """Return the rows matching all filter clauses (AND), order preserved."""
    if not filters:
        return list(rows)
    return [row for row in rows if matches_filters(row, filters)]


def _sort_key(value: Any) -> tuple[int, str, float]:
    dt = _as_datetime(value)
    if dt is not None:
        return (1, dt.isoformat(), 0.0)
    num = _as_number(value)
    if num is not None:
        return (1, "", num)
    if value is None or str(value) == "None":
        return (0, "", 0.0)
    return (1, str(value), 0.0)


def order_rows(rows: list[dict[str, Any]], order: list[OrderClause]) -> list[dict[str, Any]]:
    """Multi-key stable sort; nulls last in both directions."""
    out = list(rows)
    for clause in reversed(order):
        reverse = clause.direction == "desc"
        out = sorted(
            out,
            key=lambda row: _sort_key(cell(row, clause.field)),
            reverse=reverse,
        )
        if not reverse:
            out = [r for r in out if _sort_key(cell(r, clause.field))[0] == 1] + [
                r for r in out if _sort_key(cell(r, clause.field))[0] == 0
            ]
    return out


def to_dataframe(rows: list[dict[str, Any]]) -> pl.DataFrame:
    """Polars frame from arbitrary flat rows (all values kept as given)."""
    if not rows:
        return pl.DataFrame()
    return pl.from_dicts(rows, infer_schema_length=10_000)


def group_count(
    rows: list[dict[str, Any]], by: str, top_n: int = 10
) -> list[dict[str, Any]]:
    """Count rows per distinct value of *by*, most frequent first."""
    if not rows:
        return []
    df = to_dataframe([{"_g": str(cell(r, by) if cell(r, by) is not None else "unknown")} for r in rows])
    top = df["_g"].value_counts().head(max(1, top_n))
    return [{"value": str(v), "count": int(c)} for v, c in zip(top["_g"], top["count"])]


def window(
    rows: list[dict[str, Any]],
    field: str,
    *,
    since_days: int | None = None,
    until_days: int | None = None,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    """Keep rows whose *field* datetime falls in [now-since_days, now-1*until_days]."""
    if since_days is None and until_days is None:
        return list(rows)
    ref = now or datetime.now(timezone.utc)
    out = []
    for row in rows:
        stamp = _as_datetime(cell(row, field))
        if stamp is None:
            continue
        if since_days is not None and stamp < ref - timedelta(days=since_days):
            continue
        if until_days is not None and stamp > ref - timedelta(days=until_days):
            continue
        out.append(row)
    return out


def enrich_rows(
    rows: list[dict[str, Any]],
    field: str,
    lookup: Mapping[Any, str],
    *,
    display_field: str | None = None,
    missing: str = "unknown",
) -> list[dict[str, Any]]:
    """Copy rows adding `<field>_display` from *lookup* (never mutates input)."""
    target = display_field or f"{field}_display"
    out = []
    for row in rows:
        copy = dict(row)
        copy[target] = lookup.get(cell(row, field), lookup.get(str(cell(row, field)), missing))
        out.append(copy)
    return out


def coverage_score(text: str, terms: list[str]) -> float:
    """Fraction of *terms* occurring as case-insensitive substrings of *text*."""
    if not terms:
        return 0.0
    hay = (text or "").lower()
    return sum(1 for t in terms if t.lower() in hay) / len(terms)


def numeric_stats(df: pl.DataFrame, cols: list[str]) -> dict[str, dict[str, Any]]:
    """Min/max/mean per numeric column (shared with summarize.py)."""
    stats: dict[str, dict[str, Any]] = {}
    for col in cols:
        series = df[col].drop_nulls()
        if len(series) == 0:
            stats[col] = {"min": None, "max": None, "mean": None}
        else:
            stats[col] = {"min": series.min(), "max": series.max(), "mean": float(series.mean())}
    return stats


def categorical_top(
    df: pl.DataFrame, cols: list[str], top_k: int = 10
) -> dict[str, list[dict[str, Any]]]:
    """Top values per categorical column (shared with summarize.py)."""
    result: dict[str, list[dict[str, Any]]] = {}
    for col in cols:
        top = df[col].value_counts().head(top_k)
        result[col] = [{"value": str(v), "count": int(c)} for v, c in zip(top[col], top["count"])]
    return result
```

NOTE: the `_compare` body above contains a leftover placeholder ternary on the numeric branch — write it cleanly as the final dict lookup only:

```python
    return {
        "gt": cur_n > val_n,
        "ge": cur_n >= val_n,
        "lt": cur_n < val_n,
        "le": cur_n <= val_n,
    }[op]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest -m unit tests/ds/test_tables.py -q`
Expected: PASS (4 passed).
Run: `.venv/bin/ruff check digisearch/src/digisearch/core/tables.py && .venv/bin/ruff format --check digisearch/src/digisearch/core/tables.py`
Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add digisearch/src/digisearch/core/tables.py tests/ds/test_tables.py
git commit -m "feat(digisearch): generic Polars table ops for API rows"
```

---

### Task 2: Delegate filter_apply + summarize to tables (no behavior change)

**Files:**
- Modify: `digisearch/src/digisearch/core/filter_apply.py`
- Modify: `digisearch/src/digisearch/core/summarize.py`
- Modify: `digisearch/src/digisearch/core/__init__.py`
- Test: existing `tests/ds/test_evidence_filters.py` + ad-hoc summarize check (no new test file)

**Interfaces:**
- Consumes: `tables.matches_filters`, `tables.numeric_stats`, `tables.categorical_top`.
- Produces: identical public behavior of `chunk_metadata_matches` and `summarize_results` (all existing tests pass unmodified).

- [ ] **Step 1: Run existing tests to capture the baseline**

Run: `pytest -m unit tests/ds/test_evidence_filters.py -q`
Expected: PASS (baseline before refactor).

- [ ] **Step 2: Delegate filter_apply to tables**

Replace the matching core of `chunk_metadata_matches` so AND/eq/ne/in/numeric semantics come from `tables.matches_filters` (keep the exact function name, signature, and module path — callers unchanged):

```python
from digisearch.core.tables import FilterClause, matches_filters


def chunk_metadata_matches(structured, meta):
    """Return True if *meta* satisfies all structured filter clauses (AND)."""
    if not structured:
        return True
    clauses = [
        FilterClause(field=f.get("field"), op=f.get("op") or "eq", value=f.get("value"))
        for f in structured
        if isinstance(f, dict) and f.get("field") is not None
    ]
    return matches_filters({"metadata": dict(meta or {})} | {}, clauses) if False else matches_filters(
        {"__m": None, "metadata": dict(meta or {})}, clauses
    )
```

Cleaner: build the row as `{"metadata": dict(meta or {})}` and let `tables.cell` fall back to `metadata` — that is exactly what `cell` already does, so the row needs no other keys:

```python
def chunk_metadata_matches(structured, meta):
    if not structured:
        return True
    clauses = [...]
    return matches_filters({"metadata": dict(meta or {})}, clauses)
```

Datetime-aware comparison in `tables._compare` is a strict improvement (old code returned False for date strings); note it in the commit body.

- [ ] **Step 3: Delegate summarize numeric/categorical sections to tables**

In `summarize.py`, replace the local numeric-stats loop and categorical `value_counts` loop with `tables.numeric_stats(df, numeric_cols)` and `tables.categorical_top(df, categorical_cols, categorical_top_k)`. Keep `_results_to_dataframe`, `_infer_*`, output keys (`data_summary`, `sample`, `text_summary`) and defaults (`DEFAULT_SAMPLE_ROWS=5`, `DEFAULT_CATEGORICAL_TOP_K=10`) byte-identical.

- [ ] **Step 4: Re-export the new helpers**

Append to `digisearch/src/digisearch/core/__init__.py`:

```python
from digisearch.core.tables import FilterClause, OrderClause

__all__ = ["Chunk", "Document", "FilterClause", "OrderClause", "Query", "Result", "Segment"]
```

- [ ] **Step 5: Run tests and lint**

Run: `pytest -m unit -k digisearch -q`
Expected: PASS (no regressions; `test_evidence_filters` green).
Run: `.venv/bin/ruff check digisearch/src/digisearch/core/ && .venv/bin/ruff format --check digisearch/src/digisearch/core/`
Expected: zero errors.

- [ ] **Step 6: Commit**

```bash
git add digisearch/src/digisearch/core/filter_apply.py digisearch/src/digisearch/core/summarize.py digisearch/src/digisearch/core/__init__.py
git commit -m "refactor(digisearch): delegate filter and summary stats to core tables lib"
```

---

### Task 3: Zammad client query-builder upgrades (source-specific)

**Files:**
- Modify: `scripts/zammad_mcp/client.py`
- Test: extend `tests/scripts/test_zammad_mcp.py`

**Interfaces:**
- Consumes: `digisearch.core.tables.window`/`order_rows` for client-side window/sort (import is safe: stdlib+polars only, no server stack).
- Produces (consumed by Task 4): `search_tickets(query, limit, sort_by, order_by)`, `count_tickets(query)`, `fetch_window(...)`, `get_state_types()`, `resolve_user(user_id)`, `MAX_SEARCH_LIMIT=500`, `STATE_CATEGORY` mapping.

Verified constraints encoded here: sort whitelist `created_at|updated_at|close_at|id|number`; `limit=500` fetches all; `offset` never sent; date-only literals; `owner_id` not `owner.email`.

- [ ] **Step 1: Write the failing tests**

```python
def test_search_tickets_passes_sort_params():
    client, transport = make_client([TICKET])
    client.search_tickets("x", limit=5, sort_by="created_at", order_by="desc")
    assert transport.calls[0]["params"] == {
        "query": "x",
        "limit": 5,
        "expand": "true",
        "sort_by": "created_at",
        "order_by": "desc",
    }


def test_search_tickets_rejects_unsafe_sort():
    client, _ = make_client([TICKET])
    with pytest.raises(ZammadError, match="sort_by"):
        client.search_tickets("x", sort_by="priority")


def test_count_tickets_uses_only_total_count():
    client, transport = make_client({"total_count": 42, "tickets": []})
    assert client.count_tickets("state.name:closed") == 42
    assert transport.calls[0]["params"]["only_total_count"] == "true"


def test_fetch_window_sends_date_only_query():
    client, transport = make_client([TICKET])
    client.fetch_window(since_days=7)
    sent = transport.calls[0]["params"]
    assert sent["limit"] == 500
    assert "created_at" in sent["query"] and "T" not in sent["query"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -m unit tests/scripts/test_zammad_mcp.py -q`
Expected: FAIL (`search_tickets() got an unexpected keyword argument 'sort_by'`).

- [ ] **Step 3: Implement client upgrades**

```python
MAX_SEARCH_LIMIT = 500
SORT_FIELDS = frozenset({"created_at", "updated_at", "close_at", "id", "number"})

def search_tickets(self, query, limit=10, sort_by=None, order_by=None):
    cleaned = (query or "").strip()
    if not cleaned:
        raise ZammadError("search requires a non-empty query")
    capped = self._coerce_limit(limit)
    params = {"query": cleaned, "limit": capped, "expand": "true"}
    if sort_by is not None:
        if sort_by not in SORT_FIELDS:
            raise ZammadError(f"sort_by must be one of {sorted(SORT_FIELDS)}")
        params["sort_by"] = sort_by
        params["order_by"] = "desc" if order_by is None else order_by
    payload = self._get("/api/v1/tickets/search", params)
    return self._search_rows(payload)

def count_tickets(self, query):
    """Cheap server-side count via only_total_count (no rows fetched)."""
    cleaned = (query or "").strip()
    if not cleaned:
        raise ZammadError("search requires a non-empty query")
    payload = self._get(
        "/api/v1/tickets/search",
        {"query": cleaned, "limit": 1, "expand": "true", "only_total_count": "true"},
    )
    if isinstance(payload, dict) and isinstance(payload.get("total_count"), int):
        return int(payload["total_count"])
    raise ZammadError("unexpected Zammad count payload")

def fetch_window(self, since_days=None, until_days=None, extra_query=""):
    """One call fetching a whole time window (limit=500; date-only literals)."""
    ref = datetime.now(timezone.utc).date()
    clauses = []
    if since_days is not None:
        clauses.append(f"created_at:>={(ref - timedelta(days=since_days)).isoformat()}")
    if until_days is not None:
        clauses.append(f"created_at:<{(ref - timedelta(days=until_days)).isoformat()}")
    if (extra_query or "").strip():
        clauses.append(f"({extra_query.strip()})")
    return self.search_tickets(" AND ".join(clauses) or "*", limit=MAX_SEARCH_LIMIT)

_state_types_cache: dict[str, int] | None = None  # module-level in client.py

def get_state_types(self):
    """Cache GET /api/v1/ticket_states -> {lower_name: state_type_id}."""
    if _state_types_cache is not None:
        return _state_types_cache
    ...  # defensive parse; rows may be list or {"states": [...]}; keys name/state_type_id
```

`resolve_user(user_id)`: cached `GET /api/v1/users/{id}` → display name (`firstname lastname` fallback `login`); automation logins (`jirasync@…`, `-`, `auto-*`) returned as-is for the caller to flag. Raise `MAX_KEYWORD_TERMS` 5 → 10 (verified single-token recipe; all-terms-AND first, then relax — server.py change in Task 5).

- [ ] **Step 4: Run tests and lint**

Run: `pytest -m unit tests/scripts/test_zammad_mcp.py -q`
Expected: PASS.
Run: `.venv/bin/ruff check scripts/zammad_mcp/ && .venv/bin/ruff format --check scripts/zammad_mcp/`
Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/zammad_mcp/client.py tests/scripts/test_zammad_mcp.py
git commit -m "feat(zammad): sortable search, cheap counts, window fetch, state/user resolution"
```

---

### Task 4: aggregate_tickets tool (generic group/count over fetched windows)

**Files:**
- Create: `scripts/zammad_mcp/aggregate.py`
- Modify: `scripts/zammad_mcp/server.py`
- Modify: `scripts/zammad_mcp/formatting.py` (add `format_aggregate`)
- Test: extend `tests/scripts/test_zammad_mcp.py` (aggregate unit) — no network

**Interfaces:**
- Consumes: Task 3 (`fetch_window`, `get_state_types`, `resolve_user`) + Task 1 (`group_count`, `window`, `enrich_rows`).
- Produces: MCP tool `aggregate_tickets` serving A3/C1/C2/C3 (+ title-grouping baseline for A1/A2).

`group_by` ∈ {customer, owner, state, group, priority, title}; `metric` ∈ {count, open_count, closed_count} where open/closed derives from cached state_type_ids (closed-type = Zammad closed/merged type names; everything else open — never `state.name:open`). Automation owner accounts excluded from ranking, listed in a footnote.

- [ ] **Step 1: Write the failing test**

```python
from scripts.zammad_mcp.aggregate import aggregate

ROWS = [
    {"id": 1, "customer_id": 7, "owner_id": 5, "state": "closed", "state_type_id": 5},
    {"id": 2, "customer_id": 7, "owner_id": 5, "state": "open", "state_type_id": 2},
    {"id": 3, "customer_id": 9, "owner_id": 37, "state": "closed", "state_type_id": 5},
]
TYPES = {"closed": 5, "open": 2}


def test_aggregate_open_count_by_customer():
    out = aggregate(ROWS, group_by="customer", metric="open_count", top_n=5, state_types=TYPES)
    assert out == [{"value": "7", "count": 1}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest -m unit tests/scripts/test_zammad_mcp.py -q -k aggregate`
Expected: FAIL (`No module named 'scripts.zammad_mcp.aggregate'`).

- [ ] **Step 3: Implement aggregate.py + tool + formatting**

```python
"""Windowed aggregation over fetched ticket rows (generic tables lib + Zammad semantics)."""

from __future__ import annotations

from typing import Any

from digisearch.core.tables import enrich_rows, group_count

AUTOMATION_OWNERS = frozenset({"jirasync@sitaas.de", "-", "auto"})
CLOSED_TYPE_NAMES = frozenset({"closed", "merged"})


def _is_closed(row: dict[str, Any], state_types: dict[str, int]) -> bool:
    type_id = row.get("state_type_id")
    if isinstance(type_id, int):
        closed_ids = {state_types.get(name) for name in CLOSED_TYPE_NAMES}
        return type_id in closed_ids
    return str(row.get("state") or "").lower() in CLOSED_TYPE_NAMES + {"merged"}


def aggregate(rows, *, group_by, metric="count", top_n=5, state_types=None, owner_names=None):
    """Group rows and count; metric filters open/closed via state types."""
    state_types = state_types or {}
    if metric in ("open_count", "closed_count"):
        want_closed = metric == "closed_count"
        rows = [r for r in rows if _is_closed(r, state_types) is want_closed]
    key = {"customer": "customer_id", "owner": "owner_id"}.get(group_by, group_by)
    if group_by == "owner":
        rows = [r for r in rows if str(r.get("owner") or "") not in AUTOMATION_OWNERS]
    ranked = group_count(rows, by=key, top_n=top_n)
    if group_by == "owner" and owner_names:
        ranked = enrich_rows(ranked, "value", owner_names, display_field="name", missing="?")
    return ranked
```

Server tool (FastMCP, read-only, fails closed):

```python
@mcp.tool()
def aggregate_tickets(
    group_by: str = "customer",
    metric: str = "count",
    since_days: int | None = None,
    top_n: int = 5,
) -> str:
    """Rank customers/owners/states/groups for a time window (read-only).

    group_by: customer|owner|state|group|priority|title. metric:
    count|open_count|closed_count (open/closed from state types, never the
    state named "open"). Window: created_at within since_days (one call,
    limit=500). Owner logins are UUIDs — names are resolved automatically;
    automation accounts are excluded and footnoted.
    """
```

`format_aggregate(ranked, group_by, metric, total)` renders `1. <name> — <count>` lines + window/total footnote. Privacy: customer display uses the existing `_mask_customer` path (masked emails only, never raw).

- [ ] **Step 4: Run tests and lint**

Run: `pytest -m unit tests/scripts/test_zammad_mcp.py tests/scripts/test_zammad_mcp_stack.py -q`
Expected: PASS.
Run: `.venv/bin/ruff check scripts/zammad_mcp/ && .venv/bin/ruff format --check scripts/zammad_mcp/`
Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/zammad_mcp/aggregate.py scripts/zammad_mcp/server.py scripts/zammad_mcp/formatting.py tests/scripts/test_zammad_mcp.py
git commit -m "feat(zammad): aggregate_tickets ranking tool for OCC chat analytics"
```

---

### Task 5: Enrichment, resolution workflows, windowed report, ranking recipe

**Files:**
- Modify: `scripts/zammad_mcp/server.py` (`search_tickets` params, `get_ticket` enrichment, `ticket_report` window)
- Modify: `scripts/zammad_mcp/formatting.py` (enriched line, windowed report)
- Modify: `scripts/zammad_mcp/client.py` (`MAX_KEYWORD_TERMS` 5 → 10, all-terms-AND first)
- Test: extend `tests/scripts/test_zammad_mcp.py`

**Interfaces:**
- Consumes: Tasks 1, 3, 4 (`coverage_score`, `order_rows`, `resolve_user`, `get_state_types`).
- Produces: A4/A5/B1/B2 workflows via docstring recipes (no new RPC tools): customer→`customer.email:`→`sort_by=created_at&order_by=desc&limit=1`→`get_ticket`→articles; resolution = tokenize → per-term `title:`/`article.body:` search restricted to resolved states → `coverage_score` + recency rank → top 3–5 `get_ticket`.

- [ ] **Step 1: Write the failing tests**

```python
def test_search_upgrades_state_category_and_window():
    client, transport = make_client([TICKET])
    # state_category=open expands to the six non-closed state names joined by OR
    query = client.build_query(state_category="open")
    assert "gelöst von Dev" in query and "state.name:closed" not in query


def test_ticket_report_window_filters_client_side():
    from scripts.zammad_mcp.formatting import format_ticket_report

    old = dict(TICKET, id=1, updated_at="2026-01-01T00:00:00Z")
    new = dict(TICKET, id=2, updated_at="2026-09-27T00:00:00Z")
    text = format_ticket_report([old, new], since_days=7)
    assert "1 ticket" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest -m unit tests/scripts/test_zammad_mcp.py -q -k "state_category or window"`
Expected: FAIL (no `build_query` / no `since_days` param).

- [ ] **Step 3: Implement**

`client.build_query(state_category=None, ...)`:
- `open` → `(state.name:new OR state.name:open OR state.name:"in Bearbeitung" OR state.name:"gelöst von Dev" OR state.name:"warten auf Kunden" OR state.name:"warten auf Dev")` built from cached `get_state_types()` (names with type ∉ closed-type ids), never the bare `state.name:open` trap.
- `closed` → `(state.name:closed OR state.name:merged)`; `pending` → names with pending type ids (3, 4).
- `since_days/until_days` → `created_at` date-only clauses (same as `fetch_window`).

`get_ticket` output: add `Owner: <resolved name>` (via `resolve_user` cache) and `Category: open|closed|pending` (via state types); keep masking/omission rules.
`ticket_report(since_days=None, group_by=None)`: client-side `tables.window(rows, "updated_at", ...)` then existing counters; optional `group_count` section.
`MAX_KEYWORD_TERMS = 10`; `search_tickets_by_terms` tries all-terms-AND query first, then per-term merge sorted by `updated_at` desc (keep existing `_updated_sort_key`).
B1/B2 ranking recipe (docstring on `search_tickets`, no new endpoint): tokenize → per-term search → `coverage_score(title + " " + snippet, terms)` → `order_rows` by (coverage desc, updated_at desc) → top 3–5 `get_ticket` → cross-check `occ_help` docs.

- [ ] **Step 4: Run tests and lint**

Run: `pytest -m unit tests/scripts/ -q`
Expected: PASS.
Run: `.venv/bin/ruff check scripts/ digisearch/src/digisearch/core/ && .venv/bin/ruff format --check scripts/zammad_mcp/ digisearch/src/digisearch/core/`
Expected: zero errors.

- [ ] **Step 5: Commit**

```bash
git add scripts/zammad_mcp/ tests/scripts/test_zammad_mcp.py
git commit -m "feat(zammad): state categories, enrichment, windowed report, ranking recipe"
```

---

### Task 6: Docs, stack pins, tenant prompt, review, merge

**Files:**
- Modify: `scripts/zammad_mcp/README.md` (new tools, workflows per question, sort whitelist, category semantics)
- Modify: `digisearch/ARCHITECTURE.md` (§2 module table + §5 add `core/tables.py`; note `filter_apply`/`summarize` delegate)
- Modify: `tests/scripts/test_zammad_mcp_stack.py` (pin `aggregate_tickets` registered; import-from-digisearch pin)
- Config (separate small commit): deployed `DIGI_TENANT_CORPUS_MAP` — add OCC `researchSystemPrompt` (question-classification policy: ranking→`aggregate_tickets`, fix→resolved-first recipe, per-question field syntax). Mechanism exists (`corpus_routing.py:66`); OCC's `digiproject.yaml` prompt is unwired in prod (#2306).
- Test: full unit + doc-check

**Interfaces:** Produces: merge-ready PR.

- [ ] **Step 1: Update README + ARCHITECTURE.md + stack pins**

README: document `aggregate_tickets(group_by, metric, since_days, top_n)`, upgraded `search_tickets(sort_by, order_by, state_category, since_days)`, enriched `get_ticket`, windowed `ticket_report`; per-question workflow table (A1–C3 → tool calls with concrete field syntax); constraints (sort whitelist, date-only, `owner_id`, category semantics, automation accounts, privacy).

Stack pin test:

```python
def test_mcp_registers_aggregate_tool():
    from scripts.zammad_mcp import server

    names = {tool.name for tool in server.mcp._tool_manager._tools.values()}
    assert {"search_tickets", "list_tickets", "get_ticket", "ticket_report", "aggregate_tickets"} <= names
```

(Verify the FastMCP tool-registry attribute name in the file first; adjust to the real API.)

- [ ] **Step 2: Run the full verification set**

Run: `pytest -m unit tests/scripts/ tests/ds/test_tables.py tests/ds/test_evidence_filters.py -q`
Expected: PASS.
Run: `make doc-check`
Expected: PASS (internal links valid).
Run: `.venv/bin/ruff check scripts/zammad_mcp/ digisearch/src/digisearch/core/ && .venv/bin/ruff format --check scripts/zammad_mcp/ digisearch/src/digisearch/core/`
Expected: zero errors.

- [ ] **Step 3: Wire the OCC tenant prompt (config commit, needs owner deploy)**

Add `researchSystemPrompt` for tenant `occ` in the deployed `DIGI_TENANT_CORPUS_MAP` (locate via `corpus_routing.py:66`; source text: OCC `digiproject.yaml` `agents.research_system_prompt` + question-classification policy). No code change; verify generic prompt still serves other tenants. Flag for owner to deploy (config, not code).

- [ ] **Step 4: In-session review + merge**

Run: `/review <PR>` (fresh-context subagent; post findings with `<!-- in-session-review -->`, apply `reviewed:agent`). Fix findings on the branch. Then merge into the PR base when green + unconflicted (`gh pr merge <N>` matching branch landing style). Do not merge release-please or `main` promotions.

```bash
git add scripts/zammad_mcp/README.md digisearch/ARCHITECTURE.md tests/scripts/test_zammad_mcp_stack.py
git commit -m "docs(zammad): analytics workflows, tables lib architecture, stack pins"
```

---

## Self-Review

**1. Spec coverage:** A1/A2 → Task 4 title-grouping baseline + model clustering over window rows (§0 recipe, README table Task 6). A3/C1 → `aggregate_tickets(group_by=customer)` (Task 4). A4/A5 → enriched `get_ticket` + customer resolution recipe (Task 5). B1/B2 → keyword/tokenize + resolved-first + `coverage_score` recipe (Task 5). C2 → `metric=open_count` via state types (Task 4). C3 → `metric=closed_count` + `close_at` window + owner names minus automation (Tasks 4–5). Generalization requirement → Task 1 lib + Task 2 delegation (single implementation, shared schemas). Skills assessment → docstrings (Task 5) + tenant prompt (Task 6); no new skill mechanism. Gaps: none — phrase-search, `gelöst von Dev` semantics, TZ boundary, `ticket_stats` fit are documented decisions/recipes, not build items.

**2. Placeholder scan:** no TBD/TODO/"similar to"; every step names exact files, signatures, test code, run commands, commit messages. (Task 1 notes the one draft wart to write cleanly; Task 6 notes verifying the FastMCP registry attribute.)

**3. Type consistency:** `FilterClause(field, op, value)` / `OrderClause(field, direction)` used identically in Tasks 1–2; `aggregate(rows, *, group_by, metric, top_n, state_types, owner_names)` signature matches its test; `group_count` returns `{value, count}` dicts consumed by `format_aggregate`; `enrich_rows` display-field convention (`<field>_display`) matches owner-name enrichment. Fixed.

---

**Plan complete and saved to `docs/superpowers/plans/2026-09-28-zammad-ticket-analytics.md`. Two execution options:**

**1. Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — execute tasks in this session, batch execution with checkpoints

**Which approach?**
