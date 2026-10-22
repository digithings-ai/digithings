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
        assert_account_snapshot(
            snap,
            fetched_at=_golden_snapshot()["fetchedAt"],
            account_id="coinbase-portfolio",
            equity=Decimal("32888"),
            currency="USD",
        )

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
        assert_fills_map_with_fetched_at_fallback(
            fills,
            fetched_at=fetched_at,
            count=2,
            expected=[
                FillExpectation(
                    index=0,
                    symbol="BTC",
                    quantity=Decimal("0.5"),
                    price=Decimal("65000"),
                    fee=Decimal("12.5"),
                    executed_at=datetime(2026, 9, 30, 14, 0, tzinfo=UTC),
                ),
                FillExpectation(index=1, symbol="ETH", falls_back_to_fetched_at=True),
            ],
        )

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
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )

    def test_position_none_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["positions"] = [
            {"symbol": None, "quantity": 0.5, "marketValue": 32768.0},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )

    def test_trade_missing_symbol_raises(self) -> None:
        account = dict(_golden_snapshot()["accounts"][0])
        account["trades"] = [
            {"side": "buy", "quantity": 2.0, "price": 2500.1},
        ]
        assert_missing_symbol_raises(
            snapshot_to_contracts, account, _golden_snapshot()["fetchedAt"]
        )


class TestSummarizeMirror:
    def test_equity_by_account_and_position_count(self) -> None:
        summary = summarize_mirror(_golden_snapshot())
        assert_summary_counts(
            summary,
            broker="coinbase",
            total_positions=2,
            accounts=[
                AccountExpectation(account_id="coinbase-eur", position_count=0, currency="EUR"),
                AccountExpectation(
                    account_id="coinbase-portfolio", position_count=2, equity="32888.0"
                ),
            ],
        )


class TestEnrichBriefing:
    def test_enrichment_appends_read_only_section_without_mutating(self) -> None:
        briefing = {"date": "2026-09-30", "body": "Market rallied.", "regime_label": "risk-on"}
        original = dict(briefing)
        enriched = enrich_briefing_with_mirror(briefing, _golden_snapshot())
        assert_enrichment_appends_read_only(
            enriched, briefing, original, account_id="Market rallied."
        )
