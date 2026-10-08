"""A dead macro feed must not pass the refresh gate silently (DIG-694 follow-up).

Context. ``scripts/refresh_market_data_r2.py`` makes macro fetches fail-soft: a
per-series vendor failure becomes a ``history-only`` outcome so the previous
generation keeps serving. That is the right default. ``SLOW_CADENCES``
(``monthly``/``quarterly``) then *exempts* those ``history-only`` outcomes from
marking the run stale, because a slow series legitimately publishes nothing for
weeks (#4621).

The hole this file pins: the exemption is keyed on the *cadence of the series*,
not on *how many* series failed. If the whole macro leg dies -- every monthly
series returning ``history-only`` -- then every outcome is exempt, ``failed`` is
empty, and the run reports ``stale=False`` with exit 0. A total macro outage
then looks exactly like a quiet week for a slow series. The macro panel is then
frozen at the last good seal while the run claims it is fresh.

That is the failure mode DIG-694's own author warned about: "a silent empty
dataset" rather than a clean failure.

DIG-1137 adds the second half of the same hole. The guard above reads ``mode``,
and there is a shape where the vendor keeps *answering* while the panel stops
advancing, so the run lands on ``up-to-date`` -- a success mode the soft-fail
reduction never sees. ``staleness_gate`` cannot cover it either, because healthy
price tickers pin ``max(as_of)`` at the run date. The panel is frozen at the same
place, with ``stale=False`` and exit 0. So ``_macro_as_of_stale`` measures each
macro series' ``as_of`` against its own cadence window and names anything past
it. The section at the end of this file pins that guard, including the fuse: a
monthly seal 34 days old is legitimately fresh and must stay quiet.

The reachable shape is narrow, and pinning it precisely matters. A frozen
in-window panel needs rows that survive ``_fetch_macro``'s ``<= run + 1`` clamp
yet are dropped by ``refresh_macro_series``' settled-close ``<= run`` clamp --
so, since ``obs_date`` is a whole date, every such row must be dated exactly
``run + 1``. Anything later is dropped at fetch time and becomes an empty live
window (``history-only``, the leg guard's case); anything at or before ``run``
survives into the panel and genuinely advances it. And only ``MODE_UP_TO_DATE``
can trip the guard at all: ``MODE_INCREMENTAL`` and ``MODE_FULL_REPULL`` both
derive their ``as_of`` from rows already clamped ``<= run``, so their top row is
by construction both ``<= run`` and inside the window.

How this stays a real test rather than a stub. It does not reimplement the
logic. It parses ``refresh_market_data_r2.py`` with :mod:`ast`, extracts the
*actual* source of ``_outcome``, ``_slow_macro_exempt_ids``, ``_macro_leg_dead``,
``_live_window_days`` and ``_macro_as_of_stale`` plus the real
``_SOFT_FAIL_MODES`` / ``_MACRO_SUCCESS_MODES`` / ``MODE_*`` / ``_CADENCE_*``
constants, and executes them. The second half then reads the ``failed = [...]``
comprehension out of ``main``'s AST and runs *that* with ``main``'s own
bindings -- an ``import`` cannot reach the comprehension, because it lives
inside ``main`` rather than at module scope, and inlining a copy of it here
would be the paraphrase this file exists to avoid. The DIG-1137 guard is wired
as ``failed += _macro_as_of_stale(...)``, so the same approach finds the
``AugAssign`` and runs its right-hand side. The exempt set for the
realistic shapes comes from the *shipped* ``macro_series.yaml`` through the
real ``_resolve_macro_specs``, so the fixtures cannot drift away from the
panel the cron actually runs (a quarterly ``GDPC1`` fixture, for instance,
would be testing a series the manifest dropped).

Run from the repo root::

    pytest tests/scripts/test_macro_death_is_not_silent.py -m unit
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "refresh_market_data_r2.py"
MACRO_YAML = (
    REPO_ROOT / "digiquant" / "src" / "digiquant" / "research" / "config" / "macro_series.yaml"
)

pytestmark = pytest.mark.unit

#: Executed verbatim out of the source file, so ``r2`` below is real repo code.
_EXTRACTED_FUNCS = (
    "_outcome",
    "_slow_macro_exempt_ids",
    "_macro_leg_dead",
    # DIG-1137: the per-series ``as_of`` age guard, plus the window table it
    # measures against -- so the predicate below runs on the real cadence bounds
    # rather than a copy of them that can drift.
    "_live_window_days",
    "_macro_as_of_stale",
)
_EXTRACTED_CONSTS = (
    "_SOFT_FAIL_MODES",
    "MODE_HISTORY_ONLY",
    "MODE_ERROR",
    # Only used to build the healthy half of a realistic run.
    "MODE_UP_TO_DATE",
    "MODE_INCREMENTAL",
    "MODE_FULL_REPULL",
    # `_macro_as_of_stale` reads the success set and both window constants.
    "_MACRO_SUCCESS_MODES",
    "_CADENCE_WINDOW_DAYS",
    "LIVE_WINDOW_DAYS",
    # `_slow_macro_exempt_ids` reads this at call time, so it must come along.
    "SLOW_CADENCES",
)

#: Every age fixture below is measured against this run date.
RUN = "2026-09-23"

#: 145 calendar days before ``RUN``: outside the 120d monthly window, inside the
#: 240d quarterly one. A vendor that stopped publishing a monthly series this
#: long ago has left the panel frozen, not slow.
RETIRED_MONTHLY_SEAL = "2026-05-01"


@pytest.fixture(scope="module")
def shipped_specs() -> list[tuple[str, str, str | None]]:
    """The real ``(source, series, cadence)`` specs of the shipped macro manifest.

    Imported, not hand-written: ``pytest.ini`` puts ``digiquant/src`` on
    ``pythonpath`` and the sibling ``test_refresh_market_data_r2_macro.py``
    already imports this script, so a fixture naming series the manifest no
    longer carries would be a fixture for a panel that does not exist.
    """
    spec = importlib.util.spec_from_file_location("refresh_market_data_r2_r1", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    specs = module._resolve_macro_specs([], str(MACRO_YAML))
    monthly = [s for s in specs if (s[2] or "").lower() == "monthly"]
    # The panel this guard exists for must keep existing: a total death of it is
    # the bug. If the manifest ever ships fewer than two monthly series the
    # `> 1` floor can no longer be exercised and the premise needs revisiting.
    assert len(monthly) >= 2, f"expected a multi-series monthly panel, got {monthly}"
    return specs


@pytest.fixture(scope="module")
def r2() -> dict[str, Any]:
    """Exec the real pure helpers from ``refresh_market_data_r2.py``.

    Extracted rather than imported because the ``failed = [...]`` reduction
    lives inside ``main`` and cannot be reached by an ``import``; the helpers
    are extracted with it so the comprehension runs against the same code.
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    keep: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in _EXTRACTED_FUNCS:
            keep.append(node)
        elif isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if any(name in _EXTRACTED_CONSTS for name in targets):
                keep.append(node)
        elif isinstance(node, ast.AnnAssign):
            # `_CADENCE_WINDOW_DAYS: dict[str, int] = {...}` is annotated, not a
            # plain Assign. Without this branch the age guard would execute
            # against an unbound window table and every predicate below would
            # error rather than fail on a real assertion.
            if isinstance(node.target, ast.Name) and node.target.id in _EXTRACTED_CONSTS:
                keep.append(node)

    found_funcs = {n.name for n in keep if isinstance(n, ast.FunctionDef)}
    missing = set(_EXTRACTED_FUNCS) - found_funcs
    assert not missing, f"{SCRIPT.name} no longer defines {sorted(missing)}; update this guard"

    namespace: dict[str, Any] = {"Any": Any, "frozenset": frozenset, "datetime": datetime}
    # Executing this repository's own pure helpers, by design.
    exec(
        compile(ast.Module(body=keep, type_ignores=[]), str(SCRIPT), "exec"),
        namespace,
    )
    return namespace


