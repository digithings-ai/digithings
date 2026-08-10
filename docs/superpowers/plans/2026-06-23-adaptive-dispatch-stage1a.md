# Adaptive Dispatch Stage 1a — Reason-Carrying Roster Core — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every H5 analyst dispatch carry a forward, non-empty reason (linked thesis + rationale), fix the held↔thesis link-loss bug, and stop manufacturing a post-hoc thesis for held names — without changing the held-always invariant, roster return types, or adding an LLM call.

**Architecture:** Additive `rationale` field on `FocusRosterEntry`; H3 mapping rationale is threaded through `extract_thesis_mappings` → `compute_focus_roster`; a held ticker that is also thesis-mapped inherits its `linked_market_thesis_id` + rationale; `run_asset_analyst_llm` resolves the linked thesis into the analyst's inputs; the reversed-arrow post-hoc thesis is gated to genuinely-unlinked exploratory picks only.

**Tech Stack:** Python 3.12, Pydantic v2, pytest (markers in `pytest.ini`), Polars (n/a here), LangGraph (graph wiring unchanged). Skills are generated from `agents/sources/` via `make agents-init` (never hand-edit `.claude/skills/`).

## Global Constraints

- Pydantic v2; strict typing; ruff line length 100; ruff-clean.
- New roster fields must be **additive with defaults** (no breaking existing construction sites/tests).
- Do **not** change the held-always invariant (`test_h4_focus_roster.py::test_held_always_in_roster`, `test_held_invariant.py`) — held names still always dispatch in Stage 1a; the staleness/delta gate is deferred to Stage 1b.
- Do **not** change `compute_focus_roster`'s return type (`list[FocusRosterEntry]`) — the excluded ledger is Stage 1b.
- Run tests with: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest <path> -v` (pytest.ini sets `pythonpath`; no `PYTHONPATH` needed). Unit tests use `@pytest.mark.unit` and `monkeypatch.setenv` (never `os.environ` directly).
- Branch from `module/digiquant` as `task/1017-...`; each task ends in a commit.

---

## File Structure

- `digiquant/src/digiquant/olympus/atlas/state.py` — `FocusRosterEntry` model (add `rationale`).
- `digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py` — `extract_thesis_mappings` (carry rationale), `compute_focus_roster` (unpack triples, fix link-loss, populate rationale).
- `digiquant/src/digiquant/olympus/hermes/phases/portfolio_common.py` — `run_asset_analyst_llm` (resolve linked thesis + rationale into `phase_inputs`).
- `digiquant/src/digiquant/olympus/hermes/phases/h5_asset_analyst.py` — `_h5_node_factory` (gate the reversed-arrow post-hoc thesis).
- `agents/sources/**/asset-analyst*` — asset-analyst skill prompt (add dispatch-reason framing; regenerate via `make agents-init`).
- Tests: `tests/dq/hermes/test_h4_focus_roster.py`, `tests/dq/hermes/test_h5_dispatch_reason.py` (new), `tests/dg/test_olympus_models.py`.

---

### Task 1: Add `rationale` to `FocusRosterEntry`

**Files:**
- Modify: `digiquant/src/digiquant/olympus/atlas/state.py:409-414`
- Test: `tests/dq/hermes/test_h4_focus_roster.py`

**Interfaces:**
- Produces: `FocusRosterEntry(ticker: str, roster_reason: Literal[...], linked_market_thesis_id: str | None = None, rationale: str = "")`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/hermes/test_h4_focus_roster.py — add near the other unit tests
from digiquant.olympus.atlas.state import FocusRosterEntry

@pytest.mark.unit
def test_focus_roster_entry_has_rationale_default_empty() -> None:
    e = FocusRosterEntry(ticker="SPY", roster_reason="held")
    assert e.rationale == ""
    e2 = FocusRosterEntry(ticker="XLE", roster_reason="thesis_mapped",
                          linked_market_thesis_id="T1", rationale="energy thesis")
    assert e2.rationale == "energy thesis"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h4_focus_roster.py::test_focus_roster_entry_has_rationale_default_empty -v`
Expected: FAIL — `TypeError`/`ValidationError`: unexpected keyword `rationale`.

- [ ] **Step 3: Add the field**

