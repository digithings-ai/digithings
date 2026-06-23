"""Unit tests for the _resolve_linked_thesis helper in portfolio_common."""

from typing import Any
import pytest
from digiquant.olympus.hermes.phases.portfolio_common import _resolve_linked_thesis
from digiquant.olympus.hermes.phases.h5_asset_analyst import _should_backfill_vehicle_thesis


@pytest.mark.unit
def test_resolve_linked_thesis_picks_matching_row() -> None:
    theses = [{"thesis_id": "T1", "name": "Oil"}, {"thesis_id": "T2", "name": "Rates"}]
    assert _resolve_linked_thesis("T2", theses) == {"thesis_id": "T2", "name": "Rates"}
    assert _resolve_linked_thesis(None, theses) is None
    assert _resolve_linked_thesis("T9", theses) is None


@pytest.mark.unit
def test_backfill_only_for_unlinked_exploratory() -> None:
    assert _should_backfill_vehicle_thesis({"roster_reason": "technical"}) is True
    assert _should_backfill_vehicle_thesis({"roster_reason": "held"}) is False
    assert _should_backfill_vehicle_thesis(
        {"roster_reason": "thesis_mapped", "linked_market_thesis_id": "T1"}
    ) is False
    assert _should_backfill_vehicle_thesis(
        {"roster_reason": "technical", "linked_market_thesis_id": "T1"}
    ) is False
