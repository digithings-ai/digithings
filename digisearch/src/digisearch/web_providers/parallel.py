"""Parallel provider adapter (#4711).

Docs: https://docs.parallel.ai — ``POST https://api.parallel.ai/v1/search`` with
``x-api-key: <PARALLEL_API_KEY>``. Parallel is declarative: callers hand it an
``objective`` plus ``search_queries`` and it returns ranked URLs with
token-efficient markdown excerpts.

Cost ladder: ``turbo``/``fast`` $1 per 1k searches, ``basic``/``advanced`` $5
per 1k. The API's own default mode is ``advanced``, so an unmapped effort runs
on the priciest tier — surfaced in ``cost_hint`` so that is a conscious pick.
"""

from __future__ import annotations

from typing import Any, ClassVar

from digisearch.web_providers.base import (
    BaseWebProvider,
    date_days_ago,
    rank_score,
    request_json,
    require_dict,
)
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

API_URL = "https://api.parallel.ai/v1/search"

_EFFORT_TO_MODE = {"fast": "fast", "thorough": "advanced"}


class ParallelWebProvider(BaseWebProvider):
    provider_name: ClassVar[str] = "parallel"
    env_var: ClassVar[str] = "PARALLEL_API_KEY"
    cost_hint: ClassVar[str] = "$1/1k (turbo,fast) or $5/1k (basic,advanced); $5/mo free tier"

    def _search(self, req: WebSearchRequest) -> WebSearchResponse:
        key = self.require_configured()
        body: dict[str, Any] = {"search_queries": [req.query]}
        mode = _EFFORT_TO_MODE.get(req.effort or "")
        if mode:
            body["mode"] = mode
        if req.purpose:
            # Parallel's declarative `objective` is the same NL intent field
            # Tinyfish calls `purpose`.
            body["objective"] = req.purpose

        advanced = _advanced_settings(req)
        if advanced:
            body["advanced_settings"] = advanced

        data = require_dict(
            "parallel",
            request_json(
                "parallel",
                method="POST",
                url=API_URL,
                headers={"x-api-key": key, "Content-Type": "application/json"},
                json_body=body,
            ),
        )
        rows = data.get("results")
        results = [_to_result(row, i) for i, row in enumerate(rows or []) if isinstance(row, dict)][
            : req.max_results
        ]
        extras: dict[str, Any] = {}
        for key_name in ("search_id", "session_id", "warnings", "usage"):
            if data.get(key_name) is not None:
                extras[key_name] = data[key_name]
        return WebSearchResponse(
            query=req.query,
            results=results,
            provider=self.provider_name,
            output=extras or None,
        )


def _advanced_settings(req: WebSearchRequest) -> dict[str, Any]:
    """Build ``advanced_settings`` only from the fields the caller actually set.

    The upstream object rejects unknown keys, so nothing is added speculatively.
    ``source_policy`` also drops ``exclude_domains`` whenever ``include_domains``
    is present — the API ignores the former in that case.
    """
    source: dict[str, Any] = {}
    if req.include_domains:
        source["include_domains"] = list(req.include_domains)
    elif req.exclude_domains:
        source["exclude_domains"] = list(req.exclude_domains)
    if req.recency_days is not None:
        source["after_date"] = date_days_ago(req.recency_days)
    return {"source_policy": source} if source else {}


def _to_result(row: dict[str, Any], position: int) -> WebSearchResult:
    excerpts = row.get("excerpts")
    snippet = ""
    if isinstance(excerpts, list):
        snippet = " ".join(str(e) for e in excerpts if e)
    return WebSearchResult(
        url=str(row.get("url") or ""),
        title=str(row.get("title") or ""),
        snippet=snippet,
        # Parallel reports no relevance score; rank order is the signal.
        score=rank_score(position),
        engine="parallel",
        published_date=str(row.get("publish_date") or ""),
        author="",
    )


__all__ = ["ParallelWebProvider"]