```python
# digiquant/src/digiquant/olympus/atlas/state.py
class FocusRosterEntry(BaseModel):
    """One ticker on the Hermes H4 focus roster."""

    ticker: str
    roster_reason: Literal["thesis_mapped", "technical", "held", "momentum", "other"]
    linked_market_thesis_id: str | None = None
    rationale: str = ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h4_focus_roster.py -v`
Expected: PASS (all existing tests still green — field is additive).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/atlas/state.py tests/dq/hermes/test_h4_focus_roster.py
git commit -m "feat(hermes): add rationale field to FocusRosterEntry (#1017)"
```

---

### Task 2: Thread H3 rationale through `extract_thesis_mappings`

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py:28-48` (`extract_thesis_mappings`), and its two consumers inside `compute_focus_roster` (`:78` unpack, `:115` set-comp).
- Test: `tests/dq/hermes/test_h4_focus_roster.py`

**Interfaces:**
- Consumes: an H3 `thesis_vehicle_map` dict whose `mappings[]` items have `thesis_id`, `candidate_tickers[]`, `rationale` (per `ThesisVehicleMapping`).
- Produces: `extract_thesis_mappings(...) -> list[tuple[str, str, str]]` of `(thesis_id, ticker, rationale)`.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.unit
def test_extract_thesis_mappings_carries_rationale() -> None:
    from digiquant.olympus.hermes.phases.h4_opportunity_screener import extract_thesis_mappings
    vmap = {"body": {"mappings": [
        {"thesis_id": "T1", "candidate_tickers": ["XLE", "USO"], "rationale": "oil supply squeeze"},
    ]}}
    out = extract_thesis_mappings(vmap)
    assert ("T1", "XLE", "oil supply squeeze") in out
    assert ("T1", "USO", "oil supply squeeze") in out
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h4_focus_roster.py::test_extract_thesis_mappings_carries_rationale -v`
Expected: FAIL — tuples are `(thesis_id, ticker)`, no rationale element.

- [ ] **Step 3: Return triples + update the two unpack sites**

```python
# h4_opportunity_screener.py — extract_thesis_mappings
def extract_thesis_mappings(vehicle_map: dict[str, Any] | None) -> list[tuple[str, str, str]]:
    """Return ``(thesis_id, ticker, rationale)`` triples from an H3 ``thesis_vehicle_map``."""
    if not vehicle_map:
        return []
    body = vehicle_map.get("body") if isinstance(vehicle_map.get("body"), dict) else vehicle_map
    mappings = body.get("mappings") if isinstance(body, dict) else None
    if not isinstance(mappings, list):
        return []
    triples: list[tuple[str, str, str]] = []
    for mapping in mappings:
        if not isinstance(mapping, dict):
            continue
        thesis_id = str(mapping.get("thesis_id") or "").strip()
        rationale = str(mapping.get("rationale") or "").strip()
        if not thesis_id:
            continue
        for raw in mapping.get("candidate_tickers") or []:
            ticker = str(raw or "").strip().upper()
            if ticker:
                triples.append((thesis_id, ticker, rationale))
    return triples
```

```python
# h4_opportunity_screener.py — compute_focus_roster, the thesis loop (was line ~78)
    for thesis_id, ticker, _rationale in thesis_mappings:
        ticker = ticker.strip().upper()
        if not ticker or ticker in entry_by_ticker:
            continue
        entry_by_ticker[ticker] = FocusRosterEntry(
            ticker=ticker,
            roster_reason="thesis_mapped",
            linked_market_thesis_id=thesis_id,
            rationale=_rationale,
        )
```

```python
# h4_opportunity_screener.py — compute_focus_roster, the protected set-comp (was line ~115)
    protected = set(held_set) | {ticker for _, ticker, _ in thesis_mappings}
```

Also update the `thesis_mappings` parameter type hint on `compute_focus_roster` to `Iterable[tuple[str, str, str]] = ()`.

- [ ] **Step 4: Run tests**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h4_focus_roster.py -v`
Expected: PASS (new test green; existing roster tests still green — thesis_mapped entries now carry a rationale, behaviour otherwise unchanged).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py tests/dq/hermes/test_h4_focus_roster.py
git commit -m "feat(hermes): thread H3 rationale through extract_thesis_mappings (#1017)"
```

---

### Task 3: Fix held↔thesis link-loss + populate rationale for held/technical

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py` (`compute_focus_roster` held loop `:71-76` and technical loop `:102-105`)
- Test: `tests/dq/hermes/test_h4_focus_roster.py`

