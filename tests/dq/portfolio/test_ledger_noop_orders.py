"""NO_OP decisions must not mint lot-true-up orders (#ledger 0.00pp Activity).

House 2026-09-01 booked FXI/VGK/XLF paper fills of ~0.05–0.14 shares while the
displayed weight stayed 5.0/25.0/20.0. ``_decision`` already classifies that
move as NO_OP (no-trade band); orders still minted because ``_shares`` only
checked quantity > 0.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from digiquant.portfolio.models.portfolio_ledger import DecisionAction
from digiquant.portfolio.writers.ledger_io import (
    _decision,
    _order_quantity_for_move,
    _shares,
)

pytestmark = pytest.mark.unit

_PREFS = {"rebalance_threshold_pct": 3, "rebalance_rel_band_pct": 20}


class TestNoOpDoesNotMintOrders:
    def test_decision_is_noop_inside_no_trade_band(self) -> None:
        action, _reason = _decision(
            symbol="FXI",
            prior_pct=5.0,
            target_pct=5.02,
            preferences=_PREFS,
        )
        assert action is DecisionAction.NO_OP

    def test_shares_alone_would_still_be_positive(self) -> None:
        """The hole: a 0.02pp true-up is a real share count at house NAV."""
        qty = _shares(delta_pct=0.02, nav=24_700.0, close=35.36)
        assert qty > 0

    def test_noop_order_quantity_is_zero_even_when_shares_would_be_positive(self) -> None:
        qty = _order_quantity_for_move(
            action=DecisionAction.NO_OP,
            target_pct=5.02,
            prior_pct=5.0,
            nav=24_700.0,
            close=35.36,
        )
        assert qty == Decimal(0)

    def test_add_still_mints_a_positive_quantity(self) -> None:
        qty = _order_quantity_for_move(
            action=DecisionAction.ADD,
            target_pct=10.0,
            prior_pct=5.0,
            nav=24_700.0,
            close=35.36,
        )
        assert qty == _shares(delta_pct=5.0, nav=24_700.0, close=35.36)
        assert qty > 0
