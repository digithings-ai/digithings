"""Unit tests for the gloomberb macro panel adapter (#4794, PR 1).

The adapter swaps only the macro-panel writer: the 23 kept FRED ids refresh
from anonymous ``GloomberbClient.econ_series`` while the 8 dropped ids stop
refreshing. Dataset ids (``fred__{SERIES}``) and the parquet ``source="fred"``
column are unchanged. All clients here are fakes; no network.
"""

from __future__ import annotations

from typing import Any

import pytest
from digiquant.data.gloomberb.models import (
    EconSeriesEnvelope,
    EconSeriesObservation,
    EconSeriesResult,
)
from digiquant.data.prices.gloomberb_macro import (
    DROPPED_SERIES_IDS,
    KEPT_SERIES_IDS,
    GloomberbMacroError,
    build_ingest_client,
    fetch_gloomberb,
    fetch_gloomberb_series,
    gloomberb_observations_to_rows,
    window_limit,
)
from digiquant.data.prices.macro_ingest import MacroManifest

pytestmark = pytest.mark.unit


def _envelope(observations: list[EconSeriesObservation]) -> EconSeriesEnvelope:
    return EconSeriesEnvelope(data=EconSeriesResult(observations=observations))


def _obs(date: str, value: float | None) -> EconSeriesObservation:
    return EconSeriesObservation(date=date, value=value)


class FakeGloomberbClient:
    """Fake client keyed by series id; values are envelopes or exceptions."""

    def __init__(self, by_id: dict[str, Any]) -> None:
        self._by_id = by_id
        self.calls: list[Any] = []

    def econ_series(self, request: Any) -> Any:
        self.calls.append(request)
        outcome = self._by_id[request.series_id]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _manifest(*series_ids: str) -> MacroManifest:
    return MacroManifest(
        fred_series=[{"id": sid, "unit": "percent", "title": f"{sid} title"} for sid in series_ids],
        fred_backfill_start="1990-01-01",
    )


def test_panel_sets_are_the_probed_split() -> None:
    assert len(KEPT_SERIES_IDS) == 23
    assert len(DROPPED_SERIES_IDS) == 8
    assert KEPT_SERIES_IDS.isdisjoint(DROPPED_SERIES_IDS)
    assert "DGS10" in KEPT_SERIES_IDS and "M2SL" in KEPT_SERIES_IDS
    assert "DTWEXBGS" in DROPPED_SERIES_IDS and "MANEMP" in DROPPED_SERIES_IDS


def test_window_limit_covers_cadence_and_rejects_unknown() -> None:
    assert window_limit(None) == 60
    assert window_limit("daily") == 60
    assert window_limit("weekly") == 16
    assert window_limit("monthly") == 8
    assert window_limit("quarterly") == 4
    with pytest.raises(ValueError, match="unknown cadence"):
        window_limit("hourly")


def test_rows_drop_null_prints_and_stamp_fred_source() -> None:
    rows = gloomberb_observations_to_rows(
        "DGS10",
        "percent",
        "10Y",
        [
            {"date": "2026-01-02", "value": 4.2},
            {"date": "2026-01-03", "value": None},
            {"date": "", "value": 4.3},
        ],
    )
    assert rows == [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-01-02",
            "value": 4.2,
            "unit": "percent",
            "meta": {"title": "10Y"},
        }
    ]


def test_rows_omit_meta_without_title() -> None:
    rows = gloomberb_observations_to_rows(
        "DGS10", "percent", None, [{"date": "2026-01-02", "value": 4.2}]
    )
    assert rows == [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-01-02",
            "value": 4.2,
            "unit": "percent",
        }
    ]


def test_fetch_gloomberb_series_requests_desc_limit() -> None:
    client = FakeGloomberbClient(
        {
            "CPIAUCSL": _envelope([_obs("2026-08-01", 320.1), _obs("2026-09-01", 321.5)]),
        }
    )
    rows = fetch_gloomberb_series(client, "CPIAUCSL", unit="index", title="CPI", limit=8)
    assert len(client.calls) == 1
    request = client.calls[0]
    assert request.series_id == "CPIAUCSL"
    assert request.limit == 8
    assert request.sort_order == "desc"
    assert len(rows) == 2
    assert all(r["source"] == "fred" for r in rows)
    assert [r["obs_date"] for r in rows] == ["2026-08-01", "2026-09-01"]


def test_fetch_gloomberb_series_error_envelope_raises_with_code() -> None:
    from digiquant.data.gloomberb.models import DigifetchError

    client = FakeGloomberbClient(
        {
            "DGS10": EconSeriesEnvelope(
                data=DigifetchError(code="rate_limited", message="slow down", retryable=True)
            ),
        }
    )
    with pytest.raises(GloomberbMacroError, match="rate_limited"):
        fetch_gloomberb_series(client, "DGS10", unit="percent", title=None, limit=60)


def test_fetch_gloomberb_isolates_one_failure() -> None:
    client = FakeGloomberbClient(
        {
            "DGS10": GloomberbMacroError("DGS10: upstream_error: boom"),
            "DGS5": _envelope([_obs("2026-09-23", 4.1)]),
        }
    )
    rows = fetch_gloomberb(_manifest("DGS10", "DGS5"), client)
    assert [r["series_id"] for r in rows] == ["DGS5"]

    both_fail = FakeGloomberbClient(
        {
            "DGS10": GloomberbMacroError("DGS10: upstream_error: boom"),
            "DGS5": GloomberbMacroError("DGS5: upstream_error: boom"),
        }
    )
    with pytest.raises(RuntimeError, match="all"):
        fetch_gloomberb(_manifest("DGS10", "DGS5"), both_fail)


def test_fetch_gloomberb_respects_only_series() -> None:
    client = FakeGloomberbClient(
        {
            "DGS5": _envelope([_obs("2026-09-23", 4.1)]),
        }
    )
    rows = fetch_gloomberb(_manifest("DGS10", "DGS5"), client, only_series="DGS5")
    assert [r["series_id"] for r in rows] == ["DGS5"]
    assert [c.series_id for c in client.calls] == ["DGS5"]


def test_fetch_gloomberb_empty_page_is_an_error() -> None:
    client = FakeGloomberbClient({"DGS10": _envelope([])})
    with pytest.raises(GloomberbMacroError, match="empty"):
        fetch_gloomberb_series(client, "DGS10", unit="percent", title=None, limit=60)


def test_build_ingest_client_disables_cache() -> None:
    from digiquant.data.gloomberb.client import GloomberbClient

    client = build_ingest_client()
    try:
        assert isinstance(client, GloomberbClient)
        assert client._cache_ttl == 0
    finally:
        client.close()