**Interfaces:**
- Consumes: `thesis_mappings: Iterable[tuple[str, str, str]]` from Task 2.
- Produces: `compute_focus_roster(...) -> list[FocusRosterEntry]` where a held ticker that is also thesis-mapped carries `roster_reason="held"`, `linked_market_thesis_id=<id>`, `rationale=<held + thesis rationale>`; technical entries carry a non-empty rationale.

- [ ] **Step 1: Write the failing test**

```python
@pytest.mark.unit
def test_held_ticker_also_thesis_mapped_keeps_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "10")
    roster = compute_focus_roster(
        watchlist=["XLE", "SPY"],
        held={"XLE"},
        thesis_mappings=[("T-OIL", "XLE", "oil supply squeeze")],
        run_date=date(2026, 6, 20),
    )
    xle = next(e for e in roster if e.ticker == "XLE")
    assert xle.roster_reason == "held"
    assert xle.linked_market_thesis_id == "T-OIL"   # link no longer lost
    assert xle.rationale  # non-empty

@pytest.mark.unit
def test_technical_entry_carries_rationale(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "10")
    roster = compute_focus_roster(
        watchlist=["QQQ"], held=set(), thesis_mappings=[], run_date=date(2026, 6, 20),
    )
    qqq = next((e for e in roster if e.ticker == "QQQ"), None)
    if qqq is not None and qqq.roster_reason == "technical":
        assert qqq.rationale  # non-empty, honest "technical screen" reason
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h4_focus_roster.py::test_held_ticker_also_thesis_mapped_keeps_link -v`
Expected: FAIL — `xle.linked_market_thesis_id is None` (held added first, thesis link dropped).

- [ ] **Step 3: Build a thesis-by-ticker lookup, apply it to held + technical**

```python
# h4_opportunity_screener.py — at the top of compute_focus_roster, before the held loop:
    thesis_by_ticker: dict[str, tuple[str, str]] = {}
    for thesis_id, ticker, rationale in thesis_mappings:
        t = ticker.strip().upper()
        if t and t not in thesis_by_ticker:
            thesis_by_ticker[t] = (thesis_id, rationale)

    # held loop (replaces lines ~71-76): held inherits any thesis link + rationale
    def _held_entry(ticker: str) -> FocusRosterEntry:
        tid_rat = thesis_by_ticker.get(ticker)
        return FocusRosterEntry(
            ticker=ticker,
            roster_reason="held",
            linked_market_thesis_id=tid_rat[0] if tid_rat else None,
            rationale=(f"held position; {tid_rat[1]}" if tid_rat and tid_rat[1] else "held position"),
        )

    for ticker in normalized_watchlist:
        if ticker in held_set:
            entry_by_ticker[ticker] = _held_entry(ticker)
    for ticker in sorted(held_set):
        if ticker not in entry_by_ticker:
            entry_by_ticker[ticker] = _held_entry(ticker)

    # technical loop (replaces the FocusRosterEntry build at lines ~102-105):
    for ticker in technical_picks:
        if ticker in entry_by_ticker:
            continue
        entry_by_ticker[ticker] = FocusRosterEntry(
            ticker=ticker,
            roster_reason="technical",
            rationale="technical screen: top-ranked watchlist candidate by price/technical signal (no linked thesis)",
        )
```

(The `thesis_mappings` loop from Task 2 stays as the source of `thesis_mapped` entries for non-held tickers.)

- [ ] **Step 4: Run tests**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h4_focus_roster.py -v`
Expected: PASS (link-loss + rationale tests green; held-always invariant still green).

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py tests/dq/hermes/test_h4_focus_roster.py
git commit -m "fix(hermes): held ticker inherits thesis link + rationale; technical carries reason (#1017)"
```

---

