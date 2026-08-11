# Adaptive Dispatch Stage 1b — Excluded Ledger + Held Staleness Gate — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record *why each watchlist name was NOT analyzed* (the excluded ledger — the missing half of anti-waste), and stop unconditionally re-analyzing held names that haven't materially moved (the held staleness/delta gate) — the two Stage-1b items deferred from Stage 1a.

**Architecture:** Builds on Stage 1a (merged): `FocusRosterEntry` carries `rationale`; `compute_focus_roster` returns `list[FocusRosterEntry]`. Stage 1b adds (a) an `ExcludedTicker` record + a `focus_roster_excluded` slot on `PhaseHermesState`, populated in the H4 node and persisted; and (b) a staleness/delta gate so a held name is dispatched only when it has a material price move OR a linked thesis — otherwise it lands in the excluded ledger.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, LangGraph (graph wiring unchanged).

## Global Constraints

- Pydantic v2; strict typing; ruff line length 100; `ruff check` + `ruff format` clean.
- New model fields/slots additive with defaults.
- `compute_focus_roster` keeps return type `list[FocusRosterEntry]` (excluded ledger flows via a new state slot, not a return-type change).
- Tests: `/Users/chrisstefan/Code/digithings/.venv/bin/python -m pytest <path> -v` (pytest.ini sets pythonpath); unit tests `@pytest.mark.unit`, `monkeypatch.setenv` for env.
- Branch from `origin/develop` as `task/1017-...`; each task ends in a commit; TDD throughout.

## ⚠️ Decisions needed before/at implementation (recommended defaults in brackets)

1. **Held staleness threshold** — a held name with no linked thesis is dispatched only if `abs(price_delta) >= HELD_STALENESS_DELTA` . **[default `0.005` = 0.5% daily move; env `HERMES_HELD_STALENESS_DELTA`]**. Your call on the number.
2. **Held-always invariant** — Stage 1b *intentionally relaxes* "every held name is always analyzed" to "held analyzed iff material move OR thesis-linked." Confirm this is desired (the existing `test_held_invariant` / `test_held_always_in_roster` are updated to the new semantics). A kill-switch env **[`HERMES_HELD_GATE=on|off`, default `on`]** lets ops revert to always-analyze without a deploy.
3. **Excluded-ledger persistence** — store the ledger **[in a new `documents` row `doc_type` = "Focus Roster Ledger" via the existing publish path]**, or only on graph state? Default: persist a compact ledger doc so it's auditable on the dashboard.

---

## File Structure

- `digiquant/src/digiquant/olympus/atlas/state.py` — add `ExcludedTicker` model + `focus_roster_excluded: list[ExcludedTicker]` to `PhaseHermesState`.
- `digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py` — `compute_focus_roster` gains an optional `price_deltas` input + emits exclusions; the H4 node derives + persists the ledger.
- `digiquant/src/digiquant/olympus/hermes/roster_cap.py` — unchanged (held-gate happens before capping).
- `digiquant/src/digiquant/olympus/hermes/writers/` — a small `publish_focus_roster_ledger` writer (if decision 3 = persist).
- Tests: `tests/dq/hermes/test_h4_focus_roster.py`, `tests/dq/hermes/test_held_invariant.py` (updated), `tests/dq/hermes/test_focus_roster_ledger.py` (new).

---

### Task 1: `ExcludedTicker` model + state slot

**Files:** Modify `digiquant/src/digiquant/olympus/atlas/state.py`. Test: `tests/dq/hermes/test_h4_focus_roster.py`.

**Interfaces — Produces:** `ExcludedTicker(ticker: str, reason: str)`; `PhaseHermesState.focus_roster_excluded: list[ExcludedTicker] = Field(default_factory=list)`.

