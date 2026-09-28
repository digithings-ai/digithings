"""Tinyfish AI provider adapter (#4711).

Docs: https://tinyfish.ai — ``GET https://api.search.tinyfish.ai/`` with
``X-API-Key: <TINYFISH_API_KEY>``.

Search itself is free at any wallet balance (it never draws from the wallet),
but a key is still required, so this adapter fails closed like the rest —
"free with a key", not "keyless".

Tinyfish is the provider that first motivated the unified ``purpose`` field: it
takes a natural-language intent (≤2000 chars) alongside the query, and it is
the only one of the five with a ``domain_type`` axis (``web`` / ``news`` /
``research_paper``).
"""

from __future__ import annotations

from typing import Any, ClassVar

from digisearch.web_providers.base import (
    BaseWebProvider,
    rank_score,
    request_json,
    require_dict,
)
from digisearch.web_search.models import WebSearchRequest, WebSearchResponse, WebSearchResult

API_URL = "https://api.search.tinyfish.ai/"


class TinyfishWebProvider(BaseWebProvider):
    provider_name: ClassVar[str] = "tinyfish"
    env_var: ClassVar[str] = "TINYFISH_API_KEY"
    cost_hint: ClassVar[str] = "search is free with any key (never draws the wallet)"

    def _search(self, req: WebSearchRequest) -> WebSearchResponse:
        key = self.require_configured()
        params: dict[str, Any] = {"query": req.query}
        if req.purpose:
            params["purpose"] = req.purpose
        if req.include_domains:
            params["include_domains"] = ",".join(req.include_domains)
        if req.exclude_domains:
            params["exclude_domains"] = ",".join(req.exclude_domains)
        if req.recency_days is not None:
            # Tinyfish is minute-granular: 1 day = 1440 minutes.
            params["recency_minutes"] = req.recency_days * 1440

        data = require_dict(
            "tinyfish",
            request_json(
                "tinyfish",
                method="GET",
                url=API_URL,
                headers={"X-API-Key": key},
                params=params,
            ),
        )
        rows = data.get("results")
        results = [_to_result(row, i) for i, row in enumerate(rows or []) if isinstance(row, dict)][
            : req.max_results
        ]
        extras: dict[str, Any] = {}
        for key_name in ("total_results", "page", "request_id"):
            if data.get(key_name) is not None:
                extras[key_name] = data[key_name]
        return WebSearchResponse(
            query=req.query,
            results=results,
            provider=self.provider_name,
            output=extras or None,
        )


def _to_result(row: dict[str, Any], position: int) -> WebSearchResult:
    authors = row.get("authors")
    author = str(row.get("publisher") or "")
    if not author and isinstance(authors, list) and authors:
        author = ", ".join(str(a) for a in authors if a)
    published = str(row.get("date") or "")
    if not published and row.get("year"):
        published = str(row["year"])
    return WebSearchResult(
        url=str(row.get("url") or ""),
        title=str(row.get("title") or ""),
        snippet=str(row.get("snippet") or ""),
        # Tinyfish returns no relevance score; rank order is the signal.
        score=rank_score(position),
        engine="tinyfish",
        published_date=published,
        author=author,
    )


__all__ = ["TinyfishWebProvider"]
