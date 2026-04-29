"""Unit tests for digiquant.profiles.asset_preferences (#306)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from digiquant.profiles import AssetPreferences

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "example_asset_preferences.json"


@pytest.mark.unit
class TestAssetPreferences:
    def test_minimal_construction_uses_defaults(self) -> None:
        prefs = AssetPreferences()
        assert prefs.schema_version == 1
        assert prefs.watchlists == {}
        assert prefs.custom_universe == []
        assert prefs.excluded_tickers == []
        assert prefs.excluded_sectors == []

    def test_round_trips_json(self) -> None:
        prefs = AssetPreferences(
            watchlists={"core": ["spy", "QQQ", "spy"]},
            custom_universe=["nvda"],
            excluded_tickers=["XOM"],
            excluded_sectors=["Tobacco"],
        )
        loaded = AssetPreferences.model_validate_json(prefs.model_dump_json())
        assert loaded == prefs

    def test_tickers_normalized_to_uppercase_and_deduped(self) -> None:
        prefs = AssetPreferences(
            watchlists={"core": ["spy", " SPY ", "qqq"]},
            custom_universe=["nvda", "NVDA", "amd"],
        )
        assert prefs.watchlists["core"] == ["SPY", "QQQ"]
        assert prefs.custom_universe == ["NVDA", "AMD"]

    def test_sectors_normalized_to_lowercase_and_deduped(self) -> None:
        prefs = AssetPreferences(excluded_sectors=["Tobacco", "tobacco", "Defense"])
        assert prefs.excluded_sectors == ["tobacco", "defense"]

    def test_excluded_ticker_dropped_from_watchlist(self) -> None:
        """Exclusion wins over inclusion — even if user lists a ticker in both."""
        prefs = AssetPreferences(
            watchlists={"core": ["SPY", "XOM", "QQQ"], "energy": ["XOM"]},
            custom_universe=["XOM", "NVDA"],
            excluded_tickers=["XOM"],
        )
        assert "XOM" not in prefs.watchlists["core"]
        assert prefs.watchlists["core"] == ["SPY", "QQQ"]
        assert prefs.watchlists["energy"] == []  # all members excluded
        assert "XOM" not in prefs.custom_universe

    def test_extra_field_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssetPreferences.model_validate({"foo": "bar"})

    def test_schema_version_below_one_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssetPreferences(schema_version=0)

    def test_empty_watchlist_name_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssetPreferences(watchlists={"   ": ["SPY"]})

    def test_non_string_ticker_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AssetPreferences.model_validate({"custom_universe": ["NVDA", 42]})

    def test_empty_string_tickers_dropped(self) -> None:
        prefs = AssetPreferences(custom_universe=["NVDA", "", "  ", "AMD"])
        assert prefs.custom_universe == ["NVDA", "AMD"]

    def test_example_fixture_loads(self) -> None:
        data = json.loads(FIXTURE_PATH.read_text())
        prefs = AssetPreferences.model_validate(data)
        assert prefs.schema_version == 1
        assert "core" in prefs.watchlists
        assert "XOM" in prefs.excluded_tickers
        # Fixture lists XOM only in excluded_tickers (not watchlists), so the
        # cross-check should leave watchlists untouched.
        assert prefs.watchlists["core"] == ["SPY", "QQQ", "IWM"]

    def test_round_trip_via_fixture_path(self) -> None:
        """Loading + dumping the fixture should round-trip unchanged."""
        data = json.loads(FIXTURE_PATH.read_text())
        prefs = AssetPreferences.model_validate(data)
        reloaded = AssetPreferences.model_validate(json.loads(prefs.model_dump_json()))
        assert reloaded == prefs
