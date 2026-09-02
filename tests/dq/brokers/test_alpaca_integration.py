"""Live Alpaca paper integration tests (K1) — excluded from CI.

Marked ``alpaca_paper`` and skipped unless ``ALPACA_PAPER_KEY_ID`` and
``ALPACA_PAPER_SECRET`` are set. Never collected by ``pytest -m unit``.
"""

from __future__ import annotations

import os
from decimal import Decimal

import pytest
from digiquant.brokers.alpaca import AlpacaAdapter, ApiKeyAuth
from digiquant.brokers.contracts import BrokerOrderRequest, OrderSide, TimeInForce

pytestmark = [
    pytest.mark.alpaca_paper,
    pytest.mark.skipif(
        not (os.environ.get("ALPACA_PAPER_KEY_ID") and os.environ.get("ALPACA_PAPER_SECRET")),
        reason="ALPACA_PAPER_KEY_ID / ALPACA_PAPER_SECRET not set",
    ),
]


@pytest.fixture
def paper_adapter() -> AlpacaAdapter:
    return AlpacaAdapter(
        auth=ApiKeyAuth(
            key_id=os.environ["ALPACA_PAPER_KEY_ID"],
            secret=os.environ["ALPACA_PAPER_SECRET"],
        )
    )


def test_paper_account_snapshot(paper_adapter: AlpacaAdapter) -> None:
    paper_adapter.connect()
    snap = paper_adapter.get_account()
    assert snap.account_id
    assert snap.currency == "USD"
    assert snap.equity is not None


def test_paper_submit_and_cancel_tiny_order(paper_adapter: AlpacaAdapter) -> None:
    """Submits a tiny notional DAY market order then cancels if still open.

    Destructive against the paper book — only runs when env keys are present.
    """
    req = BrokerOrderRequest(
        client_order_id=f"k1-itest-{os.getpid()}",
        symbol="AAPL",
        side=OrderSide.BUY,
        notional=Decimal("1.00"),
        time_in_force=TimeInForce.DAY,
    )
    ack = paper_adapter.submit_order(req)
    assert ack.external_order_id
    try:
        paper_adapter.cancel_order(ack.external_order_id)
    except Exception:
        # Already filled/canceled on paper is acceptable for this smoke.
        pass
