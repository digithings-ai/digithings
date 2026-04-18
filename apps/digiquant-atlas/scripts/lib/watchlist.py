"""Parse watchlist tickers from config/watchlist.md (no heavy imports)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
WATCHLIST_PATH = ROOT / "config" / "watchlist.md"

EXCLUDE = frozenset({"ETF", "DXY", "VIX"})


def parse_tickers_from_watchlist() -> list[str]:
    """Extract unique ticker symbols from markdown table rows."""
    if not WATCHLIST_PATH.exists():
        return []
    text = WATCHLIST_PATH.read_text(encoding="utf-8")
    tickers = re.findall(
        r"^\|\s*([A-Z][A-Z0-9]{1,9}(?:-[A-Z]{2,4})?)\s*\|",
        text,
        re.MULTILINE,
    )
    seen: set[str] = set()
    result: list[str] = []
    for t in tickers:
        if t not in seen and t not in EXCLUDE:
            seen.add(t)
            result.append(t)
    return result
