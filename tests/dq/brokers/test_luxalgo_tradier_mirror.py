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
        assert snap.account_id == "VA000001"
        assert snap.equity == Decimal("25000.5")
        assert snap.cash == Decimal("5000")
        assert snap.currency == "USD"
        assert snap.as_of == datetime(2026, 8, 6, 12, 0, tzinfo=UTC)

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
        assert fills[0].symbol == "SPY"
        assert fills[0].quantity == Decimal("10")
        assert fills[0].price == Decimal("500")
        assert fills[0].executed_at == datetime(2026, 8, 1, 0, 0, tzinfo=UTC)
        # Missing executedAt falls back to the snapshot fetchedAt, never naive.
        assert fills[2].symbol == "QQQ"
        assert fills[2].price == Decimal("400.25")
        assert fills[2].executed_at == datetime(2026, 8, 6, 12, 0, tzinfo=UTC)
        assert fills[2].executed_at.tzinfo is not None

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
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])

    def test_position_none_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"symbol": None, "quantity": 10.0, "averageEntryPrice": 150.0},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])

    def test_trade_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["trades"] = [
            {"side": "buy", "quantity": 5.0, "price": 400.25},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])


class TestSummarizeMirror:
    def test_equity_by_account_and_position_count(self) -> None:
        summary = summarize_mirror(_golden_snapshot())
        assert summary["broker"] == "tradier"
        assert summary["total_positions"] == 1
        by_id = {row["account_id"]: row for row in summary["accounts"]}
        assert by_id["VA000001"]["equity"] == "25000.5"
        assert by_id["VA000001"]["position_count"] == 1
        assert by_id["VA000001"]["currency"] == "USD"


class TestEnrichBriefing:
    def test_enrichment_appends_read_only_section_without_mutating(self) -> None:
        briefing = {"date": "2026-08-06", "body": "Market rallied.", "regime_label": "risk-on"}
        enriched = enrich_briefing_with_mirror(briefing, _golden_snapshot())
        assert enriched["date"] == "2026-08-06"
        assert enriched["regime_label"] == "risk-on"
        assert "Market rallied." in enriched["body"]
        assert "VA000001" in enriched["body"]
        assert "read-only" in enriched["body"].lower()
        # Input mapping is untouched; nothing is written into positions.
        assert briefing["body"] == "Market rallied."
        assert "positions" not in enriched
