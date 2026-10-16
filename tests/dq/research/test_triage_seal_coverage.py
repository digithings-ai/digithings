"""Every ticker triage reads must be in the sealed watchlist universe (#4167).

Triage's price-delta input is the union of the sector ``etfs`` lists and the
high-tier asset-class lists. The R2 seal covers ``watchlist.md`` (plus macro
series). Nothing tied the two together, so 21 of the 50 tracked tickers — every
secondary sector ETF — sat outside the seal and their signals were permanently
absent, surfacing only as ``UnknownTickerError`` noise on every run.
"""

from __future__ import annotations

import pytest
from digiquant.data.prices.fetchers import parse_watchlist
from digiquant.research.graph import _research_config_root
from digiquant.research.triage_signals import all_tracked_tickers, segment_tickers

pytestmark = pytest.mark.unit

WATCHLIST = _research_config_root() / "watchlist.md"


def test_the_watchlist_file_exists():
    # ``parse_watchlist`` falls back to a hard-coded universe when the file is
    # missing, which would silently defeat the check below.
    assert WATCHLIST.is_file(), f"missing seal universe: {WATCHLIST}"


def test_every_triage_ticker_is_in_the_sealed_watchlist():
    sealed = set(parse_watchlist(str(WATCHLIST)))
    missing = sorted(set(all_tracked_tickers()) - sealed)
    assert not missing, (
        "triage reads tickers the R2 seal never covers, so their price-delta "
        "signals are permanently absent. Add them to "
        "digiquant/src/digiquant/research/config/watchlist.md (the seal universe "
        "is generated from it), or drop them from config/sectors.yaml and the "
        f"asset-class lists in triage_signals.py: {missing}"
    )


def test_segment_tickers_are_not_empty():
    # Guards the check above against a vacuous pass if the sector config stops
    # parsing (an empty tracked-set would satisfy the subset assertion).
    segments = segment_tickers()
    assert segments
    assert all(segments.values())
