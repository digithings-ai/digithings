"""Prediction-market payload fixtures shared by the gloomberb tool suites.

The Polymarket Gamma event, the Kalshi event and the KXFED rate ladder are
the same wire shapes in three suites. One definition each, handed out as a
fresh copy so a suite that mutates its payload cannot reach into another's.
"""

from __future__ import annotations

import copy
from typing import Any

_GAMMA_EVENT: dict[str, Any] = {
    "id": "1001",
    "title": "Fed December decision",
    "slug": "fed-december-decision",
    "volume": "9999.0",
    "tags": [{"label": "Macro"}],
    "markets": [
        {
            "question": "25bp hike in December?",
            "outcomes": '["Yes", "No"]',
            "outcomePrices": '["0.25", "0.75"]',
            "volume": "1234.5",
            "liquidity": "567.8",
            "endDate": "2026-12-16T00:00:00Z",
        }
    ],
}

_KALSHI_EVENT: dict[str, Any] = {
    "event_ticker": "FED-26",
    "title": "Fed December decision",
    "category": "Economics",
    "markets": [
        {
            "ticker": "FED-26-Y1",
            "yes_bid": 24,
            "yes_ask": 26,
            "last_price": 25,
            "volume": 1000,
            "open_interest": 500,
            "close_time": "2026-12-16T00:00:00Z",
            "status": "open",
        }
    ],
}

_KXFED_LADDER: tuple[dict[str, Any], ...] = (
    {
        "ticker": "KXFED-26DEC-450",
        "event_ticker": "KXFED-26DEC",
        "floor_strike": 4.5,
        "strike_type": "greater",
        "yes_bid": 90,
        "yes_ask": 92,
        "last_price": 91,
        "close_time": "2026-12-16T00:00:00Z",
        "status": "open",
    },
    {
        "ticker": "KXFED-26DEC-475",
        "event_ticker": "KXFED-26DEC",
        "floor_strike": 4.75,
        "strike_type": "greater",
        "yes_bid": 40,
        "yes_ask": 42,
        "last_price": 41,
        "close_time": "2026-12-16T00:00:00Z",
        "status": "open",
    },
    {
        "ticker": "KXFED-26DEC-500",
        "event_ticker": "KXFED-26DEC",
        "floor_strike": 5.0,
        "strike_type": "greater",
        "yes_bid": 9,
        "yes_ask": 11,
        "last_price": 10,
        "close_time": "2026-12-16T00:00:00Z",
        "status": "open",
    },
)


def gamma_events() -> list[dict[str, Any]]:
    """The Polymarket Gamma event the prediction-markets client reads."""
    return copy.deepcopy([_GAMMA_EVENT])


def kalshi_events() -> dict[str, Any]:
    """The Kalshi trade-api event envelope the client reads."""
    return {"events": copy.deepcopy([_KALSHI_EVENT])}


def kxfed_markets() -> list[dict[str, Any]]:
    """The KXFED rate ladder (cents wire) the rate-path composition reads."""
    return copy.deepcopy(list(_KXFED_LADDER))
