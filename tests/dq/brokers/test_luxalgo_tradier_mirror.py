"""Mocked unit tests for the luxalgo broker-sdk read-only Tradier mirror (#4848).

Every test is offline: the "transport" is a canned ``BrokerSnapshot``-shaped dict
mirroring ``@luxalgo/broker-sdk@0.5.1`` ``connect({broker:'tradier'}).fetchSnapshot()``
output (TypeScript SDK — mirrored, never imported). No live HTTP, no real keys,
no secret material in fixtures. Header pattern follows ``test_alpaca_adapter.py``.

Mirror only: Tradier ``supportsBars`` in the SDK, but no bars code lives here —
positions/trades normalization only.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from digiquant.brokers.luxalgo_tradier_mirror import (
    enrich_briefing_with_mirror,
    snapshot_to_contracts,
    summarize_mirror,
)

from tests.dq.brokers.luxalgo_mirror_cases import (
    AccountExpectation,
    FillExpectation,
    assert_account_snapshot,
    assert_enrichment_appends_read_only,
    assert_fills_map_with_fetched_at_fallback,
    assert_missing_symbol_raises,
    assert_summary_counts,
)

pytestmark = pytest.mark.unit


def _golden_snapshot() -> dict[str, Any]:
    """Port of the SDK ``conformance/vectors/tradier`` normalized account.

    Upstream quirks already resolved by the SDK adapter: the single-position
    object arrives as an array, dividend events are filtered out (trades only),
    sells arrive as ``side: sell`` with a positive quantity, and the position
    carries ``averageEntryPrice`` (cost basis per unit) with no ``marketValue``
    — Tradier reports cost basis, not market value. A third trade with no
    ``executedAt`` pins the fetchedAt fallback.
    """
    return {
        "broker": "tradier",
        "fetchedAt": "2026-08-06T12:00:00Z",
        "accounts": [
            {
                "id": "VA000001",
                "name": "Tradier VA000001",
                "currency": "usd",
                "equity": 25000.5,
                "cash": 5000.0,
                "positions": [
                    {
                        "symbol": "aapl",
                        "quantity": 10.0,
                        "averageEntryPrice": 150.0,
                        "assetClass": "equity",
                    },
                ],
                "trades": [
                    {
                        "symbol": "SPY",
                        "side": "buy",
                        "quantity": 10.0,
                        "price": 500.0,
                        "executedAt": "2026-08-01T00:00:00.000Z",
                    },
                    {
                        "symbol": "SPY",
                        "side": "sell",
                        "quantity": 10.0,
                        "price": 510.0,
                        "fee": 1.0,
                        "executedAt": "2026-08-05T00:00:00.000Z",
                    },
                    {
                        "symbol": "QQQ",
                        "side": "buy",
                        "quantity": 5.0,
                        "price": 400.25,
                    },
                ],
            },
        ],
    }


class TestSnapshotToContracts:
    def test_account_snapshot_exact_decimals_and_utc(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        snap, _, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        assert_account_snapshot(
            snap,
            fetched_at=_golden_snapshot()["fetchedAt"],
            account_id="VA000001",
            equity=Decimal("25000.5"),
            currency="USD",
            cash=Decimal("5000"),
        )

    def test_position_without_market_value_stays_zero(self) -> None:
        """Tradier reports cost basis, not market value — never fabricated."""
        account = _golden_snapshot()["accounts"][0]
        _, positions, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        assert len(positions) == 1
        assert positions[0].symbol == "AAPL"
        assert positions[0].quantity == Decimal("10")
        assert positions[0].avg_entry_price == Decimal("150")
        assert positions[0].market_value == Decimal("0")

    def test_sell_side_preserved_with_positive_quantity(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        _, _, fills = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        assert len(fills) == 3
        assert fills[1].symbol == "SPY"
        assert fills[1].quantity == Decimal("10")
        assert fills[1].price == Decimal("510")
        assert fills[1].fee == Decimal("1")
        assert fills[1].executed_at == datetime(2026, 8, 5, 0, 0, tzinfo=UTC)

    def test_trades_map_to_fills_with_fetched_at_fallback(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        fetched_at = _golden_snapshot()["fetchedAt"]
        _, _, fills = snapshot_to_contracts(account, fetched_at=fetched_at)
        assert_fills_map_with_fetched_at_fallback(
            fills,
            fetched_at=fetched_at,
            expected=[
                FillExpectation(
                    index=0,
                    symbol="SPY",
                    quantity=Decimal("10"),
                    price=Decimal("500"),
                    executed_at=datetime(2026, 8, 1, 0, 0, tzinfo=UTC),
                ),
                FillExpectation(
                    index=2, symbol="QQQ", price=Decimal("400.25"), falls_back_to_fetched_at=True
                ),
            ],
        )

    def test_no_fx_fabrication_single_currency_preserved(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        snap, _, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        assert snap.currency == "USD"
        assert snap.equity == Decimal("25000.5")

    def test_position_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"quantity": 10.0, "averageEntryPrice": 150.0, "assetClass": "equity"},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )

    def test_position_none_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"symbol": None, "quantity": 10.0, "averageEntryPrice": 150.0},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )

    def test_trade_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["trades"] = [
            {"side": "buy", "quantity": 5.0, "price": 400.25},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )


class TestSummarizeMirror:
    def test_equity_by_account_and_position_count(self) -> None:
        summary = summarize_mirror(_golden_snapshot())
        assert_summary_counts(
            summary,
            broker="tradier",
            total_positions=1,
            accounts=[
                AccountExpectation(
                    account_id="VA000001", position_count=1, equity="25000.5", currency="USD"
                ),
            ],
        )


class TestEnrichBriefing:
    def test_enrichment_appends_read_only_section_without_mutating(self) -> None:
        briefing = {"date": "2026-08-06", "body": "Market rallied.", "regime_label": "risk-on"}
        original = dict(briefing)
        enriched = enrich_briefing_with_mirror(briefing, _golden_snapshot())
        assert_enrichment_appends_read_only(enriched, briefing, original, account_id="VA000001")