### Task 4: Resolve the linked thesis into the analyst's inputs

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/phases/portfolio_common.py:203-213` (`run_asset_analyst_llm` `phase_inputs`)
- Test: `tests/dq/hermes/test_h5_dispatch_reason.py` (new)

**Interfaces:**
- Consumes: `roster_entry: dict[str, Any]` (now includes `rationale`), `state.prior_context.active_theses` (list of thesis dicts with `thesis_id`).
- Produces: `phase_inputs` additionally contains `rationale: str` and `linked_thesis: dict | None` (the single active-thesis row whose `thesis_id == linked_market_thesis_id`, else `None`).

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/hermes/test_h5_dispatch_reason.py  (new file)
from datetime import date
from typing import Any
import pytest
from digiquant.olympus.hermes.phases.portfolio_common import _resolve_linked_thesis

@pytest.mark.unit
def test_resolve_linked_thesis_picks_matching_row() -> None:
    theses = [{"thesis_id": "T1", "name": "Oil"}, {"thesis_id": "T2", "name": "Rates"}]
    assert _resolve_linked_thesis("T2", theses) == {"thesis_id": "T2", "name": "Rates"}
    assert _resolve_linked_thesis(None, theses) is None
    assert _resolve_linked_thesis("T9", theses) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h5_dispatch_reason.py -v`
Expected: FAIL — `ImportError: cannot import name '_resolve_linked_thesis'`.

- [ ] **Step 3: Add the helper + thread it into phase_inputs**

```python
# portfolio_common.py — module-level helper
def _resolve_linked_thesis(
    thesis_id: str | None, active_theses: list[dict[str, Any]]
) -> dict[str, Any] | None:
    """Return the single active-thesis row matching ``thesis_id`` (or None)."""
    if not thesis_id:
        return None
    for row in active_theses:
        if isinstance(row, dict) and str(row.get("thesis_id") or "") == thesis_id:
            return dict(row)
    return None
```

```python
# portfolio_common.py — inside run_asset_analyst_llm, extend the phase_inputs dict
    _active = list(state.prior_context.active_theses)
    phase_inputs: dict[str, Any] = {
        "segment": phase_slug,
        "ticker": ticker,
        "roster_reason": roster_entry.get("roster_reason"),
        "rationale": roster_entry.get("rationale", ""),
        "linked_market_thesis_id": roster_entry.get("linked_market_thesis_id"),
        "linked_thesis": _resolve_linked_thesis(
            roster_entry.get("linked_market_thesis_id"), _active
        ),
        "bias_row": state.phase6_bias_row or {},
        "active_theses": _active,
        "price_deltas": dict(state.price_deltas),
        "held_in_prior_book": ticker
        in set(holdings_from_prior_book(state.prior_context.prior_book)),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h5_dispatch_reason.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/hermes/phases/portfolio_common.py tests/dq/hermes/test_h5_dispatch_reason.py
git commit -m "feat(hermes): resolve linked thesis + rationale into analyst inputs (#1017)"
```

---

### Task 5: Stop manufacturing a post-hoc thesis for held/linked names

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/phases/h5_asset_analyst.py:67-73` (`_h5_node_factory`)
- Test: `tests/dq/hermes/test_h5_dispatch_reason.py`

**Interfaces:**
- Consumes: `entry` dict with `roster_reason`, `linked_market_thesis_id`.
- Produces: `upsert_vehicle_thesis_from_analyst` is called **only** for genuinely-unlinked exploratory picks (`roster_reason in {"technical", "momentum", "other"}` AND no `linked_market_thesis_id`); never for `held` or `thesis_mapped`.

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/hermes/test_h5_dispatch_reason.py
from digiquant.olympus.hermes.phases.h5_asset_analyst import _should_backfill_vehicle_thesis

@pytest.mark.unit
def test_backfill_only_for_unlinked_exploratory() -> None:
    assert _should_backfill_vehicle_thesis({"roster_reason": "technical"}) is True
    assert _should_backfill_vehicle_thesis({"roster_reason": "held"}) is False
    assert _should_backfill_vehicle_thesis({"roster_reason": "thesis_mapped",
                                            "linked_market_thesis_id": "T1"}) is False
    assert _should_backfill_vehicle_thesis(
        {"roster_reason": "technical", "linked_market_thesis_id": "T1"}) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h5_dispatch_reason.py::test_backfill_only_for_unlinked_exploratory -v`
Expected: FAIL — `ImportError: cannot import name '_should_backfill_vehicle_thesis'`.

- [ ] **Step 3: Add the predicate + use it at the call site**

