"""Tests for position_events row validation (#2494)."""

from __future__ import annotations

import pytest
from digiquant.olympus.hermes.models.position_event import PositionEventRow
from pydantic import ValidationError

pytestmark = pytest.mark.unit

_VALID = {
    "date": "2026-07-31",
    "ticker": "FXI",
    "event": "OPEN",
    "weight_pct": 7.0,
    "prev_weight_pct": None,
    "price": 39.85,
    "reason": "OPEN — filled 10 share(s) at 39.85 from order intent …",
    "thesis_id": None,
    "book_source": "authoritative",
}


class TestPositionEventRow:
    def test_constructs_from_required_fields(self) -> None:
        row = PositionEventRow(**_VALID)
        assert row.ticker == "FXI"
        assert row.event == "OPEN"

    def test_missing_required_key_fails_at_construction(self) -> None:
        payload = dict(_VALID)
        del payload["ticker"]
        with pytest.raises(ValidationError, match="ticker"):
            PositionEventRow(**payload)

    def test_unknown_key_fails_at_construction(self) -> None:
        with pytest.raises(ValidationError, match="extra_forbidden"):
            PositionEventRow(**_VALID, run_date="2026-07-31")

    def test_bad_event_value_fails_at_construction(self) -> None:
        payload = dict(_VALID, event="REBALANCE")
        with pytest.raises(ValidationError, match="event"):
            PositionEventRow(**payload)

    def test_to_postgrest_row_preserves_expected_key_set(self) -> None:
        dumped = PositionEventRow(**_VALID).to_postgrest_row()
        assert set(dumped) == {
            "date",
            "ticker",
            "event",
            "weight_pct",
            "prev_weight_pct",
            "price",
            "reason",
            "thesis_id",
            "book_source",
        }

    def test_bad_book_source_fails_at_construction(self) -> None:
        payload = dict(_VALID, book_source="prose")
        with pytest.raises(ValidationError, match="book_source"):
            PositionEventRow(**payload)
