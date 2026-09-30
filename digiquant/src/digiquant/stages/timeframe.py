"""Consensus timeframe contract for ADR-0030 stage handoffs.

``medium`` and ``long`` are the contract. Every other string is display-only.
"""

from __future__ import annotations

from enum import StrEnum


class ConsensusTimeframe(StrEnum):
    MEDIUM = "medium"
    LONG = "long"


class TimeframeContractError(ValueError):
    """Raised when a caller required a consensus timeframe and none was present."""


def split_timeframe(raw: str | None) -> tuple[ConsensusTimeframe | None, str | None]:
    """Split a hub timeframe string into contract vs display.

    ``medium`` and ``long`` are case-sensitive. ``Medium``, ``1-3M``, blank,
    and ``None`` are not consensus values. A non-empty non-contract string is
    returned as display text and does not raise.
    """
    if raw is None:
        return None, None
    text = raw.strip()
    if text == "":
        return None, None
    if text == ConsensusTimeframe.MEDIUM.value:
        return ConsensusTimeframe.MEDIUM, None
    if text == ConsensusTimeframe.LONG.value:
        return ConsensusTimeframe.LONG, None
    return None, text