```python
# h5_asset_analyst.py — module-level predicate
_EXPLORATORY_REASONS = frozenset({"technical", "momentum", "other"})

def _should_backfill_vehicle_thesis(entry: dict[str, Any]) -> bool:
    """Post-hoc vehicle thesis only for genuinely-unlinked exploratory picks —
    never for held or thesis-linked names (the reversed-arrow fix, #1017)."""
    if entry.get("linked_market_thesis_id"):
        return False
    return entry.get("roster_reason") in _EXPLORATORY_REASONS
```

```python
# h5_asset_analyst.py — replace the `if entry.get("roster_reason") != "thesis_mapped":` guard (lines ~67-73)
            if _should_backfill_vehicle_thesis(entry):
                upsert_vehicle_thesis_from_analyst(
                    client,
                    run_date=state.run_date,
                    ticker=ticker,
                    analyst_payload=payload.model_dump(mode="json"),
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest tests/dq/hermes/test_h5_dispatch_reason.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/hermes/phases/h5_asset_analyst.py tests/dq/hermes/test_h5_dispatch_reason.py
git commit -m "fix(hermes): post-hoc vehicle thesis only for unlinked exploratory picks (#1017)"
```

---

### Task 6: Tell the analyst why it was dispatched (skill prompt)

**Files:**
- Modify: the `asset-analyst` skill **source** under `agents/sources/` (locate via the command below — never edit the generated `.claude/skills/` copy), then regenerate.
- Test: manual (prompt content) + `make agents-init` idempotence.

**Interfaces:**
- Consumes: `phase_inputs` keys `rationale`, `linked_thesis`, `roster_reason` (from Tasks 3–4).

- [ ] **Step 1: Locate the skill source**

Run: `grep -rl "asset-analyst" agents/sources/ | head` and open the matching source skill file.

- [ ] **Step 2: Add the dispatch-reason framing**

Add to the asset-analyst skill prompt (near the top of the task instructions), verbatim:

```
You were dispatched to analyze this vehicle for a reason. Read `rationale` and
`roster_reason` from your inputs, and if `linked_thesis` is present, treat it as
the thesis you are validating: judge whether THIS vehicle is an effective way to
express that thesis and whether now is the right time to act. If `linked_thesis`
is absent (an exploratory/technical pick), say so explicitly and assess whether a
thesis is warranted — do not invent one.
```

- [ ] **Step 3: Regenerate the agent surface**

Run: `make agents-init`
Expected: regenerates `.claude/skills/` from sources; `git status` shows the regenerated skill changed.

- [ ] **Step 4: Verify idempotence**

Run: `make agents-init` again
Expected: no further diff (CI enforces idempotence).

- [ ] **Step 5: Commit**

```bash
git add agents/sources/ .claude/skills/
git commit -m "feat(hermes): asset-analyst prompt consumes its dispatch reason (#1017)"
```

---

## Self-Review

**Spec coverage (Stage 1a subset):**
- "every dispatch carries a reason" → Tasks 1–3 (rationale on every entry) + Task 6 (analyst consumes it). ✓
- "remove the reversed arrow" → Task 5. ✓
- "fix held+thesis-mapped link-loss" → Task 3. ✓
- "carry H3 rationale + linked thesis into the analyst" → Tasks 2–4 + 6. ✓
- **Deferred to Stage 1b (own plan):** excluded ledger (changes `compute_focus_roster` return type), held staleness/delta gate (changes the held-always invariant + needs a threshold design), and the full `FocusRosterEntry`→`RosterPick` convergence. Stages 2–4 (adaptive budget, T1 scan, follow-up loop) are separate per the spec, measurement-gated.

**Placeholder scan:** none — every code/test step has exact content; Task 6's only lookup is a `grep` to find the skill source (path varies by repo layout), with exact prompt text given.

**Type consistency:** `extract_thesis_mappings` returns `tuple[str, str, str]` and both unpack sites (`for thesis_id, ticker, _rationale` and `{ticker for _, ticker, _ in ...}`) + the `compute_focus_roster` param hint are updated together (Task 2). `_resolve_linked_thesis` / `_should_backfill_vehicle_thesis` names match between their defining task and their test.

**Risk note:** Task 2 changes a shared tuple shape — its two consumers are updated in the same task to stay green. No graph-topology change; no new LLM call; held-always invariant preserved.
