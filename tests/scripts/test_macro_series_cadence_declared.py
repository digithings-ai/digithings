"""Every macro series the cron fetches declares the cadence it is judged on.

DIG-2406, out of the DIG-2381 review of #5248. Six of the 23 ids on
``KEPT_SERIES_IDS`` shipped a ``cadence:``; the other 17 were fetched all the
same and left undeclared, so they fell to the 45-day daily window by accident
rather than by decision. DIG-1137 makes that accident louder than it used to be:
the run now fails when a series' ``as_of`` is older than its cadence window, so
an undeclared cadence is not a neutral default but a daily series judged at the
narrowest of the four windows with no stated expectation behind it.

What this pins, against the real manifest and the real script:

* every fetched FRED id declares a cadence, so nothing rides the fallback;
* every declared cadence is one the code can act on -- ``_live_window_days`` and
  ``window_limit`` both raise ``ValueError`` on an unknown key, so a typo would crash
  a refresh instead of quietly resizing a window;
* declaring ``daily`` on the 17 changed no runtime behaviour and, specifically, did
  not enlarge the soft-fail exempt set;
* the ``None`` cadences that remain are the two the code names out loud (the Yahoo
  FX list and a ``--macro-series`` override), and ``None`` resolves to the narrowest
  window: the intent, enforced in code rather than asserted in a comment.

Nothing here re-implements the panel. The specs come from the real
``_resolve_macro_specs`` reading the real shipped ``macro_series.yaml``, so a series the
manifest drops cannot linger here as a phantom expectation.

Run from the repo root::

    pytest tests/scripts/test_macro_series_cadence_declared.py -m unit
"""

from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "refresh_market_data_r2.py"
MACRO_YAML = (
    REPO_ROOT / "digiquant" / "src" / "digiquant" / "research" / "config" / "macro_series.yaml"
)

pytestmark = pytest.mark.unit

#: The ids that sat on ``KEPT_SERIES_IDS`` with no ``cadence:`` key when DIG-2381 reviewed
#: #5248, in ``macro_series.yaml`` order. Kept as a literal so "the 17 are declared" stays
#: a checkable claim: a later drop or rename of one of them fails here instead of
#: quietly returning to ``None`` with this file's memory as the only evidence.
REVIEWED_UNDECLARED = (
    "DGS2",
    "DGS5",
    "DGS10",
    "DGS30",
    "DFF",
    "SOFR",
    "T10Y2Y",
    "T10Y3M",
    "T10YIE",
    "T5YIE",
    "DFII10",
    "T5YIFR",
    "BAMLH0A0HYM2",
    "BAMLC0A0CM",
    "VIXCLS",
    "VXVCLS",
    "DCOILWTICO",
)


def _load(name: str, path: Path) -> types.ModuleType:
    """Import ``refresh_market_data_r2.py`` by path, the way the cron runs it."""
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def refresh() -> types.ModuleType:
    return _load("refresh_market_data_r2_cadence", REFRESH_SCRIPT)


@pytest.fixture(scope="module")
def shipped_specs(refresh: types.ModuleType) -> list[tuple[str, str, str | None]]:
    """``(source, series, cadence)`` as the cron reads them off the real manifest."""
    return refresh._resolve_macro_specs([], str(MACRO_YAML))


@pytest.fixture(scope="module")
def fred_cadences(shipped_specs) -> dict[str, str | None]:
    """The shipped FRED panel as ``{series: cadence}``.

    Keyed by id rather than listed, so an assertion can name a series instead of
    a position.
    """
    return {series: cadence for source, series, cadence in shipped_specs if source == "fred"}


@pytest.fixture(scope="module")
def window_days() -> dict[str, int]:
    """The real ``_CADENCE_WINDOW_DAYS`` table, read out of the script's own AST.

    ``daily`` and ``weekly`` are written as ``LIVE_WINDOW_DAYS`` rather than as
    literals, so ``ast.literal_eval`` alone raises on the name. Substitute the
    one name the table uses from the same parse -- read as data, not re-parsed
    by hand -- so the table stays the shipped one.
    """
    tree = ast.parse(REFRESH_SCRIPT.read_text(encoding="utf-8"))
    names: dict[str, ast.expr] = {}
    table: ast.expr | None = None
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "LIVE_WINDOW_DAYS":
                names["LIVE_WINDOW_DAYS"] = node.value
            elif node.target.id == "_CADENCE_WINDOW_DAYS":
                table = node.value
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "LIVE_WINDOW_DAYS":
                    names["LIVE_WINDOW_DAYS"] = node.value
    if table is None:
        raise AssertionError(f"{REFRESH_SCRIPT.name} no longer defines _CADENCE_WINDOW_DAYS")
    if not isinstance(table, ast.Dict):
        raise AssertionError(f"_CADENCE_WINDOW_DAYS is a {type(table).__name__}, not a dict")
    resolved: dict[str, int] = {}
    for key, value in zip(table.keys, table.values, strict=True):
        if isinstance(value, ast.Name):
            if value.id not in names:
                raise AssertionError(f"unresolved name {value.id!r} in _CADENCE_WINDOW_DAYS")
            value = names[value.id]
        assert key is not None
        resolved[ast.literal_eval(key)] = ast.literal_eval(value)
    return resolved