- [ ] **Step 1 — failing test**
```python
@pytest.mark.unit
def test_excluded_ticker_and_state_slot() -> None:
    from digiquant.olympus.atlas.state import ExcludedTicker, PhaseHermesState
    e = ExcludedTicker(ticker="TLT", reason="held, no material change (Δ<0.5%)")
    assert e.ticker == "TLT" and e.reason
    assert PhaseHermesState().focus_roster_excluded == []
```
- [ ] **Step 2 — run, expect ImportError / attribute error.** `…/.venv/bin/python -m pytest tests/dq/hermes/test_h4_focus_roster.py::test_excluded_ticker_and_state_slot -v`
- [ ] **Step 3 — implement**
```python
class ExcludedTicker(BaseModel):
    """A watchlist ticker that was NOT dispatched to an analyst, and why."""
    ticker: str
    reason: str
```
Add to `PhaseHermesState`: `focus_roster_excluded: list[ExcludedTicker] = Field(default_factory=list)`.
- [ ] **Step 4 — run, expect pass.** **Step 5 — commit** `feat(hermes): ExcludedTicker model + focus_roster_excluded slot (#1017)`

---

### Task 2: Held staleness/delta gate in `compute_focus_roster`

**Files:** Modify `h4_opportunity_screener.py` (`compute_focus_roster` held loop). Test: `tests/dq/hermes/test_h4_focus_roster.py`.

**Interfaces:**
- Consumes: a new keyword `price_deltas: Mapping[str, float] | None = None` on `compute_focus_roster`; env `HERMES_HELD_STALENESS_DELTA` (default 0.005), `HERMES_HELD_GATE` (default "on").
- Produces: a held ticker is included only if gate off, OR thesis-linked, OR `abs(price_deltas.get(ticker, 0)) >= threshold`; otherwise it is omitted from the roster (Task 3 records it as excluded). Return type unchanged.

- [ ] **Step 1 — failing tests**
```python
@pytest.mark.unit
def test_held_gate_drops_stale_unlinked_held(monkeypatch):
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "10")
    monkeypatch.setenv("HERMES_HELD_STALENESS_DELTA", "0.005")
    roster = compute_focus_roster(
        watchlist=["TLT", "XLE"], held={"TLT", "XLE"},
        thesis_mappings=[("T-OIL", "XLE", "oil")],
        price_deltas={"TLT": 0.001, "XLE": 0.0},  # both quiet; XLE thesis-linked
        run_date=date(2026, 6, 20),
    )
    tickers = {e.ticker for e in roster}
    assert "TLT" not in tickers          # stale + unlinked → gated out
    assert "XLE" in tickers              # thesis-linked → kept despite quiet

@pytest.mark.unit
def test_held_gate_keeps_material_move(monkeypatch):
    monkeypatch.setenv("HERMES_HELD_STALENESS_DELTA", "0.005")
    roster = compute_focus_roster(
        watchlist=["TLT"], held={"TLT"}, price_deltas={"TLT": 0.02},
        run_date=date(2026, 6, 20))
    assert "TLT" in {e.ticker for e in roster}   # 2% move ≥ 0.5% → kept

@pytest.mark.unit
def test_held_gate_off_keeps_all(monkeypatch):
    monkeypatch.setenv("HERMES_HELD_GATE", "off")
    roster = compute_focus_roster(
        watchlist=["TLT"], held={"TLT"}, price_deltas={"TLT": 0.0},
        run_date=date(2026, 6, 20))
    assert "TLT" in {e.ticker for e in roster}   # kill-switch → always-analyze
```
- [ ] **Step 2 — run, expect fail** (`price_deltas` kwarg unknown / TLT still present).
- [ ] **Step 3 — implement** a module helper + use it in the held loop:
```python
def _held_passes_gate(ticker: str, linked_thesis_id: str | None,
                      price_deltas: Mapping[str, float] | None) -> bool:
    if os.environ.get("HERMES_HELD_GATE", "on").strip().lower() == "off":
        return True
    if linked_thesis_id:
        return True
    threshold = float(os.environ.get("HERMES_HELD_STALENESS_DELTA", "0.005"))
    return abs((price_deltas or {}).get(ticker, 0.0)) >= threshold
```
Add `price_deltas: Mapping[str, float] | None = None` to `compute_focus_roster`; in `_held_entry` insertion, only insert the held entry when `_held_passes_gate(...)` is True; collect gated-out held tickers for Task 3.
- [ ] **Step 4 — run, expect pass.** **Step 5 — commit** `feat(hermes): held staleness/delta dispatch gate (#1017)`

