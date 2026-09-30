"""Mocked unit tests for the luxalgo broker-sdk read-only Alpaca mirror (#4829).

Every test is offline: the "transport" is a canned ``BrokerSnapshot``-shaped dict
mirroring ``@luxalgo/broker-sdk@0.5.1`` ``connect({broker:'alpaca'}).fetchSnapshot()``
output (TypeScript SDK — mirrored, never imported). No live HTTP, no real keys,
no secret material in fixtures. Header pattern follows ``test_alpaca_adapter.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from digiquant.brokers.luxalgo_mirror import (
    enrich_briefing_with_mirror,
    snapshot_to_contracts,
    summarize_mirror,
)

pytestmark = pytest.mark.unit


def _golden_snapshot() -> dict[str, Any]:
    """Port of one SDK ``conformance/vectors/`` Alpaca raw vector (JS floats kept).

    Two accounts, mixed currencies, one short position, three trades — the third
    with no ``executedAt`` so the fetchedAt fallback is pinned.
    """
    return {
        "broker": "alpaca",
        "fetchedAt": "2026-09-30T15:30:00Z",
        "accounts": [
            {
                "id": "alpaca-acct-1",
                "name": "alpaca paper",
                "currency": "usd",
                "equity": 100000.50,
                "cash": 25000.0,
                "positions": [
                    {
                        "symbol": "aapl",
                        "quantity": 10.0,
                        "marketValue": 1050.0,
                        "averageEntryPrice": 100.0,
                    },
                    {
                        "symbol": "TSLA",
                        "quantity": -2.0,
                        "marketValue": -400.5,
                        "averageEntryPrice": 200.25,
                    },
                ],
                "trades": [
                    {
                        "symbol": "AAPL",
                        "side": "buy",
                        "quantity": 10.0,
                        "price": 100.0,
                        "fee": 0.5,
                        "executedAt": "2026-09-30T14:00:00Z",
                    },
                    {
                        "symbol": "TSLA",
                        "side": "sell",
                        "quantity": 2.0,
                        "price": 200.25,
                        "executedAt": "2026-09-30T14:05:00Z",
                    },
                    {
                        "symbol": "MSFT",
                        "side": "buy",
                        "quantity": 5.0,
                        "price": 300.1,
                    },
                ],
            },
            {
                "id": "alpaca-acct-2",
                "name": "euro sleeve",
                "currency": "EUR",
                "equity": 50000.25,
                "cash": 10000.0,
                "positions": [],
                "trades": [],
            },
        ],
    }


class TestSnapshotToContracts:
    def test_account_snapshot_exact_decimals_and_utc(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        snap, _, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        assert snap.account_id == "alpaca-acct-1"
        assert snap.equity == Decimal("100000.5")
        assert snap.cash == Decimal("25000")
        assert snap.currency == "USD"
        assert snap.as_of == datetime(2026, 9, 30, 15, 30, tzinfo=UTC)

    def test_positions_keep_signed_short_and_decimals(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        _, positions, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        by_symbol = {p.symbol: p for p in positions}
        assert by_symbol["AAPL"].quantity == Decimal("10")
        assert by_symbol["AAPL"].avg_entry_price == Decimal("100")
        assert by_symbol["AAPL"].market_value == Decimal("1050")
        assert by_symbol["TSLA"].quantity == Decimal("-2")
        assert by_symbol["TSLA"].avg_entry_price == Decimal("200.25")

    def test_trades_map_to_fills_with_fetched_at_fallback(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        fetched_at = _golden_snapshot()["fetchedAt"]
        _, _, fills = snapshot_to_contracts(account, fetched_at=fetched_at)
        assert len(fills) == 3
        assert fills[0].symbol == "AAPL"
        assert fills[0].quantity == Decimal("10")
        assert fills[0].price == Decimal("100")
        assert fills[0].fee == Decimal("0.5")
        assert fills[0].executed_at == datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
        # Missing executedAt falls back to the snapshot fetchedAt, never naive.
        assert fills[2].symbol == "MSFT"
        assert fills[2].executed_at == datetime(2026, 9, 30, 15, 30, tzinfo=UTC)
        assert fills[2].executed_at.tzinfo is not None

    def test_empty_window_preserved_as_empty_list(self) -> None:
        account = _golden_snapshot()["accounts"][1]
        snap, positions, fills = snapshot_to_contracts(
            account, fetched_at=_golden_snapshot()["fetchedAt"]
        )
        assert snap.currency == "EUR"
        assert snap.equity == Decimal("50000.25")
        assert positions == []
        assert fills == []


class TestSummarizeMirror:
    def test_equity_by_account_and_position_count(self) -> None:
        summary = summarize_mirror(_golden_snapshot())
        assert summary["broker"] == "alpaca"
        assert summary["total_positions"] == 2
        by_id = {row["account_id"]: row for row in summary["accounts"]}
        assert by_id["alpaca-acct-1"]["equity"] == "100000.5"
        assert by_id["alpaca-acct-1"]["position_count"] == 2
        assert by_id["alpaca-acct-2"]["currency"] == "EUR"
        assert by_id["alpaca-acct-2"]["position_count"] == 0


class TestEnrichBriefing:
    def test_enrichment_appends_read_only_section_without_mutating(self) -> None:
        briefing = {"date": "2026-09-30", "body": "Market rallied.", "regime_label": "risk-on"}
        enriched = enrich_briefing_with_mirror(briefing, _golden_snapshot())
        assert enriched["date"] == "2026-09-30"
        assert enriched["regime_label"] == "risk-on"
        assert "Market rallied." in enriched["body"]
        assert "alpaca-acct-1" in enriched["body"]
        assert "read-only" in enriched["body"].lower()
        # Input mapping is untouched; nothing is written into positions.
        assert briefing["body"] == "Market rallied."
        assert "positions" not in enriched
