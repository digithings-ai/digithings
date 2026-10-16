"""Attribution + external-link conventions for Gloomberb-sourced values (§7).

Canonical attribution is **"Sourced from Gloomberb"** plus the free-tier delay
notice wherever a value is rendered outside the terminal. Deep links use the
``?ticker=`` form - there is no bare-path symbol route
(``research-entry.ts``; spec §7).
"""

from __future__ import annotations

from urllib.parse import quote

__all__ = [
    "GLOOMBERB_ATTRIBUTION",
    "GLOOMBERB_DELAY_NOTICE",
    "GLOOMBERB_TERMINAL_URL",
    "attribution_fields",
    "terminal_ticker_url",
]

GLOOMBERB_ATTRIBUTION = "Sourced from Gloomberb"
GLOOMBERB_DELAY_NOTICE = "Data delayed up to 15 minutes"
GLOOMBERB_TERMINAL_URL = "https://term.gloom.sh/"


def terminal_ticker_url(symbol: str) -> str:
    """Deep link to the Gloomberb terminal page for *symbol* (§7)."""
    return f"{GLOOMBERB_TERMINAL_URL}?ticker={quote(symbol.strip(), safe='')}"


def attribution_fields(symbol: str | None = None) -> dict[str, str]:
    """The §7 attribution block appended to every Gloomberb tool payload."""
    fields = {
        "attribution": GLOOMBERB_ATTRIBUTION,
        "delay_notice": GLOOMBERB_DELAY_NOTICE,
    }
    if symbol:
        fields["source_url"] = terminal_ticker_url(symbol)
    return fields
