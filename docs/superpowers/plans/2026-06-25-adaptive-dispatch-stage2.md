# Adaptive Regime-Conditioned Analyst Budget (Stage 2) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace H4's static `ATLAS_MAX_ANALYSTS` analyst-dispatch cap with a market-regime-driven budget `B` and explore/exploit split, computed at H4 from signals Atlas already computes, with a fail-soft fallback to the static cap.

**Architecture:** A new pure-ish `budget_controller` module classifies a market regime from VIX term-structure + market breadth + cross-sectional return dispersion, and maps it to `(budget, explore_floor)`. H4's `_h4_node` calls it (the node already holds the Supabase client) and threads `budget`/`explore_floor` into `compute_focus_roster` → `roster_cap.capped_tickers`. Signal gathering is fail-soft: any missing signal or read error degrades to the static `ATLAS_MAX_ANALYSTS` cap and logs, never raising (H4 must not crash the daily run). This is Stage 2 of the adaptive two-track dispatch design (spec `docs/superpowers/specs/2026-06-23-adaptive-two-track-dispatch-design.md`, umbrella #1017).

**Tech Stack:** Python 3.12, Pydantic v2, Polars (not pandas), pytest (`@pytest.mark.unit`). LangGraph H1–H9 Hermes sub-graph.

## Global Constraints

- **Polars only** — never pandas. Pydantic v2; ruff line-length 100; ruff-compliant.
- **Backward compatible.** `ATLAS_MAX_ANALYSTS` remains the fallback cap. `capped_tickers` gains an optional `adaptive_max_analysts: int | None = None` that, when set, is preferred over the env var; when `None`, behavior is byte-identical to today. Every existing test that monkeypatches `ATLAS_MAX_ANALYSTS` must stay green unchanged.
- **Fail-soft, never raise.** Any failure to compute the regime (client unavailable, DB read error, empty signals) → return `None` budget → H4 falls back to the static cap and logs a warning. The budget controller must never propagate an exception into the H4 node.
- **Cost-safe by default.** The adaptive budget may only *tighten* dispatch relative to the configured cap — `B ≤ effective_static_cap` always (when a finite cap is configured). It never increases analyst spend beyond today's cap. Regimes with low idiosyncratic information value (high-correlation / risk-off) shrink `B`; calm/dispersion regimes keep the cap. (Increasing `B` above the cap in dispersion regimes is explicitly deferred until measurement justifies it — spec build-sequence note.)
- **Instrumentation is load-bearing.** Every run logs the regime label, the signal values used, and the resulting `(budget, explore_floor)` at INFO. Measurement of whether the adaptive budget helps depends on this log line.
- **Deterministic mapping.** `regime → (budget, explore_floor)` is a pure function of the assessment, fully unit-testable with no I/O.
- **No model churn.** Do not touch `RosterPick`/`OpportunityScreenOutput` (dead) or replace `FocusRosterEntry` — out of Stage 2 scope.
- **Issue linkage.** Open a Stage 2 sub-issue under #1017; use a `task/<N>-slug` branch and/or `Fixes #<N>` in the PR body.

## File Structure

- **Create** `digiquant/src/digiquant/olympus/hermes/budget_controller.py` — the regime classifier, the deterministic budget mapping, and the fail-soft `assess_budget(state, client, *, static_cap)` entry point. One responsibility: turn market state into a dispatch budget.
- **Create** `tests/dq/hermes/test_budget_controller.py` — unit tests for the model, classifier, mapping, and fail-soft assessment.
- **Modify** `digiquant/src/digiquant/olympus/hermes/roster_cap.py` — add the optional `adaptive_max_analysts` param to `capped_tickers`.
- **Modify** `digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py` — thread `adaptive_max_analysts` + `min_new` through `compute_focus_roster`; call the budget controller in `_h4_node` and log the decision.
- **Modify** `tests/dq/hermes/test_roster_cap.py` (create if absent) and `tests/dq/hermes/test_h4_focus_roster.py` — cover the new param + wiring.
- **Modify** `digiquant/src/digiquant/olympus/hermes/docs/ARCHITECTURE.md` — document the regime-adaptive budget at H4.

---

### Task 1: `RegimeAssessment` model + signal dispersion helper

