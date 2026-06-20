"""Read helpers for thesis-first Hermes state slots."""

from __future__ import annotations

from typing import Any  # noqa  # scored-lint suppression: heterogeneous graph / dict shapes
from digiquant.olympus.atlas.state import RebalancePayload
from digiquant.olympus.hermes.state import HermesState


def analyst_payloads(state: HermesState) -> dict[str, dict[str, Any]]:
    """Per-ticker unified analyst payloads (H5)."""
    return {
        ticker: {k: v for k, v in payload.items() if k != "_document"}
        for ticker, payload in state.phase_hermes.asset_analysts.items()
    }


def sized_book(state: HermesState) -> RebalancePayload | None:
    """H8 sized portfolio — sole weight owner on the thesis-first path."""
    book = state.phase_hermes.sized_book
    if book is not None:
        return book
    # Legacy strangler: chain-terminal 7E may still populate phase7d_rebalance.
    return state.phase7d_rebalance


def deliberation_summaries(state: HermesState) -> dict[str, dict[str, Any]]:
    """Per-ticker deliberation summaries (H6) — PM-compatible debate shape."""
    out: dict[str, dict[str, Any]] = {}
    for ticker, summary in state.phase_hermes.deliberation_summaries.items():
        if not isinstance(summary, dict):
            continue
        out[ticker] = {
            "ticker": ticker,
            "rounds": summary.get("transcript", summary.get("rounds", [])),
            "bull_thesis": summary.get("bull_thesis") or summary.get("conclusion", ""),
            "bear_thesis": summary.get("bear_thesis") or summary.get("conclusion", ""),
            "bear_case": summary.get("bear_case") or summary.get("bear_thesis"),
            "net_stance": summary.get("net_stance", "neutral"),
            "conviction_delta": summary.get("conviction_delta", 0),
            "carried": summary.get("carried", False),
        }
    return out