---

### Task 3: Populate + emit the excluded ledger in the H4 node

**Files:** Modify `h4_opportunity_screener.py` (`compute_focus_roster` returns/exposes exclusions to the node; `_h4_node` stores `focus_roster_excluded`). Wire `price_deltas` from `state.price_deltas`. Test: `tests/dq/hermes/test_h4_focus_roster.py`.

**Interfaces:** `compute_focus_roster` additionally returns its exclusions — to avoid a return-type break, add a sibling `compute_focus_roster_excluded(watchlist, roster, *, held, price_deltas, gated_held) -> list[ExcludedTicker]` that the node calls; the node sets `state.phase_hermes.focus_roster_excluded`.

- [ ] **Step 1 — failing test**: a watchlist of 3 where 1 is rostered, 1 is gated-out held, 1 is unscreened → `focus_roster_excluded` has 2 entries with non-empty reasons; the rostered one is absent from the ledger.
- [ ] **Step 2 — run, expect fail.**
- [ ] **Step 3 — implement** the sibling + node wiring (derive excluded = watchlist − rostered, reason per cause: "held, no material change", "not thesis-mapped and below technical screen", etc.); pass `price_deltas=dict(state.price_deltas)` into `compute_focus_roster`.
- [ ] **Step 4 — run, expect pass.** **Step 5 — commit** `feat(hermes): populate focus_roster excluded ledger in H4 node (#1017)`

---

### Task 4: Update the held-always invariant tests to the gated semantics

**Files:** Modify `tests/dq/hermes/test_held_invariant.py`, `tests/dq/hermes/test_h4_focus_roster.py::test_held_always_in_roster`.

**Interfaces:** Consumes the gate from Task 2. The invariant becomes: a held name is in the roster iff (gate off) OR (thesis-linked) OR (material move); otherwise it's in `focus_roster_excluded`.

- [ ] **Step 1 — rewrite the invariant tests** to assert the new semantics (held-with-material-move or thesis-link stays; stale-unlinked held moves to the ledger; with `HERMES_HELD_GATE=off`, all held stay). These are existing tests asserting the OLD always-in invariant — update them, do not delete (the gate is a deliberate behavior change, plan-mandated; see Decision 2).
- [ ] **Step 2 — run** the two files, expect pass. **Step 3 — commit** `test(hermes): held invariant reflects staleness gate (#1017)`

---

### Task 5 (optional, gated on Decision 3): Persist the excluded ledger

**Files:** new `publish_focus_roster_ledger` writer + H4/commit wiring; migration to allow `doc_type="Focus Roster Ledger"` (⚠️ prod-apply via the db-migrate gate). Test: `tests/dq/hermes/test_focus_roster_ledger.py`.

- [ ] Add the doc_type to `chk_documents_doc_type` (new migration, applied to prod by the db-migrate gate); publish a compact `{date, rostered:[…], excluded:[{ticker,reason}]}` document; test the writer with `FakeSupabaseClient`. Commit `feat(hermes): persist focus-roster excluded ledger (#1017)`.

> If Decision 3 = state-only, skip Task 5; the ledger lives on `phase_hermes.focus_roster_excluded` for downstream/PM use without a new doc_type.

---

## Self-Review

- **Spec coverage:** excluded ledger (Tasks 1–3, 5) + held staleness/delta gate (Tasks 2, 4) — the two Stage-1b deferrals. `RosterPick` full convergence remains a separate refactor (not behavior-changing; defer).
- **Placeholders:** none — helper code + tests are concrete; the three genuinely-open product choices are isolated in "Decisions needed" with defaults so the plan is executable as written.
- **Type consistency:** `compute_focus_roster` return type unchanged; exclusions flow via the new sibling + state slot; `_held_passes_gate` / `compute_focus_roster_excluded` names consistent across tasks.
- **Risk:** Task 2 changes a tested invariant (held-always) — Task 4 updates those tests in lockstep, and the `HERMES_HELD_GATE=off` kill-switch makes the change reversible without a deploy.