**Files:**
- Create: `digiquant/src/digiquant/olympus/hermes/budget_controller.py`
- Test: `tests/dq/hermes/test_budget_controller.py`

**Interfaces:**
- Produces: `RegimeLabel = Literal["stress", "neutral", "dispersion"]`; `RegimeAssessment(BaseModel)` with fields `regime: RegimeLabel`, `vix_state: str | None`, `vix_ratio: float | None`, `pct_above_50dma: float | None`, `return_dispersion: float | None`, `note: str = ""`. `cross_sectional_dispersion(price_deltas: Mapping[str, float]) -> float | None` (population stdev of the delta values; `None` if fewer than 2 non-null values).

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/hermes/test_budget_controller.py
from __future__ import annotations

import pytest

from digiquant.olympus.hermes.budget_controller import (
    RegimeAssessment,
    cross_sectional_dispersion,
)


@pytest.mark.unit
def test_regime_assessment_defaults() -> None:
    a = RegimeAssessment(regime="neutral")
    assert a.regime == "neutral"
    assert a.vix_state is None and a.return_dispersion is None and a.note == ""


@pytest.mark.unit
def test_cross_sectional_dispersion_population_stdev() -> None:
    # stdev of {0.01, -0.01, 0.03, -0.03} (population) == 0.02
    out = cross_sectional_dispersion({"A": 0.01, "B": -0.01, "C": 0.03, "D": -0.03})
    assert out == pytest.approx(0.02, abs=1e-9)


@pytest.mark.unit
def test_cross_sectional_dispersion_insufficient_data_is_none() -> None:
    assert cross_sectional_dispersion({}) is None
    assert cross_sectional_dispersion({"A": 0.01}) is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/bin/python -m pytest tests/dq/hermes/test_budget_controller.py -q`
Expected: FAIL — module/symbols not defined.

- [ ] **Step 3: Minimal implementation**

```python
# digiquant/src/digiquant/olympus/hermes/budget_controller.py
"""Stage 2 — regime-conditioned analyst dispatch budget (#1017).

Turns market state (VIX term structure + breadth + cross-sectional return
dispersion) into a dispatch budget for H4's focus roster, with a fail-soft
fallback to the static ATLAS_MAX_ANALYSTS cap. See
docs/superpowers/specs/2026-06-23-adaptive-two-track-dispatch-design.md.
"""

from __future__ import annotations

import logging
import statistics
from collections.abc import Mapping
from typing import Any, Literal

from pydantic import BaseModel

logger = logging.getLogger(__name__)

RegimeLabel = Literal["stress", "neutral", "dispersion"]


class RegimeAssessment(BaseModel):
    """The classified regime plus the signals that produced it (for the audit log)."""

    regime: RegimeLabel
    vix_state: str | None = None
    vix_ratio: float | None = None
    pct_above_50dma: float | None = None
    return_dispersion: float | None = None
    note: str = ""


def cross_sectional_dispersion(price_deltas: Mapping[str, float]) -> float | None:
    """Population stdev of per-ticker daily returns — a no-DB dispersion proxy.

    Returns ``None`` when fewer than two finite values are present.
    """
    vals = [float(v) for v in price_deltas.values() if v is not None]
    if len(vals) < 2:
        return None
    return statistics.pstdev(vals)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/bin/python -m pytest tests/dq/hermes/test_budget_controller.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add digiquant/src/digiquant/olympus/hermes/budget_controller.py tests/dq/hermes/test_budget_controller.py
git commit -m "feat(olympus): RegimeAssessment model + dispersion helper (Stage 2, #1017)"
```

---

### Task 2: Deterministic regime classifier + budget/split mapping

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/budget_controller.py`
- Test: `tests/dq/hermes/test_budget_controller.py`

**Interfaces:**
- Consumes: `RegimeAssessment`, `cross_sectional_dispersion` (Task 1).
- Produces:
  - `classify_regime(*, vix_state, vix_ratio, pct_above_50dma, return_dispersion) -> RegimeAssessment` — pure function.
  - `budget_for(assessment: RegimeAssessment, *, static_cap: int) -> tuple[int, int]` — returns `(budget, explore_floor)`, pure, cost-safe (`budget <= static_cap` when `static_cap > 0`).

