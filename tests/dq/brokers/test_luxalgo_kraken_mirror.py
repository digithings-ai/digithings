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
        assert_account_snapshot(
            snap,
            fetched_at=_golden_snapshot()["fetchedAt"],
            account_id="kraken-spot",
            equity=Decimal("6150"),
            currency="USD",
        )

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
        assert_fills_map_with_fetched_at_fallback(
            fills,
            fetched_at=fetched_at,
            count=2,
            expected=[
                FillExpectation(
                    index=0,
                    symbol="BTC",
                    quantity=Decimal("0.1"),
                    price=Decimal("60000"),
                    fee=Decimal("15.6"),
                    executed_at=datetime(2026, 9, 30, 14, 0, tzinfo=UTC),
                ),
                FillExpectation(
                    index=1, symbol="ADA", price=Decimal("0.45"), falls_back_to_fetched_at=True
                ),
            ],
        )

    def test_position_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"quantity": 0.1, "marketValue": 6000.0, "assetClass": "crypto"},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )

    def test_position_none_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"symbol": None, "quantity": 0.1, "marketValue": 6000.0},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )

    def test_trade_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["trades"] = [
            {"side": "buy", "quantity": 25.0, "price": 0.45},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )


class TestSummarizeMirror:
    def test_equity_by_account_and_position_count(self) -> None:
        summary = summarize_mirror(_golden_snapshot())
        assert_summary_counts(
            summary,
            broker="kraken",
            total_positions=3,
            accounts=[
                AccountExpectation(
                    account_id="kraken-spot", position_count=3, equity="6150.0", currency="USD"
                ),
            ],
        )


class TestEnrichBriefing:
    def test_enrichment_appends_read_only_section_without_mutating(self) -> None:
        briefing = {"date": "2026-09-30", "body": "Market rallied.", "regime_label": "risk-on"}
        original = dict(briefing)
        enriched = enrich_briefing_with_mirror(briefing, _golden_snapshot())
        assert_enrichment_appends_read_only(enriched, briefing, original, account_id="kraken-spot")
