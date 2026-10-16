"""Opt-in live smoke for the Gloomberb client (spec §12.4).

Never hits the network in the default suite: the module is marked
``integration`` and skipped unless the operator explicitly sets
``GLOOMBERB_LIVE_SMOKE=1``. When enabled it performs one anonymous quote
against ``https://api.gloom.sh`` and asserts the envelope contract holds.
"""

from __future__ import annotations

import os

import pytest

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("GLOOMBERB_LIVE_SMOKE") != "1",
        reason="opt-in live smoke; set GLOOMBERB_LIVE_SMOKE=1 to run",
    ),
]


def test_live_anonymous_quote_smoke() -> None:
    from digiquant.data.gloomberb import GloomberbClient, QuoteResult

    with GloomberbClient(enabled=True) as client:
        envelope = client.quote({"symbol": "AAPL"})

    assert isinstance(envelope.data, QuoteResult), f"unexpected envelope: {envelope.data}"
    assert envelope.data.quote is not None
    assert envelope.data.quote.symbol
    assert envelope.provider_id == "gloomberb-cloud"
