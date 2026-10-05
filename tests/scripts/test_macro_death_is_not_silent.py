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
and executes them. So the exemption behaviour under test is the repository's
own code. The second half of the file then reads the ``failed = [...]``
comprehension out of ``main``'s AST, runs *that* with ``main``'s own bindings,
and pins that a whole-leg guard is wired into it -- so the aggregate cannot be
quietly dropped again.

Run from the repo root::

    pytest tests/scripts/test_macro_death_is_not_silent.py -m unit
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "refresh_market_data_r2.py"

pytestmark = pytest.mark.unit

#: Executed verbatim out of the source file, so ``r2`` below is real repo code.
_EXTRACTED_FUNCS = ("_outcome", "_slow_macro_exempt_ids", "_macro_leg_dead")
_EXTRACTED_CONSTS = (
    "_SOFT_FAIL_MODES",
    "MODE_HISTORY_ONLY",
    "MODE_ERROR",
    # `_slow_macro_exempt_ids` reads this at call time, so it must come along.
    "SLOW_CADENCES",
)


@pytest.fixture(scope="module")
def r2() -> dict[str, Any]:
    """Exec the real pure helpers from ``refresh_market_data_r2.py``.

    Deliberately not an ``import``: the module pulls in the whole digiquant
    runtime, which needs Python >= 3.12 (``enum.StrEnum``). Extracting the
    dependency-free helpers keeps this guard runnable on any interpreter while
    still executing the repository's own logic.
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


def test_total_macro_feed_death_fails_the_leg(r2: dict[str, Any]) -> None:
    """THE FINDING, inverted: a total macro outage now fails loud.

    Every macro series in a real slow-cadence manifest (``macro_series.yaml``
    carries M2SL/UNRATE/CPIAUCSL/PCEPI monthly) returning ``history-only`` at
    once is the whole leg dead, not a release calendar. The per-series #4621
    exemption must not swallow it: the run reports ``stale=True`` and exits 1.
    """
    specs = [
        ("fred", "M2SL", "monthly"),
        ("fred", "PCEPI", "monthly"),
        ("fred", "UNRATE", "monthly"),
        ("fred", "GDPC1", "quarterly"),
    ]
    outcomes = [
        r2["_outcome"](name, r2["MODE_HISTORY_ONLY"], note="fetch failed, serving history")
        for name in ("fred__M2SL", "fred__PCEPI", "fred__UNRATE", "fred__GDPC1")
    ]

    failed = _real_failed(r2, outcomes, specs)

    assert failed != [], "a total macro-feed outage is silent again: the whole-leg guard is gone"
    assert [o["ticker"] for o in failed] == [o["ticker"] for o in outcomes], (
        "the whole leg should fail loud, not just part of it"
    )


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


def test_stale_comprehension_keeps_a_whole_leg_guard() -> None:
    """The aggregate is wired into the comprehension, not bolted on beside it.

    The per-series cadence exemption alone cannot see a leg, so the
    comprehension must also consult a whole-leg condition. This is the check
    that keeps a future refactor from deleting the aggregate while every
    behavioural test above still passes.
    """
    comp = _failed_comprehension()
    clauses = [ast.unparse(cond) for gen in comp.generators for cond in gen.ifs]
    joined = " ".join(clauses)

    assert "exempt" in joined, f"expected the cadence exemption, got {clauses}"
    assert "_macro_leg_dead" in joined, (
        "the `failed` comprehension filters per-outcome only again: a whole-leg "
        "macro outage would be reported as a fresh run. Re-wire the aggregate "
        "guard through _macro_leg_dead."
    )
