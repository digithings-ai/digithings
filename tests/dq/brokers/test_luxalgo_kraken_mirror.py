"""Mocked unit tests for the luxalgo broker-sdk read-only Kraken mirror (#4847).

Every test is offline: the "transport" is a canned ``BrokerSnapshot``-shaped dict
mirroring ``@luxalgo/broker-sdk@0.5.1`` ``connect({broker:'kraken'}).fetchSnapshot()``
output (TypeScript SDK — mirrored, never imported). No live HTTP, no real keys,
no secret material in fixtures. Header pattern follows ``test_alpaca_adapter.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from digiquant.brokers.luxalgo_kraken_mirror import (
    enrich_briefing_with_mirror,
    snapshot_to_contracts,
    summarize_mirror,
)

pytestmark = pytest.mark.unit


def _golden_snapshot() -> dict[str, Any]:
    """Port of the SDK ``conformance/vectors/kraken`` normalized account.

    Legacy asset codes (``XXBT``, ``ZUSD``) arrive already normalized to
    ``BTC``/``USD`` by the SDK adapter — the fixture carries the
    post-normalization shape, never raw venue codes. ADA carries no
    ``marketValue`` (no USD ticker upstream); two trades added in SDK ``Trade``
    shape — the second with no ``executedAt`` so the fetchedAt fallback is
    pinned.
    """
    return {
        "broker": "kraken",
        "fetchedAt": "2026-09-30T15:30:00Z",
        "accounts": [
            {
                "id": "kraken-spot",
                "name": "Kraken spot",
                "currency": "usd",
                "equity": 6150.0,
                "positions": [
                    {
                        "symbol": "BTC",
                        "quantity": 0.1,
                        "marketValue": 6000.0,
                        "assetClass": "crypto",
                    },
                    {
                        "symbol": "USD",
                        "quantity": 150.0,
                        "marketValue": 150.0,
                        "assetClass": "cash",
                    },
                    {
                        "symbol": "ADA",
                        "quantity": 25.0,
                        "assetClass": "crypto",
                    },
                ],
                "trades": [
                    {
                        "symbol": "BTC",
                        "side": "buy",
                        "quantity": 0.1,
                        "price": 60000.0,
                        "fee": 15.6,
                        "executedAt": "2026-09-30T14:00:00Z",
                    },
                    {
                        "symbol": "ADA",
                        "side": "buy",
                        "quantity": 25.0,
                        "price": 0.45,
                    },
                ],
            },
        ],
    }


class TestSnapshotToContracts:
    def test_account_snapshot_exact_decimals_and_utc(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        snap, _, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        assert snap.account_id == "kraken-spot"
        assert snap.equity == Decimal("6150")
        assert snap.currency == "USD"
        assert snap.as_of == datetime(2026, 9, 30, 15, 30, tzinfo=UTC)

    def test_unpriced_position_maps_market_value_zero(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        _, positions, _ = snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])
        by_symbol = {p.symbol: p for p in positions}
        assert by_symbol["BTC"].quantity == Decimal("0.1")
        assert by_symbol["BTC"].market_value == Decimal("6000")
        # ADA has no USD ticker upstream: zero, never a fabricated price.
        assert by_symbol["ADA"].quantity == Decimal("25")
        assert by_symbol["ADA"].market_value == Decimal("0")

    def test_sdk_side_symbol_normalization_xxbt_to_btc(self) -> None:
        """Legacy Kraken codes normalize upstream; the mirror passes through.

        The SDK adapter maps ``XXBT`` → ``BTC`` before the snapshot reaches
        this module (conformance vector ``kraken.json`` pins it: raw
        ``balances`` key ``XXBT`` becomes position symbol ``BTC``). The mirror
        therefore asserts the normalized symbol it receives and performs no
        legacy-code mapping of its own — a raw venue code would pass through
        untouched rather than be silently remapped here.
        """
        account = _golden_snapshot()["accounts"][0]
        _, positions, fills = snapshot_to_contracts(
            account, fetched_at=_golden_snapshot()["fetchedAt"]
        )
        assert "BTC" in {p.symbol for p in positions}
        assert "XXBT" not in {p.symbol for p in positions}
        assert fills[0].symbol == "BTC"
        # Pass-through proof: the mirror never maps legacy codes itself.
        legacy = dict(account)
        legacy["positions"] = [{"symbol": "XXBT", "quantity": 0.1, "marketValue": 6000.0}]
        legacy["trades"] = []
        _, legacy_positions, _ = snapshot_to_contracts(
            legacy, fetched_at=_golden_snapshot()["fetchedAt"]
        )
        assert legacy_positions[0].symbol == "XXBT"

    def test_trades_map_to_fills_with_fetched_at_fallback(self) -> None:
        account = _golden_snapshot()["accounts"][0]
        fetched_at = _golden_snapshot()["fetchedAt"]
        _, _, fills = snapshot_to_contracts(account, fetched_at=fetched_at)
        assert len(fills) == 2
        assert fills[0].symbol == "BTC"
        assert fills[0].quantity == Decimal("0.1")
        assert fills[0].price == Decimal("60000")
        assert fills[0].fee == Decimal("15.6")
        assert fills[0].executed_at == datetime(2026, 9, 30, 14, 0, tzinfo=UTC)
        # Missing executedAt falls back to the snapshot fetchedAt, never naive.
        assert fills[1].symbol == "ADA"
        assert fills[1].price == Decimal("0.45")
        assert fills[1].executed_at == datetime(2026, 9, 30, 15, 30, tzinfo=UTC)
        assert fills[1].executed_at.tzinfo is not None

    def test_position_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"quantity": 0.1, "marketValue": 6000.0, "assetClass": "crypto"},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])

    def test_position_none_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"symbol": None, "quantity": 0.1, "marketValue": 6000.0},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])

    def test_trade_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["trades"] = [
            {"side": "buy", "quantity": 25.0, "price": 0.45},
        ]
        with pytest.raises(ValueError, match="symbol"):
            snapshot_to_contracts(account, fetched_at=_golden_snapshot()["fetchedAt"])


class TestSummarizeMirror:
    def test_equity_by_account_and_position_count(self) -> None:
        summary = summarize_mirror(_golden_snapshot())
        assert summary["broker"] == "kraken"
        assert summary["total_positions"] == 3
        by_id = {row["account_id"]: row for row in summary["accounts"]}
        assert by_id["kraken-spot"]["equity"] == "6150.0"
        assert by_id["kraken-spot"]["position_count"] == 3
        assert by_id["kraken-spot"]["currency"] == "USD"


class TestEnrichBriefing:
    def test_enrichment_appends_read_only_section_without_mutating(self) -> None:
        briefing = {"date": "2026-09-30", "body": "Market rallied.", "regime_label": "risk-on"}
        enriched = enrich_briefing_with_mirror(briefing, _golden_snapshot())
        assert enriched["date"] == "2026-09-30"
        assert enriched["regime_label"] == "risk-on"
        assert "Market rallied." in enriched["body"]
        assert "kraken-spot" in enriched["body"]
        assert "read-only" in enriched["body"].lower()
        # Input mapping is untouched; nothing is written into positions.
        assert briefing["body"] == "Market rallied."
        assert "positions" not in enriched
