"""Tavily provider adapter (#4711).

Docs: https://docs.tavily.com — ``POST https://api.tavily.com/search`` with
``Authorization: Bearer <TAVILY_API_KEY>``. Free tier is 1,000 credits/month;
``advanced`` search depth costs 2 credits, every other depth costs 1.
"""

from __future__ import annotations

from typing import Any, ClassVar  # score:allow untyped any — heterogeneous vendor payloads

from digisearch.web_providers.base import (
    BaseWebProvider,
    rank_score,
    request_json,
    require_dict,
)
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

API_URL = "https://api.tavily.com/search"

#: ``recency_days`` -> tavily ``time_range`` bucket (tavily supports week too).
_EFFORT_TO_DEPTH = {"fast": "fast", "thorough": "advanced"}


class TavilyWebProvider(BaseWebProvider):
    provider_name: ClassVar[str] = "tavily"
    env_var: ClassVar[str] = "TAVILY_API_KEY"
    cost_hint: ClassVar[str] = "1,000 free credits/mo, then ~$0.008/credit"

    def _search(self, req: WebSearchRequest) -> WebSearchResponse:
        key = self.require_configured()
        body: dict[str, Any] = {
            "query": req.query,
            "max_results": req.max_results,
            "include_usage": True,
        }
        if req.include_domains:
            body["include_domains"] = req.include_domains
        if req.exclude_domains:
            body["exclude_domains"] = req.exclude_domains
        time_range = _time_range(req.recency_days)
        if time_range:
            body["time_range"] = time_range
        depth = _EFFORT_TO_DEPTH.get(req.effort or "")
        if depth:
            body["search_depth"] = depth

        data = require_dict(
            "tavily",
            request_json(
                "tavily",
                method="POST",
                url=API_URL,
                headers={"Authorization": f"Bearer {key}"},
                json_body=body,
            ),
        )
        rows = data.get("results")
        results = [_to_result(row, i) for i, row in enumerate(rows or []) if isinstance(row, dict)]
        usage = data.get("usage") if isinstance(data.get("usage"), dict) else None
        extras: dict[str, Any] = {}
        if isinstance(usage, dict) and usage.get("credits") is not None:
            # Credits, not dollars — kept in `output` so `cost_dollars` stays honest.
            extras["credits"] = usage["credits"]
        if data.get("response_time") is not None:
            extras["response_time"] = data["response_time"]
        if data.get("answer"):
            extras["answer"] = data["answer"]
        return WebSearchResponse(
            query=req.query,
            results=results,
            provider=self.provider_name,
            output=extras or None,
        )


def _time_range(recency_days: int | None) -> str | None:
    if recency_days is None:
        return None
    if recency_days <= 1:
        return "day"
    if recency_days <= 7:
        return "week"
    if recency_days <= 30:
        return "month"
    return "year"


def _to_result(row: dict[str, Any], position: int) -> WebSearchResult:
    score = row.get("score")
    return WebSearchResult(
        url=str(row.get("url") or ""),
        title=str(row.get("title") or ""),
        snippet=str(row.get("content") or ""),
        # tavily reports a native relevance score; fall back to a rank-derived
        # one only if an upstream row omits it.
        score=float(score) if isinstance(score, (int, float)) else rank_score(position),
        engine="tavily",
        # tavily returns RFC 1123 ("Tue, 11 Mar 2025 17:00:00 GMT"); kept verbatim.
        published_date=str(row.get("published_date") or ""),
        author=str(row.get("author") or ""),
    )


__all__ = ["TavilyWebProvider"]