**Classifier policy (deterministic):**
- `stress` if VIX backwardation (`vix_state == "backwardation"`) OR breadth weak (`pct_above_50dma is not None and pct_above_50dma < 40.0`). Risk-off / likely high correlation → idiosyncratic dives low-value.
- `dispersion` else if `return_dispersion is not None and return_dispersion >= DISPERSION_HI` (default 0.015 = 1.5% cross-sectional stdev). Wide dispersion → idiosyncratic dives high-value.
- `neutral` otherwise (including when signals are sparse/None).

**Budget policy (cost-safe — only tightens):** for `static_cap > 0`:
- `stress` → `budget = max(STRESS_FLOOR, round(static_cap * 0.5))`, `explore_floor = 0` (bias to held/thesis exploit).
- `neutral` → `budget = static_cap`, `explore_floor = 1` (today's default min_new).
- `dispersion` → `budget = static_cap`, `explore_floor = max(2, round(static_cap * 0.25))` (probe more new names, still within cap).
- When `static_cap <= 0` (no cap configured), return `(0, explore_floor)` so the roster stays uncapped exactly as today; `explore_floor` still follows the regime.

`STRESS_FLOOR` default 3, `DISPERSION_HI` default 0.015, both module constants overridable via env (`ATLAS_BUDGET_STRESS_FLOOR`, `ATLAS_BUDGET_DISPERSION_HI`).

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/dq/hermes/test_budget_controller.py
from digiquant.olympus.hermes.budget_controller import budget_for, classify_regime


@pytest.mark.unit
class TestClassifyRegime:
    def test_backwardation_is_stress(self) -> None:
        a = classify_regime(vix_state="backwardation", vix_ratio=1.1,
                             pct_above_50dma=70.0, return_dispersion=0.02)
        assert a.regime == "stress"  # backwardation dominates even with wide dispersion

    def test_weak_breadth_is_stress(self) -> None:
        a = classify_regime(vix_state="contango", vix_ratio=0.9,
                             pct_above_50dma=30.0, return_dispersion=0.005)
        assert a.regime == "stress"

    def test_wide_dispersion_is_dispersion(self) -> None:
        a = classify_regime(vix_state="contango", vix_ratio=0.9,
                             pct_above_50dma=65.0, return_dispersion=0.02)
        assert a.regime == "dispersion"

    def test_calm_is_neutral(self) -> None:
        a = classify_regime(vix_state="contango", vix_ratio=0.95,
                             pct_above_50dma=55.0, return_dispersion=0.005)
        assert a.regime == "neutral"

    def test_all_signals_none_is_neutral(self) -> None:
        a = classify_regime(vix_state=None, vix_ratio=None,
                            pct_above_50dma=None, return_dispersion=None)
        assert a.regime == "neutral"


@pytest.mark.unit
class TestBudgetFor:
    def test_stress_tightens_below_cap(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="stress"), static_cap=20)
        assert b == 10 and b <= 20
        assert floor == 0

    def test_stress_respects_floor(self) -> None:
        b, _ = budget_for(RegimeAssessment(regime="stress"), static_cap=4)
        assert b == 3  # STRESS_FLOOR, not round(4*0.5)=2

    def test_neutral_equals_cap(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="neutral"), static_cap=20)
        assert b == 20 and floor == 1

    def test_dispersion_keeps_cap_raises_explore_floor(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="dispersion"), static_cap=20)
        assert b == 20  # never exceeds cap (cost-safe)
        assert floor == 5  # round(20*0.25)

    def test_no_cap_configured_stays_uncapped(self) -> None:
        b, floor = budget_for(RegimeAssessment(regime="neutral"), static_cap=0)
        assert b == 0  # 0 == "no cap" downstream
        assert floor == 1

    def test_budget_never_exceeds_cap_any_regime(self) -> None:
        for regime in ("stress", "neutral", "dispersion"):
            b, _ = budget_for(RegimeAssessment(regime=regime), static_cap=12)
            assert b <= 12
