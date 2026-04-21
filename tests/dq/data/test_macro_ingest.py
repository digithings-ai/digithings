"""Unit tests for digiquant.data.prices.macro_ingest (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from digiquant.data.prices.macro_ingest import (
    MacroManifest,
    dedupe_observation_rows,
    fetch_crypto_fng,
    fetch_fred,
    fetch_frankfurter,
    fng_entries_to_rows,
    frankfurter_payload_to_rows,
    fred_observations_to_rows,
)


def _manifest() -> MacroManifest:
    return MacroManifest.from_dict(
        {
            "fred": {
                "series": [
                    {"id": "DGS10", "title": "10-Year Treasury", "unit": "percent"},
                ],
                "backfill_start": "1990-01-01",
            },
            "frankfurter": {
                "base": "USD",
                "symbols": ["EUR", "GBP"],
                "backfill_start": "1999-01-04",
            },
            "crypto_fear_greed": {"series_value_id": "FNG/value", "backfill_limit": 365},
        }
    )


@pytest.mark.unit
def test_fred_observations_to_rows_filters_missing_values() -> None:
    observations = [
        {"date": "2025-01-01", "value": "4.12"},
        {"date": "2025-01-02", "value": "."},  # FRED sentinel for missing
        {"date": "2025-01-03", "value": ""},
        {"date": "", "value": "4.15"},
        {"date": "2025-01-04", "value": "not-a-number"},
    ]
    rows = fred_observations_to_rows("DGS10", "percent", "10Y", observations)
    assert len(rows) == 1
    assert rows[0]["obs_date"] == "2025-01-01"
    assert rows[0]["value"] == pytest.approx(4.12)
    assert rows[0]["source"] == "fred"
    assert rows[0]["series_id"] == "DGS10"
    assert rows[0]["meta"]["title"] == "10Y"


@pytest.mark.unit
def test_fetch_fred_mocks_http_and_returns_rows() -> None:
    fake_payload = {
        "observations": [
            {"date": "2025-04-01", "value": "4.12"},
            {"date": "2025-04-02", "value": "4.15"},
        ]
    }
    with patch("digiquant.data.prices.macro_ingest.fetch_fred_series") as fake:
        fake.return_value = fake_payload["observations"]
        rows = fetch_fred(_manifest(), api_key="fake-key", end="2025-04-30")
    assert len(rows) == 2
    assert {r["value"] for r in rows} == {4.12, 4.15}


@pytest.mark.unit
def test_fetch_fred_requires_api_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        fetch_fred(_manifest(), api_key="")


@pytest.mark.unit
def test_frankfurter_payload_parses_rows_within_range() -> None:
    payload = {
        "rates": {
            "2025-01-01": {"EUR": 0.91, "GBP": 0.78},
            "2025-01-02": {"EUR": 0.915, "GBP": 0.785},
            "2024-12-31": {"EUR": 0.90},  # out of range
        }
    }
    rows = frankfurter_payload_to_rows(payload, "USD", ["EUR", "GBP"], "2025-01-01", "2025-01-02")
    assert len(rows) == 4
    assert all(r["source"] == "frankfurter" for r in rows)
    assert {r["series_id"] for r in rows} == {"FX/EUR", "FX/GBP"}


@pytest.mark.unit
def test_fetch_frankfurter_pulls_year_chunks() -> None:
    called_ranges: list[tuple[str, str]] = []

    def fake_range(start, end, base, symbols, timeout=120.0):
        called_ranges.append((start, end))
        return {"rates": {start: {"EUR": 0.9, "GBP": 0.8}}}

    with patch(
        "digiquant.data.prices.macro_ingest.fetch_frankfurter_range", side_effect=fake_range
    ):
        rows = fetch_frankfurter(_manifest(), start="2023-06-15", end="2025-03-10")

    assert called_ranges == [
        ("2023-06-15", "2023-12-31"),
        ("2024-01-01", "2024-12-31"),
        ("2025-01-01", "2025-03-10"),
    ]
    assert rows  # at least the first-day rates are captured


@pytest.mark.unit
def test_fng_entries_to_rows_skips_bad_entries() -> None:
    entries = [
        {"timestamp": "1700000000", "value": "55", "value_classification": "Greed"},
        {"timestamp": "0", "value": "40"},  # bad ts
        {"timestamp": "1700086400", "value": "not-num"},  # bad value
    ]
    rows = fng_entries_to_rows(entries, "FNG/value")
    assert len(rows) == 1
    assert rows[0]["value"] == 55.0
    assert rows[0]["meta"] == {"classification": "Greed"}


@pytest.mark.unit
def test_fetch_crypto_fng_happy_path() -> None:
    with patch("digiquant.data.prices.macro_ingest.fetch_fng_raw") as raw:
        raw.return_value = [{"timestamp": "1700000000", "value": "73"}]
        rows = fetch_crypto_fng(_manifest(), backfill=False)
    assert len(rows) == 1
    assert rows[0]["source"] == "crypto_fear_greed"
    assert rows[0]["unit"] == "index"


@pytest.mark.unit
def test_dedupe_observation_rows_keeps_last() -> None:
    rows = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2025-01-01", "value": 4.0},
        {"source": "fred", "series_id": "DGS10", "obs_date": "2025-01-01", "value": 4.1},
        {"source": "fred", "series_id": "DGS10", "obs_date": "2025-01-02", "value": 4.2},
    ]
    out = dedupe_observation_rows(rows)
    assert len(out) == 2
    # Last-wins on duplicate (2025-01-01)
    for r in out:
        if r["obs_date"] == "2025-01-01":
            assert r["value"] == 4.1


@pytest.mark.unit
def test_macro_manifest_defaults() -> None:
    mani = MacroManifest.from_dict({})
    assert mani.frankfurter_base == "USD"
    assert "EUR" in mani.frankfurter_symbols
    assert mani.fng_series_id == "FNG/value"
