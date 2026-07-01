"""Grounding pre-pass for the `alt-ai-portfolios` segment (#658).

Reads the latest public posts of tracked AI-run portfolio accounts on X via
OpenRouter web search, returning a cited summary to inject into phase_inputs.
Requires ``OPENROUTER_API_KEY``; fails soft to ``None`` otherwise.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any  # noqa  # scored-lint suppression: heterogeneous yaml config

import yaml

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "ai_portfolio_accounts.yaml"


@lru_cache(maxsize=1)
def _config() -> dict[str, Any]:
    with open(_CONFIG, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _build_query(accounts: list[dict[str, Any]], run_date: date, recency_days: int) -> str:
    roster = "; ".join(
        f"@{a['handle']} ({a.get('model', '?')}, {a.get('type', 'portfolio')}, "
        f"weight={a.get('weight', 'low')})"
        for a in accounts
    )
    return (
        f"As of {run_date.isoformat()}, search the web and X (Twitter) for the LATEST posts "
        f"(last {recency_days} days) from each of these AI-run investment accounts: {roster}.\n\n"
        "For EACH account that posted in-window, summarize: current/added/trimmed holdings with "
        "NAMED tickers, direction (long/add/trim/exit), any stated conviction, overall stance "
        "(risk-on/off), and the date. Cite each claim with the specific post URL — do not "
        "report a holding you cannot cite. If an account did not post in-window or has no equity "
        "holdings, say so explicitly (do not infer).\n\n"
        "Then give a CROSS-ACCOUNT read: consensus tickers (named by 2+ accounts), notable "
        "divergences, and the implied SECTOR tilt (roll the stock picks up to sectors, e.g. "
        "semis/software/energy). Weight higher-conviction, higher-activity accounts more; flag "
        "low-follower or stale accounts as weak. Bullet points; keep it tight."
    )


def fetch_ai_portfolio_grounding(
    *,
    model: str,
    run_date: date,
) -> dict[str, Any] | None:
    """Return ``{"summary", "sources", "accounts", "as_of"}`` or ``None`` (ungrounded)."""
    if not model.startswith("openrouter/"):
        return None
    cfg = _config()
    accounts = list(cfg.get("accounts", []))
    if not accounts:
        return None
    recency = int(cfg.get("recency_days", 7))
    max_results = int(cfg.get("max_search_results", 16))
    from digigraph.llm_client import openrouter_web_search

    result = openrouter_web_search(
        model,
        _build_query(accounts, run_date, recency),
        max_results=max_results,
        engine="exa",
    )
    if result is None:
        return None
    summary, sources = result
    if not summary.strip():
        return None
    return {
        "summary": summary,
        "sources": sources,
        "accounts": [a["handle"] for a in accounts],
        "as_of": run_date.isoformat(),
    }
