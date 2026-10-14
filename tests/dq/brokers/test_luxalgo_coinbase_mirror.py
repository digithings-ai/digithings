"""Mocked unit tests for the luxalgo broker-sdk read-only Coinbase mirror (#4843).

Every test is offline: the "transport" is a canned ``BrokerSnapshot``-shaped dict
mirroring ``@luxalgo/broker-sdk@0.5.1`` ``connect({broker:'coinbase'}).fetchSnapshot()``
output (TypeScript SDK — mirrored, never imported). No live HTTP, no real keys,
no secret material in fixtures. Header pattern follows ``test_alpaca_adapter.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from digiquant.brokers.luxalgo_coinbase_mirror import (
    enrich_briefing_with_mirror,
    snapshot_to_contracts,
    summarize_mirror,
)

pytestmark = pytest.mark.unit


def _golden_snapshot() -> dict[str, Any]:
    """Port of the SDK ``conformance/vectors/coinbase`` normalized account.

    Wallet balances valued via public USD rates (value = quantity / rate); USD
    wallets are cash rows, coins are crypto, zero balances drop out upstream.
    One cash-class ``USD`` position included; two trades added in SDK ``Trade``
    shape — the second with no ``executedAt`` so the fetchedAt fallback is
    pinned. A second EUR account pins no-FX fabrication across currencies.
    """
    return {
        "broker": "coinbase",
        "fetchedAt": "2026-09-30T15:30:00Z",
        "accounts": [
            {
                "id": "coinbase-portfolio",
                "name": "Coinbase",
                "currency": "usd",
                "equity": 32888.0,
                "positions": [
                    {
                        "symbol": "btc",
                        "quantity": 0.5,
                        "marketValue": 32768.0,
                        "assetClass": "crypto",
                    },
                    {
                        "symbol": "USD",
                        "quantity": 120.0,
                        "marketValue": 120.0,
                        "assetClass": "cash",
                    },
                ],
                "trades": [
                    {
                        "symbol": "BTC",
                        "side": "buy",
                        "quantity": 0.5,
                        "price": 65000.0,
                        "fee": 12.5,
                        "executedAt": "2026-09-30T14:00:00Z",
                    },
                    {
                        "symbol": "ETH",
                        "side": "buy",
                        "quantity": 2.0,
                        "price": 2500.1,
                    },
                ],
            },
            {
                "id": "coinbase-eur",
                "name": "Coinbase EUR",
                "currency": "EUR",
                "equity": 1000.25,
                "cash": 1000.25,
                "positions": [],
                "trades": [],
            },
        ],
    }


class TestSnapshotToContracts:
    def test_account_snapshot_exact_decimals_and_utc(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        snap, _, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        assert snap.account_id == "coinbase-portfolio"
        assert snap.equity == Decimal("32888")
        assert snap.currency == "USD"
        assert snap.as_of == datetime(2026, 9, 30, 15, 30, tzinfo=UTC)

    def test_positions_include_cash_row_with_decimals(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        _, positions, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        by_symbol = {p.symbol: p for p in positions}
        assert by_symbol["BTC"].quantity == Decimal("0.5")
        assert by_symbol["BTC"].market_value == Decimal("32768")
        assert by_symbol["USD"].quantity == Decimal("120")
        assert by_symbol["USD"].market_value == Decimal("120")

    def test_trades_map_to_fills_with_fetched_at_fallback(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        fetched_at = _golden_snapshot()["fetchedAt"]
        _, _, fills = snapshot_to_contracts(account, fetched_at=fetched_at)
        assert len(fills) == 2
        assert fills[0].symbol == "BTC"
        assert fills[0].quantity == Decimal("0.5")
        assert fills[0].price == Decimal("65000")
        assert fills[0].fee == Decimal("12.5")
        assert fills[0].executed_at == datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
        # Missing executedAt falls back to the snapshot fetchedAt, never naive.
        assert fills[1].symbol == "ETH"
        assert fills[1].executed_at == datetime(2026, 9, 30, 15, 30, tzinfo=UTC)
        assert fills[1].executed_at.tzinfo is not None

    def test_no_fx_fabrication_across_currencies(self) -> None:
        first, second = _golden_snapshot()["accounts"]
        fetched_at = _golden_snapshot()["fetchedAt"]
        snap_usd, _, _ = snapshot_to_contracts(first, fetched_at=fetched_at)
        snap_eur, positions_eur, fills_eur = snapshot_to_contracts(second, fetched_at=fetched_at)
        assert snap_usd.currency == "USD"
        assert snap_usd.equity == Decimal("32888")
        assert snap_eur.currency == "EUR"
        assert snap_eur.equity == Decimal("1000.25")
        assert positions_eur == []
        assert fills_eur == []

    def test_position_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"quantity": 0.5, "marketValue": 32768.0, "assetClass": "crypto"},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])

    def test_position_none_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"symbol": None, "quantity": 0.5, "marketValue": 32768.0},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])

    def test_trade_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["trades"] = [
            {"side": "buy", "quantity": 2.0, "price": 2500.1},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])


class TestSummarizeMirror:
    def test_equity_by_account_and_position_count(self) -> None:
        summary = summarize_mirror(_golden_snapshot())
        assert summary["broker"] == "coinbase"
        assert summary["total_positions"] == 2
        by_id = {row["account_id"]: row for row in summary["accounts"]}
        assert by_id["coinbase-portfolio"]["equity"] == "32888.0"
        assert by_id["coinbase-portfolio"]["position_count"] == 2
        assert by_id["coinbase-eur"]["currency"] == "EUR"
        assert by_id["coinbase-eur"]["position_count"] == 0


class TestEnrichBriefing:
    def test_enrichment_appends_read_only_section_without_mutating(self) -> None:
        briefing = {"date": "2026-09-30", "body": "Market rallied.", "regime_label": "risk-on"}
        enriched = enrich_briefing_with_mirror(briefing, _golden_snapshot())
        assert enriched["date"] == "2026-09-30"
        assert enriched["regime_label"] == "risk-on"
        assert "Market rallied." in enriched["body"]
        assert "coinbase-portfolio" in enriched["body"]
        assert "read-only" in enriched["body"].lower()
        # Input mapping is untouched; nothing is written into positions.
        assert briefing["body"] == "Market rallied."
        assert "positions" not in enriched