```

- [ ] **Step 2: Run to verify fail** — `... -k "ClassifyRegime or BudgetFor"`; expected FAIL (undefined).

- [ ] **Step 3: Implement** `classify_regime` + `budget_for` + the module constants (read env with the documented defaults) exactly per the policy above.

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit** — `feat(olympus): regime classifier + cost-safe budget mapping (Stage 2, #1017)`.

---

### Task 3: Fail-soft `assess_budget(state, client, *, static_cap)` entry point

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/budget_controller.py`
- Test: `tests/dq/hermes/test_budget_controller.py`

**Interfaces:**
- Consumes: `classify_regime`, `budget_for`, `cross_sectional_dispersion`; `get_market_breadth` + `get_vix_term_structure` from `digiquant.olympus.atlas.data.queries`.
- Produces: `assess_budget(state: Any, client: Any, *, static_cap: int) -> tuple[int, int, RegimeAssessment | None]` returning `(budget, explore_floor, assessment)`. On ANY failure or `client is None`, returns `(static_cap, 1, None)` (static fallback) and logs a warning — never raises.

**Behavior:**
- `return_dispersion = cross_sectional_dispersion(state.price_deltas)` (no DB; `state.price_deltas` always present post-Stage-1b).
- If `client is not None`: fetch `get_vix_term_structure(client=client, run_date=state.run_date)` and `get_market_breadth(client=client, run_date=state.run_date)` inside a `try/except Exception` (advisory — must not block the book). Pull `vix_state`/`ratio`/`pct_above_50dma` (`.get(...)`, tolerate `{}`).
- `assessment = classify_regime(...)`; `(budget, floor) = budget_for(assessment, static_cap=static_cap)`.
- Log INFO: `"H4 budget: regime=%s vix=%s breadth=%s dispersion=%s -> B=%d explore_floor=%d"`.
- Wrap the whole body in `try/except Exception`; on exception log a warning and return `(static_cap, 1, None)`.

- [ ] **Step 1: Write the failing tests** (use a fake client + a minimal state stub):

```python
# append to tests/dq/hermes/test_budget_controller.py
from datetime import date
from types import SimpleNamespace

from digiquant.olympus.hermes.budget_controller import assess_budget


def _state(price_deltas: dict[str, float]) -> SimpleNamespace:
    return SimpleNamespace(price_deltas=price_deltas, run_date=date(2026, 6, 25))


@pytest.mark.unit
class TestAssessBudget:
    def test_none_client_falls_back_to_static(self) -> None:
        b, floor, a = assess_budget(_state({"A": 0.01, "B": -0.01}), None, static_cap=20)
        assert (b, floor) == (20, 1) and a is None

    def test_reader_error_falls_back_to_static(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(**_kw: object) -> dict:
            raise RuntimeError("db down")
        monkeypatch.setattr(
            "digiquant.olympus.hermes.budget_controller.get_vix_term_structure", boom
        )
        b, floor, a = assess_budget(_state({"A": 0.01}), object(), static_cap=15)
        assert (b, floor) == (15, 1) and a is None

    def test_stress_signals_tighten_budget(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "digiquant.olympus.hermes.budget_controller.get_vix_term_structure",
            lambda **_k: {"state": "backwardation", "ratio": 1.2},
        )
        monkeypatch.setattr(
            "digiquant.olympus.hermes.budget_controller.get_market_breadth",
            lambda **_k: {"pct_above_50dma": 35.0, "universe_size": 50},
        )
        b, floor, a = assess_budget(_state({"A": 0.001, "B": -0.001}), object(), static_cap=20)
        assert a is not None and a.regime == "stress"
        assert b == 10 and floor == 0
```

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** `assess_budget` per behavior; import the two query readers at module top so the monkeypatch targets resolve.
- [ ] **Step 4: Run → PASS.**
- [ ] **Step 5: Commit** — `feat(olympus): fail-soft assess_budget entry point (Stage 2, #1017)`.

---

### Task 4: `capped_tickers` accepts `adaptive_max_analysts` (backward-compatible)

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/roster_cap.py:14-27`
- Test: `tests/dq/hermes/test_roster_cap.py` (create if absent)

**Interfaces:**
- Produces: `capped_tickers(tickers, held=(), *, min_new=_DEFAULT_MIN_NEW, adaptive_max_analysts: int | None = None) -> list[str]`. When `adaptive_max_analysts is not None`, it is used as the cap; otherwise the existing `os.environ.get("ATLAS_MAX_ANALYSTS", "0")` read is used. All downstream cap logic (held protection, min_new expansion, over-budget) is unchanged.

- [ ] **Step 1: Write the failing test**

```python
# tests/dq/hermes/test_roster_cap.py
from __future__ import annotations

import pytest

from digiquant.olympus.hermes.roster_cap import capped_tickers


@pytest.mark.unit
class TestCappedTickersAdaptive:
    def test_adaptive_param_overrides_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "100")  # env says no real cap
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=2)
        assert len(out) == 2  # adaptive cap wins

    def test_none_adaptive_uses_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=None)
        assert len(out) == 2  # env cap, exactly today's behavior

    def test_adaptive_zero_means_no_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "2")
        out = capped_tickers(["A", "B", "C", "D"], held=(), min_new=1, adaptive_max_analysts=0)
        assert len(out) == 4  # 0 == no cap, overriding the env's 2