@pytest.fixture(scope="module")
def backfill_limit():
    """``window_limit`` -- the other cadence consumer, one layer down in the fetch."""
    from digiquant.data.prices.gloomberb_macro import window_limit

    return window_limit


def test_every_fetched_fred_series_declares_a_cadence(fred_cadences) -> None:
    undeclared = sorted(s for s, c in fred_cadences.items() if not c)
    assert not undeclared, f"fetched with no declared cadence: {undeclared}"


def test_the_seventeen_ids_the_review_named_are_still_declared(fred_cadences) -> None:
    gone = sorted(set(REVIEWED_UNDECLARED) - set(fred_cadences))
    assert not gone, f"the manifest no longer fetches ids this file pins: {gone}"
    bare = sorted(s for s in REVIEWED_UNDECLARED if not fred_cadences.get(s))
    assert not bare, f"back to an undeclared cadence: {bare}"


def test_every_declared_cadence_is_a_key_the_code_knows(
    refresh, fred_cadences, window_days, backfill_limit
) -> None:
    """A cadence the tables do not carry is a ValueError mid-refresh, not a default."""
    for series, cadence in sorted(fred_cadences.items()):
        assert cadence in window_days, f"{series}: {cadence!r} is unknown to the script"
        assert refresh._live_window_days(cadence) == window_days[cadence]
        assert backfill_limit(cadence) > 0


def test_an_undeclared_cadence_lands_on_the_narrowest_window(refresh, window_days) -> None:
    """The intent behind ``None``, enforced instead of asserted in a comment.

    ``None`` has to resolve to the *smallest* window in the table. If it ever
    resolved to the largest, an undeclared cadence would quietly buy the most
    patience -- the opposite of what the fallback is for.
    """
    assert refresh._live_window_days(None) == min(window_days.values()), (
        "None must resolve to the narrowest window, so an undeclared cadence buys no patience"
    )


def test_declaring_daily_changed_no_window(refresh, fred_cadences, backfill_limit) -> None:
    daily = sorted(s for s, c in fred_cadences.items() if c == "daily")
    assert set(daily) == set(REVIEWED_UNDECLARED), f"daily drifted: {daily}"
    assert refresh._live_window_days("daily") == refresh.LIVE_WINDOW_DAYS
    assert backfill_limit("daily") == backfill_limit(None), (
        "the 17 are declared daily precisely so that declaring them changes no window"
    )


def test_declaring_a_cadence_exempted_nothing(refresh, shipped_specs, fred_cadences) -> None:
    declared = {s: (c or "").lower() for s, c in fred_cadences.items()}
    slow = {f"fred__{s}" for s, c in declared.items() if c in refresh.SLOW_CADENCES}
    exempt = refresh._slow_macro_exempt_ids(shipped_specs)
    assert exempt == slow, f"the soft-fail exemption drifted: {sorted(exempt)}"
    assert exempt, "the monthly panel is the premise; none is left"
    widened = sorted(exempt & {f"fred__{s}" for s in REVIEWED_UNDECLARED})
    assert not widened, f"a declared cadence quietly exempted: {widened}"


def test_the_undeclared_paths_are_the_two_the_code_names(refresh, shipped_specs) -> None:
    yahoo = [(s, c) for source, s, c in shipped_specs if source == "yahoo"]
    assert yahoo, "the Yahoo FX leg is still on the panel"
    assert [s for s, c in yahoo if c is not None] == [], (
        "Yahoo FX symbols are daily by construction; a cadence there "
        "would be a claim nobody can check"
    )
    cli = refresh._resolve_macro_specs(["fred:DGS10"], str(MACRO_YAML))
    assert cli == [("fred", "DGS10", None)], "a CLI override cannot know a cadence"
