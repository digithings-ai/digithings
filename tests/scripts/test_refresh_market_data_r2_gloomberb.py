"""Unit tests for the PR2 Gloomberb wire (#4794).

``scripts/refresh_market_data_r2.py`` and ``digiquant prices fetch-macro``
seal the macro panel from anonymous Gloomberb ``econ_series`` pages. Sealed
R2 keys (``fred__{SERIES}``), the parquet ``source="fred"`` column, and the
read path are unchanged — only the writer moves. A missing ``FRED_API_KEY``
is normal, not a skip.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module
from unittest.mock import patch

import polars as pl
import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
REFRESH_SCRIPT = REPO_ROOT / "scripts" / "refresh_market_data_r2.py"

RUN = "2026-09-23"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _refresh_module() -> Any:
    mod = sys.modules.get("refresh_market_data_r2")
    if mod is not None:
        return mod
    return _load("refresh_market_data_r2", REFRESH_SCRIPT)


refresh = _refresh_module()


def test_fred_fetch_uses_gloomberb_and_ignores_missing_key(monkeypatch) -> None:
    """``source=="fred"`` fetches Gloomberb with no key and a cadence window."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    calls: dict[str, object] = {}

    def fake_fetch(manifest, client, *, only_series, limit_for):
        calls["series"] = only_series
        cadence = manifest.fred_series[0].get("cadence")
        calls["limit"] = limit_for(cadence)
        return [
            {
                "source": "fred",
                "series_id": "DGS10",
                "obs_date": "2026-09-23",
                "value": 4.1,
                "unit": "percent",
            }
        ]

    monkeypatch.setattr(
        "digiquant.data.prices.gloomberb_macro.fetch_gloomberb",
        fake_fetch,
    )
    store = refresh.RefreshStore.__new__(refresh.RefreshStore)
    rows = store._fetch_macro("fred", "DGS10", "2026-08-01", "2026-09-24", cadence=None)
    assert calls["series"] == "DGS10"
    assert calls["limit"] == 60
    assert rows[0]["value"] == 4.1


def test_fred_dropped_ids_are_not_fetched(monkeypatch) -> None:
    """The 8 dropped ids never reach Gloomberb — no fetch, loud history-only."""
    monkeypatch.delenv("FRED_API_KEY", raising=False)

    def _boom(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("dropped series must not be fetched")

    monkeypatch.setattr(
        "digiquant.data.prices.gloomberb_macro.fetch_gloomberb",
        _boom,
    )
    store = refresh.RefreshStore.__new__(refresh.RefreshStore)
    with pytest.raises(refresh.FetchError, match="not on the gloomberb panel"):
        store._fetch_macro("fred", "DTWEXBGS", "2026-08-01", "2026-09-24", cadence=None)


class _MergeStore:
    """History in, ``put`` captures the sealed frame (short-page merge shape)."""

    def __init__(self, history: pl.DataFrame, live_rows: list[dict[str, Any]]) -> None:
        self.history = history
        self.live_rows = live_rows
        self.puts: list[pl.DataFrame] = []

    def read_macro(self, source: str, series: str) -> pl.DataFrame:
        return self.history

    def fetch_macro(
        self, source: str, series: str, start: str, end: str, *, cadence=None
    ) -> list[dict[str, Any]]:
        return list(self.live_rows)

    def fetch_macro_full(self, source: str, series: str, end: str) -> list[dict[str, Any]]:
        raise AssertionError("fred restatement must merge the short page, not full-repull")

    def put_generation(self, *args: Any, **kwargs: Any) -> str:
        return "sha"

    def swap_latest_pointer(self, *args: Any, **kwargs: Any) -> None:
        return None


def test_fred_restatement_merges_short_page_and_keeps_older_rows() -> None:
    """A revised print inside the page overwrites only its dates; older rows stay."""
    history = pl.DataFrame(
        {
            "source": ["fred", "fred"],
            "series_id": ["DGS10", "DGS10"],
            "obs_date": [date(2020, 1, 2), date(2026, 9, 1)],
            "value": [1.0, 2.0],
            "unit": ["percent", "percent"],
        }
    )
    live = [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-09-01",
            "value": 2.5,
            "unit": "percent",
        }
    ]
    store = _MergeStore(history, live)

    sealed: list[pl.DataFrame] = []
    real_put = refresh._put_macro

    def _capture_put(s: Any, source: str, series: str, frame: pl.DataFrame, as_of: str) -> str:
        sealed.append(frame)
        return real_put(store, source, series, frame, as_of)

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(refresh, "_put_macro", _capture_put)
    try:
        outcome = refresh.refresh_macro_series("fred", "DGS10", store, {}, as_of=RUN)
    finally:
        monkeypatch.undo()
    assert outcome["mode"] == refresh.MODE_FULL_REPULL
    assert sealed, "expected one sealed generation"
    frame = sealed[-1].sort("obs_date")
    by_date = {str(d): v for d, v in zip(frame["obs_date"].to_list(), frame["value"].to_list())}
    assert by_date["2020-01-02"] == 1.0
    assert by_date["2026-09-01"] == 2.5


