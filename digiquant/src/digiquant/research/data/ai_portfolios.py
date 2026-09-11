"""Tool-only grounding pre-pass for the `alt-ai-portfolios` segment (#658 / #2567 / #3859).

Reads the latest public posts of tracked AI-run portfolio accounts on X via the
first-party digisearch ``web_search`` tool scoped to
``include_domains=["x.com", "twitter.com"]``, returning a cited summary to
inject into phase_inputs. There is no synthesis fallback: a missing roster,
empty results, and tool errors all raise :exc:`DashboardWebSearchError`.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import (
    Any,  # score:allow untyped any — scored-lint suppression: heterogeneous yaml config
)

import yaml

from digiquant.research.data.web_grounding import DashboardWebSearchError, call_web_search_tool

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "ai_portfolio_accounts.yaml"

# X-leg domain scope on the first-party web_search tool call.
_X_DOMAINS = ["x.com", "twitter.com"]


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
) -> dict[str, Any]:
    """Return ``{"summary", "sources", "accounts", "as_of"}`` or raise.

    Tool-only: the X leg goes through the first-party ``web_search`` tool
    scoped to x.com / twitter.com. A missing roster, empty results, or a tool
    error raises :exc:`DashboardWebSearchError` — never ``None``. ``model`` is
    accepted for caller compatibility and ignored: grounding comes from the
    tool, not a synthesis model.
    """
    cfg = _config()
    accounts = list(cfg.get("accounts", []))
    if not accounts:
        raise DashboardWebSearchError(
            "alt-ai-portfolios: no tracked accounts in ai_portfolio_accounts.yaml"
        )
    recency = int(cfg.get("recency_days", 7))
    try:
        max_results = int(cfg.get("max_search_results", 8) or 8)
    except (TypeError, ValueError):
        max_results = 8
    max_results = max(1, min(max_results, 10))
    try:
        tool_out = call_web_search_tool(
            query=_build_query(accounts, run_date, recency),
            include_domains=list(_X_DOMAINS),
            max_results=max_results,
        )
    except DashboardWebSearchError:
        raise
    except Exception as exc:
        raise DashboardWebSearchError(
            f"web_search tool failed for alt-ai-portfolios: {exc}"
        ) from exc
    summary = str(tool_out.get("summary") or "").strip()
    sources = list(tool_out.get("sources") or [])
    if not summary:
        raise DashboardWebSearchError(
            "web_search tool returned empty summary for alt-ai-portfolios"
        )
    return {
        "summary": summary,
        "sources": sources,
        "accounts": [a["handle"] for a in accounts],
        "as_of": run_date.isoformat(),
    }