```

- [ ] **Step 2: Run → FAIL** (unexpected kwarg / wrong counts).
- [ ] **Step 3: Implement.** Add the kwarg; replace the cap read with:

```python
max_analysts = (
    adaptive_max_analysts
    if adaptive_max_analysts is not None
    else int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")
)
```

Leave all subsequent logic untouched.

- [ ] **Step 4: Run → PASS**, then run the existing cap tests to prove no regression: `.venv/bin/python -m pytest tests/dq/hermes/test_held_invariant.py tests/dq/hermes/test_h4_focus_roster.py -q`.
- [ ] **Step 5: Commit** — `feat(olympus): capped_tickers accepts adaptive_max_analysts (Stage 2, #1017)`.

---

### Task 5: Thread budget + explore_floor through `compute_focus_roster`

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py` (`compute_focus_roster` signature + the `capped_tickers` call at ~line 180)
- Test: `tests/dq/hermes/test_h4_focus_roster.py`

**Interfaces:**
- Produces: `compute_focus_roster(..., adaptive_max_analysts: int | None = None, min_new_candidates: int = 1)` — passes `adaptive_max_analysts=adaptive_max_analysts` to `capped_tickers`; `min_new_candidates` already exists and maps to the explore floor.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/dq/hermes/test_h4_focus_roster.py
@pytest.mark.unit
def test_compute_focus_roster_honors_adaptive_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATLAS_MAX_ANALYSTS", "100")  # env would allow all
    monkeypatch.setenv("HERMES_HELD_GATE", "off")
    roster = compute_focus_roster(
        watchlist=["AAA", "BBB", "CCC", "DDD"],
        held=set(),
        run_date=date(2026, 6, 20),
        adaptive_max_analysts=2,  # regime budget tightens to 2
        min_new_candidates=1,
    )
    assert len(roster) == 2
```

- [ ] **Step 2: Run → FAIL** (unexpected kwarg).
- [ ] **Step 3: Implement** — add the param; change the call to `capped_tickers(ordered_tickers, held=protected, min_new=min_new_candidates, adaptive_max_analysts=adaptive_max_analysts)`.
- [ ] **Step 4: Run → PASS**; re-run the full `tests/dq/hermes/test_h4_focus_roster.py` to confirm no regression.
- [ ] **Step 5: Commit** — `feat(olympus): thread adaptive budget through compute_focus_roster (Stage 2, #1017)`.

---

### Task 6: Wire the budget controller into `_h4_node` + log the decision

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/phases/h4_opportunity_screener.py` (`_h4_node`)
- Test: `tests/dq/hermes/test_h4_focus_roster.py` (or the chain test)

**Interfaces:**
- Consumes: `assess_budget` (Task 3).
- `_h4_node` reads the static cap once (`int(os.environ.get("ATLAS_MAX_ANALYSTS", "0") or "0")`), calls `budget, explore_floor, assessment = assess_budget(state, client, static_cap=static_cap)`, and passes `adaptive_max_analysts=budget, min_new_candidates=explore_floor` into `compute_focus_roster`. The existing `compute_focus_roster_excluded` + logging stay; add the regime to the H4 log line.

- [ ] **Step 1: Write the failing test** — assert that when `assess_budget` is monkeypatched to return a tight budget, `_h4_node` (run via the built phase node) produces a capped roster; and when it returns the static fallback, behavior matches today. (Construct a `HermesState` with a small watchlist + a fake client; patch `h4_opportunity_screener.assess_budget`.)

```python
# append to tests/dq/hermes/test_h4_focus_roster.py
@pytest.mark.unit
def test_h4_node_applies_adaptive_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.olympus.hermes.phases import h4_opportunity_screener as h4
    monkeypatch.setenv("HERMES_HELD_GATE", "off")
    monkeypatch.setattr(h4, "assess_budget", lambda *a, **k: (1, 0, None))
    node = h4.build_h4_opportunity_screener(client=None).nodes[0].run
    # Build a minimal HermesState with watchlist of 3, no held, no thesis map.
    state = _make_min_hermes_state(watchlist=["AAA", "BBB", "CCC"])  # helper in this file
    out = node(state)
    roster = out["phase_hermes"].focus_roster
    assert len(roster) == 1  # adaptive budget=1 applied
```

(If a `_make_min_hermes_state` helper does not yet exist, add one mirroring the construction in the existing simulator/chain tests; keep it minimal.)

- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** the `_h4_node` wiring + import `assess_budget`; extend the existing `logger.info` H4 line (or add one) to include `assessment.regime` when present.
- [ ] **Step 4: Run → PASS**; then run the integration path: `.venv/bin/python -m pytest tests/dq/atlas/test_simulator_gates.py tests/dq/hermes/test_chain_atlas_then_hermes.py -q` to confirm the daily/quiet paths still pass (budget controller fail-soft → static cap when the sim client lacks VIX/breadth data).
- [ ] **Step 5: Commit** — `feat(olympus): H4 applies regime-adaptive dispatch budget (Stage 2, #1017)`.

---

### Task 7: Document the regime-adaptive budget

**Files:**
- Modify: `digiquant/src/digiquant/olympus/hermes/docs/ARCHITECTURE.md` (H4 row/section)

- [ ] **Step 1:** Update the H4 description to note: focus roster is capped by a regime-adaptive budget (`budget_controller.assess_budget`) that tightens dispatch in stress/high-correlation regimes and falls back to `ATLAS_MAX_ANALYSTS` when signals are unavailable; document the `stress/neutral/dispersion` taxonomy, the cost-safe invariant (`B ≤ cap`), and the env knobs (`ATLAS_MAX_ANALYSTS`, `ATLAS_BUDGET_STRESS_FLOOR`, `ATLAS_BUDGET_DISPERSION_HI`).
- [ ] **Step 2:** Run `make doc-check` (validate internal links). Expected: PASS.
- [ ] **Step 3: Commit** — `docs(olympus): document regime-adaptive H4 budget (Stage 2, #1017)`.

---

## Self-Review

- **Spec coverage:** regime classifier ✓ (Task 2, signals = VIX term + breadth + dispersion per spec §"Budget controller"; dispersion sourced free from `price_deltas` rather than a new metric, matching spec's "resolve exact signal set during planning"); adaptive `B` ✓; explore/exploit split ✓ (via `explore_floor`→`min_new`); applied at the real choke point `compute_focus_roster`→`capped_tickers` (spec build-sequence Stage 2, NOT the test-only `build_h5_asset_analyst`) ✓; fail-soft + static fallback ✓ (spec error-handling); instrumentation/logging ✓. **Deferred (explicit, per spec):** increasing `B` above the cap in dispersion regimes (cost-gated), a dedicated cross-asset dispersion metric, and the `dispatch_outcomes` feedback table (Stage 4).
- **Placeholder scan:** none — every step has concrete code or an exact command. The one helper (`_make_min_hermes_state`) is flagged as "add if absent, mirror existing tests".
- **Type consistency:** `assess_budget` returns `(int, int, RegimeAssessment | None)` used identically in Task 6; `adaptive_max_analysts: int | None` consistent across `capped_tickers` (Task 4) and `compute_focus_roster` (Task 5); `RegimeLabel` literal consistent across Tasks 1–3.
- **Backward-compat check:** `adaptive_max_analysts=None` path is byte-identical to today; Task 4 Step 4 + Task 5 Step 4 re-run existing cap tests to prove it.

## Execution Handoff

Plan saved. **Recommended: subagent-driven-development** — fresh implementer per task, task review (spec + quality) after each, broad final review. Tasks 1–3 are mechanical (clear specs, isolated module) → cheap model; Tasks 4–6 touch shared/wired code → standard model + the existing-test regression gate; final whole-branch review on the most capable model (it changes a dispatch-budget path).
