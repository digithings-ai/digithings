"""Shared assertions for the luxalgo mirror venue suites.

Every venue adapter (``alpaca``, ``coinbase``, ``kraken``, ``tradier``) mirrors
the same SDK snapshot shape into the same read-only contracts, so the four
venue suites run the same seven checks with venue-specific values. The
skeleton lives here; the venue files keep the data.

The helpers take the expectations explicitly on purpose: the contract skips a
trade with a non-positive quantity or price, and a trade without a fee yields
``fee=None`` — neither is safe to derive from the snapshot.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest


def expected_as_of(fetched_at: str) -> datetime:
    """The UTC instant the mirror stamps a snapshot with."""
    text = str(fetched_at).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def assert_account_snapshot(
    snap: Any,
    *,
    fetched_at: str,
    account_id: str,
    equity: Decimal,
    currency: str,
    cash: Decimal | None = None,
) -> None:
    """The account contract: exact decimals, canonical currency, UTC timestamp."""
    assert snap.account_id == account_id
    assert snap.equity == equity
    if cash is not None:
        assert snap.cash == cash
    assert snap.currency == currency
    assert snap.as_of == expected_as_of(fetched_at)


@dataclass(frozen=True)
class FillExpectation:
    """One expected fill. ``None`` means "this field is not part of the check"."""

    index: int
    symbol: str | None = None
    quantity: Decimal | None = None
    price: Decimal | None = None
    fee: Decimal | None = None
    executed_at: datetime | None = None
    falls_back_to_fetched_at: bool = False


def assert_fills_map_with_fetched_at_fallback(
    fills: list[Any],
    *,
    fetched_at: str,
    expected: list[FillExpectation],
    count: int | None = None,
) -> None:
    """Trades map to fills; a trade with no ``executedAt`` falls back to ``fetchedAt``."""
    if count is not None:
        assert len(fills) == count
    for exp in expected:
        fill = fills[exp.index]
        if exp.symbol is not None:
            assert fill.symbol == exp.symbol
        if exp.quantity is not None:
            assert fill.quantity == exp.quantity
        if exp.price is not None:
            assert fill.price == exp.price
        if exp.fee is not None:
            assert fill.fee == exp.fee
        if exp.falls_back_to_fetched_at:
            assert fill.executed_at == expected_as_of(fetched_at)
            assert fill.executed_at.tzinfo is not None
        elif exp.executed_at is not None:
            assert fill.executed_at == exp.executed_at


def assert_missing_symbol_raises(
    contract: Callable[..., Any],
    account: Mapping[str, Any],
    fetched_at: str,
) -> None:
    """A position or trade without a symbol is refused, never guessed."""
    with pytest.raises(ValueError, match="symbol"):
        contract(account, fetched_at=fetched_at)


@dataclass(frozen=True)
class AccountExpectation:
    """One account row in the mirror summary."""

    account_id: str
    position_count: int
    equity: str | None = None
    currency: str | None = None


def assert_summary_counts(
    summary: Mapping[str, Any],
    *,
    broker: str,
    total_positions: int,
    accounts: list[AccountExpectation],
) -> None:
    """The summary groups equity and position counts per account."""
    assert summary["broker"] == broker
    assert summary["total_positions"] == total_positions
    by_id = {row["account_id"]: row for row in summary["accounts"]}
    for account in accounts:
        row = by_id[account.account_id]
        assert row["position_count"] == account.position_count
        if account.equity is not None:
            assert row["equity"] == account.equity
        if account.currency is not None:
            assert row["currency"] == account.currency


def assert_enrichment_appends_read_only(
    enriched: Mapping[str, Any],
    briefing: Mapping[str, Any],
    original: Mapping[str, Any],
    *,
    account_id: str,
) -> None:
    """Enrichment appends a read-only section and never mutates the input."""
    assert enriched["date"] == original["date"]
    assert enriched["regime_label"] == original["regime_label"]
    assert original["body"] in enriched["body"]
    assert account_id in enriched["body"]
    assert "read-only" in enriched["body"].lower()
    # The input mapping is untouched; nothing is written into positions.
    assert briefing == original
    assert "positions" not in enriched