class _MainStore:
    """Minimal main() store: up-to-date price side, one fred macro series."""

    def __init__(self) -> None:
        day = date(2026, 9, 23)
        self.price = pl.DataFrame(
            {
                "date": [day],
                "ticker": ["SPY"],
                "open": [100.0],
                "high": [101.0],
                "low": [99.0],
                "close": [100.5],
                "volume": [1000],
            }
        )
        self.macro = pl.DataFrame(
            {
                "source": ["fred"],
                "series_id": ["DGS10"],
                "obs_date": [day],
                "value": [4.1],
                "unit": ["percent"],
            }
        )
        self.macro_fetches: list[tuple[str, str]] = []

    def read_history(self, ticker: str) -> pl.DataFrame:
        return self.price

    def fetch_live(self, ticker: str, start: str, end: str) -> pl.DataFrame:
        return self.price

    def fetch_live_full(self, ticker: str, end: str) -> pl.DataFrame:
        return self.price

    def read_macro(self, source: str, series: str) -> pl.DataFrame:
        return self.macro

    def fetch_macro(
        self, source: str, series: str, start: str, end: str, *, cadence=None
    ) -> list[dict[str, Any]]:
        self.macro_fetches.append((source, series))
        return [
            {
                "source": source,
                "series_id": series,
                "obs_date": "2026-09-23",
                "value": 4.1,
                "unit": "percent",
            }
        ]

    def fetch_macro_full(self, source: str, series: str, end: str) -> list[dict[str, Any]]:
        raise AssertionError("up-to-date path must not full-repull")

    def put_generation(self, *args: Any, **kwargs: Any) -> str:
        return "sha"

    def swap_latest_pointer(self, *args: Any, **kwargs: Any) -> None:
        return None

    def write_manifest(self, manifest: dict[str, Any]) -> str:
        return "fake"


def test_main_fetches_fred_without_key_and_reports_no_skip(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """No ``drop_fred_without_key``: key unset, fred still reaches the fetch."""
    import scripts.refresh_market_data_r2 as refresh_mod

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    store = _MainStore()
    manifest_doc: dict[str, Any] = {"version": 1, "as_of": RUN, "datasets": {}}
    monkeypatch.setattr(refresh_mod, "build_store", lambda uri: (store, manifest_doc))
    out = tmp_path / "refresh.json"
    rc = refresh_mod.main(
        [
            "--tickers",
            "SPY",
            "--macro-series",
            "fred:DGS10",
            "--postgres-uri",
            "postgresql://fake",
            "--as-of",
            RUN,
            "--no-core-macro-mirror",
            "--manifest-out",
            str(out),
        ]
    )
    assert rc == 0
    assert ("fred", "DGS10") in store.macro_fetches
    artifact = json.loads(out.read_text())
    assert artifact.get("fred_skipped", []) == []
    assert artifact["stale"] is False


def test_fetch_macro_cli_reads_gloomberb_without_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """``fetch-macro`` source fred needs no key and never echoes the stale line."""
    from digiquant.cli.prices import fetch_macro_cmd

    monkeypatch.delenv("FRED_API_KEY", raising=False)
    monkeypatch.delenv("DIGIQUANT_MARKET_DATA_BACKEND", raising=False)
    manifest = tmp_path / "macro_series.yaml"
    manifest.write_text("fred:\n  series:\n    - id: DGS10\n")
    row = {
        "source": "fred",
        "series_id": "DGS10",
        "obs_date": "2026-09-23",
        "value": 4.1,
        "unit": "percent",
    }
    with patch(
        "digiquant.data.prices.gloomberb_macro.fetch_gloomberb",
        return_value=[row],
    ) as gloomb:
        result = CliRunner().invoke(
            fetch_macro_cmd,
            ["--manifest", str(manifest), "--sources", "fred"],
        )
    assert result.exit_code == 0, result.output
    assert "stale until #4794" not in result.output
    assert "FRED_API_KEY unset" not in result.output
    assert '"DGS10": 1' in result.output
    gloomb.assert_called_once()