def _failed_comprehension() -> ast.ListComp:
    """Return the ``failed = [...]`` comprehension from ``main``'s real AST."""
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    for node in ast.walk(main):
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            if "failed" in targets and isinstance(node.value, ast.ListComp):
                return node.value
    raise AssertionError(f"{SCRIPT.name} no longer assigns `failed = [...]`; update this guard")


def _real_failed(r2: dict[str, Any], outcomes: list[dict], macro_specs: list[tuple]) -> list[dict]:
    """Execute ``main``'s *actual* ``failed = [...]`` comprehension.

    The comprehension is read out of ``main``'s AST and run with the same
    bindings ``main`` has at that point (``outcomes``, ``exempt``, the mode
    constants). Nothing about the reduction is reimplemented here, so this is
    the repository's own staleness logic, not a paraphrase of it.
    """
    source = ast.unparse(_failed_comprehension())
    scope: dict[str, Any] = {
        "outcomes": outcomes,
        "exempt": r2["_slow_macro_exempt_ids"](macro_specs),
        **r2,
    }
    # Running this repo's own expression, not a paraphrase of it.
    exec(f"_result = {source}", scope)
    return scope["_result"]


def _age_addition() -> ast.expr:
    """Return the ``failed += _macro_as_of_stale(...)`` expression from ``main``.

    The age guard is additive by construction, so it cannot live inside the
    comprehension: folding it in would let it share the ``exempt`` clause and
    quietly become conditional on the cadence exemption it exists to sit beside.
    Reading it back out of ``main``'s AST is what keeps that structural claim
    testable rather than a comment.
    """
    tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
    main = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "main")
    for node in ast.walk(main):
        if (
            isinstance(node, ast.AugAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "failed"
            and isinstance(node.op, ast.Add)
        ):
            return node.value
    raise AssertionError(
        f"{SCRIPT.name} no longer adds the age guard to `failed`; a macro panel "
        "frozen behind a vendor that keeps answering reports itself fresh again. "
        "Re-wire `failed += _macro_as_of_stale(outcomes, macro_specs, run)`."
    )


def _real_failed_with_age(
    r2: dict[str, Any],
    outcomes: list[dict],
    macro_specs: list[tuple],
    run: str,
) -> list[dict]:
    """``main``'s whole reduction: the DIG-694 comprehension *and* the age addition.

    ``run`` is required rather than defaulted. The guard is a comparison against
    the run date, so a fixture that does not state its run date is not asserting
    anything about age -- it is asserting whatever the default happened to be.
    """
    failed = _real_failed(r2, outcomes, macro_specs)
    scope: dict[str, Any] = {
        "failed": failed,
        "outcomes": outcomes,
        "macro_specs": macro_specs,
        "run": run,
        **r2,
    }
    exec(f"failed += {ast.unparse(_age_addition())}", scope)
    return scope["failed"]


def test_history_only_is_a_soft_fail_mode(r2: dict[str, Any]) -> None:
    """Precondition: a vendor failure is recorded as a soft fail, not an error."""
    assert r2["MODE_HISTORY_ONLY"] in r2["_SOFT_FAIL_MODES"]
    assert r2["MODE_ERROR"] in r2["_SOFT_FAIL_MODES"]


def test_slow_exempt_ids_only_covers_slow_cadences(r2: dict[str, Any]) -> None:
    """The exemption is cadence-scoped; daily and unspecified series are not exempt."""
    assert r2["_slow_macro_exempt_ids"]([("fred", "M2SL", "monthly")]) == {"fred__M2SL"}
    assert r2["_slow_macro_exempt_ids"]([("fred", "GDPC1", "quarterly")]) == {"fred__GDPC1"}
    assert r2["_slow_macro_exempt_ids"]([("fred", "DGS10", "daily")]) == set()
    assert r2["_slow_macro_exempt_ids"]([("fred", "X", None)]) == set()


def test_single_slow_series_quiet_week_is_exempt(r2: dict[str, Any]) -> None:
    """The #4621 intent holds: ONE slow series sitting out is not an outage."""
    specs = [("fred", "M2SL", "monthly")]
    outcomes = [r2["_outcome"]("fred__M2SL", r2["MODE_HISTORY_ONLY"], note="empty live window")]
    assert _real_failed(r2, outcomes, specs) == []


def test_error_mode_on_slow_series_still_fails_loud(r2: dict[str, Any]) -> None:
    """A hard error on a slow cadence is never exempt -- the escape hatch is narrow."""
    specs = [("fred", "M2SL", "monthly")]
    outcomes = [r2["_outcome"]("fred__M2SL", r2["MODE_ERROR"], note="live fetch raised")]
    assert _real_failed(r2, outcomes, specs) == outcomes


def _healthy_run(r2: dict[str, Any], n_prices: int = 99) -> list[dict]:
    """Outcomes of a *healthy* run: prices and FX landed, only the macro leg failed.

    Every other fixture in this file is all-silent or one-off-from-silent, which
    is not a shape a real run has. A wrong ``_macro_leg_dead`` therefore slips
    through them; this shape is what the cron actually produces.
    """
    outcomes = [
        r2["_outcome"](f"T{i}", r2["MODE_UP_TO_DATE"], as_of="2026-09-23", rows=250)
        for i in range(n_prices)
    ]
    outcomes += [
        r2["_outcome"](sym, r2["MODE_UP_TO_DATE"], as_of="2026-09-23", rows=250)
        for sym in ("yahoo__EURUSD=X", "yahoo__USDJPY=X", "yahoo__GBPUSD=X", "yahoo__AUDUSD=X")
    ]
    return outcomes


def test_total_macro_feed_death_fails_the_leg(
    r2: dict[str, Any], shipped_specs: list[tuple[str, str, str | None]]
) -> None:
    """THE FINDING, inverted: a total macro outage now fails loud.

    The shipped manifest's monthly series all returning ``history-only`` at once,
    alongside a healthy price and FX book, is the whole macro leg dead rather
    than a release calendar. The per-series #4621 exemption must not swallow it:
    the run reports ``stale=True`` and exits 1 naming every dead macro id.
    """
    exempt = r2["_slow_macro_exempt_ids"](shipped_specs)
    outcomes = _healthy_run(r2)
    outcomes += [
        r2["_outcome"](name, r2["MODE_HISTORY_ONLY"], note="fetch failed, serving history")
        for name in sorted(exempt)
    ]

    failed = _real_failed(r2, outcomes, shipped_specs)

    assert failed != [], "a total macro-feed outage is silent again: the whole-leg guard is gone"
    assert {o["ticker"] for o in failed} == exempt, (
        "every dead macro series should be named, alongside the rest of the universe still fresh"
    )


def test_a_partial_slow_leg_still_runs_quiet(r2: dict[str, Any]) -> None:
    """The other side of the guard: a *subset* of slow series is not an outage.

    ``_fetch_macro`` builds a fresh client per series, so a rate-limit blip
    silences an arbitrary subset of the panel. A majority rule would fail the
    cron on a healthy panel, which is how operators learn to ignore the gate.
    Unanimity is what makes the guard safe to alert on.
    """
    specs = [
        ("fred", "M2SL", "monthly"),
        ("fred", "PCEPI", "monthly"),
        ("fred", "UNRATE", "monthly"),
        ("fred", "CPIAUCSL", "monthly"),
    ]
    outcomes = _healthy_run(r2)
    # One outcome per spec, as `main` emits -- including the slow series that
    # came back fine. Without those the fixture has no healthy series *inside*
    # the exempt set, which is a shape no real run has.
    outcomes += [
        r2["_outcome"](name, r2["MODE_HISTORY_ONLY"], note="fetch failed: rate_limited")
        for name in ("fred__M2SL", "fred__PCEPI")
    ]
    outcomes += [
        r2["_outcome"](name, r2["MODE_UP_TO_DATE"], as_of="2026-09-23", rows=8)
        for name in ("fred__UNRATE", "fred__CPIAUCSL")
    ]

    assert _real_failed(r2, outcomes, specs) == []


def test_slow_cadence_failure_alongside_a_daily_failure_still_fails_loud(
    r2: dict[str, Any],
) -> None:
    """A non-exempt soft fail already makes the run stale, macro leg or not."""
    specs = [("fred", "M2SL", "monthly"), ("fred", "DGS10", "daily")]
    outcomes = [
        r2["_outcome"]("fred__M2SL", r2["MODE_HISTORY_ONLY"], note="empty live window"),
        r2["_outcome"]("fred__DGS10", r2["MODE_HISTORY_ONLY"], note="fetch failed"),
    ]

    failed = _real_failed(r2, outcomes, specs)

    assert [o["ticker"] for o in failed] == ["fred__DGS10"], (
        "a daily history-only is never exempt; the macro aggregate must not change that"
    )


def test_main_run_exits_nonzero_and_names_the_whole_leg(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end through ``main()``: the exit code and the published artifact.

    Every other test in this file executes the reduction with a namespace it
    builds itself, including its own ``exempt`` set. That is deliberate -- the
    comprehension is not reachable by import -- but it means none of them
    exercise ``main``'s own ``exempt`` binding. This one pins the whole-leg
    shape end-to-end: the exit code the workflow alerts on, and the ``failed``
    list an operator debugs from.
    """
    # Imported inside the test so this file stays runnable on its own; the
    # sibling already imports the real script through the same importlib seam.
    from tests.scripts.test_market_data_restatement_4621 import (
        HIST,
        FakeStore,
        _run_main,
        price_frame,
        price_rows,
    )

    store = FakeStore()
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(HIST))
    # Four monthly series, all dead, plus one daily macro series, also dead --
    # the shape that must name *both* the macro leg and the daily failure.
    specs = [("fred", s, "monthly") for s in ("M2SL", "PCEPI", "UNRATE", "CPIAUCSL")]
    specs.append(("fred", "DGS10", None))
    for source, series, _cadence in specs:
        store.macros[(source, series)] = [
            {"source": source, "series_id": series, "obs_date": "2026-07-01", "value": 84.0},
        ]
        store.macro_empty.add((source, series))

    rc, artifact = _run_main(monkeypatch, tmp_path, store, specs, "2026-09-23")

    assert rc == 1, "a dead macro leg must exit non-zero so the workflow alerts"
    assert artifact["stale"] is True
    assert set(artifact["failed"]) == {
        f"fred__{s}" for s in ("M2SL", "PCEPI", "UNRATE", "CPIAUCSL", "DGS10")
    }, "the artifact must name every dead macro series, not just the daily one"


def test_main_run_keeps_the_daily_leg_unexempt(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exemption is cadence-scoped, end to end: a daily dead series still fails.

    This is not a restatement of
    ``test_market_data_restatement_4621::test_slow_macro_history_only_does_not_fail_run``
    (that one pins the quiet side, and it is what catches ``main``'s ``exempt``
    binding collapsing to an empty set). This pins the opposite direction.

    The fixture is deliberately uneven: two monthly series dead, one *daily*
    series dead, and a second daily series that came back fine. If the exemption
    over-reached to every macro id, the healthy series would join the exempt set,
    unanimity over that set would fail to hold, and the two dead daily series
    would be silently exempt -- the run would exit 0 while a daily macro feed
    was dead. Uneven is what makes the mutant visible; an all-dead panel hides it.
    """
    from tests.scripts.test_market_data_restatement_4621 import (
        HIST,
        FakeStore,
        _run_main,
        price_frame,
        price_rows,
    )

    store = FakeStore()
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(HIST))
    specs = [
        ("fred", "M2SL", "monthly"),
        ("fred", "PCEPI", "monthly"),
        ("fred", "DGS10", None),
        ("fred", "DFII10", None),
    ]
    for source, series, _cadence in specs:
        store.macros[(source, series)] = [
            {"source": source, "series_id": series, "obs_date": "2026-07-01", "value": 84.0},
        ]
    # Three of the four are dead; DFII10 answers normally.
    for series in ("M2SL", "PCEPI", "DGS10"):
        store.macro_empty.add(("fred", series))
    store.macro_lives[("fred", "DFII10")] = [
        {"source": "fred", "series_id": "DFII10", "obs_date": "2026-09-20", "value": 1.5},
    ]

    rc, artifact = _run_main(monkeypatch, tmp_path, store, specs, "2026-09-23")

    assert rc == 1, "a dead daily macro series must fail the run whatever its neighbours do"
    assert "fred__DGS10" in artifact["failed"], (
        "the daily series is not cadence-exempt and must be named"
    )
    assert "fred__DFII10" not in artifact["failed"]


def test_stale_comprehension_keeps_a_whole_leg_guard() -> None:
    """The aggregate is *called* from the comprehension, not computed beside it.

    ``_macro_leg_dead`` could be hoisted above the comprehension and left
    unwired -- every behavioural test above would then pass while a whole-leg
    outage went unreported again. Behavioural coverage cannot see that; the
    call site can.
    """
    comp = _failed_comprehension()
    calls = [ast.unparse(n.func) for n in ast.walk(comp) if isinstance(n, ast.Call)]
    clauses = [ast.unparse(cond) for gen in comp.generators for cond in gen.ifs]
    joined = " ".join(clauses)

    assert "exempt" in joined, f"expected the cadence exemption, got {clauses}"
    assert "_macro_leg_dead" in calls, (
        "the `failed` comprehension no longer calls _macro_leg_dead: a whole-leg "
        "macro outage would be reported as a fresh run. Re-wire the aggregate "
        f"guard. Calls found: {calls}"
    )


# -- DIG-1137: the per-series `as_of` age guard -------------------------------
#
# `_macro_leg_dead` above reads `mode`. The hole this section pins is the one it
# structurally cannot see: a macro vendor that stops *publishing* while keeping
# *answering*. The live fetch succeeds, finds nothing newer than the seal, and
# returns `up-to-date` — not a soft fail, so nothing enters `failed`, and the
# reduction reports `stale=False` with exit 0 while the panel serves a months-old
# seal. `staleness_gate` is no help: it takes the newest `as_of` across all
# datasets, and the healthy price book pins that at the run date.


def test_the_frozen_panel_shape_is_reachable_through_the_real_fetch(r2: dict[str, Any]) -> None:
    """The finding's shape is built here by real code, not asserted as hypothetical.

    The obvious way for a series to freeze -- an empty live window -- reports
    ``history-only``, which the cadence exemption deliberately forgives and
    ``_macro_leg_dead`` can count. The shape that slips between them is a live
    window whose rows are all dated *after* the run: ``rows`` is truthy so no
    soft fail fires, the ``<= run`` filter empties ``live``, ``new_rows`` is
    empty, and the series reports ``up-to-date`` carrying its old seal.

    Building it through ``refresh_macro_series`` is what keeps the fixtures below
    honest: an age guard tested only against invented outcomes could pass while
    describing a state the script cannot produce.
    """
    from scripts.refresh_market_data_r2 import refresh_macro_series
    from tests.scripts.test_market_data_restatement_4621 import FakeStore

    store = FakeStore()
    store.macros[("fred", "M2SL")] = [
        {"source": "fred", "series_id": "M2SL", "obs_date": RETIRED_MONTHLY_SEAL, "value": 21.0},
    ]
    store.macro_lives[("fred", "M2SL")] = [
        {"source": "fred", "series_id": "M2SL", "obs_date": "2026-09-24", "value": 22.0},
    ]

    outcome = refresh_macro_series(
        "fred", "M2SL", store, store.manifest, as_of=RUN, cadence="monthly"
    )

    assert outcome["mode"] == r2["MODE_UP_TO_DATE"], (
        f"expected the frozen-panel shape to be up-to-date, got {outcome}"
    )
    assert outcome["as_of"] == RETIRED_MONTHLY_SEAL
    specs = [("fred", "M2SL", "monthly")]
    assert _real_failed(r2, [outcome], specs) == [], (
        "precondition: the DIG-694 reduction alone cannot see this outcome"
    )
    assert _real_failed_with_age(r2, [outcome], specs, RUN) == [outcome], (
        "the age guard is the only thing that sees a success-mode outcome sealed "
        "past its cadence window"
    )


def test_a_retired_macro_series_fails_loud_though_the_fetch_worked(r2: dict[str, Any]) -> None:
    """THE FINDING, inverted: a macro series frozen past its window now fails loud.

    Two monthly series whose vendor stopped publishing four months ago, a healthy
    price and FX book alongside them. Nothing here is a soft fail and nothing is
    ``history-only``, so before DIG-1137 the run reported itself fresh and the
    artifact named nothing.
    """
    specs = [("fred", "M2SL", "monthly"), ("fred", "PCEPI", "monthly")]
    outcomes = _healthy_run(r2)
    outcomes += [
        r2["_outcome"](name, r2["MODE_UP_TO_DATE"], as_of=RETIRED_MONTHLY_SEAL, rows=8)
        for name in ("fred__M2SL", "fred__PCEPI")
    ]

    failed = _real_failed_with_age(r2, outcomes, specs, RUN)

    assert {o["ticker"] for o in failed} == {"fred__M2SL", "fred__PCEPI"}, (
        "every macro series sealed past its own cadence window must be named, "
        f"alongside the universe still fresh; got {[o['ticker'] for o in failed]}"
    )
    assert {o["mode"] for o in failed} == {r2["MODE_UP_TO_DATE"]}, (
        "the guard must name a mode that is not a soft fail -- that is the hole"
    )


def test_a_slow_series_inside_its_window_is_still_quiet(r2: dict[str, Any]) -> None:
    """The fuse: 34 days is a quiet month, not a dead panel.

    This is the shape the issue was filed against, and it is *not* a defect: a
    monthly series holding a 34-day-old seal is comfortably inside its 120-day
    window, and #4621 exists so that operators are not paged for it. A guard
    keyed on ``as_of != run_date`` instead of on age would page here.
    """
    specs = [("fred", "M2SL", "monthly")]
    outcomes = _healthy_run(r2) + [
        r2["_outcome"]("fred__M2SL", r2["MODE_UP_TO_DATE"], as_of="2026-08-20", rows=8)
    ]

    assert _real_failed_with_age(r2, outcomes, specs, RUN) == []


def test_a_full_repull_of_a_retired_series_is_judged_too(r2: dict[str, Any]) -> None:
    """Bootstrap of a series the vendor dropped reports success; age still judges it.

    The other reachable shape. ``_fetch_full`` clamps only to the run date, not
    to the cadence window, so a first seal of a dead series lands on the newest
    observation that series ever had -- ``full-repull``, a success mode, no soft
    fail, and older than any window. A bootstrap that succeeds is exactly when
    the operator most needs to be told the panel it just sealed is dead.
    """
    specs = [("fred", "GDPC1", "quarterly")]
    outcomes = _healthy_run(r2) + [
        r2["_outcome"](
            "fred__GDPC1",
            r2["MODE_FULL_REPULL"],
            as_of="2025-06-01",
            rows=300,
            note="bootstrap",
        )
    ]

    assert [o["ticker"] for o in _real_failed_with_age(r2, outcomes, specs, RUN)] == ["fred__GDPC1"]


def test_the_cadence_decides_the_window_not_one_flat_bound(r2: dict[str, Any]) -> None:
    """Same age, two cadences, two verdicts -- a flat 45d bound would page a quarterly.

    145 days is dead for a monthly series and unremarkable for a quarterly one,
    which publishes four observations a year. The bound has to come from
    ``_CADENCE_WINDOW_DAYS`` or the guard pages on healthy quarterly panels every
    winter.
    """
    outcomes = _healthy_run(r2) + [
        r2["_outcome"](name, r2["MODE_UP_TO_DATE"], as_of=RETIRED_MONTHLY_SEAL, rows=8)
        for name in ("fred__M2SL", "fred__GDPC1")
    ]
    monthly = [("fred", "M2SL", "monthly"), ("fred", "GDPC1", "quarterly")]

    failed = _real_failed_with_age(r2, outcomes, monthly, RUN)

    assert [o["ticker"] for o in failed] == ["fred__M2SL"], (
        "only the series whose own window the seal outlives may be named"
    )


def test_the_window_boundary_is_inclusive(r2: dict[str, Any]) -> None:
    """Exactly at the window is fresh; one day past it is not.

    ``>`` versus ``>=`` is the difference between a guard that measures the
    window and one that pages on the last legal day of it. 120 days is
    2026-05-26 for a 2026-09-23 run.
    """
    specs = [("fred", "M2SL", "monthly")]

    def _named(seal: str) -> list[str]:
        outcomes = [r2["_outcome"]("fred__M2SL", r2["MODE_UP_TO_DATE"], as_of=seal, rows=8)]
        return [o["ticker"] for o in _real_failed_with_age(r2, outcomes, specs, RUN)]

    assert _named("2026-05-26") == [], "the 120th day is still inside the window"
    assert _named("2026-05-25") == ["fred__M2SL"]


def test_an_undeclared_cadence_is_judged_at_the_daily_window(r2: dict[str, Any]) -> None:
    """``cadence=None`` falls to the narrowest reading, not to leniency.

    ``--macro-series fred:DGS10`` and every Yahoo FX series are declared with no
    cadence at all. Judging them by the slowest window in the table would let a
    dead daily series sit quiet for eight months.
    """
    specs = [("fred", "DGS10", None)]

    def _named(seal: str) -> list[str]:
        outcomes = [r2["_outcome"]("fred__DGS10", r2["MODE_UP_TO_DATE"], as_of=seal, rows=250)]
        return [o["ticker"] for o in _real_failed_with_age(r2, outcomes, specs, RUN)]

    assert _named("2026-08-09") == [], "45 days is inside the daily window"
    assert _named("2026-08-08") == ["fred__DGS10"]


def test_soft_fail_modes_are_left_to_the_leg_guard(r2: dict[str, Any]) -> None:
    """Age does not second-guess ``_macro_leg_dead``'s territory.

    A ``history-only`` series has an *empty live window* at any age, young or
    old, so its age cannot separate a quiet release cycle from a dead feed --
    the window already did, and the #4621 exemption already forgives the quiet
    case. Re-judging those modes here would fail every monthly series that sits
    out a month, which is precisely the false page #4621 removed.
    """
    specs = [("fred", "M2SL", "monthly"), ("fred", "PCEPI", "monthly")]
    dead = [
        r2["_outcome"](name, r2["MODE_HISTORY_ONLY"], as_of=RETIRED_MONTHLY_SEAL, note="empty")
        for name in ("fred__M2SL", "fred__PCEPI")
    ]

    # Both silent at once: the leg guard fires, on unanimity -- never on age,
    # though these seals are 145 days old and every window in the table.
    failed = _real_failed_with_age(r2, _healthy_run(r2) + dead, specs, RUN)
    assert {o["ticker"] for o in failed} == {"fred__M2SL", "fred__PCEPI"}
    assert {o["mode"] for o in failed} == {r2["MODE_HISTORY_ONLY"]}

    # One of them answering is a #4621 quiet month, at the same 145-day age.
    partial = [dead[0], r2["_outcome"]("fred__PCEPI", r2["MODE_UP_TO_DATE"], as_of=RUN, rows=8)]
    assert _real_failed_with_age(r2, _healthy_run(r2) + partial, specs, RUN) == []


def test_an_undated_outcome_is_skipped_not_guessed(r2: dict[str, Any]) -> None:
    """No ``as_of`` means nothing to measure, and the guard must not invent a date.

    Treating a blank as epoch would page on any outcome that omits it; the
    fetch branches that do omit it all report a soft fail, which is judged on
    its own terms.
    """
    outcomes = _healthy_run(r2) + [
        r2["_outcome"]("fred__M2SL", r2["MODE_UP_TO_DATE"], as_of="", rows=0)
    ]

    assert _real_failed_with_age(r2, outcomes, [("fred", "M2SL", "monthly")], RUN) == []


def test_price_outcomes_are_not_the_macro_leg_business(r2: dict[str, Any]) -> None:
    """A price ticker is not judged against a macro cadence window.

    ``outcomes`` interleaves price tickers with macro series, so a guard that
    read every outcome would either page on a stale ticker under a cadence
    borrowed from a same-named macro id, or crash on the lookup. Price staleness
    is ``staleness_gate``'s job, and it already covers it.
    """
    outcomes = [
        r2["_outcome"]("SPY", r2["MODE_UP_TO_DATE"], as_of=RETIRED_MONTHLY_SEAL, rows=250),
        r2["_outcome"]("fred__M2SL", r2["MODE_UP_TO_DATE"], as_of=RUN, rows=8),
    ]

    assert _real_failed_with_age(r2, outcomes, [("fred", "M2SL", "monthly")], RUN) == []


def test_the_age_guard_only_adds_names(r2: dict[str, Any]) -> None:
    """It never clears a name the leg guard already produced, and never clears a run.

    The two guards are orthogonal, so the age addition is monotone: a run the
    leg guard already failed must keep every name it had. If a later edit made
    the addition conditional on the run being otherwise fresh, this fails.
    """
    specs = [
        ("fred", "M2SL", "monthly"),
        ("fred", "PCEPI", "monthly"),
        ("fred", "DGS10", None),
        ("fred", "GDP", "daily"),
    ]
    outcomes = _healthy_run(r2) + [
        r2["_outcome"]("fred__M2SL", r2["MODE_HISTORY_ONLY"], note="fetch failed"),
        r2["_outcome"]("fred__PCEPI", r2["MODE_HISTORY_ONLY"], note="fetch failed"),
        r2["_outcome"]("fred__DGS10", r2["MODE_ERROR"], note="live fetch raised"),
        r2["_outcome"]("fred__GDP", r2["MODE_UP_TO_DATE"], as_of=RETIRED_MONTHLY_SEAL, rows=8),
    ]

    failed = _real_failed_with_age(r2, outcomes, specs, RUN)
    named = {o["ticker"] for o in failed}

    assert {"fred__DGS10", "fred__M2SL", "fred__PCEPI", "fred__GDP"} <= named, (
        f"the leg guard's names must survive the age addition; got {sorted(named)}"
    )


def test_main_run_exits_nonzero_for_a_retired_macro_series(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End to end through ``main()``: the exit code and the published artifact.

    The other tests in this section execute the reduction against a namespace
    they build themselves, which means none of them exercise ``main``'s own
    ``macro_specs``/``run`` bindings or the ``stale`` flag the workflow reads.
    This one pins the operator-facing shape of the whole feature.

    The panel is Yahoo FX rather than FRED, and that is load-bearing: on a
    bootstrap ``refresh_macro_series``'s ``_fetch_full`` fetches FRED straight
    from the Gloomberb client and never asks the store, so a FRED first seal
    cannot be faked at all and this test would silently hit the network. Yahoo
    goes through ``store.fetch_macro_full``, which is the store-owned seam.
    Yahoo specs are declared with no cadence, so this also exercises the
    undeclared-cadence path end to end.
    """
    from tests.scripts.test_market_data_restatement_4621 import (
        HIST,
        FakeStore,
        _run_main,
        price_frame,
        price_rows,
    )

    store = FakeStore()
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(HIST))
    series = ("EURUSD=X", "USDJPY=X", "GBPUSD=X")
    specs = [("yahoo", s, None) for s in series]
    # No `store.macros` entry, so each series bootstraps -- and the only rows the
    # vendor has ever published are older than the daily window.
    for sym in series:
        store.macro_lives[("yahoo", sym)] = [
            {"source": "yahoo", "series_id": sym, "obs_date": RETIRED_MONTHLY_SEAL, "value": 1.1},
        ]

    rc, artifact = _run_main(monkeypatch, tmp_path, store, specs, RUN)

    by_ticker = {o["ticker"]: o for o in artifact["outcomes"]}
    assert {by_ticker[f"yahoo__{s}"]["mode"] for s in series} == {"full-repull"}, (
        f"precondition: these bootstrap as successes; got {by_ticker}"
    )
    assert rc == 1, "a macro panel sealed past its cadence windows must exit non-zero"
    assert artifact["stale"] is True
    assert set(artifact["failed"]) == {f"yahoo__{s}" for s in series}, (
        "the artifact must name every retired series"
    )


def test_main_run_stays_fresh_for_a_healthy_macro_panel(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other side, end to end: a current panel exits 0 with the guard wired in.

    A guard that fires on a healthy panel is worse than no guard, because the
    cron alerts on this exit code and stops being read. Fresh monthly seals, one
    sitting out its release cycle, and a healthy price book: rc 0, no names.
    """
    from tests.scripts.test_market_data_restatement_4621 import (
        HIST,
        FakeStore,
        _run_main,
        price_frame,
        price_rows,
    )

    store = FakeStore()
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(HIST))
    specs = [("fred", "M2SL", "monthly"), ("fred", "PCEPI", "monthly")]
    store.macros[("fred", "M2SL")] = [
        {"source": "fred", "series_id": "M2SL", "obs_date": "2026-09-18", "value": 21.0},
    ]
    store.macro_lives[("fred", "M2SL")] = [
        {"source": "fred", "series_id": "M2SL", "obs_date": "2026-09-18", "value": 21.0},
    ]
    store.macros[("fred", "PCEPI")] = [
        {"source": "fred", "series_id": "PCEPI", "obs_date": "2026-08-01", "value": 84.0},
    ]
    store.macro_empty.add(("fred", "PCEPI"))

    rc, artifact = _run_main(monkeypatch, tmp_path, store, specs, RUN)

    assert rc == 0, f"a healthy panel must stay fresh; failed={artifact['failed']}"
    assert artifact["stale"] is False
    assert artifact["failed"] == []


def test_age_guard_is_wired_not_merely_defined(r2: dict[str, Any]) -> None:
    """The guard is *called* from ``main``'s reduction, not defined beside it.

    ``_macro_as_of_stale` could sit in the file, be covered by every behavioural
    test above via the extracted namespace, and never be called by ``main`` --
    which is precisely what happened once already on this guard, when a design
    note described it as implemented at lines 890-930 while ``main`` never
    mentioned it. Behavioural coverage cannot see an unwired helper; the call
    site can.
    """
    addition = ast.unparse(_age_addition())

    assert "_macro_as_of_stale" in addition, (
        f"`failed` is extended by something else; expected the age guard. Got: {addition}"
    )
    for binding in ("outcomes", "macro_specs", "run"):
        assert binding in addition, (
            f"the age guard is missing main's `{binding}` binding, so it is being "
            f"called against something else. Got: {addition}"
        )


def test_the_age_guard_cannot_fail_open(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """A guard that raises marks the run stale rather than quietly vanishing (DIG-2406).

    The addition is wrapped so a future divergence cannot take ``write_manifest``
    down with it. The tempting shape for that ``except`` is to log and carry on,
    and it is wrong here: the panel's ages went *unmeasured*, not *verified young*.
    Swallowing turns an unprovable panel into a fresh one, which is the exact
    silent-freeze failure this guard exists to catch -- so the except arm forces
    ``stale`` instead.

    Exercised through ``main`` with the real guard stubbed to raise, so the
    assertion covers the wiring rather than a copy of the except body.
    """
    import scripts.refresh_market_data_r2 as refresh_mod
    from scripts.refresh_market_data_r2 import _macro_as_of_stale as _real_guard
    from tests.scripts.test_market_data_restatement_4621 import (
        HIST,
        FakeStore,
        _run_main,
        price_frame,
        price_rows,
    )

    store = FakeStore()
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(HIST))
    # A panel that is genuinely healthy: fresh monthly seals, nothing expired.
    # Without the raising guard this run is fresh, so `stale` can only be True
    # because the guard failed to measure.
    specs = [("fred", "M2SL", "monthly")]
    store.macros[("fred", "M2SL")] = [
        {"source": "fred", "series_id": "M2SL", "obs_date": "2026-09-18", "value": 21.0},
    ]
    store.macro_lives[("fred", "M2SL")] = [
        {"source": "fred", "series_id": "M2SL", "obs_date": "2026-09-18", "value": 21.0},
    ]

    def _raising_guard(outcomes, macro_specs, run):
        raise RuntimeError("cadence source diverged")

    monkeypatch.setattr(refresh_mod, "_macro_as_of_stale", _raising_guard)

    rc, artifact = _run_main(monkeypatch, tmp_path, store, specs, RUN)

    # The guard is additive, so a raise costs no names -- it costs certainty.
    assert _real_guard is not _raising_guard
    assert artifact["failed"] == [], (
        "the guard is additive and raises before naming anything; a raise must "
        f"not fabricate failures. Got: {artifact['failed']}"
    )
    assert artifact["stale"] is True, (
        "a macro panel whose as_of ages could not be measured must not report "
        "itself fresh; that is the silent freeze this guard exists to catch"
    )
    assert rc == 1, "an unmeasured panel must exit non-zero so the cron alerts"
