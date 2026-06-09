"""Grounding pre-pass for the `alt-ai-portfolios` segment via xAI x_search (#658).

Reads the LATEST posts of the tracked AI-run portfolio/aggregator accounts on X and
returns a cited summary (per-account holdings/changes + cross-account consensus + sector
tilt) to inject into the segment's phase_inputs. A proxy for what other AI investment
systems are picking. xAI-only; fails soft to ``None`` (ungrounded) otherwise.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any  # noqa  # scored-lint suppression: heterogeneous yaml config

import yaml

from digigraph.llm import x_search

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
        f"As of {run_date.isoformat()}, read the LATEST posts (last {recency_days} days) of each "
        f"of these AI-run / AI-driven investment accounts on X: {roster}.\n\n"
        "For EACH account that posted in-window, summarize: current/added/trimmed holdings with "
        "NAMED tickers, direction (long/add/trim/exit), any stated conviction, overall stance "
        "(risk-on/off), and the date. Cite each claim with the specific X post URL — do not "
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
    cfg = _config()
    accounts = list(cfg.get("accounts", []))
    if not accounts:
        return None
    recency = int(cfg.get("recency_days", 7))
    max_results = int(cfg.get("max_search_results", 16))
    result = x_search(model, _build_query(accounts, run_date, recency), max_results=max_results)
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
