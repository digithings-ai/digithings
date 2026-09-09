"""CoverageDirective model + roster application (#3739).

The coverage director (PM role, between H4 and H5) decides which H4-rostered
tickers get fresh analysis today. Strict schema: every selected ticker needs a
reason, and no ticker may appear in more than one bucket.
"""

import pytest
from digiquant.portfolio.phases.coverage_director import (
    CoverageDirective,
    apply_coverage,
)
from digiquant.research.state import ExcludedTicker, FocusRosterEntry
from pydantic import ValidationError


def _entry(ticker: str, reason: str = "held") -> FocusRosterEntry:
    return FocusRosterEntry(ticker=ticker, roster_reason=reason, rationale="h4")


def test_directive_requires_reason_per_ticker() -> None:
    with pytest.raises(ValidationError):
        CoverageDirective(
            refresh=[{"ticker": "BTC-USD", "reason": ""}],
            explore=[],
            skip=[],
        )


def test_directive_rejects_ticker_in_two_buckets() -> None:
    with pytest.raises(ValidationError):
        CoverageDirective(
            refresh=[{"ticker": "BTC-USD", "reason": "thesis challenged"}],
            explore=[],
            skip=[{"ticker": "BTC-USD", "reason": "quiet"}],
        )


def test_apply_coverage_keeps_selected_with_director_reasons() -> None:
    roster = [_entry("BTC-USD"), _entry("ETH-USD"), _entry("SOL-USD")]
    directive = CoverageDirective(
        refresh=[{"ticker": "BTC-USD", "reason": "funding regime shifted"}],
        explore=[{"ticker": "ETH-USD", "reason": "thesis T-7 names it"}],
        skip=[{"ticker": "SOL-USD", "reason": "unchanged, analyzed 2026-09-06"}],
    )
    kept, excluded = apply_coverage(roster, directive)
    assert [e.ticker for e in kept] == ["BTC-USD", "ETH-USD"]
    assert all(e.roster_reason in {"director_refresh", "director_explore"} for e in kept)
    assert [e.ticker for e in excluded] == ["SOL-USD"]
    assert isinstance(excluded[0], ExcludedTicker)


def test_apply_coverage_never_widens_roster() -> None:
    """A directive ticker that was never on the H4 roster is dropped, not added."""
    roster = [_entry("BTC-USD")]
    directive = CoverageDirective(
        refresh=[{"ticker": "DOGE-USD", "reason": "meme frenzy"}],
        explore=[],
        skip=[{"ticker": "BTC-USD", "reason": "quiet"}],
    )
    kept, excluded = apply_coverage(roster, directive)
    assert [e.ticker for e in kept] == []
    assert "DOGE-USD" not in [e.ticker for e in excluded]


def test_apply_coverage_omitted_ticker_is_excluded() -> None:
    """Rostered tickers the directive does not mention are excluded, never kept."""
    roster = [_entry("BTC-USD"), _entry("ETH-USD")]
    directive = CoverageDirective(
        refresh=[{"ticker": "BTC-USD", "reason": "stale"}],
        explore=[],
        skip=[],
    )
    kept, excluded = apply_coverage(roster, directive)
    assert [e.ticker for e in kept] == ["BTC-USD"]
    assert [e.ticker for e in excluded] == ["ETH-USD"]
