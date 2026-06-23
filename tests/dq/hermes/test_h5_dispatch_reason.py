"""Unit tests for the _resolve_linked_thesis helper in portfolio_common."""

from typing import Any
import pytest
from digiquant.olympus.hermes.phases.portfolio_common import _resolve_linked_thesis


@pytest.mark.unit
def test_resolve_linked_thesis_picks_matching_row() -> None:
    theses = [{"thesis_id": "T1", "name": "Oil"}, {"thesis_id": "T2", "name": "Rates"}]
    assert _resolve_linked_thesis("T2", theses) == {"thesis_id": "T2", "name": "Rates"}
    assert _resolve_linked_thesis(None, theses) is None
    assert _resolve_linked_thesis("T9", theses) is None
