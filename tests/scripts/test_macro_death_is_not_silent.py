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

How this stays a real test rather than a stub. It does not reimplement the
logic. It parses ``refresh_market_data_r2.py`` with :mod:`ast`, extracts the
*actual* source of ``_outcome``, ``_slow_macro_exempt_ids`` and
``_macro_leg_dead`` plus the real ``_SOFT_FAIL_MODES`` / ``MODE_*`` constants,
and executes them. The second half then reads the ``failed = [...]``
comprehension out of ``main``'s AST and runs *that* with ``main``'s own
bindings -- an ``import`` cannot reach the comprehension, because it lives
inside ``main`` rather than at module scope, and inlining a copy of it here
would be the paraphrase this file exists to avoid. The exempt set for the
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
_EXTRACTED_FUNCS = ("_outcome", "_slow_macro_exempt_ids", "_macro_leg_dead")
_EXTRACTED_CONSTS = (
    "_SOFT_FAIL_MODES",
    "MODE_HISTORY_ONLY",
    "MODE_ERROR",
    # Only used to build the healthy half of a realistic run.
    "MODE_UP_TO_DATE",
    # `_slow_macro_exempt_ids` reads this at call time, so it must come along.
    "SLOW_CADENCES",
)


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

    found_funcs = {n.name for n in keep if isinstance(n, ast.FunctionDef)}
    missing = set(_EXTRACTED_FUNCS) - found_funcs
    assert not missing, f"{SCRIPT.name} no longer defines {sorted(missing)}; update this guard"

    namespace: dict[str, Any] = {"Any": Any, "frozenset": frozenset}
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
    """End-to-end through ``main()`` itself: the exit code and the artifact.

    Every other test in this file executes the reduction with a namespace it
    builds itself, including its own ``exempt`` set. That is deliberate (the
    comprehension is not reachable by import) but it means none of them can see
    ``main`` mis-wiring its own ``exempt`` binding -- a body that reached the
    guard with ``exempt = set()`` passes every test above while the macro leg is
    reported fresh. This one drives the real entry point, so it pins the wiring,
    the exit code and the published ``failed`` list together.
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


def test_main_run_stays_quiet_for_one_slow_series(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The other direction through ``main()``: the #4621 exemption still holds.

    ``test_main_run_exits_nonzero_and_names_the_whole_leg`` pins that a dead leg
    is loud, but loudness alone cannot catch ``main`` reaching the guard with an
    empty ``exempt`` set -- never exempting anything is *more* loud, so that
    mutant satisfies it. This one pins the quiet side: with ``main``'s own
    ``exempt`` binding mis-wired the slow series would stop being exempt and a
    legitimate quiet week would fail the cron.
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
    specs = [("fred", "PCEPI", "monthly")]
    for source, series, _cadence in specs:
        store.macros[(source, series)] = [
            {"source": source, "series_id": series, "obs_date": "2026-07-01", "value": 84.0},
        ]
        store.macro_empty.add((source, series))

    rc, artifact = _run_main(monkeypatch, tmp_path, store, specs, "2026-09-23")

    assert rc == 0, "one monthly series sitting out its release cycle is a quiet week (#4621)"
    assert artifact["stale"] is False
    assert artifact["failed"] == []


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
