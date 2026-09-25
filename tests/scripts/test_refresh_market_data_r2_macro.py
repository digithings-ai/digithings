"""Unit tests for the macro path of scripts/refresh_market_data_r2.py (#4588).

A macro series' live fetch window has to span at least one publication period.
``LIVE_WINDOW_DAYS`` (45) assumes a series that publishes inside 45 days; a
monthly FRED series legitimately has no new observation in that window (release
lag plus the pending release), so ``_fetch_macro`` raised ``empty live window``
and the whole refresh was marked stale — every scheduled run exited 1.

These tests pin the contract: the window follows the series' declared cadence, and
the widened window contains the seal row so the existing benign ``up-to-date``
path covers it. An **empty** window is still ``history-only`` (a soft fail) — the
code has no benign-empty branch, and the fix is the window, not a new mode. An
unknown cadence is loud.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import polars as pl
import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "refresh_market_data_r2.py"
MACRO_YAML = (
    REPO_ROOT / "digiquant" / "src" / "digiquant" / "research" / "config" / "macro_series.yaml"
)


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


refresh = _load("refresh_market_data_r2", REFRESH_SCRIPT)

RUN = "2026-09-23"


class FakeStore:
    """Captures the live fetch window and serves a canned history generation."""

    def __init__(self, history: pl.DataFrame) -> None:
        self.history = history
        self.live_windows: list[tuple[str, str]] = []
        self.puts: list[str] = []

    def read_macro(self, source: str, series: str) -> pl.DataFrame:
        return self.history

    def fetch_macro(self, source: str, series: str, start: str, end: str) -> list[dict[str, Any]]:
        self.live_windows.append((start, end))
        # A monthly series with nothing inside the window: FRED answers 200 with
        # no observations, which _fetch_macro reports as "empty live window".
        raise refresh.FetchError(f"{source}__{series}", "empty live window")

    def put_generation(self, *args: Any, **kwargs: Any) -> str:
        self.puts.append(str(args[:2]))
        return "sha"


def monthly_history(seal: str) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "source": ["fred"],
            "series_id": ["PCEPI"],
            "obs_date": [date.fromisoformat(seal)],
            "value": [84.0],
        }
    )


def window_start(run: str, days: int) -> str:
    return str(date.fromisoformat(run) - timedelta(days=days))


def test_monthly_cadence_widens_the_live_window() -> None:
    """A monthly series fetches a window that spans more than one release."""
    assert refresh._live_window_days("monthly") == 120
    assert refresh._live_window_days("quarterly") == 240
    # Weekly already fits several publications in the 45-day default, so widening
    # it would only slow detection of a dead feed.
    assert refresh._live_window_days("weekly") == refresh.LIVE_WINDOW_DAYS
    # Absent or empty cadence keeps the pre-#4588 daily behaviour.
    assert refresh._live_window_days(None) == refresh.LIVE_WINDOW_DAYS
    assert refresh._live_window_days("") == refresh.LIVE_WINDOW_DAYS
    assert refresh._live_window_days("DAILY") == refresh.LIVE_WINDOW_DAYS


def test_unknown_cadence_is_loud() -> None:
    with pytest.raises(ValueError, match="unknown cadence"):
        refresh._live_window_days("fortnightly")


def test_monthly_window_is_wider_than_daily_at_the_fetch() -> None:
    store = FakeStore(monthly_history("2026-07-01"))
    refresh.refresh_macro_series("fred", "PCEPI", store, {}, as_of=RUN, cadence="monthly")
    assert store.live_windows == [(window_start(RUN, 120), "2026-09-24")]


def test_daily_window_unchanged_without_a_cadence() -> None:
    store = FakeStore(monthly_history("2026-09-22"))
    refresh.refresh_macro_series("fred", "DGS10", store, {}, as_of=RUN)
    assert store.live_windows == [(window_start(RUN, refresh.LIVE_WINDOW_DAYS), "2026-09-24")]


def test_empty_live_window_is_still_history_only() -> None:
    """An empty window stays a soft fail — there is no benign-empty branch.

    This pins the mechanism the fix relies on: the widened window *contains* the
    seal row, so the fetch is non-empty. A feed that is genuinely dead (nothing in
    the widened window either) is still caught, just at the slower cadence.
    """
    store = FakeStore(monthly_history("2026-07-01"))
    outcome = refresh.refresh_macro_series("fred", "PCEPI", store, {}, as_of=RUN, cadence="monthly")
    assert outcome["mode"] == refresh.MODE_HISTORY_ONLY
    assert outcome["mode"] in refresh._SOFT_FAIL_MODES
    assert outcome["as_of"] == "2026-07-01"
    assert outcome["rows"] == 1
    assert "empty live window" in outcome["note"]


def test_monthly_observation_inside_the_window_lands_as_up_to_date() -> None:
    """The regression: with the 120-day window a fresh monthly row is fetched,
    is not newer than the seal, and resolves to up-to-date (not a soft fail)."""
    store = FakeStore(monthly_history("2026-07-01"))

    def fetch_same_row(source: str, series: str, start: str, end: str) -> list[dict[str, Any]]:
        store.live_windows.append((start, end))
        return [
            {
                "source": source,
                "series_id": series,
                "obs_date": "2026-07-01",
                "value": 84.0,
            }
        ]

    store.fetch_macro = fetch_same_row  # type: ignore[method-assign]
    outcome = refresh.refresh_macro_series("fred", "PCEPI", store, {}, as_of=RUN, cadence="monthly")
    assert outcome["mode"] == refresh.MODE_UP_TO_DATE
    assert outcome["note"] == "no new observations"
    assert outcome["mode"] not in refresh._SOFT_FAIL_MODES


def test_unknown_cadence_raises_at_the_fetch() -> None:
    store = FakeStore(monthly_history("2026-07-01"))
    with pytest.raises(ValueError, match="unknown cadence"):
        refresh.refresh_macro_series("fred", "PCEPI", store, {}, as_of=RUN, cadence="fortnightly")


def _series_block(text: str, series: str) -> str:
    """The YAML text of one ``- id: <series>`` entry, up to the next entry.

    Anchors on the newline-prefixed literal ``- id: <series>`` and cuts at the
    next ``- id:``, so an id that is a prefix of another (``M2`` vs ``M2SL``)
    cannot anchor on the wrong entry.
    """
    marker = f"\n    - id: {series}\n"
    assert marker in text, f"missing entry for {series}"
    return text.split(marker, 1)[1].split("\n    - id: ", 1)[0]


def test_registry_declares_cadences_for_slow_series() -> None:
    """The manifest that drives the refresh must declare the slow cadences."""
    text = MACRO_YAML.read_text()
    for series in ("M2SL", "UNRATE", "MANEMP", "CPIAUCSL", "PCEPI"):
        assert "cadence: monthly" in _series_block(text, series), series
    for series in ("NFCI", "STLFSI4", "MORTGAGE30US", "WALCL", "ICSA"):
        assert "cadence: weekly" in _series_block(text, series), series


def test_daily_series_carry_no_cadence() -> None:
    """Daily is the default, so the daily block should stay unannotated."""
    text = MACRO_YAML.read_text()
    for series in ("DGS10", "DFF", "SOFR", "VIXCLS", "DCOILWTICO"):
        assert "cadence:" not in _series_block(text, series), series


def test_resolver_carries_the_manifest_cadence() -> None:
    specs = refresh._resolve_macro_specs([], str(MACRO_YAML))
    by_series = {series: cadence for _source, series, cadence in specs}
    assert by_series["PCEPI"] == "monthly"
    assert by_series["ICSA"] == "weekly"
    assert by_series["DGS10"] is None


def test_cli_specs_default_to_daily() -> None:
    assert refresh._resolve_macro_specs(["fred:PCEPI"], "unused") == [("fred", "PCEPI", None)]
